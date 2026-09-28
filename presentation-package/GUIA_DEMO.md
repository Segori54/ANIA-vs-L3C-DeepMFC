# Demo guiada de AFC en tiempo real

Duración objetivo: 2 min 35 s. El efecto audible se reproduce desde archivos locales; no se provoca howling acústico durante la exposición.

## Preparación (antes de presentar)

1. Abrir `AFC_Tesis_Pitch.pptx` y comprobar que las notas del presentador estén visibles.
2. Abrir la aplicación `RealtimeFeedbackEngine` con ASIO, 48 kHz, entrada y salida mono.
3. Abrir la carpeta `demo/audio_ab` en un reproductor que no aplique normalización automática.
4. Dejar visibles `demo/respaldo/captura_telemetria.png` y `demo/evidencia/figura_resultados_preliminares.png`.
5. Mantener el volumen de reproducción fijo. Los cuatro audios ya están igualados a -20 dBFS RMS, con techo de pico de -1 dBFS.

## Guion cronometrado

| Tiempo | Acción | Frase sugerida |
|---|---|---|
| 0:00-0:20 | Mostrar la aplicación | "La plataforma opera a 48 kHz y conserva internamente la referencia enviada al parlante." |
| 0:20-0:45 | Recorrer `Bypass`, `Calibration`, `Cancelling` y `Recalibration` | "La calibración estima el camino acústico; en operación normal el FIR queda congelado." |
| 0:45-1:00 | Mostrar telemetría p50/p95/p99 | "Estos percentiles permiten verificar si el callback cumple su presupuesto; la campaña de Raspberry Pi aún está pendiente." |
| 1:00-1:15 | Reproducir `01_objetivo.wav` | "Esta es la referencia de lazo abierto." |
| 1:15-1:30 | Reproducir `02_sin_procesamiento.wav` | "Aquí aparece la coloración producida por el lazo sin cancelación." |
| 1:30-1:45 | Reproducir `03_patel_calibracion_manual.wav` | "Con el camino calibrado, el feedback residual disminuye." |
| 1:45-2:05 | Reproducir `04_patel_cambio_de_camino.wav` | "Un cambio abrupto degrada la estimación y activa la necesidad de recuperación." |
| 2:05-2:25 | Mostrar la figura preliminar | "Es una condición determinista de simulación: demuestra factibilidad, no una conclusión científica." |
| 2:25-2:35 | Cerrar con MLP, GRU y DeepMFC | "Los modelos están definidos y se entrenarán bajo el mismo protocolo; todavía no se les atribuyen resultados." |

## Contingencia

- Si ASIO o la interfaz fallan, mostrar `demo/respaldo/captura_telemetria.png` y continuar con los audios locales.
- Si el reproductor falla, usar la lámina 6 y explicar las cuatro pistas sin reproducirlas.
- No habilitar recalibración acústica automática en una sala con público.
- No cambiar el volumen entre A y B.

## Qué puede afirmarse

- Implementado y verificado: simulador, configuración por semilla, exportación de evidencia, aplicación JUCE/ASIO, estados y telemetría.
- Implementado pero pendiente de campaña: reproducción cerrada de Patel, detector y paridad numérica Python-C++.
- Futuro dependiente de recursos: datasets, entrenamiento ML, ONNX ARM64 y medición continua en Raspberry Pi 4.
