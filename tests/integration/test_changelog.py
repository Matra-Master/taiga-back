# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import pytest

from django.urls import reverse

from taiga.base.utils import json
from taiga.changelog import services
from taiga.changelog.models import ChangelogEntry, ChangelogRepository
from taiga.hooks.exceptions import ActionSyntaxException
from taiga.hooks.github import event_hooks

from .. import factories as f

pytestmark = pytest.mark.django_db


def _make_commit(message, url):
    return {
        "id": url.rsplit("/", 1)[-1],
        "message": message,
        "url": url,
        "author": {"name": "Matias Sorenson", "email": "matiassorenson@gmail.com"},
    }


# Trimmed version of a real "push" webhook payload (see taiga-back/info_de_.json):
# 5 feature commits plus 5 "Merge pull request" commits that should be discarded.
PUSH_PAYLOAD = {
    "ref": "refs/heads/main",
    "before": "2aa7167adabb3a26e213e4f6572bb068e271bb51",
    "after": "7b3aa2fba1db58f0297e14f669fcb0ca1520cd14",
    "repository": {"full_name": "MatSoren/test-taiga-wh"},
    "pusher": {"name": "MatSoren"},
    "compare": "https://github.com/MatSoren/test-taiga-wh/compare/2aa7167adabb...7b3aa2fba1db",
    "commits": [
        _make_commit("feat: primer", "https://github.com/MatSoren/test-taiga-wh/commit/8fe35a2"),
        _make_commit("feat: segundo", "https://github.com/MatSoren/test-taiga-wh/commit/06d7865"),
        _make_commit("feat: 3ero", "https://github.com/MatSoren/test-taiga-wh/commit/e7b2bdb"),
        _make_commit("feat: tuma", "https://github.com/MatSoren/test-taiga-wh/commit/7dcd2ea"),
        _make_commit(
            "Merge pull request #10 from MatSoren/TG-3---#5-Segundo-archivo\n\nfeat: segundo",
            "https://github.com/MatSoren/test-taiga-wh/commit/0f77d58",
        ),
        _make_commit(
            "Merge pull request #12 from MatSoren/TG-3---#7-y-un-cuarto-por-las-dudas\n\nfeat: tuma",
            "https://github.com/MatSoren/test-taiga-wh/commit/1815fa1",
        ),
        _make_commit(
            "Merge pull request #11 from MatSoren/TG-3---#6-tercero\n\nfeat: 3ero",
            "https://github.com/MatSoren/test-taiga-wh/commit/252ca22",
        ),
        _make_commit(
            "Merge pull request #9 from MatSoren/TG-3---#4primer-archivo\n\nfeat: primer",
            "https://github.com/MatSoren/test-taiga-wh/commit/62604fe",
        ),
        _make_commit("feat: le toco", "https://github.com/MatSoren/test-taiga-wh/commit/f133cd8"),
        _make_commit(
            "Merge pull request #13 from MatSoren/TG-3-varias-tareas-y-un-merge-grande\n\nTg 3 varias tareas y un merge grande",
            "https://github.com/MatSoren/test-taiga-wh/commit/7b3aa2f",
        ),
    ],
    "head_commit": {
        "message": "Merge pull request #13 from MatSoren/TG-3-varias-tareas-y-un-merge-grande\n\nTg 3 varias tareas y un merge grande",
    },
}


def test_store_push_creates_entry_for_configured_repo_and_branch():
    repo = f.ChangelogRepositoryFactory(full_name="MatSoren/test-taiga-wh", branches=["main"])

    entry = services.store_push(repo.project, PUSH_PAYLOAD)

    assert entry is not None
    assert ChangelogEntry.objects.filter(repository=repo).count() == 1
    assert entry.compare_url == PUSH_PAYLOAD["compare"]
    assert entry.after_sha == PUSH_PAYLOAD["after"]
    assert entry.before_sha == PUSH_PAYLOAD["before"]
    assert entry.branch == "main"
    assert entry.pusher_name == "MatSoren"

    # 5 "Merge pull request" commits excluded, only the 5 feature commits remain
    assert len(entry.commits) == 5
    messages = [c["message"] for c in entry.commits]
    assert messages == ["feat: primer", "feat: segundo", "feat: 3ero", "feat: tuma", "feat: le toco"]
    assert all(not m.startswith("Merge pull request") for m in messages)
    assert entry.commits[0]["author_name"] == "Matias Sorenson"
    assert entry.commits[0]["url"] == "https://github.com/MatSoren/test-taiga-wh/commit/8fe35a2"


def test_store_push_is_idempotent_on_redelivery():
    repo = f.ChangelogRepositoryFactory(full_name="MatSoren/test-taiga-wh", branches=["main"])

    services.store_push(repo.project, PUSH_PAYLOAD)
    services.store_push(repo.project, PUSH_PAYLOAD)

    assert ChangelogEntry.objects.filter(repository=repo).count() == 1


def test_store_push_ignored_when_repo_not_configured():
    project = f.ProjectFactory()

    entry = services.store_push(project, PUSH_PAYLOAD)

    assert entry is None
    assert ChangelogEntry.objects.count() == 0


def test_store_push_ignored_when_branch_not_of_interest():
    # Same repo configured, but only "develop" is of interest: a push to "main" is discarded.
    repo = f.ChangelogRepositoryFactory(full_name="MatSoren/test-taiga-wh", branches=["develop"])

    entry = services.store_push(repo.project, PUSH_PAYLOAD)

    assert entry is None
    assert ChangelogEntry.objects.filter(repository=repo).count() == 0


def test_store_push_ignored_for_non_branch_refs():
    repo = f.ChangelogRepositoryFactory(full_name="MatSoren/test-taiga-wh", branches=["main"])
    tag_payload = dict(PUSH_PAYLOAD, ref="refs/tags/v1.0.0")

    entry = services.store_push(repo.project, tag_payload)

    assert entry is None
    assert ChangelogEntry.objects.filter(repository=repo).count() == 0


def test_store_push_disambiguates_same_full_name_across_platforms():
    # "MatSoren/test-taiga-wh" existe como repo de GitHub Y como repo de GitLab
    # en el mismo proyecto (dos configuraciones legitimas, no un duplicado).
    project = f.ProjectFactory()
    github_repo = f.ChangelogRepositoryFactory(
        project=project, platform="github", full_name="MatSoren/test-taiga-wh", branches=["main"],
    )
    gitlab_repo = f.ChangelogRepositoryFactory(
        project=project, platform="gitlab", full_name="MatSoren/test-taiga-wh", branches=["main"],
    )

    github_entry = services.store_push(project, PUSH_PAYLOAD, platform_slug="github")
    gitlab_payload = dict(
        PUSH_PAYLOAD,
        after="deadbeef" * 5,
        project={"path_with_namespace": "MatSoren/test-taiga-wh", "web_url": "https://gitlab.com/MatSoren/test-taiga-wh"},
    )
    gitlab_entry = services.store_push(project, gitlab_payload, platform_slug="gitlab")

    assert github_entry.repository_id == github_repo.id
    assert gitlab_entry.repository_id == gitlab_repo.id


def test_push_event_hook_still_stores_changelog_entry():
    # End-to-end through the real GitHub push event hook (not just the
    # service): confirms the hook keeps running its existing TG-<n>
    # mention/status-change scan (already covered by test_hooks_github.py)
    # while also feeding the changelog. Commit messages here don't reference
    # any TG-<n>, so the base hook's scan is a no-op and doesn't need a
    # matching Epic/Issue/Task/UserStory to exist.
    repo = f.ChangelogRepositoryFactory(full_name="MatSoren/test-taiga-wh", branches=["main"])
    payload = dict(PUSH_PAYLOAD, commits=[
        _make_commit("feat: primer", "https://github.com/MatSoren/test-taiga-wh/commit/8fe35a2"),
        _make_commit(
            "Merge pull request #9 from MatSoren/some-branch\n\nfeat: primer",
            "https://github.com/MatSoren/test-taiga-wh/commit/62604fe",
        ),
    ])

    ev_hook = event_hooks.PushEventHook(repo.project, payload)
    ev_hook.process_event()

    entry = ChangelogEntry.objects.get(repository=repo, after_sha=payload["after"])
    assert len(entry.commits) == 1
    assert entry.commits[0]["message"] == "feat: primer"


def test_push_event_hook_stores_changelog_even_when_tg_ref_scan_raises():
    # Found in manual testing: real commit messages often carry "TG-<n>"
    # from branch names (see PUSH_PAYLOAD's merge commits). If that ref
    # doesn't match an Epic/Issue/Task/UserStory, BasePushEventHook.process_event()
    # raises ActionSyntaxException (-> 400 to GitHub) - store_push must run
    # first so the changelog is still recorded regardless.
    repo = f.ChangelogRepositoryFactory(full_name="MatSoren/test-taiga-wh", branches=["main"])
    payload = dict(PUSH_PAYLOAD, ref="refs/heads/main")

    ev_hook = event_hooks.PushEventHook(repo.project, payload)
    with pytest.raises(ActionSyntaxException):
        ev_hook.process_event()

    entry = ChangelogEntry.objects.get(repository=repo, after_sha=payload["after"])
    assert len(entry.commits) == 5


##############################################################################
# API
##############################################################################

def test_api_admin_can_create_repository_config(client):
    project = f.create_project()
    f.MembershipFactory(project=project, user=project.owner, is_admin=True)

    url = reverse("changelog-repositories-list")
    client.login(project.owner)
    data = {"project": project.id, "full_name": "owner/repo", "branches": ["main", "release"]}
    response = client.post(url, json.dumps(data), content_type="application/json")

    assert response.status_code == 201
    assert ChangelogRepository.objects.filter(project=project, full_name="owner/repo").count() == 1


def test_api_non_admin_cannot_create_repository_config(client):
    project = f.create_project()
    member = f.UserFactory()
    role = f.RoleFactory(project=project, permissions=["view_project"])
    f.MembershipFactory(project=project, user=member, role=role, is_admin=False)

    url = reverse("changelog-repositories-list")
    client.login(member)
    data = {"project": project.id, "full_name": "owner/repo", "branches": ["main"]}
    response = client.post(url, json.dumps(data), content_type="application/json")

    assert response.status_code == 403
    assert ChangelogRepository.objects.filter(project=project).count() == 0


def test_api_member_can_list_entries_scoped_to_project(client):
    project = f.create_project()
    member = f.UserFactory()
    role = f.RoleFactory(project=project, permissions=["view_project"])
    f.MembershipFactory(project=project, user=member, role=role, is_admin=False)
    repo = f.ChangelogRepositoryFactory(project=project, full_name="owner/repo", branches=["main"])
    services.store_push(project, dict(PUSH_PAYLOAD, repository={"full_name": "owner/repo"}))

    other_project_entry_repo = f.ChangelogRepositoryFactory(full_name="owner/other-repo", branches=["main"])
    services.store_push(
        other_project_entry_repo.project,
        dict(PUSH_PAYLOAD, repository={"full_name": "owner/other-repo"}),
    )

    url = reverse("changelog-entries-list")
    client.login(member)
    response = client.get(url, {"project": project.id})

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["repository"] == repo.id
