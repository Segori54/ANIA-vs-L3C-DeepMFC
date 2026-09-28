# Comparación 16 y 48 kHz

| Condición | Aprobados 16 kHz | Aprobados 48 kHz | Δ predicción dB (48−16), media |
|---|---:|---:|---:|
| simple | 5/5 | 5/5 | 0.0079 |
| reflections | 5/5 | 5/5 | 0.0073 |
| reverberant | 5/5 | 5/5 | 0.0138 |
| weak_onset | 5/5 | 5/5 | 0.0065 |
| noise40 | 5/5 | 5/5 | 0.0070 |
| noise20 | 5/5 | 5/5 | 0.0029 |
| no_return | 5/5 | 5/5 | N/A |
| clipped | 5/5 | 5/5 | N/A |
| nonfinite | 5/5 | 5/5 | N/A |
| short160 | 5/5 | 5/5 | -0.0136 |

## Interpretación y límites

Aprobado significa acuerdo numérico y controles sintéticos definidos, no validación acústica.
Los errores respecto del camino verdadero se conservan separados del acuerdo Python/C++.
Las diferencias entre tasas son descriptivas: se comparan realizaciones independientes y
discretizaciones de un mismo diseño temporal. No se exige igualdad tap a tap.
Banda común: 100–7000 Hz; magnitudes y fases completas en frequencies/.
El margen de inicio del Engine conserva 32 muestras: 2 ms a 16 kHz y 0.667 ms a 48 kHz.
La ventana FIR es 683/16000 = 42.6875 ms y 2048/48000 = 42.6667 ms.
Pendiente: exportación en vivo, dispositivo a ambas tasas, estabilidad, calidad de voz,
plazos del callback y detector/recalibración automática. Los tiempos medidos aquí son offline.

## Ejecuciones utilizadas

- 16000 Hz: 20260924T191744.474334Z_1b8bd408; matemáticas: 25; aprobado: True.
- 48000 Hz: 20260924T191756.727872Z_8f2cbe35; matemáticas: 25; aprobado: True.
