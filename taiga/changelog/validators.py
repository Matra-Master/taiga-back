# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base.api import validators
from taiga.base.fields import PgArrayField

from . import models


class ChangelogRepositoryValidator(validators.ModelValidator):
    branches = PgArrayField(required=False)

    class Meta:
        model = models.ChangelogRepository
        read_only_fields = ("id", "created_date")
