# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from taiga.base.db.models.fields import JSONField


class ChangelogRepository(models.Model):
    """
    Configuration of a repository + branches of interest for a project's
    changelog. This is admin-managed config, not auto-created: a push is only
    stored (see ChangelogEntry) when its platform+repo+branch matches one of these.
    """
    PLATFORM_GITHUB = "github"
    PLATFORM_GITLAB = "gitlab"
    PLATFORM_CHOICES = (
        (PLATFORM_GITHUB, _("GitHub")),
        (PLATFORM_GITLAB, _("GitLab")),
    )

    project = models.ForeignKey(
        "projects.Project",
        null=False, blank=False,
        related_name="changelog_repositories",
        verbose_name=_("project"),
        on_delete=models.CASCADE,
    )
    # ponytail: "github" por default porque el changelog nació GitHub-only;
    # las filas ya existentes (creadas antes de este campo) quedan como GitHub.
    platform = models.CharField(
        max_length=20, null=False, blank=False,
        choices=PLATFORM_CHOICES, default=PLATFORM_GITHUB,
        verbose_name=_("platform"),
    )
    full_name = models.TextField(
        null=False, blank=False,
        verbose_name=_("repository full name"),
        help_text=_("Repository, e.g. \"my-org/my-repo\""),
    )
    branches = ArrayField(
        models.TextField(),
        default=list, blank=True,
        verbose_name=_("branches of interest"),
    )
    created_date = models.DateTimeField(
        null=False, blank=False, default=timezone.now,
        verbose_name=_("created date"),
    )

    class Meta:
        verbose_name = "changelog repository"
        verbose_name_plural = "changelog repositories"
        ordering = ["project", "full_name"]
        # El mismo full_name puede existir en dos plataformas distintas (ej.
        # "acme/webapp" como repo de GitHub Y como repo de GitLab) -> platform
        # forma parte de la clave, si no dos repos legítimos chocarían entre sí.
        unique_together = ("project", "platform", "full_name")

    def __str__(self):
        return f"{self.full_name} ({self.project})"


class ChangelogEntry(models.Model):
    """
    A single push event recorded for a configured repository+branch: the diff
    (compare) plus the list of non-merge commits included in it.
    """
    repository = models.ForeignKey(
        ChangelogRepository,
        null=False, blank=False,
        related_name="entries",
        verbose_name=_("repository"),
        on_delete=models.CASCADE,
    )
    branch = models.TextField(
        null=False, blank=False,
        verbose_name=_("branch"),
    )
    compare_url = models.URLField(
        null=False, blank=False,
        verbose_name=_("compare URL"),
    )
    before_sha = models.CharField(
        max_length=64, null=True, blank=True,
        verbose_name=_("before commit sha"),
    )
    after_sha = models.CharField(
        max_length=64, null=False, blank=False,
        verbose_name=_("after (head) commit sha"),
    )
    head_message = models.TextField(
        null=True, blank=True,
        verbose_name=_("head commit message"),
    )
    pusher_name = models.TextField(
        null=True, blank=True,
        verbose_name=_("pusher name"),
    )
    commits = JSONField(
        null=False, blank=True, default=list,
        verbose_name=_("commits"),
        help_text=_("List of {message, author_name, url}, merge commits excluded"),
    )
    delivery_id = models.CharField(
        max_length=64, null=True, blank=True,
        verbose_name=_("GitHub delivery id"),
    )
    created_date = models.DateTimeField(
        null=False, blank=False, default=timezone.now,
        verbose_name=_("created date"),
    )

    class Meta:
        verbose_name = "changelog entry"
        verbose_name_plural = "changelog entries"
        ordering = ["-created_date"]
        unique_together = ("repository", "after_sha")

    def __str__(self):
        return f"{self.repository.full_name}@{self.branch} {self.after_sha[:8]}"
