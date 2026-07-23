# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from django.contrib import admin

from . import models


@admin.register(models.ChangelogRepository)
class ChangelogRepositoryAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "full_name", "branches", "created_date"]
    list_display_links = ["id", "full_name"]
    search_fields = ["full_name", "project__name", "project__slug"]
    raw_id_fields = ["project"]


@admin.register(models.ChangelogEntry)
class ChangelogEntryAdmin(admin.ModelAdmin):
    list_display = ["id", "repository", "branch", "after_sha", "created_date"]
    list_display_links = ["id", "after_sha"]
    list_filter = ["branch"]
    date_hierarchy = "created_date"
    search_fields = ["repository__full_name", "after_sha", "before_sha"]
    raw_id_fields = ["repository"]
