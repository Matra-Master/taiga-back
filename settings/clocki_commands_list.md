# Comandos de ejemplo

## Iniciar tarea no interactiva con descripción, proyecto y tag usando el token del usuario

```bash
clockify-cli in --interactive=0 --token "$USER_TOKEN" --description "$DESCRIPTION" --project "$PROJECT" --tag "$TAG"
```

## Mismo que el anterior pero devuelve un json con el parámetro `-j`

```bash
clockify-cli in -j --interactive=0 --token "$USER_TOKEN" --description "$DESCRIPTION" --project "$PROJECT" --tag "$TAG"
```

## Tag se puede repetir
```bash
clockify-cli in -j --interactive=0 --token "$USER_TOKEN" --description "$DESCRIPTION" --project "$PROJECT" --tag "$TAG1" --tag "$TAG2"
```

## Listar tags en dos columnas: ID y nombre

```bash
clockify-cli tag --format "{{.ID}},{{.Name}}"
```


# Comportamientos útiles de saber:

## Cómo interactúan dos tareas una después de otra:

- Iniciar una tarea con hora de inicio anterior a la actual

```bash
clockify-cli in -s 1400 --description "Tarea iniciada a las 14"
```

- Si iniciás a las 15 una nueva tarea sin detener la anterior la anterior se cierra sola y arranca la nueva

```bash
clockify-cli in --description "Nueva tarea a las 15"
```

- Si iniciás a las 15 una tarea y le ponés hora de inicio a las 14:40 clocky detiene la de las 14 y le pone 14:40 como hora de fin :O

```bash
clockify-cli in -s 1440 --description "Nueva tarea a las 15 pero empezada a las 14:40"
```
