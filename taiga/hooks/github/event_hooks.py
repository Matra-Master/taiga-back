# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

import logging
import re

from django.utils.translation import gettext as _

from taiga.hooks.event_hooks import (BaseEventHook, BaseIssueEventHook, BaseIssueCommentEventHook,
                                     BasePushEventHook, BaseStatusTransitionMixin, TG_REF_RE,
                                     ISSUE_ACTION_CREATE, ISSUE_ACTION_UPDATE, ISSUE_ACTION_CLOSE,
                                     ISSUE_ACTION_REOPEN)
from taiga.projects.userstories.models import PullRequest

logger = logging.getLogger("taiga.hooks.github")


class BaseGitHubEventHook():
    platform = "GitHub"
    platform_slug = "github"

    def replace_github_references(self, project_url, wiki_text):
        if wiki_text is None:
            wiki_text = ""

        template = fr"\g<1>[GitHub#\g<2>]({project_url}/issues/\g<2>)\g<3>"
        return re.sub(r"(\s|^)#(\d+)(\s|$)", template, wiki_text, 0, re.M)


class GitHubStatusTransitionMixin(BaseStatusTransitionMixin):
    """Alias con nombre propio de `BaseStatusTransitionMixin` para los hooks de
    GitHub (create, pull_request, pull_request_review) — sin lógica propia,
    toda la lógica de transición vive en la clase base agnóstica de proveedor."""
    pass

#!IMPORTANTE, WRAPPER DEL HOOK BASE DONDE SE CARGA LA IMPLEMENTACION DE CADA UNO PARA EL CASO GITHUB
class IssuesEventHook(BaseGitHubEventHook, BaseIssueEventHook):
    _ISSUE_ACTIONS = {
      "opened": ISSUE_ACTION_CREATE,
      "edited": ISSUE_ACTION_UPDATE,
      "closed": ISSUE_ACTION_CLOSE,
      "reopened": ISSUE_ACTION_REOPEN,
    }

    @property
    def action_type(self):
        _action = self.payload.get('action', '')
        return self._ISSUE_ACTIONS.get(_action, None)

    def ignore(self):
        return self.action_type not in [
            ISSUE_ACTION_CREATE,
            ISSUE_ACTION_UPDATE,
            ISSUE_ACTION_CLOSE,
            ISSUE_ACTION_REOPEN,
        ]

    def get_data(self):
        description = self.payload.get('issue', {}).get('body', None)
        project_url = self.payload.get('repository', {}).get('html_url', None)
        state = self.payload.get('issue', {}).get('state', 'open')

        return {
            "number": self.payload.get('issue', {}).get('number', None),
            "subject": self.payload.get('issue', {}).get('title', None),
            "url": self.payload.get('issue', {}).get('html_url', None),
            "user_id": self.payload.get('sender', {}).get('id', None),
            "user_name": self.payload.get('sender', {}).get('login', None),
            "user_url": self.payload.get('sender', {}).get('html_url', None),
            "description": self.replace_github_references(project_url, description),
            "status": self.close_status if state == "closed" else self.open_status,
        }


class IssueCommentEventHook(BaseGitHubEventHook, BaseIssueCommentEventHook):
    def ignore(self):
        return self.payload.get('action', None) != "created"

    def get_data(self):
        comment_message = self.payload.get('comment', {}).get('body', None)
        project_url = self.payload.get('repository', {}).get('html_url', None)
        return {
            "number": self.payload.get('issue', {}).get('number', None),
            "url": self.payload.get('issue', {}).get('html_url', None),
            "user_id": self.payload.get('sender', {}).get('id', None),
            "user_name": self.payload.get('sender', {}).get('login', None),
            "user_url": self.payload.get('sender', {}).get('html_url', None),
            "comment_url": self.payload.get('comment', {}).get('html_url', None),
            "comment_message": self.replace_github_references(project_url, comment_message),
        }


class PullRequestEventHook(GitHubStatusTransitionMixin, BaseGitHubEventHook, BaseEventHook):
    _ACTIONS_OF_INTEREST = {"opened", "closed"}

    def ignore(self):
        action = self.payload.get("action", "")
        if action not in self._ACTIONS_OF_INTEREST:
            return True
        if action == "closed":
            merged = self.payload.get("pull_request", {}).get("merged", False)
            return merged is not True
        return False

    def process_event(self):
        if self.ignore():
            return

        action = self.payload.get("action", "")
        pr = self.payload.get("pull_request", {})
        head = pr.get("head", {})
        branch_name = head.get("ref")
        pr_url = pr.get("html_url")
        pr_id = pr.get("id")
        repo_full_name = self.payload.get("repository", {}).get("full_name")

        if not all([branch_name, pr_url]):
            logger.warning(
                "Incomplete pull_request payload: branch=%s url=%s",
                branch_name, pr_url,
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
                "Entity TG-%s not found in project %s. PR: %s branch: %s",
                tg_ref, self.project.id, pr_url, branch_name,
            )
            return

        defaults = {
            "project": self.project,
            "ref": tg_ref,
            "branch_name": branch_name,
            "pull_request_id": pr_id,
            "repository": repo_full_name,
        }

        if action == "closed":
            defaults["status"] = PullRequest.STATUS_MERGED
            defaults["merged_by"] = (pr.get("merged_by") or {}).get("login")
            defaults["merged_at"] = pr.get("merged_at")
            obj, created = PullRequest.objects.update_or_create(
                pull_request_url=pr_url,
                defaults=defaults,
            )

            all_prs = PullRequest.objects.filter(project=self.project, ref=tg_ref)
            if all_prs.exists() and not all_prs.exclude(status=PullRequest.STATUS_MERGED).exists():
                self._transition(entity, "all_merged", _("all linked pull requests were merged"))
        else:
            defaults["status"] = PullRequest.STATUS_OPEN
            obj, created = PullRequest.objects.get_or_create(
                pull_request_url=pr_url,
                defaults=defaults,
            )
            self._transition(entity, "pr_open", _("pull request opened: %s") % pr_url)

        if created:
            logger.info(
                "Linked PR %s to TG-%s [%s] (project %s)",
                pr_url, tg_ref, entity.__class__.__name__, self.project.id,
            )
        else:
            logger.info(
                "Updated PR %s for TG-%s (merged_by=%s)",
                pr_url, tg_ref, defaults.get("merged_by"),
            )


class CreateEventHook(GitHubStatusTransitionMixin, BaseGitHubEventHook, BaseEventHook):
    """Evento `create` de GitHub: dispara cuando se crea una rama (o tag). Solo
    nos interesa `ref_type == "branch"` con un TG-<ref> en el nombre."""

    def ignore(self):
        return self.payload.get("ref_type") != "branch"

    def process_event(self):
        if self.ignore():
            return

        branch_name = self.payload.get("ref")
        if not branch_name:
            logger.warning("Incomplete create payload: no ref")
            return

        m = TG_REF_RE.search(branch_name)
        if not m:
            logger.info("No TG ref in branch: %s", branch_name)
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


class PullRequestReviewEventHook(GitHubStatusTransitionMixin, BaseGitHubEventHook, BaseEventHook):
    """Evento `pull_request_review` de GitHub: nos interesa únicamente el caso
    `state == "changes_requested"`, que manda el ticket de vuelta a Re-work."""

    def ignore(self):
        action = self.payload.get("action", "")
        state = self.payload.get("review", {}).get("state", "")
        return action != "submitted" or state != "changes_requested"

    def process_event(self):
        if self.ignore():
            return

        pr = self.payload.get("pull_request", {})
        pr_url = pr.get("html_url")
        branch_name = pr.get("head", {}).get("ref")
        review_url = self.payload.get("review", {}).get("html_url") or pr_url

        if not all([pr_url, branch_name]):
            logger.warning(
                "Incomplete pull_request_review payload: url=%s branch=%s",
                pr_url, branch_name,
            )
            return

        PullRequest.objects.filter(pull_request_url=pr_url).update(
            status=PullRequest.STATUS_CHANGES_REQUESTED
        )

        m = TG_REF_RE.search(branch_name)
        if not m:
            logger.info("No TG ref in branch: %s", branch_name)
            return

        tg_ref = int(m.group(1))
        entity = self._find_entity(tg_ref)
        if entity is None:
            logger.warning(
                "Entity TG-%s not found in project %s. PR: %s",
                tg_ref, self.project.id, pr_url,
            )
            return

        self._transition(entity, "changes_requested", _("changes requested on %s") % review_url)


class PushEventHook(BaseGitHubEventHook, BasePushEventHook):
    def get_data(self):
        result = []
        github_user = self.payload.get('sender', {})
        commits = self.payload.get("commits", [])
        for commit in filter(None, commits):
            result.append({
                "user_id": github_user.get('id', None),
                "user_name": github_user.get('login', None),
                "user_url": github_user.get('html_url', None),
                "commit_id": commit.get("id", None),
                "commit_url": commit.get("url", None),
                "commit_message": commit.get("message").strip(),
                "commit_short_message": commit.get("message").split("\n")[0].strip(),
            })

        return result

    def process_event(self):
        # Runs first and unconditionally: the base TG-<n> status-change/mention
        # scan below raises ActionSyntaxException (-> 400) when a commit
        # references a ref that doesn't exist (see BasePushEventHook), which
        # would otherwise stop the changelog from ever being recorded for
        # that push. Recording it here keeps that concern independent from
        # the pre-existing TG-ref logic.
        from taiga.changelog.services import store_push
        store_push(self.project, self.payload, platform_slug=self.platform_slug)

        super().process_event()
