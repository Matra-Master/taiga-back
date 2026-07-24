# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base.api.permissions import TaigaResourcePermission
from taiga.base.api.permissions import HasProjectPerm
from taiga.base.api.permissions import IsProjectAdmin
from taiga.base.api.permissions import AllowAny
from taiga.base.api.permissions import IsSuperUser


class ChangelogRepositoryPermission(TaigaResourcePermission):
    # Repos + branches of interest are admin-managed config, always editable
    # by the project admin regardless of the visual module toggle.
    enough_perms = IsProjectAdmin() | IsSuperUser()
    global_perms = None
    retrieve_perms = HasProjectPerm('view_project')
    list_perms = AllowAny()
    create_perms = IsProjectAdmin()
    update_perms = IsProjectAdmin()
    partial_update_perms = IsProjectAdmin()
    destroy_perms = IsProjectAdmin()


class ChangelogEntryPermission(TaigaResourcePermission):
    # Read-only: entries are only ever written by the GitHub webhook.
    enough_perms = IsProjectAdmin() | IsSuperUser()
    global_perms = None
    retrieve_perms = HasProjectPerm('view_project')
    list_perms = AllowAny()
