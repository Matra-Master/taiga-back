# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2021-present Kaleidos INC

from taiga.base import exceptions as exc
from taiga.base.api.utils import get_object_or_404

from django.apps import apps
from django.utils.translation import gettext as _

# ponytail: la Application del token personal se auto-crea con un id fijo en vez de una data
# migration + management command; si hacen falta varias apps del equipo, pasar a migración.
PERSONAL_APPLICATION_ID = "00000000-0000-0000-0000-000000000001"


def get_user_for_application_token(token:str) -> object:
    """
    Given an application token it tries to find an associated user
    """
    app_token = apps.get_model("external_apps", "ApplicationToken").objects.filter(token=token).first()
    if not app_token:
        raise exc.NotAuthenticated(_("Invalid token"))
    return app_token.user


def get_or_create_personal_token(user:object) -> object:
    """
    Given a user it returns its personal application token, creating it the first time.
    ApplicationToken.generate_token() is idempotent, so the token is stable.
    """
    ApplicationToken = apps.get_model("external_apps", "ApplicationToken")
    Application = apps.get_model("external_apps", "Application")
    application, _ = Application.objects.get_or_create(
        id=PERSONAL_APPLICATION_ID,
        defaults={"name": "Personal API token", "next_url": "/"})
    token, _ = ApplicationToken.objects.get_or_create(user=user, application=application)
    token.generate_token()
    token.save()
    return token


def authorize_token(application_id:int, user:object, state:str) -> object:
    ApplicationToken = apps.get_model("external_apps", "ApplicationToken")
    Application = apps.get_model("external_apps", "Application")
    application = get_object_or_404(Application, id=application_id)
    token, _ = ApplicationToken.objects.get_or_create(user=user, application=application)
    token.update_auth_code()
    token.state = state
    token.save()
    return token
