# Primera predicción oficial

La ronda de práctica terminó. El mismo cliente descubre ahora el ciclo oficial,
consume observaciones nuevas y envía una predicción que sí entra al scoring.

## Objetivo

Cada estudiante debe conseguir un recibo `accepted` con todos los targets que
devuelva `/v1/forecast-cycles/current`. Un ciclo oficial normal contiene 48
valores: 12 estaciones por cuatro horizontes de 15, 30, 45 y 60 minutos.

## Ejecución rápida

```bash
git clone https://github.com/uexternadojz/pulso-transmi.git
cd pulso-transmi
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-student.txt
export PULSO_API_KEY="ptm_live_..."
python examples/first_prediction.py
```

En Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-student.txt
$env:PULSO_API_KEY="ptm_live_..."
python examples/first_prediction.py
```

El ejemplo verifica la identidad, descubre el ciclo, entrena un Random Forest
con rezagos y variables temporales, y envía el payload con una
`Idempotency-Key` nueva.

Salida esperada:

```text
Estudiante: Nombre Apellido
Entrega: sub_...
Estado: accepted
Predicciones: 48/48
```

## Errores frecuentes

- `401 invalid_api_key`: la variable no existe, tiene espacios o la llave fue revocada.
- `404 no_open_cycle`: no hay ventana abierta en ese instante; vuelve a consultar
  en la siguiente ejecución programada.
- `409 attempt_limit_reached`: ya se usaron los tres intentos del ciclo.
- `422 invalid_target_set`: faltan objetivos, sobran o se alteró un timestamp.

No copies nombres de estaciones ni fechas desde esta guía para construir el
payload. El cliente siempre debe tomar el target set de la API.
