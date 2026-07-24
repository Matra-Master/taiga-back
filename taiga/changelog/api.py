# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base import filters
from taiga.base.api import ModelCrudViewSet
from taiga.base.api import ModelListViewSet
from taiga.base.api.mixins import BlockedByProjectMixin

from . import models
from . import permissions
from . import serializers
from . import validators


class ChangelogRepositoryViewSet(BlockedByProjectMixin, ModelCrudViewSet):
    model = models.ChangelogRepository
    serializer_class = serializers.ChangelogRepositorySerializer
    validator_class = validators.ChangelogRepositoryValidator
    permission_classes = (permissions.ChangelogRepositoryPermission,)
    filter_backends = (filters.CanViewProjectFilterBackend,)
    filter_fields = ("project",)


class ChangelogEntryViewSet(ModelListViewSet):
    model = models.ChangelogEntry
    serializer_class = serializers.ChangelogEntrySerializer
    permission_classes = (permissions.ChangelogEntryPermission,)
    filter_backends = (
        filters.custom_filter_class(
            filters.CanViewProjectFilterBackend,
            project_query_param="repository__project",
        ),
        filters.CreatedDateFilter,
    )
    # ChangelogEntry has no direct "project" FK (only via repository.project),
    # so "project" is mapped to the actual ORM lookup for the generic exact-match filter.
    # CreatedDateFilter (above) adds created_date/__gte/__lte on top of these exact-match fields.
    filter_fields = (("project", "repository__project"), "repository", "branch")

    def get_queryset(self):
        qs = self.model.objects.all()
        qs = qs.select_related("repository", "repository__project")
        return qs
