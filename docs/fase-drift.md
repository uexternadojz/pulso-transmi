# Fase de adaptación a cambios de demanda

La continuación se habilita con dificultad controlada y conserva el corte vigente.
El cierre está configurado para el viernes **2 de octubre de 2026 a las 23:59,
hora de Bogotá**. La API determina los ciclos abiertos y su plazo individual;
los últimos se abren con tiempo suficiente para evaluarse antes del cierre.

## Objetivo académico

Operar un sistema de predicción que observe sus resultados, detecte cambios,
evalúe nuevas versiones y mantenga entregas trazables. La demanda puede cambiar
de nivel, distribución horaria o relación entre estaciones. El desempeño puede
variar aunque el programa siga ejecutándose correctamente.

Cada estudiante debe diseñar y justificar su estrategia de monitoreo,
entrenamiento y selección de modelos. No se prescribe algoritmo, ventana de
entrenamiento, umbral de alerta ni política de promoción.

## Contrato que conserva el pipeline

- Consultar el ciclo vigente y respetar sus targets, corte y ventana de entrega.
- Usar únicamente observaciones disponibles hasta el corte de ese ciclo.
- Mantener las credenciales protegidas y los reintentos idempotentes.
- Conservar recibos, versiones y evidencia de las decisiones del pipeline.
- Interpretar accuracy junto con cobertura: una entrega ausente también afecta
  el resultado. Una submission aceptada puede seguir pendiente de evaluación.

Los niveles internos de dificultad pueden ajustarse para la cohorte. Todos
reciben la misma demanda para una estación y un timestamp. Un ajuste no cambia
observaciones publicadas, targets de ciclos ya abiertos ni notas retroactivamente.
No se publican parámetros privados, estaciones afectadas, semillas ni respuestas
futuras. La API vigente, no este documento, determina cuándo se puede entregar.

## Evidencia para la entrega del proyecto

El repositorio del estudiante debe permitir explicar:

1. Cómo verifica la continuidad de la ingesta y de las submissions.
2. Cómo diferencia problemas operativos de cambios en la demanda.
3. Qué dispara una evaluación o un nuevo entrenamiento y qué datos utiliza.
4. Cómo compara versiones temporalmente sin utilizar información futura.
5. Qué evidencia respalda mantener, promover o retirar una versión.
6. Qué ocurrió antes, durante y después de un cambio observado.

La evidencia puede incluir ejecuciones, recibos, métricas, versiones y decisiones
registradas. No basta con cambiar el nombre del modelo en cada submission.
El ranking aporta evidencia; no equivale automáticamente a una calificación.
El peso del corte y la conversión a nota siguen pendientes de definición docente.

## Disponibilidad

El escenario original agotó su horizonte el 28 de septiembre. Durante el intervalo
sin ciclos abiertos no existen nuevas entregas exigibles ni ausencias que
penalizar. La continuación conserva el histórico y el inicio del corte
del 25 de septiembre a las 00:00, hora de Bogotá.

El esquema técnico de control se describe en
[Control versionado de drift](drift-control.md). Su ejemplo es ficticio y no
representa la programación del ejercicio.
