# Calificación individual de desempeño — Proyecto 1

## Criterio autorizado por el docente

- Fuente congelada: `closeout-20261006T002135Z`, 215 ciclos desde el 25 de
  septiembre a las 00:00 Bogotá hasta el cierre del 4 de octubre de 2026.
- Quien participó recibe una nota entre 2,00 y 5,00:
  `2 + 3 × (accuracy − mínimo) / (máximo − mínimo)`.
- Mínimo y máximo se toman únicamente de quienes tienen entregas oficiales.
  Se usan valores completos, redondeando la nota a dos decimales; resultados
  cercanos pueden compartir nota redondeada.
- Cero submissions: 0,00 por no presentar, autorizado el 6 de octubre.
- Las ausencias ya cuentan como predicción cero; no se penalizan nuevamente.
- Los últimos seis ciclos sirven para explicar recuperación o interrupción,
  sin sustituir el acumulado ni probar por sí solos reentrenamiento automático.
- Esta es la calificación de desempeño competitivo. No registra ni sustituye
  automáticamente la evaluación técnica del repositorio o la nota de la materia.

## Privacidad y trazabilidad

`GET /v1/portal/grade` exige sesión vigente y devuelve una sola calificación.
El participante se resuelve desde la cookie autenticada, nunca desde una URL,
query string, nombre o body. No hay endpoint de listado de notas.

La tabla `competition.student_grades` tiene RLS: el rol API solo puede leer el
participante establecido por el servidor dentro de la transacción local. La
consulta además filtra identidad, cohorte y tipo estudiante. El API no puede
insertar ni actualizar notas; el scheduler no tiene acceso. La respuesta usa
`Cache-Control: no-store`; el frontend limpia la nota al cerrar o perder sesión.
Los rankings y respuestas públicas no contienen notas.

El docente revisa un bundle privado con nota, evidencia y explicación para cada
estudiante. Su publicación atómica usa `python -m app.grade_admin --file ...`
mediante el perfil ops. Cada publicación tiene versión, hash del snapshot y
registro de auditoría. El importador rechaza reemplazar una versión existente.
Una corrección se publica como nueva versión. El bundle, nombres, mensajes y
notas permanecen fuera del Git público.

## Publicación verificada — 6 de octubre de 2026

Versión `performance-v1-20261006`: 32 registros, 28 notas escaladas de 2,00 a
5,00 y cuatro ceros por no presentar. Cada explicación fue revisada con sus
entregas, cobertura, acumulado y últimos seis ciclos finales. No se escribieron
notas oficiales en el LMS de Academy.

Verificación: 71 pruebas automatizadas; consulta HTTP con las 32 sesiones de
estudiantes; intento de consultar otro participante mediante query string;
respuesta privada con `no-store`; RLS sin filtro de sesión devuelve cero filas,
y con identidad establecida devuelve una sola fila propia. Las sesiones de QA
se revocaron al terminar. Los conteos del cierre permanecen en 6.837 submissions
y 327.492 predicciones. La cuenta docente no recibe notas ajenas en este módulo.

El bundle y la revisión individual del docente se conservan en el directorio
privado `grading-performance-v1-20261006`, fuera del repositorio público.
