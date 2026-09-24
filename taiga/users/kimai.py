"""Cliente mínimo de la API REST de Kimai (time tracking), usando el token de API de cada usuario."""
from django.conf import settings

import requests


class KimaiError(Exception):
    pass


def _request(user, method, path, **kwargs):
    if not settings.KIMAI_URL:
        raise KimaiError("KIMAI_URL is not configured")
    if not user.kimai_token:
        raise KimaiError("Kimai token must be set on profile config")

    headers = {"Authorization": f"Bearer {user.kimai_token}", "Accept": "application/json"}
    url = f"{settings.KIMAI_URL.rstrip('/')}/api{path}"
    try:
        res = requests.request(method, url, headers=headers, timeout=10, **kwargs)
    except requests.RequestException as e:
        raise KimaiError(f"Kimai is unreachable: {e}")

    if not res.ok:
        try:
            message = res.json().get("message", res.text)
        except ValueError:
            message = res.text
        raise KimaiError(message or f"Kimai error {res.status_code}")
    return res.json() if res.content else None


def resolve_kimai_project(project, epic_id=None):
    """Proyecto de Kimai al que se imputa el tiempo según el tracking_mode del proyecto de Taiga."""
    if project.tracking_mode == "epic":
        if epic_id is None:
            raise KimaiError("epicId is required when project tracking mode is 'epic'")
        epic = project.epics.filter(id=epic_id).first()
        if epic is None:
            raise KimaiError("Epic not found")
        if not epic.kimai_project_id:
            raise KimaiError("Epic does not have a Kimai project configured")
        return epic.kimai_project_id

    if not project.kimai_project_id:
        raise KimaiError("Project does not have a Kimai project configured")
    return project.kimai_project_id


def list_projects(user):
    return [{"id": p["id"], "name": p["name"], "parentTitle": p.get("parentTitle")}
            for p in _request(user, "GET", "/projects")]


def list_activities(user, kimai_project_id):
    # Kimai devuelve las activities del proyecto más las globales (si el proyecto las admite).
    return [{"id": a["id"], "name": a["name"], "project": a.get("project")}
            for a in _request(user, "GET", "/activities", params={"project": kimai_project_id})]


def start(user, kimai_project_id, activity_id, description, tags=()):
    data = {
        "project": kimai_project_id,
        "activity": activity_id,
        "description": description,
        "billable": False,
    }
    if tags:
        data["tags"] = ",".join(tags)
    return _request(user, "POST", "/timesheets", json=data)


def stop_active(user):
    active = _request(user, "GET", "/timesheets/active")
    for timesheet in active:
        _request(user, "PATCH", f"/timesheets/{timesheet['id']}/stop")
    return len(active)
