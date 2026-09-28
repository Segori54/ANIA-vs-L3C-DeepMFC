# Estado de la tesis — 28 de septiembre de 2026

## Objetivo

Comparar ANIA y L3C-DeepMFC para audio en vivo con evidencia
de ganancia estable, calidad, robustez y coste de ejecución. No se ha completado
todavía la comparación final entre métodos ni validado la implementación de L3C-DeepMFC.

## Implementado

- Laboratorio Python de simulación, cambios de camino, barridos y métricas.
- Particiones deterministas por identidad y adaptadores para métricas externas.
- Candidatos MLP, GRU causal y variante compacta inspirada en DeepMFC, con herramientas
  de entrenamiento y exportación ONNX; disponer del código no equivale a entrenarlos.
- Banco C++/JUCE mono: identificación por correlaciones Toeplitz regularizadas,
  validación independiente y cancelación mediante FIR fijo con retardo separado.
- Ganancia digital, ruido blanco/rosa, protección, monitorización y observaciones.
- Selección 16/48 kHz y exportación de audio, modelos y cronología de sesiones.
- Referencia NumPy independiente y auditoría causal de las señales exportadas.

El laboratorio Python histórico usa otro estimador y no es el oráculo del C++.
La paridad numérica se evalúa con la carpeta independiente Referencia ASNI AFC Patel.
El detector tonal existente es experimental; no activa recalibración automática.

## Evidencia obtenida

- Campaña independiente: 50 casos y 25 pruebas matemáticas por tasa, aprobados a
  16 y 48 kHz bajo los criterios establecidos. Incluye controles de rechazo.
- Última verificación del banco: 5/5 pruebas C++ y 17/17 Python aprobadas.
- Laboratorio de investigación: 6/6 pruebas básicas aprobadas el 28 de septiembre;
  esta suite no entrena ni evalúa los candidatos neuronales definitivos.
- Captura: 12 sesiones sintéticas completas aprobadas por el auditor y dos fallos
  inyectados correctamente marcados como incompletos. Se incluyen cambios de modelo,
  historial inicial, cancelaciones, rechazos y continuidad entre segmentos.
- Callback completo sintético: cero asignaciones instrumentadas y cero plazos
  incumplidos. Percentiles y límites en el informe de integración del 28 de septiembre.

Esta evidencia demuestra corrección numérica e integración sintética dentro del
alcance probado. No demuestra reproducción del algoritmo automático completo del
paper, ganancia acústica adicional, calidad perceptual ni desempeño sostenido en Pi.

## Próximos hitos y criterios de cierre

1. **Sesiones físicas a 16/48 kHz:** registrar geometría y ganancias físicas, comprobar
   frecuencia/búfer efectivos, capturar y obtener auditorías íntegras. Documentar
   incompatibilidad si el dispositivo no admite alguna tasa; no remuestrear a escondidas.
2. **Evaluación acústica clásica:** medir umbral de acople, calidad y tiempos bajo un
   protocolo repetible; distinguir saturación, inestabilidad y fallos de captura.
3. **Corpus y modelo aprendido:** obtener/licenciar datos, congelar particiones y
   parámetros usando validación; implementar y entrenar L3C-DeepMFC, usando los
   candidatos exploratorios como apoyo sin confundirlos con el método objetivo.
4. **Comparación justa:** integrar el modelo seleccionado, aplicar los mismos ensayos
   y reportar variantes independiente/residual, si se evalúan, de forma diferenciada.
5. **Tiempo real embebido:** construir para Pi 4 y medir sostenidamente con bloques de
   64/128/256 muestras; no extrapolar resultados del PC como mediciones de la Pi.
6. **Control automático posterior:** validar detección de howling antes de conectarla
   a recalibración. Mantener control explícito de las inyecciones audibles.

STOI/ESTOI, PESQ y ViSQOL requieren sus dependencias y datos adecuados; sus
adaptadores no constituyen resultados experimentales. Las sesiones físicas
exportadas, el entrenamiento definitivo y las tablas finales permanecen pendientes.
