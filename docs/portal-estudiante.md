# Portal del estudiante

El portal reúne la activación de identidad, la API key, la ronda abierta, los
recibos y el leaderboard. Está disponible en:

`https://pulso-transmi.72-60-245-2.sslip.io/`

## Acceso

Ingresa el correo institucional y el número de documento que aparecen en la
lista oficial. Esos son los dos datos que verifican la identidad. La aplicación
normaliza mayúsculas del correo y puntuación del documento.

El campo de nombre es libre: puede contener el nombre preferido o la forma en que
quieres que el portal te salude. No interviene en la autenticación y no cambia el
nombre oficial que aparece en el tablero de la cohorte. Se conserva únicamente en
la sesión temporal del navegador.

La cédula viaja por HTTPS, no se registra en logs y se compara contra una firma
criptográfica; el VPS no necesita conservarla en texto legible.

Este acceso es una verificación académica simplificada para el reto. No es un
mecanismo apropiado para notas oficiales ni información de mayor sensibilidad.

## Obtener la API key

1. Presiona **Generar mi API key**.
2. Cópiala o descarga el archivo `.env`.
3. Guárdala en la variable `PULSO_API_KEY`.
4. No la publiques en commits, notebooks, capturas, logs o variables de frontend.

La llave completa se muestra una sola vez. El portal conserva únicamente el
prefijo y el servidor almacena el secreto con scrypt.

## Si perdiste la API key

1. Vuelve a entrar al portal con tu correo y documento.
2. En **Tu API key**, presiona **Generar una nueva API key**.
3. Confirma que entiendes que la llave anterior dejará de funcionar.
4. Copia o descarga la nueva credencial antes de recargar la página.
5. Actualiza inmediatamente `PULSO_API_KEY` en GitHub Actions y en cualquier
   entorno donde ejecutes el cliente.

La rotación ocurre en una sola transacción: revoca la credencial activa y crea
una nueva. El secreto anterior no puede recuperarse. El backend limita la
cantidad de emisiones por hora y registra el cambio sin guardar secretos legibles.

## Tablero

La carrera de accuracy aparece encima del benchmark operativo. **Acumulada**
recalcula el WAPE por estación desde el inicio del escenario; **Últimos 6 ciclos**
lo recalcula sobre los seis ciclos completamente resueltos más recientes en cada
punto. No es un promedio simple de porcentajes. La fórmula conserva las ausencias
como predicción cero y muestra cobertura y versiones de modelo en el detalle.
Una persona sin entregas evaluadas permanece en la leyenda sin una línea ficticia.

Los avatares permiten seleccionar una trayectoria; pulsar de nuevo restaura todas.
Las etapas corresponden a escenarios con resultados evaluados de la cohorte.
El selector conserva el histórico entre escenarios; no crea cortes ni resetea datos.
Los cortes adicionales dentro de un escenario requieren una definición posterior.
El endpoint autenticado es `GET /v1/portal/accuracy-chart`.

Debajo de la carrera se conserva el **Sprint de submissions**, un ranking operativo que
permite verificar quién ya conectó su pipeline y está entregando de forma
consistente. La ventana contiene los seis ciclos cerrados más recientes. Cada
punto marcado equivale a una entrega oficial aceptada; al enfocarlo o pasar el
cursor aparecen la hora, el modelo y el identificador del ciclo.

El orden usa, en este orden: entregas en la ventana, racha vigente, ciclos
oficiales totales y hora de la última entrega. Enviar varias veces al mismo ciclo
no suma puntos: únicamente cuenta la submission oficial registrada por el
servidor. Los 32 estudiantes aparecen al tiempo; quienes todavía no han enviado
se muestran como **Por iniciar** y aún no reciben una posición competitiva.

El ranking operativo mide continuidad, no calidad predictiva. La carrera superior
muestra accuracy calculada únicamente sobre ground truth revelado; sus valores
cambian con cada ciclo resuelto y deben interpretarse junto con la cobertura.
En la ventana móvil, quien ya no tiene envíos en los últimos seis ciclos conserva
su trayectoria histórica, pero la leyenda indica **Sin envíos en ventana**.

La cohorte puede ver nombres y estado académico del reto, pero nunca correos,
documentos, llaves, payloads o predicciones individuales.
