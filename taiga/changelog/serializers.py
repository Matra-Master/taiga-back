# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base.fields import Field
from taiga.base.api import serializers


class ChangelogRepositorySerializer(serializers.LightSerializer):
    id = Field()
    project = Field(attr="project_id")
    full_name = Field()
    branches = Field()
    created_date = Field()


class ChangelogEntrySerializer(serializers.LightSerializer):
    id = Field()
    repository = Field(attr="repository_id")
    branch = Field()
    compare_url = Field()
    before_sha = Field()
    after_sha = Field()
    head_message = Field()
    pusher_name = Field()
    commits = Field()
    created_date = Field()
