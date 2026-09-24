import pytest
from unittest import mock

from django.urls import reverse

from .. import factories as f

from taiga.base.utils import json

pytestmark = pytest.mark.django_db


def _ok(payload):
    return mock.Mock(ok=True, content=b"x", json=mock.Mock(return_value=payload))


@pytest.fixture
def kimai(settings):
    settings.KIMAI_URL = "https://kimai.test/"
    with mock.patch("taiga.users.kimai.requests.request") as request:
        yield request


def _member(project):
    user = f.UserFactory.create(kimai_token="secret")
    f.MembershipFactory.create(project=project, user=user)
    return user


@pytest.mark.parametrize("tracking_mode", ["project", "epic"])
def test_start_kimai_timer(client, kimai, tracking_mode):
    project = f.ProjectFactory.create(kimai_project_id=7, tracking_mode=tracking_mode)
    epic = f.EpicFactory.create(project=project, kimai_project_id=9)
    user = _member(project)
    kimai.return_value = _ok({"id": 1})

    client.login(user)
    data = {"projectId": project.id, "epicId": epic.id, "activityId": 3,
            "usRef": 12, "taskRef": 15, "subject": "Hola", "tags": ["BF-QA"]}
    res = client.post(reverse("users-start-kimai-timer"), json.dumps(data), content_type="application/json")

    assert res.status_code == 200, res.data
    method, url = kimai.call_args.args
    assert (method, url) == ("POST", "https://kimai.test/api/timesheets")
    assert kimai.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kimai.call_args.kwargs["json"] == {
        "project": 7 if tracking_mode == "project" else 9,
        "activity": 3,
        "description": "TG-12 - #15 Hola",
        "billable": False,
        "tags": "BF-QA",
    }


def test_start_kimai_timer_requires_membership(client, kimai):
    project = f.ProjectFactory.create(kimai_project_id=7)
    user = f.UserFactory.create(kimai_token="secret")

    client.login(user)
    data = {"projectId": project.id, "activityId": 3}
    res = client.post(reverse("users-start-kimai-timer"), json.dumps(data), content_type="application/json")

    assert res.status_code == 400
    kimai.assert_not_called()


def test_kimai_activities_rejects_non_numeric_ids(client, kimai):
    user = f.UserFactory.create(kimai_token="secret")

    client.login(user)
    res = client.get(reverse("users-kimai-activities"), {"projectId": "abc"})

    assert res.status_code == 400
    kimai.assert_not_called()


def test_stop_kimai_timer_stops_every_active_timesheet(client, kimai):
    user = f.UserFactory.create(kimai_token="secret")
    kimai.side_effect = [_ok([{"id": 4}, {"id": 5}]), _ok({}), _ok({})]

    client.login(user)
    res = client.post(reverse("users-stop-kimai-timer"))

    assert res.status_code == 200
    assert [c.args for c in kimai.call_args_list] == [
        ("GET", "https://kimai.test/api/timesheets/active"),
        ("PATCH", "https://kimai.test/api/timesheets/4/stop"),
        ("PATCH", "https://kimai.test/api/timesheets/5/stop"),
    ]


def test_kimai_token_is_not_public(client):
    owner = f.UserFactory.create(kimai_token="secret")
    other = f.UserFactory.create()

    client.login(other)
    res = client.get(reverse("users-detail", args=[owner.pk]))

    assert "kimai_token" not in res.data
