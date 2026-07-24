# Arquitectura de taiga-back (para explorar menos, la próxima vez)

Notas de arquitectura recopiladas al implementar features de este fork, para no tener
que re-explorar el código desde cero en cada sesión. Complementa (no repite) lo que ya
está en `/CLAUDE.md`. Si algo de acá queda desactualizado, corregirlo en el mismo PR
que lo desactualiza.

## Enrutado (`taiga/routers.py` + `taiga/urls.py`)

Un único `DefaultRouter` en `taiga/routers.py` centraliza el registro de todos los
viewsets de todas las apps de dominio. Todo cuelga de `api/v1/` (`taiga/urls.py`). Al
agregar un endpoint nuevo, el patrón es: viewset en `<app>/api.py`, registrarlo en
`taiga/routers.py`, no tocar `urls.py`.

## Apps de dominio (`taiga/projects/<submodule>/`)

Cada app de dominio (`userstories`, `issues`, `tasks`, `epics`, `milestones`, `wiki`,
`attachments`, `custom_attributes`, `notifications`, `history`, `tagging`, `votes`,
`likes`, `occ`, `due_dates`, `references`...) sigue la misma convención de archivos:

- `models.py` — modelos Django.
- `api.py` — viewsets DRF.
- `serializers.py` — normalmente `LightSerializer` con `Field`/`MethodField` explícitos
  (no serializers "mágicos" que introspeccionan el modelo).
- `permissions.py`, `validators.py` — un `ModelValidator` sin `fields` explícito acepta
  **todos** los campos del modelo salvo los listados en `Meta.read_only_fields`; agregar
  un campo al modelo lo hace automáticamente editable por API a menos que se declare
  `read_only_fields` o el campo requiera un validator custom (ver JSONField más abajo).
- `services.py` — lógica de negocio que no pertenece a las vistas.
- `signals.py`, `migrations/`.

Al tocar una feature, mirar los mismos archivos en un módulo hermano (p.ej. `issues/`
si se está tocando `userstories/`) para entender el patrón esperado antes de inventar uno
nuevo.

### JSONField en modelos

`taiga.base.db.models.fields.JSONField` es el tipo para JSON arbitrario en modelos
(ej. `ProjectModulesConfig.config`, `Project.webhook_status_map`). El validator DRF
correspondiente es un import **distinto**: `from taiga.base.fields import JSONField`
(`taiga/projects/validators.py`) — hay que declararlo explícitamente en el
`ModelValidator` (`campo = JSONField(required=False)`) para que el campo sea aceptado
como JSON arbitrario en el PATCH; sin esa declaración, `ModelValidator` igual lo
aceptaría por ser un campo del modelo, pero sin la validación/parseo de JSON correctos.

## Config a nivel proyecto: tres mecanismos, según qué tan "de negocio" sea

1. **FK directo en `Project`/`ProjectDefaults`** (`taiga/projects/models.py`): para
   defaults de negocio de primera clase (`default_us_status`, `default_issue_status`,
   etc.). Patrón: `OneToOneField(..., on_delete=models.SET_NULL, related_name="+",
   null=True, blank=True)`. Se exponen en `ProjectSerializer` como
   `Field(attr="default_us_status_id")` (el id, no el objeto anidado).
2. **`JSONField` directo en `Project`** (ej. `webhook_status_map`): para un mapeo o
   config estructurada que no amerita una tabla propia y tolera ids "colgantes" (un
   status borrado simplemente deja de aplicar, sin `on_delete` que limpiar). Igual que
   el punto 1, se expone en el serializer con `Field()` y se declara en el validator
   como se explica arriba.
3. **`ProjectModulesConfig.config`** (`taiga/projects/models.py`, un `JSONField` en un
   modelo aparte, `OneToOneField` a `Project`): para config de **integraciones**
   externas (github/gitlab/bitbucket/gogs), bajo una clave por módulo
   (`config["github"] = {...}`). Se lee/escribe con
   `taiga.projects.services.modules_config.get_modules_config(project)` (hace
   `get_or_create` + corre los `PROJECT_MODULES_CONFIGURATORS` de settings para
   recomputar cada módulo) y se expone en `GET/PATCH /api/v1/projects/{id}/modules`
   (`ProjectViewSet.modules`, `taiga/projects/api.py`). El PATCH hace un merge
   (`modules_config.config.update(request.DATA)`), no un reemplazo total.

Elegir 1 vs 2 vs 3 según: ¿es un valor de negocio simple y único? → FK. ¿Es un mapeo o
estructura arbitraria propia de Taiga? → JSONField directo en Project. ¿Es config de una
integración externa (secret, ids remotos)? → `ProjectModulesConfig`.

## Flujo de webhooks entrantes (GitHub/GitLab/Bitbucket/Gogs)

Todas las integraciones viven en `taiga/hooks/<proveedor>/` con la misma forma
(`api.py`, `event_hooks.py`, `models.py`, `services.py`).

- `taiga/hooks/api.py` — `BaseWebhookApiViewSet.create()`: resuelve el proyecto por
  `?project=<id>`, valida la firma (`_validate_signature`, específico de cada
  proveedor), lee `event_name = self._get_event_name(request)` (para GitHub, el header
  `x-github-event`) y busca la clase en `self.event_hook_classes.get(event_name)`. Si no
  hay clase para ese evento, responde `NoContent` sin hacer nada — **agregar soporte
  para un evento nuevo de GitHub es registrar una entrada en ese dict**, no tocar el
  dispatcher genérico.
- `taiga/hooks/github/api.py` (`GitHubViewSet.event_hook_classes`) — dict
  `nombre-de-evento-de-GitHub -> clase de event hook`. Los eventos soportados hoy:
  `push`, `issues`, `issue_comment`, `pull_request`, `create`, `pull_request_review`
  (los dos últimos, agregados para las transiciones automáticas de columna, ver más
  abajo). Firma validada con HMAC-SHA1 contra
  `project.modules_config.config["github"]["secret"]`.
- `taiga/hooks/event_hooks.py` — clases base reutilizables entre proveedores:
  - `BaseEventHook.get_user(user_id, platform)` — intenta mapear el autor externo vía
    `AuthData`; si no lo encuentra, cae al **usuario de sistema** de la plataforma
    (`User.objects.get(is_system=True, username__startswith=platform)`, creado en la
    migración `0001_initial.py` de cada app `hooks/<proveedor>/migrations/`).
  - `BaseIssueEventHook` — crear/actualizar/cerrar/reabrir un `Issue` a partir de un
    evento externo de issue.
  - `BasePushEventHook.set_item_status(ref, status_slug)` — el patrón canónico para
    mover un US/Issue/Task/Epic de columna desde un hook: resuelve el modelo por ref
    (`get_item_classes`), busca el `Status` por **slug** dentro del proyecto, asigna y
    guarda. Se usa junto con `take_snapshot(...)` + `send_notifications(...)` para que
    el cambio quede en el historial y dispare notificaciones (ver
    `BasePushEventHook.process_event`, que parsea `tg-<ref> #<status-slug>` de los
    mensajes de commit).
  - Cada método `generate_*_comment` arma el texto (markdown) que va como `comment` del
    `take_snapshot`, con fallback simple si faltan datos del usuario externo.

### Historial (`taiga/projects/history/services.py`)

`take_snapshot(obj, *, comment="", user=None, delete=False)` es la única forma de dejar
un registro en el historial de un objeto. Puntos no obvios:

- Compara contra el **último snapshot congelado** de `obj` (`get_last_snapshot_for_key`).
  Si `obj` nunca tuvo un snapshot previo, el entry se crea con `type="create"`
  (`HistoryType.create`), no `"change"`.
- `get_history_queryset_by_model_instance(obj, types=(HistoryType.change,))` —
  **filtra por defecto solo entries tipo `change`**. Si un test/flujo llama
  `take_snapshot` una sola vez sobre un objeto sin historial previo, esa consulta
  devuelve **vacío** (el entry quedó tipado `create`). El patrón en los tests
  existentes (`tests/integration/test_hooks_github.py`) es llamar `take_snapshot(obj,
  user=...)` una vez al principio (sin comment) para fijar la baseline, y recién
  después ejercitar el hook — así el cambio real del hook queda tipado `change` y es
  contado.
- Si no hay diff de campos **y** `comment` viene vacío **y** ya existía un snapshot
  previo, `take_snapshot` no crea nada (evita entries vacíos). Pasar siempre un
  `comment` no vacío si se quiere garantizar que quede registro aunque el diff sea nulo.

## Personalización: PR linking + transiciones automáticas de columna (RuloBot)

- Modelo `PullRequest` (`taiga/projects/userstories/models.py`, a pesar del módulo
  aplica a Issues/Tasks/Epics también): vincula un PR de GitHub a **cualquier** entidad
  con `ref` por `(project, ref)` — no hay FK directa a `UserStory`/`Issue`, es un join
  manual en los serializers (`get_pull_requests` en
  `userstories/serializers.py` e `issues/serializers.py`). Campo `status`
  (`open`/`merged`/`changes_requested`, constantes `PullRequest.STATUS_*`) reemplaza la
  antigua inferencia implícita por `merged_at is not None`.
- `taiga/hooks/github/event_hooks.py`:
  - `GitHubStatusTransitionMixin` — mixin compartido por `CreateEventHook`,
    `PullRequestEventHook` y `PullRequestReviewEventHook`. Dado un US/Issue y una
    `event_key` (`"branch"`, `"pr_open"`, `"all_merged"`, `"changes_requested"`), busca
    el status destino en `project.webhook_status_map[<userstory|issue>][event_key]`; si
    no está configurado (select vacío en el front) o el id ya no existe, no hace nada.
    Si transiciona, llama `take_snapshot(..., user=get_rulobot_user())` +
    `send_notifications(...)`, igual que el resto de los hooks.
  - `get_rulobot_user()` — resuelve el usuario que figura como autor de estas
    transiciones: `settings.RULOBOT_USER_ID` si está seteado, si no cae al usuario de
    sistema `github-*` (mismo fallback que el resto del hook).
  - El TG-ref se extrae siempre del **nombre de rama** (`head.ref` en PRs/reviews, `ref`
    en el evento `create`) con el mismo regex `TG-(\d+)` (case-insensitive), nunca del
    título/cuerpo del PR.
  - "Todos los PRs mergeados" se resuelve consultando `PullRequest.objects.filter(project,
    ref)` y comprobando que ninguno tenga `status` distinto de `merged` (no hay contador
    separado ni campo agregado en el ticket).
- `Project.webhook_status_map` (JSONField, ver mecanismo 2 más arriba) — configurable
  por proyecto en la solapa Attributes del front (ver `taiga-front/docs/architecture.md`).

## Otras personalizaciones del fork (resumen, detalle en `/CLAUDE.md`)

Changelog automático desde push (`taiga.changelog`, alimentado desde
`PushEventHook.process_event` **antes** de la lógica de TG-ref preexistente, para que un
`ActionSyntaxException` de esa lógica no impida grabar el changelog), Clockify,
clonado de user stories, tipos de proyecto UX/Design. Ver `/CLAUDE.md` para el detalle
completo y qué archivos tocar en cada caso.
