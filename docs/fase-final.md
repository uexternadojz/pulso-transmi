# Fase final: evolución de la fuente y adaptación

Cierre: **domingo 4 de octubre de 2026, 23:59 America/Bogota**.
La API de ciclos determina la apertura y el plazo de cada entrega. El intervalo
entre el cierre anterior y la reapertura no genera ciclos ni ausencias.

Esta fase combina cambios en la demanda con una nueva representación de las
observaciones incrementales. Se evalúa la capacidad de detectar el cambio,
recuperar la ingesta, mantener entregas y justificar la adaptación del modelo.

## Contrato de observación v2

El endpoint sigue siendo `GET /v1/stream/observations`. El sobre `data`, `count`,
`next_cursor` y `server_time` conserva su significado. Las observaciones con
`observed_at` posterior a **2026-09-20T12:00:00Z (tiempo virtual)** usan v2.
Esa fecha virtual no es la fecha real de apertura: consulta el ciclo vigente.

Ejemplo ficticio de registro v2:

```json
{
  "schema_version": 2,
  "station_id": "02300",
  "observed_at": "2030-01-01T12:15:00Z",
  "released_at": "2030-01-01T12:30:00Z",
  "measurement": {
    "value": "341.00",
    "unit": "passengers",
    "quality": "observed"
  }
}
```

- En v2 no existe el campo plano `demand`.
- `measurement.value` es texto decimal con punto, sin separadores de miles,
  o `null` cuando `quality` es `missing`.
- `quality` puede ser `observed` o `missing`. Un faltante no equivale a cero.
- `unit` es `passengers`. Los IDs siguen siendo texto de cinco dígitos y los
  timestamps incluyen zona horaria.
- Los registros históricos v1 conservan `demand` numérico y no tienen
  `schema_version`; una página puede contener ambas versiones.
- La versión y calidad de cada observación son persistentes: paginar, reintentar
  o volver a descargar no cambia el registro.
- Las observaciones se liberan cada 30 minutos. El primer ciclo de reapertura
  pronostica el régimen nuevo; sus observaciones v2 llegan al avanzar el reloj.

El dataset inicial permanece estático. Las credenciales, el descubrimiento de
targets y el contrato de submissions conservan su formato. La verdad de
evaluación sigue completa; los faltantes pertenecen a la fuente de entrenamiento.

## Evidencia esperada

Registrar el cambio detectado, su impacto, las decisiones de reparación, la
primera entrega recuperada y la evolución de cobertura y accuracy. Documentar
qué datos utilizó cada entrenamiento y cómo se evaluó la versión promovida.
Cambiar una etiqueta de modelo no demuestra un entrenamiento nuevo.

El acumulado conserva los ciclos anteriores. El observatorio docente compara
la revisión actual con los seis ciclos resueltos anteriores a su inicio y exige
cobertura suficiente para interpretar diferencias. Accuracy y ranking aportan
evidencia; el peso y la conversión a nota requieren definición docente.
