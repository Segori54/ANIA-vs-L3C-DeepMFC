# ANIA-vs-L3C-DeepMFC

Comparación de ANIA y L3C-DeepMFC para cancelación de realimentación acústica en tiempo real.

Este repositorio reúne la metodología, implementaciones y evidencia de una tesis
sobre **cancelación de realimentación acústica (AFC)** en un lazo
micrófono–procesador–parlante. La aplicación JUCE es el banco experimental de la
tesis; la comparación científica es el objetivo del proyecto.

El método clásico es el **Adaptive Noise Injection Algorithm de Patel y Panahi,
abreviado ANIA en esta tesis**. Esta abreviatura se adopta a partir del título del
[artículo](https://pmc.ncbi.nlm.nih.gov/articles/PMC7545262/); no se atribuye a los
autores como sigla oficial. El artículo también describe la técnica como
*Adaptive Short-duration Noise Injection*, origen de la etiqueta ASNI usada antes.

El segundo método de la comparación es **L3C-DeepMFC**. Su implementación fiel,
entrenamiento e integración para la comparación final siguen pendientes. Los
candidatos neuronales exploratorios existentes no se presentan como una
implementación validada de L3C-DeepMFC. El nombre del repositorio identifica el
objetivo de la tesis, no una comparación ya terminada ni una reproducción completa
del control automático de ANIA.

## Objetivo y preguntas de investigación

Comparar ANIA, basado en identificación del camino acústico, con
L3C-DeepMFC, considerando conjuntamente:

- ganancia adicional estable antes del acople;
- calidad de voz/audio y distorsión introducida;
- robustez frente a cambios del camino acústico;
- coste computacional, latencia y cumplimiento del plazo de procesamiento;
- viabilidad de ejecución en PC y, posteriormente, Raspberry Pi 4.

La selección de parámetros y modelos debe realizarse con datos de entrenamiento
y validación separados; las grabaciones propias se reservan para evaluación
externa. Las simulaciones, la equivalencia numérica y las mediciones físicas se
reportan por separado. No se declara todavía superioridad de ningún método.

## Avance al 28 de septiembre de 2026

| Línea de trabajo | Avance demostrado | Pendiente |
|---|---|---|
| Núcleo Patel | Estimador C++, calibración manual, validación con segunda sonda y FIR fijo durante cancelación | Control automático completo del artículo |
| Referencia independiente | Python float64 y comparación con C++ a 16/48 kHz; 50 casos de campaña y 25 matemáticos aprobados por tasa | Capturas del montaje real |
| Banco de audio | Ganancia, sondas, monitorización y exportación reproducible | Estabilidad acústica y calidad en hardware |
| Captura y auditoría | 12 sesiones sintéticas completas aprobadas; dos incompletas rechazadas; replay causal y hashes | Primera campaña física con este exportador |
| Aprendizaje profundo | Laboratorio y candidatos MLP, GRU causal y variante compacta inspirada en DeepMFC | Implementación fiel de L3C-DeepMFC, corpus, entrenamiento e integración C++ |
| Plataforma embebida | Guía de compilación y protocolo | Mediciones sostenidas en Raspberry Pi 4 |

La última verificación del banco y la referencia aprobó **5 pruebas C++ y 17
Python**. El ensayo sintético del callback completo registró cero asignaciones
de memoria instrumentadas y cero incumplimientos de plazo. Estos resultados no
certifican latencia acústica, calidad perceptual ni ausencia de fallos del hardware.

## Organización y evidencia

- [Estado y próximos hitos](IMPLEMENTATION_STATUS.md): progreso y criterios de cierre.
- [Laboratorio de investigación](research/README.md): simulación, métricas, particiones y candidatos neuronales.
- [Referencia ANIA de Patel](Referencia%20ASNI%20AFC%20Patel/README.md): oráculo independiente, campañas y auditoría.
- [Banco experimental](RealtimeFeedbackEngine/README.md): construcción y operación del Engine.
- [Primera sesión física](RealtimeFeedbackEngine/docs/CAPTURA_SESIONES.md): protocolo y límites.
- [Comparación sintética 16/48 kHz](Referencia%20ASNI%20AFC%20Patel/resumen_comparacion/20260924T192214.107788Z_344703b0/informe.md).
- [Integración de captura y tiempos](Referencia%20ASNI%20AFC%20Patel/resumen_comparacion/captura_integracion_20260928.md).
- [Presentación de la tesis](presentation-package/README.md): material preliminar.

Los informes fechados conservan el estado de su ejecución; los README y el estado
de implementación describen el avance actual. Se versionan fuentes, configuraciones,
pruebas e informes seleccionados. Compilaciones, dependencias descargadas, temporales,
capturas completas y modelos generados se conservan localmente y se regeneran con
los comandos documentados. Las grabaciones de micrófono no se agregan a Git por defecto.

## Reproducir el banco de validación

Requiere Windows, CMake 3.22+, Visual Studio Build Tools, Python 3.10+ y NumPy.
JUCE 8.0.10 se descarga al configurar; el SDK ASIO está incluido.

```powershell
cmake -S RealtimeFeedbackEngine -B build -G "Visual Studio 18 2026" -A x64
cmake --build build --config Release --parallel 4
ctest --test-dir build -C Release --output-on-failure
```

Con Visual Studio 2022 usar `Visual Studio 17 2022`. CTest genera las sesiones
sintéticas necesarias para las pruebas Python de auditoría. Seguir después el
README de la referencia para compilar su comparador y ejecutar las campañas.

El siguiente hito es capturar el mismo montaje físico a 16 y 48 kHz, auditarlo y
medir estabilidad y calidad. La detección validada de howling y la recalibración
automática permanecen fuera de la etapa actual; calibrar sigue siendo una acción manual.
