# Referencia ANIA de Patel

**ANIA** significa Adaptive Noise Injection Algorithm de Patel y Panahi,
abreviado así en esta tesis. La carpeta conserva el nombre histórico
`Referencia ASNI AFC Patel` para mantener compatibles las rutas de capturas,
configuraciones y herramientas; ASNI procede de Adaptive Short-duration Noise
Injection, expresión también empleada en el artículo.

## Aporte a la tesis

Esta carpeta aporta evidencia independiente de la corrección del método clásico
antes de compararlo con L3C-DeepMFC. No entrena redes ni certifica estabilidad acústica.
La campaña consolidada del 24 de septiembre aprobó, por tasa, 50 casos sintéticos
y 25 pruebas matemáticas. El 28 de septiembre se verificó la exportación del Engine:
12 sesiones sintéticas completas aprobadas y dos incompletas rechazadas.
El próximo hito son las capturas físicas, no una declaración de superioridad del método.
Ver el [estado general de la tesis](../IMPLEMENTATION_STATUS.md).

Los informes consolidados se versionan como evidencia fechada. Capturas, modelos y
resultados por ejecución se generan localmente y no se incluyen en Git; los IDs
de informes históricos identifican esas ejecuciones, no garantizan su presencia en
un clon nuevo. Reproducir con `all` genera IDs nuevos y conserva resultados previos.
La suite de auditoría requiere generar primero sesiones con `SessionCaptureTest`.

La referencia también admite `python -m referencia audit-session --session RUTA`
para auditar sesiones exportadas por el Engine sin modificar los originales.
Las sesiones reales quedan en `16khz/sesiones_reales/` o `48khz/sesiones_reales/`;
los informes nuevos, en `resumen_comparacion/audit_<id>/`.
El procedimiento está en `../RealtimeFeedbackEngine/docs/CAPTURA_SESIONES.md`.
Antes de ejecutar toda la suite Python, compilar y ejecutar también el CTest
`SessionCaptureTest`, que genera las sesiones de integración requeridas.

Referencia matemática independiente del núcleo de identificación de ANIA de
Patel y Panahi (EMBC 2020), con comparación ejecutable contra el estimador C++
actual de RealtimeFeedbackEngine. No modifica el Engine ni importa el laboratorio
Python histórico. La campaña del estimador usa señales sintéticas. La exportación
de sesiones ya está integrada en el Engine; la validación con hardware real sigue pendiente.

## Preparar y ejecutar

Desde esta carpeta, con Python 3.10+ y NumPy:

```powershell
python -m pip install -r requirements.txt
cmake -S comparador_cpp -B build -G "Visual Studio 18 2026" -A x64
cmake --build build --config Release --target patel_compare --parallel 4
python -m unittest discover -s tests -v
python -m referencia run --rate 16000
python -m referencia run --rate 48000
python -m referencia compare
```

`python -m referencia all` ejecuta ambas campañas en ese orden y compara esas
mismas ejecuciones. `--cpp RUTA` permite elegir el ejecutable en `run` y `all`.
Para Visual Studio 2022, usar el generador `Visual Studio 17 2022`.
En Linux puede omitirse el generador; usar `-DCMAKE_BUILD_TYPE=Release`.

CMake reutiliza por defecto `../build/_deps/juce-src` del workspace, comprobando
que sea JUCE 8.0.10. Se puede pasar `-DJUCE_SOURCE_PATH=RUTA`. Si no existe esa
ruta, descarga JUCE 8.0.10 dentro de `build/`. No necesita iniciar la aplicación
ni abrir dispositivos de audio.

Salida del CLI: 0 = criterios satisfechos; 1 = campaña completada con discrepancias;
2 = fallo operativo. La falta del comparador C++ es un error, nunca un skip o una
simulación de resultados. `all` continúa con 48 kHz si 16 kHz termina con discrepancias;
un error operativo interrumpe la ejecución y deja el manifest sin `completed`.

## Carpetas y reproducción

- `referencia/`: correlaciones directas, solución densa, replay causal y campañas.
- `comparador_cpp/`: wrapper JSON que compila el `PatelEstimator.cpp` original.
- `tests/`: pruebas unitarias y de integración obligatoria con C++.
- `16khz/` y `48khz/`: configuración, capturas, modelos y resultados de cada tasa.
- `resumen_comparacion/`: tablas e informe conjunto, con curvas 100–7000 Hz en CSV.
- `build/`: compilador, dependencias y archivos temporales de pruebas.

Cada ejecución utiliza un identificador UTC más sufijo aleatorio. Capturas/modelos/
resultados comparten ese identificador; ninguna ejecución sobrescribe las anteriores.
`latest.json` es solamente un puntero actualizable. Para comparar ejecuciones
anteriores: `python -m referencia compare --run16 ID16 --run48 ID48`.

El manifest guarda la configuración, versiones, hash del ejecutable y snapshots
con hashes de las fuentes Python/C++ utilizadas. Una modificación del estimador
requiere recompilar antes de ejecutar. El binario incorpora hashes del estimador
al compilar; el puente verifica esos hashes y rechaza ejecutables desactualizados.
Cada respuesta C++ identifica también compilador y versión. Las rutas de señales en las solicitudes son
absolutas; al mover el paquete hay que regenerar solicitudes con las nuevas rutas.

## Qué se compara

El perfil `paper_core` construye la matriz Toeplitz de las ecuaciones publicadas,
sin regularización ni recorte, y con orden conocido. Primero hay 20 sistemas
con solución conocida (cinco semillas por cuatro tamaños), luego cinco casos de
identificación `paper_core`, por tasa.

El perfil `engine_matched` calcula de forma independiente correlaciones por sumas
directas en float64, construye la matriz explícita y utiliza `numpy.linalg.solve`.
Aplica las políticas documentadas del Engine: inicio al 15% del pico, margen de
32 muestras, regularización relativa 1e-4, retención 99.9% y aceptación a 6 dB.
El modelo se cuantiza a float32 al terminar el ajuste, como en C++.
No utiliza FFT ni Levinson. La recurrencia de GLD sólo se ejecuta en el C++ real.

La convención es:

```
r_yf[l] = sum_n y[n] * f[n-l]     (extensión por ceros)
R[i,j] = r_ff[abs(i-j)]
R h = r_yf[D:D+P]
b_hat[n] = sum_k h[k] * v[n-D-k]
```

No hay normalización distinta por lag. Para comprobar el solucionador se envían
idénticos r y b a NumPy y C++. Para comprobar identificación, ambos reciben los
mismos cuatro archivos float32, pero estiman independientemente el retardo.
La comparación reconstruye la respuesta completa D+FIR y no exige idénticos cortes.
Los errores respecto de la verdad sintética se reportan por separado.

Cada tasa incluye 50 casos: cinco semillas por retorno simple, reflexiones, cola
reverberante, inicio débil, SNR 40 dB, SNR 20 dB, ausencia de retorno, saturación,
no finitos y sonda de 160 ms. Las sondas son gaussianas, -30 dBFS RMS durante su
parte activa, con rampas de 10 ms y cola completa. La validación usa otra semilla.
SNR se define por energía de toda la captura, incluida la cola.

Las campañas principales usan sonda 1 s, validación 0.5 s y retardo máximo 100 ms.
El FIR máximo es 683 taps a 16 kHz y 2048 a 48 kHz (redondeo al entero más próximo).
El ensayo `short160` usa sonda exactamente 160 ms, retardo máximo 10 ms y FIR
máximo 10 ms para que la ventana sea compatible, sin alargamiento implícito.
El margen de 32 muestras permanece tal como existe en el Engine: 2 ms frente a
0.667 ms. Es una diferencia documentada, no una equivalencia temporal perfecta.

Los caminos comparten tiempos de ecos y decaimiento. La cola reverberante se
discretiza con factor dt para conservar su integral. Las sondas a tasas distintas
son realizaciones de ruido independientes, no una grabación remuestreada.

## Criterios fijados

| Comprobación | Criterio |
|---|---:|
| Oráculo contra sistemas conocidos, error relativo | <= 1e-10 |
| Solucionador C++ contra oráculo | <= 1e-8 |
| Paper core contra FIR conocido con captura float32 | <= 1e-6 |
| Respuesta reconstruida C++ contra referencia | <= 1e-3 |
| Diferencia predictiva en casos con ruido | <= 0.1 dB |
| Retardo en casos simple/reflexiones/short160 | <= 1 muestra |
| Replay causal frente a convolución completa | <= 1e-12 |

El replay prueba bloques 1/64/128/256 y particiones irregulares sin realineamiento.
No prueba el callback C++: comprueba el modelo exportado y la reconstrucción causal.
Las pruebas también verifican rechazos, formato, hashes, round-trip float32 y que
no se sobrescriba evidencia. Un FIR con inicio débil puede recortar el primer tap;
en ese caso el retardo físico y el retardo efectivo se reportan separadamente.

Los umbrales son de ingeniería, no valores publicados por los autores. No se
relajan después de observar resultados. La comparación entre tasas es descriptiva:
no se ha establecido aún un margen de equivalencia acústica. Un aprobado significa
acuerdo numérico en esta campaña, no igualdad de desempeño en cualquier ambiente.

## Intercambio de señales y modelos

`schema_version=1`. Cada señal declara `path`, `dtype="<f4"`, `samples`,
`sample_rate` y SHA-256. Archivos mono float32 little-endian sin normalización ni
resampling. NaN se permite en el binario únicamente para probar su rechazo;
el JSON no contiene números no finitos. Modelos JSON y CSV guardan coeficientes
con precisión de round-trip y retardo explícito.

El ejecutable acepta `patel_compare request.json response.json`:

- `operation="solve"`: vectores `r` y `b`; devuelve `ok` y `solution`.
- `operation="estimate"`: `sample_rate`, `config` con los campos de EstimatorConfig,
  y `signals` con `probe`, `microphone`, `validationProbe`, `validationMicrophone`.
  Devuelve `result`, `delaySamples`, `coefficients`, `validationImprovementDb`.

La referencia valida hashes; el C++ valida formato, tasa, longitud y configuración.
Capturas rechazadas siguen conservadas, junto con solicitudes/respuestas del C++.
Los resultados incluyen el tiempo offline Python y del proceso C++ (incluye I/O).
No deben interpretarse como p99 del callback ni como latencia del sistema en vivo.

## Fuentes y límites

Patel y Panahi, *Efficient Real-Time Acoustic Feedback Cancellation using Adaptive
Noise Injection Algorithm*, EMBC 2020, DOI 10.1109/EMBC44109.2020.9175686.

El repositorio DyncEric/Acoustic-Feedback-Cancellation, commit
373248cafed843b47bc4a32d47dbd95451471e78, se revisó como material relacionado,
pero no se copió su código ni se usa como oráculo: su integración pública es incompleta.

No se incluyen detector VAD/PHPR/PNPR, recalibración automática,
mediciones con hardware ni PESQ/CSII. Este paquete permite auditar
el núcleo antes de incorporar esas etapas al audio en vivo.
