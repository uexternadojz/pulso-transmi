# Primer corte observable para el Proyecto 1

**Decisión docente del 25 de septiembre de 2026.** El primer corte comienza el
**24 de septiembre de 2026 a las 00:00 America/Bogota**
(`2026-09-24T05:00:00Z`). Es un inicio fijo, no una ventana móvil. La primera
semana sirvió para aprender a conectar el portal, obtener la API key y operar
submissions. Desde este instante las ausencias en ciclos elegibles afectan los
indicadores que servirán de evidencia para la nota del Proyecto 1.

## Qué muestra el leaderboard del Corte 1

El tablero se actualiza con los **ciclos oficiales resueltos** cuyo `opens_at` es
igual o posterior al inicio del corte. Los ciclos abiertos, cerrados sin resolver,
cancelados y anteriores al corte no entran. El escenario fijado es
`official-20260921`; futuros escenarios no alteran este corte. Todos los estudiantes elegibles de la
cohorte aparecen, incluso si todavía no tienen entrega. Cada fila muestra:

- accuracy del corte, calculada por estación como
  `100 × promedio_estaciones(max(0, 1 - suma_error_absoluto / max(1, suma_real)))`;
- cobertura de targets del mismo período: entregados / esperados;
- ciclos con submission oficial / ciclos resueltos desde el corte;
- hora de la última entrega dentro del corte y posición del leaderboard.

El scoring ya registra cada target no entregado como predicción cero. Por ello,
quien no haya entregado desde el inicio del corte aparece con **0 % de accuracy,
0 % de cobertura y 0/N ciclos entregados** una vez existan ciclos resueltos.
Reintentos del mismo ciclo no suman ciclos adicionales: cuenta el intento oficial
de `competition.cycle_entries`. Un recibo aceptado pendiente de evaluación aún
no altera la accuracy. El tablero no calcula porcentajes promediando snapshots
anteriores; reconstruye el WAPE desde los componentes inmutables de los ciclos
seleccionados.

Este tablero es **evidencia académica provisional**, no una nota publicada. La
rúbrica vigente de MLOps 2026-II en Academy asigna **20 % de la materia al
Proyecto 1 — Automatización de pipelines**, en escala de 0 a 5. El peso de este
primer corte *dentro* del Proyecto 1, la conversión de métricas a nota y las
excepciones justificadas todavía requieren decisión docente explícita. Hasta
entonces no se escribe ninguna calificación en Academy ni se anuncia una nota
numérica basada solo en el leaderboard. El orden competitivo tampoco equivale a
una nota.

Antes de cerrar una nota oficial se debe fijar el **fin del corte** y conservar
un snapshot reproducible con instante de consulta, ciclos incluidos, métricas por
estudiante, versión de la regla y revisión de matrícula/excepciones. Si alguien
aplazó el semestre, se verifica la situación académica antes de aplicar una
penalización individual; el listado técnico de participantes no decide eso.

## Relación con drift

Julián prevé comenzar la fase de drift la noche del 25 de septiembre. El Corte 1
conserva su inicio aunque cambie el régimen de datos. El escenario oficial usa
un bundle de futuro precomputado y congelado: activar o cambiar drift requiere
documentar el evento y su hora efectiva, validar el mecanismo vigente y preservar
la auditabilidad de los ciclos anteriores. No se reescribe ground truth ni se
recalifican retroactivamente entregas por el solo hecho de comenzar esta fase.
Una comparación pedagógica antes/después del drift debe fijar ventanas separadas
y mostrar cobertura junto a accuracy.

## Verificación del tablero

`GET /v1/portal/first-cutoff` usa la sesión del portal y devuelve `starts_at`,
`as_of`, `resolved_cycles` y las 32 filas de la cohorte con accuracy, cobertura,
ciclos y última entrega. No incluye documentos, correos, llaves ni predicciones
individuales. La carrera acumulada y los totales del Sprint ahora empiezan en
el mismo instante fijo. Los datos anteriores permanecen almacenados para
auditoría, pero no entran en estas métricas visibles.
