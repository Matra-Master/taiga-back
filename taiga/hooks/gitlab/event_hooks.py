# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import re
import os
import logging

from django.utils.translation import gettext as _

from taiga.hooks.event_hooks import (BaseEventHook, BaseIssueEventHook, BaseIssueCommentEventHook,
                                     BasePushEventHook, BaseStatusTransitionMixin, TG_REF_RE,
                                     ISSUE_ACTION_CREATE, ISSUE_ACTION_UPDATE, ISSUE_ACTION_CLOSE,
                                     ISSUE_ACTION_REOPEN)
from taiga.projects.userstories.models import PullRequest

logger = logging.getLogger("taiga.hooks.gitlab")

# antes de 40 ceros: antes de que exista ningún commit en la rama -> se acaba de crear.
_ZERO_SHA = "0" * 40
_REFS_HEADS_PREFIX = "refs/heads/"


class BaseGitLabEventHook():
    platform = "GitLab"
    platform_slug = "gitlab"

    def replace_gitlab_references(self, project_url, wiki_text):
        if wiki_text is None:
            wiki_text = ""

        template = fr"\g<1>[GitLab#\g<2>]({project_url}/issues/\g<2>)\g<3>"
        return re.sub(r"(\s|^)#(\d+)(\s|$)", template, wiki_text, 0, re.M)


class GitLabStatusTransitionMixin(BaseStatusTransitionMixin):
    """Alias con nombre propio de `BaseStatusTransitionMixin` para los hooks de
    GitLab (merge_request, push) — sin lógica propia, ver el mixin base."""
    pass


class IssuesEventHook(BaseGitLabEventHook, BaseIssueEventHook):
    _ISSUE_ACTIONS = {
      "open": ISSUE_ACTION_CREATE,
      "update": ISSUE_ACTION_UPDATE,
      "close": ISSUE_ACTION_CLOSE,
      "reopen": ISSUE_ACTION_REOPEN,
    }

    @property
    def action_type(self):
        _action = self.payload.get('object_attributes', {}).get("action", "")
        return self._ISSUE_ACTIONS.get(_action, None)

    def ignore(self):
        return self.action_type not in [
            ISSUE_ACTION_CREATE,
            ISSUE_ACTION_UPDATE,
            ISSUE_ACTION_CLOSE,
            ISSUE_ACTION_REOPEN,
        ]

    def get_data(self):
        description = self.payload.get('object_attributes', {}).get('description', None)
        project_url = self.payload.get('repository', {}).get('homepage', "")
        user_name = self.payload.get('user', {}).get('username', None)
        state = self.payload.get('object_attributes', {}).get('state', 'opened')

        return {
            "number": self.payload.get('object_attributes', {}).get('iid', None),
            "subject": self.payload.get('object_attributes', {}).get('title', None),
            "url": self.payload.get('object_attributes', {}).get('url', None),
            "user_id": None,
            "user_name": user_name,
            "user_url": os.path.join(os.path.dirname(os.path.dirname(project_url)), user_name),
            "description": self.replace_gitlab_references(project_url, description),
            "status": self.close_status if state == "closed" else self.open_status,
        }


class IssueCommentEventHook(BaseGitLabEventHook, BaseIssueCommentEventHook):
    def ignore(self):
        return self.payload.get('object_attributes', {}).get("noteable_type", None) != "Issue"

    def get_data(self):
        comment_message = self.payload.get('object_attributes', {}).get('note', None)
        project_url = self.payload.get('repository', {}).get('homepage', "")
        issue_url = self.payload.get('issue', {}).get('url', None)
        number = self.payload.get('issue', {}).get('iid', None)
        user_name = self.payload.get('user', {}).get('username', None)
        return {
            "number": number,
            "url": issue_url,
            "user_id": None,
            "user_name": user_name,
            "user_url": os.path.join(os.path.dirname(os.path.dirname(project_url)), user_name),
            "comment_url": self.payload.get('object_attributes', {}).get('url', None),
            "comment_message": self.replace_gitlab_references(project_url, comment_message),
        }


class MergeRequestEventHook(GitLabStatusTransitionMixin, BaseGitLabEventHook, BaseEventHook):
    """Evento `merge_request` de GitLab. GitLab no tiene un estado formal de
    "changes requested": usamos `action == "unapproved"` como equivalente,
    asumiendo que el proyecto tiene habilitado el flujo de aprobaciones de MR
    (si no lo tiene, ese trigger puntual simplemente no se dispara)."""

    _ACTIONS_OF_INTEREST = {"open", "merge", "unapproved"}

    def ignore(self):
        return self.payload.get("object_attributes", {}).get("action") not in self._ACTIONS_OF_INTEREST

    def process_event(self):
        if self.ignore():
            return

        attrs = self.payload.get("object_attributes", {})
        action = attrs.get("action")
        branch_name = attrs.get("source_branch")
        mr_url = attrs.get("url")
        mr_id = attrs.get("id")
        repo_full_name = self.payload.get("project", {}).get("path_with_namespace")

        if not all([branch_name, mr_url]):
            logger.warning(
                "Incomplete merge_request payload: branch=%s url=%s",
                branch_name, mr_url,
            )
            return

        m = TG_REF_RE.search(branch_name)
        if not m:
            logger.info("No TG ref in branch: %s", branch_name)
            return

        tg_ref = int(m.group(1))

        entity = self._find_entity(tg_ref)
        if entity is None:
            logger.warning(
                "Entity TG-%s not found in project %s. MR: %s branch: %s",
                tg_ref, self.project.id, mr_url, branch_name,
            )
            return

        defaults = {
            "project": self.project,
            "ref": tg_ref,
            "branch_name": branch_name,
            "pull_request_id": mr_id,
            "repository": repo_full_name,
        }

        if action == "merge":
            defaults["status"] = PullRequest.STATUS_MERGED
            defaults["merged_by"] = self.payload.get("user", {}).get("username")
            defaults["merged_at"] = attrs.get("updated_at") or attrs.get("last_edited_at")
            PullRequest.objects.update_or_create(pull_request_url=mr_url, defaults=defaults)

            all_prs = PullRequest.objects.filter(project=self.project, ref=tg_ref)
            if all_prs.exists() and not all_prs.exclude(status=PullRequest.STATUS_MERGED).exists():
                self._transition(entity, "all_merged", _("all linked merge requests were merged"))
        elif action == "unapproved":
            PullRequest.objects.filter(pull_request_url=mr_url).update(
                status=PullRequest.STATUS_CHANGES_REQUESTED
            )
            self._transition(entity, "changes_requested", _("changes requested on %s") % mr_url)
        else:  # open
            defaults["status"] = PullRequest.STATUS_OPEN
            PullRequest.objects.get_or_create(pull_request_url=mr_url, defaults=defaults)
            self._transition(entity, "pr_open", _("merge request opened: %s") % mr_url)


class PushEventHook(GitLabStatusTransitionMixin, BaseGitLabEventHook, BasePushEventHook):
    def get_data(self):
        result = []
        for commit in self.payload.get("commits", []):
            user_name = commit.get('author', {}).get('name', None)
            result.append({
                "user_id": None,
                "user_name": user_name,
                "user_url": None,
                "commit_id": commit.get("id", None),
                "commit_url": commit.get("url", None),
                "commit_message": commit.get("message").strip(),
                "commit_short_message": commit.get("message").split("\n")[0].strip(),
            })
        return result

    def _handle_branch_created(self):
        # GitLab no manda un evento separado de "rama creada": lo señaliza dentro
        # del propio Push Hook con `before` en 40 ceros.
        ref = self.payload.get("ref", "")
        if not ref.startswith(_REFS_HEADS_PREFIX):
            return

        branch_name = ref[len(_REFS_HEADS_PREFIX):]
        m = TG_REF_RE.search(branch_name)
        if not m:
            return

        tg_ref = int(m.group(1))
        entity = self._find_entity(tg_ref)
        if entity is None:
            logger.warning(
                "Entity TG-%s not found in project %s. branch: %s",
                tg_ref, self.project.id, branch_name,
            )
            return

        self._transition(entity, "branch", _("branch `%s` created") % branch_name)

    def process_event(self):
        from taiga.changelog.services import store_push
        store_push(self.project, self.payload, platform_slug=self.platform_slug)

        if self.payload.get("before") == _ZERO_SHA:
            self._handle_branch_created()

        super().process_event()
