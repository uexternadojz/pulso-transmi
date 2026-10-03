# Control versionado de drift — contrato v1

Fecha de diseño: 28 de septiembre de 2026.

## Alcance y estado verificable

Actualización 0.9.0: `operation: reopen` habilita una extensión explícita desde
un reloj completado y sin ciclos pendientes. La revisión enlaza el hash anterior,
conserva la frontera comprometida y puede ampliar el final virtual. El contrato
de observaciones puede versionarse por registro mediante una política inmutable.
Ver [fase final](fase-final.md) y [operación](drift-operations.md).

Actualización 0.8.0: implementados validador de planes, importación transaccional
por tramos, archivo inmutable de revisiones, frontera protegida, continuación,
cierre real con drenaje y observatorio docente. El generador reconstruido y su
calibración permanecen en el entorno privado. Procedimiento ejecutable en
[Operación de drift](drift-operations.md).

La CLI `app.drift_plan` sigue siendo solo preview. La activación utiliza
`app.drift_admin` con bundle calibrado y verificación del reloj en la BD.
La sección de diseño conserva decisiones y gates; no se ha implementado una
escalada automática ni un botón de edición en el portal.

## Decisión arquitectónica

Conservar el escenario, matrícula, credenciales, cursor de observaciones y corte
actuales. Añadir continuaciones versionadas con timestamps virtuales crecientes.
El cargador original de bundles de siete días conserva su validación; una nueva
operación de extensión validará la continuidad en vez de relajar ese contrato.

La programación de drift se define en horas virtuales. La agenda docente utiliza
America/Bogota y muestra también el instante virtual efectivo. Una pausa o
retraso puede desplazar la correspondencia: no asumir que el calendario real y
el simulado son idénticos. El cierre real se configura por separado; debe dejar
resolver los ciclos admitidos antes de detener la publicación.

El esquema `sim` permanece privado. El rol público no obtiene acceso a planes,
perfiles, semillas, previews de demanda ni resultados futuros. El control inicial
será una herramienta administrativa provisionada; un panel posterior requerirá
autorización docente real, no inferida del nombre de usuario.

## Niveles y semántica

`level` es un entero de 0 a 3 que selecciona un perfil privado calibrado:

| Nivel | Significado operativo |
|---|---|
| 0 | Estabilización; régimen de referencia de esta continuación |
| 1 | Cambio de complejidad baja |
| 2 | Cambio de complejidad intermedia |
| 3 | Combinación de cambios de complejidad alta |

El perfil fija límites físicos, estaciones, magnitudes y composición. Un número
mayor no promete una caída exacta de accuracy para todos los modelos. El perfil
incluye una referencia fija por estación; nunca se reaplica un multiplicador sobre
el resultado de la revisión anterior. Mantener nivel/perfil conserva el régimen
y no vuelve a sortear estaciones ni reinicia el ruido. Bajar de nivel transiciona
desde el estado vigente hacia el nuevo objetivo. No restaura observaciones del
pasado. Perfil y generador quedan identificados por versión y hash de artefacto.

Una fase contiene `phase_id`, `level`, `duration_hours` y `transition_hours`.
Debe reservar al menos seis horas tras su transición; el mínimo estructural no
demuestra que exista información suficiente para aprender. La calibración puede
exigir permanencias mayores. Los planes tienen máximo siete días virtuales y
pueden encadenarse. Las fases son intervalos `(inicio, fin]`, sin duplicar el
punto puente entre tramos.

## Revisiones y frontera inmutable

Cada revisión contiene identidad de plan y escenario, número secuencial, hash
del padre, versión del perfil, inicio virtual, fases y motivo. Una revisión nueva
describe la continuación desde su frontera efectiva; las revisiones previas se
conservan. El hash es de contenido canónico; no sustituye autorización ni firma.

Antes de programar, el runtime debe obtener como frontera protegida el máximo de:

- reloj virtual y timestamps de observaciones ya publicadas;
- targets de TODOS los ciclos ya abiertos, incluso si todavía no recibieron
  submissions o ya cerraron sin resolver;
- cualquier tramo adicional comprometido para publicación;
- compromisos de contexto/eventos ya anunciados que restrinjan el cambio.

El nuevo inicio es una hora virtual completa igual o posterior a esa frontera;
su primer target queda 15 minutos después. Si una solicitud no cabe, el preview
la rechaza e informa la siguiente frontera disponible; no cambia su hora sin
avisar. La frontera proporcionada al validador local es solo una entrada de
preview: para activar debe recalcularse desde la BD dentro de la transacción.

Un ciclo abierto compromete sus 48 targets y la revisión que los generó. Ningún
ajuste posterior puede reemplazarlos. Corregir una generación comprometida exige
un procedimiento de incidente explícito; no una actualización silenciosa.

## Compilación y activación propuestas

1. Registrar revisión candidata y motivo; comprobar padre vigente e identidad.
2. Compilar fuera del bloqueo del scheduler a partir de un checkpoint privado.
   Guardar semilla/estado aleatorio, estado latente, versión de código, perfil,
   dependencias y hashes. La reproducción debe ser independiente del batch.
3. Validar grilla, contexto, continuidad, límites, reproducibilidad y desempeño.
   Guardar evidencia medida, no solamente una etiqueta `passed`.
4. Adquirir el mismo advisory lock del scheduler, volver a leer reloj, frontera
   y revisión activa. Rechazar si cambiaron y el candidato ya no es válido.
5. Publicar atómicamente el manifiesto aprobado, tramo y revisión activa. El
   compromiso queda persistido antes de abrir un ciclo que lo use.
6. El scheduler publica y evalúa exclusivamente targets comprometidos. El mismo
   evento de control no puede crear revisiones o ciclos duplicados al reintentarse.

Propuesta de persistencia: `sim.drift_plan_revisions` (contenido y cadena),
`sim.generation_segments` (rangos, checkpoint y hashes), asociación de ciclo a
segmento/revisión y `ops.audit_events` para cada transición administrativa.
La migración 010 implementa revisiones con el artefacto completo y la asociación de ciclos. No se creó una tabla separada de segmentos: los tramos están contenidos en cada revisión.

El futuro de ensayo vive en staging. Al reemplazar un tramo todavía editable se
marca su versión como sustituida; el manifiesto selecciona una única generación
por timestamp. Los targets comprometidos y sus artefactos permanecen inmutables.
Una reversión operativa crea una nueva continuación; nunca borra historial.

## Cadencia y manejo durante la semana

- Empezar con un perfil de baja complejidad y una permanencia suficiente para
  observar adaptación. No programar una escalada automática por día de calendario.
- Revisar en checkpoints docentes el accuracy reciente, cobertura y errores por
  estación/horizonte, con ventanas comparables y cohortes de cobertura suficiente.
- Comparar también referencias privadas estáticas y adaptativas bajo exactamente
  la misma información disponible. Los rezagos nuevos pueden ayudar a un modelo
  fijo; no atribuir toda mejora a reentrenamiento.
- Proponer subir, mantener o bajar y registrar datos/ventana que motivan la
  decisión. La decisión inicial es docente. Aplicar permanencia mínima e
  histéresis antes de automatizarla para evitar oscilaciones.
- Mantener la dificultad si hay una caída de cobertura o un incidente de servicio.
  Una decisión afecta a toda la cohorte, nunca se personaliza por estudiante.
- Reservar una ventana final de recuperación antes del cierre del viernes.
  Ni el horario exacto ni los umbrales privados se publican como receta.

`hold` conserva el régimen con publicación normal. `cancel` cancela únicamente
una intervención futura no comprometida. Pausar la competencia deja terminar
los ciclos admitidos antes de detener reloj y publicación. No generar ausencias
para horas reales sin ciclos. El `pause/resume` actual no implementa por sí solo
estas garantías; no debe usarse como sustituto del nuevo control.

## Calibración y gates antes de producción

- Recuperar o reconstruir el generador: la dependencia histórica en `/tmp` no
  forma parte de un entorno reproducible. Documentar el nuevo modelo generativo.
- Reproducir un tramo desde su checkpoint, en batches distintos, byte por byte.
- Medir caída y recuperación con evaluación temporal de los cuatro horizontes,
  sin entrenar con targets no revelados. Incluir modelos fijos con features frescas.
- Probar niveles ascendentes/descendentes, mantenimiento, reinicios, reintentos,
  activación concurrente con ticks y rechazo de cambios dentro de la frontera.
- Verificar que no cambien hashes de observaciones, targets y scores existentes.
- Verificar continuidad del stream y del leaderboard desde el mismo corte.
- Versionar la extensión del cierre con su duración virtual y agenda real; probar
  que se completa el último ciclo sin abrir uno que no pueda resolverse.
- La API de contexto vigente sirve el histórico estático. No exigir un régimen
  dependiente de nuevo contexto meteorológico hasta ofrecerlo y verificar su
  disponibilidad y sus tiempos de publicación.
- Medir consumo y tiempos en el VPS; compilación pesada fuera del tick. Si falta
  un tramo válido, no abrir ciclos sin verdad disponible: señalar `blocked` y
  conservar disponibles el histórico y los recibos.

## Ejemplo ejecutable de preview

El archivo de ejemplo usa fechas ficticias y no contiene parámetros del reto:

```bash
python -m app.drift_plan \
  --plan config/drift-plan.example.json \
  --protected-through 2030-01-01T00:00:00Z \
  --virtual-now 2030-01-01T00:00:00Z
pytest -q tests/test_drift_plan.py
```

Para revisar una modificación, proporcionar también `--previous` con la revisión
anterior. Los planes oficiales, perfiles y evidencia detallada se guardan en el
entorno privado, fuera de Git público. No colocar allí soluciones de entrenamiento
estudiantiles ni publicar semillas o respuestas futuras.
