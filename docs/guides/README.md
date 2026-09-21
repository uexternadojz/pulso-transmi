# Guías para estudiantes

## Guía operativa v2.0

Publicada el 21 de septiembre de 2026 para explicar el ciclo oficial de
submissions y su automatización:

- [Descargar la guía operativa v2.0](pulso-transmi-guia-operativa-v2.0.pdf)
- [Consultar la fuente en Markdown](pulso-transmi-guia-operativa-v2.0.md)
- [Ver lámina del reloj operativo](assets-v2/reloj-submission.png)
- [Ver lámina del loop de GitHub Actions](assets-v2/github-actions-loop.png)
- SHA-256: `1dac0ea6cccc640b2595d46ff9a7c2bf3771447539c8fa383c96852c3b884b72`
- Formato: PDF A4, 11 páginas.
- Estado: versión académica compartible.

La guía aclara el reloj horario, el batch de 48 predicciones, el workflow de
GitHub Actions cada 10 minutos, el uso de idempotencia, la separación entre
inferencia y entrenamiento, los errores esperables, el reentrenamiento y el bono
de dashboard en Vercel.

## Guía metodológica v1.0

La edición vigente es la **v1.0**, publicada el 16 de septiembre de 2026:

- [Descargar la guía metodológica v1.0](pulso-transmi-guia-metodologica-v1.0.pdf)
- SHA-256: `282e63f23800f75472e72908f53cba7d28ad93b9173c84411c37d4f109994370`
- Formato: PDF A4, 17 páginas.
- Estado: versión académica compartible.

### Alcance de la v1.0

La guía explica el propósito del reto, la arquitectura MLOps, el papel de Supabase,
GitHub Actions y Vercel, el ciclo de publicación y predicción, la forma de entregar
resultados, la evaluación progresiva, el drift, los entregables y los bonos.

Los payloads, comandos y contratos técnicos se mantienen en la documentación del
repositorio, especialmente en [`../api-contract.md`](../api-contract.md) y
[`../student-client.md`](../student-client.md).

## Política de versiones

- Las ediciones publicadas usan nombres inmutables `vMAJOR.MINOR` y no se sobrescriben.
- Un cambio de reglas, targets, métrica o calendario incrementa la versión y se anuncia
  explícitamente a los equipos.
- Las correcciones editoriales que no alteran el contrato se publican como una versión
  menor nueva para conservar trazabilidad.
