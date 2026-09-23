# Pulso TransMi

Plataforma central del primer proyecto de MLOps de Orbital Academy. El reto simula
la demanda de pasajeros en estaciones reales de TransMilenio: los estudiantes
consumen observaciones que aparecen con el tiempo, entrenan y reentrenan modelos,
envían pronósticos y compiten en un leaderboard que cambia cuando el sistema
introduce nuevos patrones y drift.

> **Competencia oficial — 21 de septiembre de 2026:** la versión `0.6.2` activa
> el escenario dinámico de siete días. Cada 30 minutos aparecen observaciones
> nuevas y cada hora se abre un ciclo de 48 predicciones con 25 minutos para
> entregar. El portal, la API key personal, los recibos y el leaderboard están
> disponibles en `https://pulso-transmi.72-60-245-2.sslip.io`.

El login valida únicamente correo institucional + documento. El nombre ingresado
es una preferencia privada para el saludo; el leaderboard conserva el nombre
oficial de matrícula.

> **Actualización del portal — 22 de septiembre de 2026:** el Home incorpora
> la **carrera de accuracy**, con histórico acumulado y ventana móvil de seis
> ciclos evaluados, encima del tablero de entregas. No cambia el procedimiento
> para enviar predicciones ni requiere generar otra API key.

La matrícula activa ya está precargada: 32 estudiantes (20 del grupo A y 12 del
grupo B). Cada persona debe activar su propia API key y realizar una entrega
individual; el repositorio no contiene correos ni documentos del curso.

## Qué se aprende

El objetivo no es obtener una buena predicción una sola vez. Cada estudiante debe
operar un pequeño sistema de ML capaz de:

1. descargar datos incrementales desde una API;
2. validar y versionar los datos usados para entrenar;
3. entrenar, evaluar y versionar un modelo;
4. ejecutar inferencia periódica con GitHub Actions;
5. enviar predicciones trazables antes del cierre de cada ciclo;
6. detectar pérdida de desempeño y drift;
7. decidir cuándo reentrenar sin intervención manual.

El catálogo se basará en nombres y coordenadas reales de estaciones de Bogotá.
La demanda, el clima, los eventos y los cambios de régimen serán sintéticos y
reproducibles.

## Dinámica prevista

- **Frecuencia de observación:** 15 minutos.
- **Publicación:** cada 30 minutos se liberan dos intervalos nuevos por estación.
- **Ciclo de entrega:** cada hora, con ventana de 25 minutos.
- **Horizonte:** cuatro intervalos futuros —15, 30, 45 y 60 minutos— para cada
  estación requerida.
- **Escenario inicial:** 12 estaciones, 45 días de historia y 7 días de
  competencia acelerada.
- **Duración académica:** dos semanas, del 16 al 30 de septiembre de 2026.
- **Métrica principal:** `Accuracy = 100 × max(0, 1 - WAPE)` calculada primero
  por estación y luego promediada.
- **Elegibilidad:** cobertura mínima prevista del 95 %; un target ausente se
  evalúa como predicción cero.
- **Bono:** dashboard en Vercel para visualizar demanda, drift, salud del pipeline
  y posición en el leaderboard.

La prueba inicial usa 12 targets —uno por estación— y comprueba integración. Los
ciclos oficiales posteriores usarán 48 targets y activarán el score cuando exista
ground truth revelado.

## Dataset inicial

[`data/starter/`](data/starter/README.md) contiene 45 días de historia, 12
estaciones, frecuencia de 15 minutos y 51.840 observaciones sintéticas. El corte
no incluye los siete días reservados para competencia ni parámetros privados del
generador. Los hashes y el rango temporal están fijados en `metadata.json`.

## Arquitectura

```text
Configuración privada + semilla
              │
              ▼
       Generador sintético ──────► sim.generated_truth (privado)
                                           │
                                           ▼
GitHub Actions ◄── API ◄── observations ◄── Scheduler / reloj virtual
      │                    (solo pasado)             │
      └── predictions ──► submissions ──► scoring ──► leaderboard
```

La separación entre el futuro privado y los datos liberados es el control de
integridad central. El rol de la API no puede leer semillas, parámetros de drift
ni `sim.generated_truth`. PostgreSQL es la fuente de verdad; no se utilizan
Redis, Celery ni un broker en esta versión.

### Componentes

| Componente | Responsabilidad | Estado |
|---|---|---|
| PostgreSQL 17 | Catálogo, simulación privada, competencia y auditoría | Operativo |
| FastAPI | Historia, stream, ciclos, autenticación, entregas y leaderboard | Pública (`0.7.1`) |
| Portal web | Carrera de accuracy, benchmark completo, API key, rotación y recibos | Sesión estudiantil |
| Scheduler | Reloj, publicación incremental, ciclos, scoring y snapshots horarios | Operativo |
| Caddy | TLS y exposición pública del servicio | Operativo |
| GitHub Actions | Pipeline gratuito de cada estudiante | Ejemplo inicial publicado; automatización completa siguiente fase |
| Supabase | Persistencia gratuita de cada solución estudiantil | A cargo de cada estudiante |
| Vercel | Dashboard opcional | Bono |

La arquitectura detallada está en [docs/architecture.md](docs/architecture.md) y
el modelo relacional en [docs/data-model.md](docs/data-model.md).

## Primer acceso y predicción

1. Abre el [portal de Pulso TransMi](https://pulso-transmi.72-60-245-2.sslip.io/).
2. Ingresa con correo institucional y documento. El nombre es solo la forma en
   que el portal te saludará y no tiene que coincidir con la lista.
3. Genera tu API key y guárdala: solo se muestra una vez. Si la pierdes, vuelve
   al portal y rótala; la anterior quedará revocada.
4. Clona este repositorio y ejecuta el baseline:

```bash
git clone https://github.com/uexternadojz/pulso-transmi.git
cd pulso-transmi
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-student.txt
export PULSO_API_KEY="ptm_live_..."
python examples/first_prediction.py
```

El ejemplo combina el histórico con el stream incremental, entrena un Random
Forest con variables temporales y rezagos, descubre los targets abiertos y envía la predicción. La
guía completa está en [Primera predicción](docs/primera-prediccion.md).

## API pública `0.7.1`

La API pública está en `https://pulso-transmi.72-60-245-2.sslip.io`; Swagger se
encuentra en `/docs`. En el VPS el proceso escucha únicamente en
`http://127.0.0.1:8010` y Caddy controla la superficie pública.

| Método | Ruta | Propósito | Requiere BD |
|---|---|---|---|
| `GET` | `/health` | Liveness del proceso | No |
| `GET` | `/ready` | Conectividad con PostgreSQL | Sí |
| `GET` | `/v1/meta` | Versión, manifiesto y enlaces | No |
| `GET` | `/v1/stations` | Catálogo de 12 estaciones | No |
| `GET` | `/v1/observations` | Demanda paginada y filtrable | No |
| `GET` | `/v1/context` | Contexto histórico paginado | No |
| `GET` | `/v1/downloads/{filename}` | CSV y manifiesto estáticos | No |
| `GET` | `/v1/stream/observations` | Nuevos datos de competencia con cursor | Sí |
| `GET` | `/v1/clock` | Estado y hora virtual autoritativa | Sí |
| `GET` | `/v1/forecast-cycles/current` | Ciclo abierto y targets exactos | Sí |
| `GET` | `/v1/me` | Identidad de la API key | Sí + key |
| `POST` | `/v1/submissions` | Envío atómico e idempotente | Sí + key |
| `GET` | `/v1/submissions/{id}` | Recibo propio | Sí + key |
| `GET` | `/v1/leaderboard` | Ranking acumulado o rolling 24 h | Sí + key |
| `POST` | `/v1/portal/login` | Sesión académica del portal | Sí |
| `POST` | `/v1/portal/api-key` | Emisión única de credencial personal | Sí + sesión |
| `POST` | `/v1/portal/api-key/rotate` | Revoca y reemplaza la credencial activa | Sí + sesión |
| `GET` | `/v1/portal/dashboard` | Identidad, ronda y entregas propias | Sí + sesión |
| `GET` | `/v1/portal/leaderboard` | Conexión o ranking de la cohorte | Sí + sesión |
| `GET` | `/v1/portal/accuracy-chart` | Histórico de accuracy acumulada y móvil de seis ciclos por etapa | Sí + sesión |

### Cómo leer el Home: desempeño y continuidad

El Home muestra dos vistas complementarias. **La carrera de accuracy** compara
el desempeño predictivo a lo largo del tiempo; el **Sprint de submissions**, que
se conserva debajo, muestra quién está enviando de forma consistente. Estar
primero en entregas no significa necesariamente tener el modelo más preciso.

#### Carrera de accuracy

| Control o elemento | Cómo interpretarlo |
|---|---|
| **Acumulada** | Recalcula el desempeño desde el inicio de la etapa hasta cada punto; conserva el efecto de los ciclos anteriores. |
| **Últimos 6 ciclos** | Cada punto usa los seis ciclos resueltos más recientes hasta ese momento, o los disponibles al inicio. No son las últimas seis entregas personales. |
| **Etapa** | Selecciona un escenario con resultados evaluados. No borra datos ni reinicia el score; los futuros cortes dentro de un escenario aún están por definir. |
| **Ejes** | Horizontal: cierre de los ciclos, en hora de Bogotá. Vertical: accuracy de 0 a 100 %, donde más alto es mejor. |
| **Avatares y leyenda** | Incluyen a los 32 estudiantes. Pulsa un avatar para resaltar su trayectoria; pulsa de nuevo para volver a compararlas todas. |
| **Puntos y detalle** | Al pasar el cursor o enfocar un punto puedes consultar accuracy, cobertura, ciclos entregados, fecha, ciclo y versiones de modelo. |

Aquí **accuracy no significa porcentaje de aciertos de clasificación**: estamos
pronosticando cantidades. Se suman los errores absolutos y la demanda real de la
ventana por estación, se calcula `100 × max(0, 1 − WAPE)` para cada estación y
se promedian sus resultados. No se promedian directamente los porcentajes de
los ciclos; el denominador de demanda se protege con un mínimo de 1.

- **Una ausencia cuenta como predicción cero**, por lo que la continuidad también
  afecta el score. Revisa siempre la cobertura: es la proporción de targets
  entregados frente a los esperados en esa ventana.
- **Sin resultado** significa que todavía no hay entregas evaluadas para esa
  vista. El portal no inventa una trayectoria. Si antes hubo resultados pero ya
  no hay envíos dentro de la ventana móvil actual, indica **Sin envíos en ventana**
  y conserva la curva histórica.
- **Recibido no significa evaluado**: tu submission puede aparecer en el tablero
  de entregas antes de tener accuracy. El gráfico solo incorpora ciclos resueltos,
  cuando ya se reveló la demanda real necesaria para evaluarlos.
- Una caída puede deberse a ausencias, errores del pipeline o peor predicción;
  **por sí sola no demuestra drift**. Contrasta cobertura, recibos y datos antes
  de decidir reentrenar.

Por ejemplo, si entregaste solo dos de los últimos seis ciclos, la ventana móvil
no mide únicamente esos dos: también contempla las ausencias de los otros cuatro.
Por eso conviene automatizar los envíos y luego mejorar el modelo.

#### Sprint de submissions

Este tablero operativo ordena a quienes ya empezaron por entregas oficiales en los últimos seis ciclos,
racha vigente, ciclos totales y hora de la última entrega. Los reintentos no
otorgan ventaja: cada punto representa el `official_submission_id` de un ciclo.

Cada checkpoint incluye un tooltip con la hora de recepción, la versión del
modelo y el identificador del ciclo. Los 32 estudiantes permanecen visibles en
una única tabla-race: quienes todavía no envían conservan su lugar en la pista,
pero no reciben posición hasta registrar un ciclo oficial. Su ventana usa ciclos
cerrados, mientras que la carrera de accuracy necesita ciclos completamente
resueltos: las dos vistas pueden actualizarse en momentos distintos.

**Rutina recomendada:** confirma tu recibo en **Conexión**, revisa continuidad en
el Sprint y, cuando el ciclo esté evaluado, compara tu accuracy reciente con la
acumulada. Usa **Actualizar datos** para consultar el estado más reciente.
No cambies el período de tus envíos basándote en el gráfico: los targets válidos
siempre los entrega `/v1/forecast-cycles/current`.

El endpoint del gráfico utiliza la sesión del portal, no la API key de GitHub
Actions. No reemplaza `/v1/leaderboard`, cuya ventana rolling de 24 horas es
distinta de la ventana de seis ciclos del gráfico. Más detalles en
[Portal del estudiante](docs/portal-estudiante.md).

Respuesta esperada de salud:

```json
{"status":"ok","service":"pulso-transmi-api"}
```

El endpoint estático `/v1/observations` no cambia. Para el collector de
competencia se usa `/v1/stream/observations`; así un proceso incremental nunca
confunde el corte inicial con una liberación nueva. El payload, errores y reglas
de reintento están en el [contrato de API](docs/api-contract.md).

### Regla de entrega y guardrail del período

El estudiante **no debe calcular ni escribir manualmente** el período que cree
que corresponde. Antes de cada inferencia consulta:

```http
GET /v1/forecast-cycles/current
Authorization: Bearer $PULSO_API_KEY
```

La respuesta autoritativa indica:

- `cycle_id`: ciclo que acepta la entrega;
- `data_cutoff`: último instante que el modelo puede usar como entrenamiento;
- `forecast_start_at` y `forecast_end_at`: período exacto a pronosticar;
- `station_count` y `horizons_minutes`: estaciones y horizontes del ciclo;
- `expected_predictions`: número exacto de filas requeridas;
- `targets`: pares exactos `(station_id, target_at)` que se deben devolver.

En un ciclo oficial normal, el corte es `T` y se solicitan las 12 estaciones en
`T+15`, `T+30`, `T+45` y `T+60`: **48 predicciones**. El ciclo de práctica puede
tener otra cantidad; por eso el cliente siempre obedece la respuesta y nunca
debe fijar `48`, estaciones o timestamps en el código.

```text
T       datos publicados hasta T; abre el ciclo
T+25m   cierra la recepción real
T+30m   se revelan los dos primeros períodos
T+60m   se completa el período, se califica y abre el siguiente ciclo
```

`POST /v1/submissions` aplica el guardrail **antes de contar un intento**:

1. la API key determina al estudiante; el body no acepta nombre ni correo;
2. `cycle_id` debe ser el ciclo vigente y no puede estar cerrado;
3. `data_cutoff` debe ser idéntico al publicado;
4. `training_data_end` no puede superar el corte;
5. deben llegar todos y únicamente los targets publicados, sin duplicados;
6. los valores deben ser finitos, estar entre `0` y `100000` y el JSON no puede
   contener campos desconocidos;
7. solo una entrega que pasa todo lo anterior consume uno de los tres intentos.

Una aceptación devuelve `validated_contract`, que confirma el ciclo, el corte,
el período, los horizontes y la cantidad de predicciones que realmente validó
el servidor. Un `422 invalid_target_set` incluye ejemplos de `missing` y `extra`
y la instrucción de volver a consultar el ciclo vigente. No se debe corregir un
timestamp “a mano”.

## Inicio rápido local

### Requisitos

- Docker Engine con Docker Compose v2.
- `curl` para las comprobaciones básicas.
- Python 3.12 solo si se ejecutan pruebas fuera de Docker.

### 1. Configurar variables

```bash
cp .env.example .env
```

Reemplaza los tres valores `replace-with-...` por secretos diferentes y largos.
No confirmes `.env` en Git. Las variables son:

| Variable | Uso |
|---|---|
| `POSTGRES_DB` | Nombre de la base |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Administración e inicialización |
| `API_DB_PASSWORD` | Rol de mínimo privilegio usado por FastAPI |
| `SCHEDULER_DB_PASSWORD` | Rol usado por el scheduler |
| `APP_ENV` / `LOG_LEVEL` | Configuración de ejecución |
| `SCHEDULER_POLL_SECONDS` | Frecuencia con que se comprueba si corresponde un tick |
| `RELEASE_INTERVAL_MINUTES` | Cadencia de publicación; valor oficial 30 |
| `SUBMISSION_WINDOW_MINUTES` | Ventana de entrega; valor oficial 25 |
| `SUBMISSION_MAX_ATTEMPTS` | Intentos válidos máximos por ciclo; valor oficial 3 |

### 2. Validar y levantar

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Los scripts de `database/init/` solo se ejecutan al crear un volumen vacío. Para
una base existente se deben aplicar las migraciones de `database/migrations/` de
forma controlada; borrar el volumen no es un mecanismo de migración.

### 3. Verificar

```bash
curl --fail http://127.0.0.1:8010/health
curl --fail http://127.0.0.1:8010/ready
curl --fail http://127.0.0.1:8010/v1/meta
curl --fail 'http://127.0.0.1:8010/v1/observations?limit=10'
docker compose logs --tail=50 scheduler
```

Sin escenario activo, el scheduler registra heartbeat y no modifica datos. Con
un escenario en ejecución, cada tick queda en `ops.job_runs`; el heartbeat
incluye el último resultado.

En la competencia oficial el primer ciclo se crea durante la activación. No se
deben construir fechas ni IDs localmente: el pipeline consulta siempre
`/v1/forecast-cycles/current`. Si responde `404 no_open_cycle`, todavía no abrió
el siguiente ciclo o el anterior ya cerró; el workflow termina sin error y vuelve
a intentarlo en su próxima ejecución.

### 4. Detener sin perder datos

```bash
docker compose down
```

Nunca ejecutes `docker compose down -v` en un entorno que quieras conservar:
elimina el volumen de PostgreSQL.

## Pruebas

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest -q
```

La suite cubre salud, metadatos, filtros, paginación, descargas, emisión y
rotación de API keys, validación estricta, hashes canónicos y autenticación. La
versión `0.4.2` fue además verificada públicamente con un nombre preferido distinto
al oficial, sin alterar el nombre mostrado en el leaderboard.

## Operación en el VPS

- **Ruta:** `/opt/pulso-transmi`
- **API interna:** `127.0.0.1:8010`
- **PostgreSQL:** sin puerto publicado al host
- **URL pública:** `https://pulso-transmi.72-60-245-2.sslip.io`
- **Exposición pública:** Caddy con HTTPS y rutas explícitamente permitidas

El procedimiento de despliegue, diagnóstico, backup y recuperación vive en el
[runbook del VPS](docs/runbook.md). No copies `.env`, tokens ni contraseñas a
issues, logs compartidos o documentación.

## Flujo previsto para estudiantes

Cada estudiante mantendrá su solución en un repositorio separado de esta plataforma
central. La implementación gratuita objetivo es:

```text
GitHub repository
  ├── código de ingesta, features, entrenamiento e inferencia
  ├── modelo o artefacto versionado
  └── GitHub Actions
          ├── descarga observaciones nuevas usando cursor
          ├── decide si reentrena
          ├── consulta el ciclo y genera la cantidad de targets indicada
          └── envía con API key e Idempotency-Key

Supabase del estudiante
  └── historial, métricas, estado del modelo y datos del dashboard

Vercel opcional
  └── demanda, drift, ejecuciones y leaderboard
```

Las API keys nunca se guardan en código, Supabase del estudiante ni variables
públicas de Vercel. Para inferencia se usa GitHub Actions Secret
`PULSO_API_KEY`. El dashboard propio consulta el leaderboard desde una función
de servidor con la llave protegida; nunca desde una variable `NEXT_PUBLIC_*`.

## Estructura del repositorio

```text
app/                  FastAPI, configuración y scheduler
config/               escenario de ejemplo versionado
database/init/        creación inicial de roles, esquemas y permisos
database/migrations/  cambios incrementales para bases existentes
docs/                 diseño, contratos, progreso y operación
tests/                pruebas automatizadas
Dockerfile            imagen compartida por API y scheduler
docker-compose.yml    stack central del VPS
```

## Estado operativo

El escenario oficial fue compilado fuera del repositorio público, validado y
congelado antes de activarse. El repositorio publica el cargador, los guardrails
y el lifecycle, pero no el bundle, la semilla, los parámetros privados ni el
ground truth. El starter kit y el contrato de submissions son la interfaz que
deben usar los estudiantes.

El detalle, la evidencia y los criterios de salida se mantienen en
[docs/progress.md](docs/progress.md).

## Documentación

- [Guía operativa de submissions y GitHub Actions v2.0](docs/guides/pulso-transmi-guia-operativa-v2.0.pdf)
- [Guía metodológica para estudiantes v1.0](docs/guides/pulso-transmi-guia-metodologica-v1.0.pdf)
- [Versiones de la guía metodológica](docs/guides/README.md)
- [Progreso y próximos hitos](docs/progress.md)
- [Arquitectura](docs/architecture.md)
- [Modelo de datos y métrica](docs/data-model.md)
- [Generador de patrones y drift](docs/pattern-generator.md)
- [Contrato de API](docs/api-contract.md)
- [Cliente estudiantil y loop MLOps](docs/student-client.md)
- [Portal del estudiante](docs/portal-estudiante.md)
- [Primera predicción](docs/primera-prediccion.md)
- [Runbook del VPS](docs/runbook.md)

## Repositorio y proyecto operativo

- GitHub: [uexternadojz/pulso-transmi](https://github.com/uexternadojz/pulso-transmi)
- Proyecto Academy en Supabase: `Pulso TransMi — Proyecto 1 MLOps`
- ID operativo: `1dde4b7d-7ab4-4df8-8298-34c25d662750`
