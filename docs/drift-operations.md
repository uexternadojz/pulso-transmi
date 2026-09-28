# Operación de la ventana de drift · 0.8.0

La continuación utiliza el escenario vigente y conserva el corte del 25 de
septiembre. El cierre real se fija para el 2 de octubre de 2026 a las 23:59
America/Bogota. No se abre un ciclo si faltan menos de 65 minutos para ese cierre;
los ciclos admitidos se terminan de evaluar. El reloj se completa en el tick
posterior al cierre, sin inventar ciclos por el intervalo de interrupción.

## Componentes implementados

- `app.drift_admin`: valida e importa un bundle privado de continuación en una
  transacción con el mismo advisory lock del scheduler.
- `sim.drift_revisions`: artefacto completo, hash, padre, nivel, motivo,
  calibración y fechas. Las revisiones son inmutables.
- `competition.drift_windows`: ventana virtual y cierre real; revisión vigente.
- Cada ciclo guarda `drift_revision_id`; abrirlo requiere sus 48 valores futuros.
- Un trigger protege el ground truth publicado o comprometido. Las sustituciones
  solo alcanzan el sufijo futuro disponible; su versión previa sigue en el
  artefacto inmutable. Los scores históricos no se reescriben.
- `/v1/portal/drift-monitor`: vista exclusiva para una identidad con `kind=admin`.
  Compara fase, últimos seis ciclos y seis ciclos previos a la fase, junto con
  cobertura, revisiones y salud. No devuelve respuestas futuras ni parámetros.
- El Home docente muestra el observatorio. La comparación en puntos solo se
  presenta con seis ciclos nuevos y al menos 95 % de cobertura en ambas ventanas.
  La ausencia de comparabilidad no equivale a falta de drift.
- `python -m app.drift_observe`: snapshot administrativo de solo lectura para
  comprobaciones operativas y seguimiento. No cambia la dificultad.

## Activación

Crear y verificar un backup antes de la migración `010_controlled_drift.sql`.
Ensayar en una restauración aislada: importación, idempotencia, conservación del
histórico, revisión posterior, scoring parcial/completo, autorización y cierre.
Construir y desplegar la misma imagen verificada para API y scheduler.

El generador y los perfiles se ejecutan en el entorno privado. Se conserva código,
fuente de datos, dependencias, semilla, hashes y evidencia de calibración. La
continuación v1 fue reconstruida a partir de historia ya revelada; no depende de
la antigua carpeta temporal. Los archivos privados se respaldan en el VPS y no
se incluyen en la imagen pública de API/scheduler.

```bash
# Validar sin escribir (ruta de ejemplo; usar el artefacto privado aprobado).
python -m app.drift_admin validate --bundle /private/continuation.json

# En el servicio administrativo provisionado; obtener el reloj de la BD primero.
python -m app.drift_admin apply \
  --bundle /private/continuation.json \
  --expected-clock '<reloj virtual verificado>' \
  --wall-end '2026-10-02T23:59:00-05:00'
```

La activación inicial requiere reloj completado y abre inmediatamente un ciclo
con una ventana completa de 25 minutos. La revisión se rechaza si cambió el reloj,
no coincide el padre, hay huecos en la grilla o se invaden targets comprometidos.
El mismo hash se procesa idempotentemente. La configuración exacta del perfil no
se incorpora al README ni a ejemplos públicos.

## Cambiar dificultad

1. Consultar observatorio, reloj, último horizonte comprometido y hash vigente.
2. Generar privadamente una nueva continuación de nivel 0–3 que comience en la
   frontera protegida y conserve el fin virtual. Mantener el perfil base y las
   innovaciones aleatorias; transicionar desde el estado anterior.
3. Calibrar causalmente los cuatro horizontes con referencias fijas, referencias
   con features recientes y adaptativas. Guardar los resultados medidos y hashes.
   No prometer una pérdida idéntica para modelos estudiantiles diferentes.
4. Incrementar revisión y referenciar el hash del bundle previo. Validar y aplicar
   con el reloj verificado. Si el reloj avanza durante la preparación, volver a
   verificar la frontera: no forzar la revisión ni modificar el pasado.
5. Comprobar revisión de los nuevos ciclos, heartbeat y continuidad de entregas.

Mantener el nivel no requiere escribir otra revisión. Bajar el nivel modifica
únicamente objetivos futuros. No existe escalada automática de dificultad en
esta versión; las alertas ayudan a la decisión docente. Las bandas exactas y
estaciones permanecen privadas para preservar el ejercicio.

## Observación y alertas

El observatorio se refresca con el Home. Marca heartbeat mayor a 120 segundos,
reloj sin avanzar más de 40 minutos, errores de evaluación y baja cobertura.
Después de seis ciclos compara el cambio de accuracy solo entre participantes
con cobertura suficiente; una caída general requiere revisión docente.

Durante las primeras horas, los valores de la fase aparecen pendientes hasta
que existan ciclos resueltos. Conservar métricas antes/después por revisión y por
estación al investigar incidentes; el acumulado general permanece desde el corte.
La bitácora docente debe registrar el motivo de todo cambio de nivel.

## Recuperación

Conservar el backup previo y los artefactos de todas las revisiones. Si un bundle
futuro falla antes de abrirse ciclos, la transacción se revierte. Si falta verdad,
el tick falla antes de publicar y registra el error. No restaurar un backup sobre
entregas nuevas: investigar y corregir con una continuación válida.

La pausa administrativa antigua no es una pausa de drenaje; no emplearla para
interrumpir ciclos comprometidos. Esta versión implementa drenaje para el cierre
real de la ventana, no un botón general de pausa docente.
