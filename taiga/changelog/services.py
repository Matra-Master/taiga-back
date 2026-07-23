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


def store_push(project, payload, delivery_id=None):
    """
    Persist a GitHub "push" webhook payload as a ChangelogEntry, but only when
    the pushed branch belongs to a repository+branch pair the project admin
    configured as "of interest" (a ChangelogRepository). Otherwise it's a no-op.

    This is called unconditionally from the push event hook: it doesn't check
    project.is_changelog_activated (that flag only gates the UI), so history
    keeps being recorded even while the visual module is switched off.
    """
    ref = payload.get("ref", "")
    if not ref.startswith(_REFS_HEADS_PREFIX):
        return None

    branch = ref[len(_REFS_HEADS_PREFIX):]
    full_name = payload.get("repository", {}).get("full_name")

    repository = models.ChangelogRepository.objects.filter(
        project=project, full_name=full_name,
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
        for commit in payload.get("commits", [])
        if not _is_merge_commit(commit)
    ]

    entry, created = models.ChangelogEntry.objects.get_or_create(
        repository=repository,
        after_sha=payload.get("after"),
        defaults={
            "branch": branch,
            "compare_url": payload.get("compare"),
            "before_sha": payload.get("before"),
            "head_message": payload.get("head_commit", {}).get("message"),
            "pusher_name": payload.get("pusher", {}).get("name"),
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
