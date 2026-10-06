# Cierre y versión privada de los datos — Proyecto 1, 2026-II

La recepción terminó el 4 de octubre de 2026 a las 23:59 America/Bogota.
Los 30 ciclos de la fase final quedaron resueltos; el último tick de drenaje
terminó el 5 de octubre a las 00:22 Bogotá. El corte académico del 25 de
septiembre permanece intacto; esta fase no reemplaza su acumulado.

## Bloqueo y consulta

- `SUBMISSIONS_ENABLED=false` deshabilita `POST /v1/submissions`, incluida su
  variante con slash final, antes de autenticar, validar o contar intentos.
- La respuesta es `410` con código `competition_closed`, sin guardar una entrega.
- Dashboard, histórico, rankings y recibos mantienen su acceso habitual.
- El scheduler se detiene mediante `sudo -n docker compose stop scheduler` una
  vez comprobado el reloj `completed` y cero ciclos abiertos o pendientes.
- Cambiar la variable o reactivar un escenario requiere una nueva decisión del
  docente. Reiniciar el API conserva el bloqueo definido en `.env`.

## Archivo reproducible (privado)

Con el bloqueo desplegado y el scheduler detenido, ejecutar en el VPS:

```bash
bash tools/archive-competition.sh
```

Cada ejecución crea una versión nueva en `private/archives/closeout-<UTC>/`:

- `database.dump`: snapshot consistente completo de PostgreSQL, incluyendo
  simulación privada, matrícula, entregas, scoring y auditoría.
- `schema.sql`: esquema y permisos del snapshot.
- CSV de observaciones, ciclos, targets, submissions, predicciones y entradas.
- `results.json`: ranking desde el corte académico y observatorio de fase final
  con accuracy acumulada, últimos seis y cobertura. Son evidencias, no notas.
- `source.bundle`, bundles privados y starter: código y generación asociados.
- `manifest.json` y `SHA256SUMS`: versión, commit, cierre, conteos y hashes.

Los archivos contienen datos personales y simulación privada. Permanecen fuera
del Git público, con permisos restrictivos. Conservar una copia fuera del VPS.
Para validar, comprobar hashes y restaurar `database.dump` en una base temporal
con `pg_restore --no-owner --no-privileges`, usando el administrador provisionado;
comparar conteos y estado de ciclos con el manifiesto. El dump original conserva
propietarios y grants para una recuperación completa con roles provisionados.
Nunca restaurar sobre la base operativa para probar el respaldo.

La conversión a notas y su peso siguen pendientes de definición docente.

## Versión de cierre verificada

Archivo `closeout-20261006T002135Z`, creado el 5 de octubre a las 19:21 Bogotá,
con código `47bbc95`. Conserva 302 ciclos históricos, 215 ciclos resueltos desde
el corte académico, 6.837 submissions, 327.492 predicciones, 6.127 entradas
oficiales y 14.460 observaciones de competencia. La fase final conserva sus
30 ciclos resueltos. Los datos del starter se archivan por separado.

La restauración completa en una base temporal terminó correctamente; los
conteos de las seis tablas exportadas coinciden con el manifiesto. La base
temporal se eliminó después de la comprobación. La evidencia privada está en
`RESTORE-VERIFIED.txt` y `restoration-counts.json`.

Ubicaciones privadas:

- VPS: `/opt/pulso-transmi/private/archives/closeout-20261006T002135Z/`.
- Copia fuera del VPS: `~/.local/state/pulso-transmi/archives/closeout-20261006T002135Z/`.

El bloqueo fue verificado tanto por localhost como por la URL pública: `410`.
API y PostgreSQL permanecen saludables; scheduler detenido explícitamente.
