# Plan de validación de Patel: referencia independiente y audio en vivo

Fecha del diseño: 2026-09-24. Documento histórico de planificación.

Actualización 2026-09-28: la referencia se implementó en `Referencia ASNI AFC Patel/`
(no en la ruta inicialmente propuesta más abajo), ambas campañas sintéticas se
ejecutaron y la captura/auditoría del Engine está integrada. La campaña física y el
control automático siguen pendientes. Consultar los README y
`IMPLEMENTATION_STATUS.md` para el estado vigente; el resto conserva el diseño original.

## Objetivo y alcance

Validar por separado la corrección matemática del estimador, su integración causal
en RealtimeFeedbackEngine y el desempeño acústico en vivo a 16 y 48 kHz.
El análisis offline sirve para auditar las mismas capturas producidas en vivo;
no sustituye las pruebas de latencia, estabilidad y continuidad de audio.

La implementación actual identifica por solicitud y mantiene un FIR fijo.
La adaptación automática VAD + PHPR + PNPR del paper constituye una etapa posterior.
No declarar equivalencia con el algoritmo completo antes de validar esa etapa.

## Revisión del repositorio relacionado

Fuente: https://github.com/DyncEric/Acoustic-Feedback-Cancellation
Commit inspeccionado: 373248cafed843b47bc4a32d47dbd95451471e78.
Inspección estática del código; no se compiló ni ejecutó la aplicación iOS.

- README vincula expresamente el trabajo de Patel y Panahi. Licencia MIT,
  copyright SSPRL; archivos identifican a Kashyap Patel/SSPRL.
- Es un proyecto iOS/Xcode, mientras que el experimento del paper utiliza Android.
- AudioFormat.h configura 48000 Hz y FRAME_SIZE=64. Esto acredita configuración,
  no validación experimental a 48 kHz.
- AFC.cpp deja comentadas la emisión de ruido y la llamada a computeFilter.
  howlingDetection devuelve siempre false; howlingDetection.cpp sólo incluye su header.
- GLD.cpp contiene correlaciones mediante FFT y una recurrencia GLD. Usa FFT fija
  de 4096 puntos y copia lenx muestras sin comprobar el límite. No se debe utilizar
  sin verificar tamaños, correlación circular frente a lineal y recurrencia.
- La interfaz recibe delay y M_behind, pero su uso para desplazar la captura está
  comentado. No resuelve por sí sola la política de separación del retardo.
- El controlador de audio deja comentada una llamada a processing y contiene
  operaciones que no tomaremos como patrón para nuestro callback.

Uso acordado: fuente complementaria y posible tercer comparador experimental.
No usar como oráculo de corrección ni copiar su GLD para construir la referencia.
Si se adapta código, conservar licencia y registrar cada modificación respecto al commit.

## Arquitectura de comparación

Tres componentes con responsabilidades distintas:

1. Referencia Python float64 derivada de las ecuaciones: correlación por sumas,
   Toeplitz explícita y solución densa mediante numpy.linalg.solve (sin inversa).
2. Engine C++: correlación FFT, GLD, selección del inicio, regularización, recorte
   y procesamiento causal en bloques.
3. Código del repositorio: comparador opcional posterior, nunca criterio de aceptación.

Módulos propuestos bajo research/patel_reference/:

- correlations.py: r_yf[l] = sum_n y[n] f[n-l], con extensión por ceros.
  Autocorrelación con la misma convención y normalización común constante.
  No introducir normalización distinta por lag.
- toeplitz_oracle.py: R[i,j] = r_ff[abs(i-j)]; b[i] = r_yf[D+i].
  Resolver R h = b; reportar residuo y condicionamiento en casos pequeños.
- policies.py: políticas explícitas de retardo y energía, separadas del solucionador.
- causal_replay.py: reconstrucción del FIR completo y convolución causal directa.
- compare_capture.py: lectura del contrato de exportación y comparación por etapa.
- fixtures.py: entradas deterministas, caminos conocidos y semillas separadas.

Perfiles:

- paper_core: primero D=0 con respuesta completa, sin regularización ni recorte;
  orden fijado explícitamente para aislar la ecuación publicada.
- engine_matched: mismo D y orden en la prueba del solucionador; después evaluar
  independientemente detección de inicio y recorte. Regularización
  R + 1e-4*r_ff[0]*I; retención de energía 0.999.
- end_to_end: referencia estima desde las capturas originales sin recibir D del
  Engine como verdad; comparar respuestas completas y predicciones aunque la
  representación D + FIR no sea idéntica.

Primero probar matrices pequeñas y bien condicionadas con solución conocida.
La resolución densa es offline y costosa: reservar las grandes para casos elegidos;
no sustituirla silenciosamente por GLD para acelerar y perder independencia.
La referencia no importa PatelEstimator, no copia solveToeplitz y no ajusta sus
resultados al C++ antes de resolver las discrepancias matemáticas.

## Ensayos y criterios numéricos

1. Correlación: impulsos, retardos enteros, ruido, extremos de captura y colas.
2. Solución: Toeplitz positiva definida, distintas longitudes y condicionamientos.
3. Identificación: FIR conocido, retorno inicial débil, reflexión tardía dominante,
   colas largas, voz independiente, varios SNR y ausencia de retorno.
4. Integración: bloques 1/64/128/256 y particiones irregulares; mismo stream,
   misma configuración y mismo instante de activación del modelo.
5. Lazo cerrado: fuente y camino conocidos; ganancia variable y cambio del camino.

En el replay separar equivalencia DSP de la programación del trabajador:
para comparar muestras usar el model_activated_sample registrado, sin confundir
variaciones del planificador con diferencias del filtro.

Umbrales iniciales de ingeniería, a congelar antes de la campaña reservada:

- Solución densa float64 conocida: error relativo L2 <= 1e-10 en casos bien condicionados.
- Correlaciones FFT/C++ frente a directas: error L2 normalizado <= 1e-5 en fixtures
  no degenerados. En señales cercanas a cero usar tolerancia absoluta documentada.
- FIR C++ frente al oráculo, con idéntico sistema y sin recorte: error relativo <= 1e-3
  en los casos bien condicionados seleccionados. Registrar residuo por separado.
- Retardo entero conocido: error <= 1 muestra en fixtures con inicio inequívoco.
- Replay con el mismo modelo float32: NRMSE <= 1e-4 sobre señales no degeneradas;
  tolerancia absoluta para silencio, sin permitir realinear para ocultar errores de índice.
- Captura con pérdidas, clipping durante identificación o metadatos incoherentes:
  inválida para comparación cuantitativa, conservada con motivo de rechazo.

Estos umbrales son propuestas propias, no valores publicados por Patel.
Los casos mal condicionados se analizan separadamente; no se relajan umbrales
después de observar el conjunto de evaluación para obtener una aprobación.

## Comparación a 16 y 48 kHz

Separar frecuencia del dispositivo, frecuencia del algoritmo y tamaño del callback.
Registrar valores solicitados y efectivos; actualmente AudioConfig solicita 48 kHz.

Campaña A, fidelidad temporal:

| Parámetro | 16 kHz | 48 kHz |
|---|---:|---:|
| Trama lógica de 16 ms | 256 | 768 |
| Sonda de 160 ms del experimento publicado | 2560 | 7680 |
| FIR efectivo de 17.5 ms | 280 | 840 |
| Retardo máximo de 100 ms | 1600 | 4800 |
| Persistencia de 192 ms del detector futuro | 12 tramas | 12 tramas |

Las tramas lógicas no obligan al dispositivo a entregar esos bloques.
Agregar muestras en buffers preasignados y contabilizar la latencia introducida.
El FIR causal puede continuar procesando en cada callback.

Campaña B, aplicación en vivo:

- Usar los bloques que soporte el dispositivo, incluyendo 48 kHz/128 muestras.
- Comparar duraciones de bloque semejantes cuando sea posible y reportar todas
  las diferencias. Mantener 128 muestras en ambas tasas no mantiene la latencia.
- Mantener en segundos la duración de sondas, la ventana de camino, rampas y
  persistencias; en Hz, las bandas; en dBFS/SPL, los niveles pertinentes.
- El actual máximo de 2048 taps a 48 kHz cubre 42.67 ms; su equivalente a 16 kHz
  es aproximadamente 683 taps. Conservar explícitamente la regla de redondeo.
- La sonda de 160 ms y la calibración robusta actual (1 s + 0.5 s independiente)
  son experimentos separados. El mínimo automático de dos ventanas de retorno
  puede alargar la sonda: registrar duración efectiva y no llamarla réplica de 160 ms.
- Comparación principal en banda común, por ejemplo 100 Hz-7 kHz, con filtrado
  documentado; evaluación adicional de banda amplia a 48 kHz por separado.
- No interpolar coeficientes y exigir igualdad tap a tap entre tasas. Comparar
  retardo en segundos, respuesta en Hz, error sobre señales equivalentes y estabilidad.

Si el dispositivo no permite 16 kHz nativos, preferir una interfaz que sí los permita
para la comparación física. Alternativa explícita: hardware a 48 kHz con conversión
causal 48->16->48, cuyo filtrado y retardo forman parte del sistema medido.
No presentar esa alternativa como hardware nativo de 16 kHz ni usar resampling
offline no causal como evidencia de funcionamiento en vivo.

## Contrato de exportación v1

Una carpeta por sesión; cada calibración y modelo tienen identificadores únicos.

```
session_<id>/
  manifest.json
  telemetry.csv
  events.jsonl
  calibrations/<id>/
    identification.wav
    validation.wav
    model.json
    coefficients.csv
    estimator_debug.npz        # generado offline a partir de exportaciones de diagnóstico
  runs/<id>/
    signals_0001.wav
    blocks.csv
  checksums.sha256
```

WAV IEEE float32 sin normalización, conversión a PCM16 ni remuestreo implícito.
Cada archivo declara sample rate, canales, sample_start y número de muestras.

Calibración: canales sincronizados de micrófono, sonda programada y salida digital
efectiva. Conservar preparación, sondas y colas, o registrar sus límites exactos
en una línea temporal común. Guardar también calibraciones rechazadas.

Funcionamiento normal: micrófono y[n], retorno estimado b_hat[n], señal limpia g[n]
antes de ganancia y salida efectiva v[n]. Ganancia/rampas y estados por muestra o
por segmentos exactos cuando sean necesarios para reproducir la salida.
La salida digital es la referencia enviada al DAC, no una medición analógica del parlante.

model.json: versión de esquema, model_id, calibration_id, frecuencia efectiva,
D, longitud máxima y efectiva, regularización, criterio de energía, mejora de
validación, resultado, instante de activación y hashes de capturas.
coefficients.csv: k y h[k] float32 con precisión suficiente para round-trip
(al menos 9 dígitos significativos), con convención explícita:
b_hat[n] = sum_k h[k] * v[n-D-k].

Diagnóstico opcional del trabajador: r_ff, r_yf, inicio detectado, D previo al
recorte, coeficientes anteriores al recorte y energía descartada. La referencia
recalcula estos valores desde audio, no los adopta como resultado esperado.

manifest.json: commit y estado dirty, hash de fuentes/diff o snapshot reproducible,
compilador/build, SO/CPU, dispositivo/driver, tasas y bloques solicitados/efectivos,
latencias reportadas/medidas, ganancias físicas anotadas, geometría, niveles,
semillas, condiciones, banda evaluada y conversiones de frecuencia utilizadas.
El árbol actual tiene cambios locales: guardar sólo el commit no identifica el ejecutable.

events.jsonl y blocks.csv: contador de muestras monotónico, secuencia de bloques,
model_id activo, inicio/fin de calibración, cambios de estado/ganancia, clipping,
silenciamiento, overruns de exportación, bloques perdidos y plazos incumplidos.
Marcas de reloj de pared complementarias; la sincronización DSP usa muestras.

## Exportación sin interferir con audio en vivo

- Modo experimental explícito con inicio/fin y duración máxima de captura.
- Callback: copiar datos a una cola SPSC acotada y preasignada; nunca abrir archivos,
  serializar JSON, bloquear, reservar memoria ni esperar al escritor.
- Escritor persistente: drenar la cola, escribir WAV/CSV/eventos, segmentar archivos
  largos y cerrar encabezados/hashes al terminar.
- Calibraciones: snapshot con propiedad explícita en buffers reservados. Evitar que
  una nueva calibración o prepare sobrescriba datos mientras el escritor los usa.
- Trabajador de estimación: entregar snapshot inmutable del modelo a la exportación;
  el callback sólo publica su instante de activación. No añadir un segundo productor
  a una cola SPSC: usar colas separadas para audio y trabajador.
- Cola llena o error de disco: preservar el procesamiento de audio, marcar el tramo
  incompleto y notificar estado. Nunca ocultar pérdidas ni concatenar bloques como
  si fueran continuos. Reservar contadores para poder registrar el propio desborde.
- Cambio de dispositivo/tasa: cerrar segmento, invalidar modelo y abrir nueva época
  de muestras con metadatos propios.
- Calcular capacidad antes del ensayo: cuatro canales float32 a 48 kHz consumen
  aproximadamente 768 kB/s, unos 461 MB por diez minutos, sin metadatos.

## Secuencia de implementación y puertas de avance

1. Congelar esquema, convenciones, perfiles y fixtures. Entregable: manifest de
   campaña y matriz ecuación-función-prueba. No modificar el estimador para hacerlo
   coincidir con el repositorio incompleto.
2. Implementar oráculo Python y adaptador C++ de pruebas que invoque el estimador
   real sobre los mismos archivos. Aprobar ecuación, lags y solución a 16 kHz.
3. Implementar exportación y configuración de tasa. Verificar round-trip de audio
   y modelos, identidades y[n]-b_hat[n]=g[n], pérdidas detectables y ciclo de vida.
4. Reproducir capturas reales de 16 kHz con el oráculo y el modelo exportado.
   Aprobar independencia de bloques y correspondencia de muestras.
5. Repetir a 48 kHz con duraciones equivalentes y banda común. Añadir banda amplia
   y evaluación de coste para la aplicación final.
6. Ensayos acústicos emparejados bypass/Patel, geometría fija y orden alternado,
   al menos tres repeticiones iniciales por condición. Estimar variabilidad antes
   de fijar el número final de repeticiones. Separar sesiones de ajuste y evaluación.
7. Medir callback completo con exportación apagada/encendida: p50/p95/p99/máximo,
   deadlines perdidos, discontinuidades y latencia de lazo. Exigir cero pérdidas de
   captura para ensayos cuantitativos y cero incumplimientos observados en la campaña
   RT acordada; no interpretar p99 por debajo del plazo como garantía absoluta.
8. Sólo después: implementar y validar detector del paper y recalibración automática,
   con métricas de detección, falsas alarmas y recuperación ante cambios físicos.

Resultados: informe de equivalencia numérica, predicción independiente, calidad,
ganancia estable y coste RT. Reportar separadamente captura completa, calibración
aceptada y validación científica: el estado actual Validated sólo significa superar
el criterio interno de 6 dB sobre la segunda sonda.
