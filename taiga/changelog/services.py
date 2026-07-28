# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import logging

from . import models

logger = logging.getLogger("taiga.changelog")

_MERGE_PR_PREFIX = "Merge pull request"
_REFS_HEADS_PREFIX = "refs/heads/"


def _is_merge_commit(commit):
    return commit.get("message", "").startswith(_MERGE_PR_PREFIX)


def _extract_github(payload):
    return {
        "full_name": payload.get("repository", {}).get("full_name"),
        "compare_url": payload.get("compare"),
        "pusher_name": payload.get("pusher", {}).get("name"),
        "head_message": payload.get("head_commit", {}).get("message"),
        "commits": payload.get("commits", []),
    }


def _extract_gitlab(payload):
    # El payload de GitLab no trae una URL de "compare" armada ni un
    # head_commit propio, y el nombre del repo/pusher vienen en otras claves
    # (path_with_namespace / user_name en vez de repository.full_name / pusher.name).
    gl_project = payload.get("project", {})
    before = payload.get("before")
    after = payload.get("after")
    project_url = gl_project.get("web_url")
    compare_url = f"{project_url}/-/compare/{before}...{after}" if project_url else None
    commits = payload.get("commits", [])

    return {
        "full_name": gl_project.get("path_with_namespace"),
        "compare_url": compare_url,
        "pusher_name": payload.get("user_name"),
        "head_message": commits[-1].get("message") if commits else None,
        "commits": commits,
    }


_EXTRACTORS = {
    "github": _extract_github,
    "gitlab": _extract_gitlab,
}


def store_push(project, payload, delivery_id=None, platform_slug="github"):
    """
    Persist a push webhook payload (GitHub or GitLab) as a ChangelogEntry, but
    only when the pushed branch belongs to a repository+branch pair the
    project admin configured as "of interest" (a ChangelogRepository).
    Otherwise it's a no-op.

    This is called unconditionally from the push event hook: it doesn't check
    project.is_changelog_activated (that flag only gates the UI), so history
    keeps being recorded even while the visual module is switched off.
    """
    ref = payload.get("ref", "")
    if not ref.startswith(_REFS_HEADS_PREFIX):
        return None

    branch = ref[len(_REFS_HEADS_PREFIX):]

    extract = _EXTRACTORS.get(platform_slug, _extract_github)
    extracted = extract(payload)
    full_name = extracted["full_name"]

    # platform entra en el lookup: el mismo full_name puede existir como repo
    # de GitHub Y de GitLab en el mismo proyecto, son configuraciones distintas.
    repository = models.ChangelogRepository.objects.filter(
        project=project, platform=platform_slug, full_name=full_name,
    ).first()
    if repository is None:
        return None

    if branch not in repository.branches:
        return None

    commits = [
        {
            "message": commit.get("message", "").strip(),
            "author_name": commit.get("author", {}).get("name"),
            "url": commit.get("url"),
        }
        for commit in extracted["commits"]
        if not _is_merge_commit(commit)
    ]

    entry, created = models.ChangelogEntry.objects.get_or_create(
        repository=repository,
        after_sha=payload.get("after"),
        defaults={
            "branch": branch,
            "compare_url": extracted["compare_url"],
            "before_sha": payload.get("before"),
            "head_message": extracted["head_message"],
            "pusher_name": extracted["pusher_name"],
            "commits": commits,
            "delivery_id": delivery_id,
        },
    )

    if created:
        logger.info(
            "Changelog entry stored for %s@%s (%s commits, project %s)",
            full_name, branch, len(commits), project.id,
        )

    return entry
