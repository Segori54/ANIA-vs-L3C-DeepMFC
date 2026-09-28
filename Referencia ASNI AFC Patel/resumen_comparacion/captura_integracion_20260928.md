# Verificación de captura — 28 septiembre 2026

Aplicación Release compilada. CTest: 5/5 aprobadas. Python unittest: 17/17 aprobadas.
Campaña: `build/session_capture_tests/4e1d1b78e2ab4f7c9c63d8664a12854e`.

La auditoría independiente aprobó las 12 sesiones sintéticas completas y rechazó
las dos incompletas generadas por desborde/error de disco. Se verificaron captura
con modelo existente e historial, cambios de modelo, calibraciones aceptadas,
rechazadas y canceladas, clipping, segmentos WAV y continuidad causal a ambas tasas.
El CLI también se ejecutó sobre sesiones a 16 y 48 kHz y sobre una sesión incompleta;
esta última devolvió código de salida 1, como corresponde.

## Callback completo: ensayo sintético

Tiempos en milisegundos, bloques de 128 muestras. Son tiempos de ejecución offline,
no latencia acústica ni certificación del dispositivo. Comparación con igual modelo,
fuente y ritmo de alimentación. La variabilidad del sistema afecta percentiles.

| Frecuencia | Captura | p50 | p95 | p99 | Máximo | Incumplimientos |
|---|---|---:|---:|---:|---:|---:|
| 16 kHz | Apagada | 0.0103 | 0.0879 | 0.1334 | 0.1334 | 0 |
| 16 kHz | Encendida | 0.0136 | 0.0525 | 0.1282 | 0.1282 | 0 |
| 48 kHz | Apagada | 0.0145 | 0.0826 | 0.0974 | 0.0974 | 0 |
| 48 kHz | Encendida | 0.0208 | 0.0890 | 0.1440 | 0.1440 | 0 |

Se detectaron cero asignaciones mediante la instrumentación de `operator new`
alrededor del callback completo. La captura utiliza colas preasignadas y atómicos
lock-free; archivos, hashes y serialización se procesan fuera del hilo de audio.

## Pendiente: ensayo físico

No se abrió un dispositivo de audio para estas pruebas. La desconexión y el error
de disco se simularon; queda probar su comportamiento con el hardware y destino
reales, confirmar frecuencia/búfer/latencias efectivos, revisar visualmente la GUI
y auditar las primeras capturas del montaje acústico. La detección de howling y la
recalibración automática siguen fuera de esta entrega.

Procedimiento: `RealtimeFeedbackEngine/docs/CAPTURA_SESIONES.md` en el workspace.
