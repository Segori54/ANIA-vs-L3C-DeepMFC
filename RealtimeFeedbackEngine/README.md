# RealtimeFeedbackEngine

## Papel dentro de la tesis

Este es el banco experimental de la comparación ANIA frente a L3C-DeepMFC descrita
en el [README principal](../README.md). Implementa actualmente la línea clásica
con calibración manual; la implementación fiel e integración de L3C-DeepMFC están pendientes.
Su finalidad es producir mediciones reproducibles de estabilidad, calidad y coste,
además de permitir auditar las señales internas. Compilar o superar las pruebas
sintéticas no equivale a validar el montaje acústico.

Al 28 de septiembre de 2026 se han aprobado cinco pruebas C++ y la auditoría de
sesiones sintéticas a ambas tasas. El siguiente hito es la campaña física descrita
en la guía de captura. El detector tonal es experimental y no recalibra automáticamente.

## Operación

La captura de validación tiene botón e indicador propios y admite selección de
16/48 kHz antes de Run. Guarda WAV float32, modelos y cronología para auditoría
independiente. Ver [procedimiento y formato](docs/CAPTURA_SESIONES.md).

Aplicación JUCE/C++20, mono a 16 o 48 kHz, para cancelar retorno acústico y medir
ganancia estable en un lazo micrófono–PC–parlante.

## Uso del banco de medición

1. Seleccionar ASIO y la misma interfaz para entrada/salida. Pulsar **Run**.
   La aplicación no arranca audio automáticamente. El búfer solicitado es
   **128 muestras (8 ms a 16 kHz; 2,67 ms a 48 kHz)**; comprobar el valor efectivo en pantalla.
2. Mantener fijas las ganancias físicas de interfaz y parlante, la geometría,
   y desactivar monitorización directa. La ganancia digital comienza en −20 dB.
3. Pulsar **Calibrate AFC**. El motor apaga el generador de ensayo con una rampa
   de 20 ms, abre el camino normal y espera un retorno completo antes de medir.
   Se emiten dos sondas blancas independientes. Los controles de ruido se bloquean.
4. Esperar **Validated**. Se muestran retardo, taps efectivos y mejora de
   predicción sobre la segunda sonda. El generador de ensayo permanece apagado.
   Ante fallo o cancelación se descarta el modelo y se silencia la salida;
   revisar el resultado y desmarcar **Mute output** para recuperarse.
5. Activar manualmente **Test noise**, blanco o rosa, y ajustar su nivel RMS
   en dBFS. Comparar **Bypass** y **Patel** cambiando solamente **Digital gain**.
   El ruido se añade después de esa ganancia, por lo que su nivel permanece fijo
   durante el barrido y forma parte de la referencia del cancelador.
6. Subir 1 dB por paso, observar 10 s y anotar el último paso estable y el primer
   acople. Repetir tres veces. **Observacion** registra la clasificación
   elegida y, opcionalmente, el SPL leído en el sonómetro.
   La observación de 10 s es manual: el botón no ejecuta un temporizador.
7. Usar la diferencia entre umbrales digitales para la mejora de ganancia estable.
   SPL es complementario: conservar posición, ponderación y tiempo de integración.
   Si satura antes de acoplar, registrar un límite de saturación, no un umbral de
   estabilidad.

Los CSV están en la carpeta **measurements** junto al ejecutable, una sesión por
Run. Incluyen dispositivos, frecuencia/búfer, latencias, ganancia, mute, ruido,
resultado de calibración, retardo, FIR, mejora de predicción, niveles, saturación,
detecciones tonales y tiempos de callback. **Open log folder** permite ubicarlos.
La telemetría se guarda cada segundo y al cambiar de estado, desde el hilo de GUI;
ese registro CSV no guarda voz. El control independiente **Iniciar captura** sí
guarda el micrófono y las señales internas. Las detecciones tonales son experimentales y no
deben reemplazar la observación del umbral.

## Identificación y cadena

micrófono → resta del retorno estimado → ganancia digital → ruido de ensayo
→ protección → salida efectiva → historial de referencia del cancelador.

La sonda de calibración reemplaza esa cadena durante identificación y validación.
La GUI no puede anular el bloqueo de ruido: una compuerta atómica rechaza las
solicitudes de encendido durante calibración, y ninguna se reproduce al terminar.
Stop/reinicio de dispositivo invalida el modelo y apaga el generador.

Parámetros iniciales de ingeniería (no una réplica de todos los parámetros del
experimento publicado): sonda gaussiana de −30 dBFS RMS durante 1000 ms,
segunda sonda de 500 ms, máximo retardo de 100 ms y FIR efectivo de hasta
683 coeficientes a 16 kHz o 2048 a 48 kHz (aproximadamente 42,67 ms).
Cada captura incluye el retorno posterior completo. Se prolongan
sondas demasiado cortas hasta al menos dos ventanas de retorno. La rampa de
sonda es de 10 ms en cada extremo.

En un trabajador se calculan correlaciones lineales mediante FFT con relleno de
ceros, se localiza el inicio significativo con margen de 32 muestras y se
resuelve el sistema simétrico Toeplitz con Levinson generalizado O(P²).
Se regulariza la diagonal con 1e−4 relativo y se conserva al menos 99,9 % de
la energía del FIR ajustado. El retardo no se implementa como miles de taps nulos:
se indexa un historial circular. La aceptación exige al menos 6 dB de reducción
del error frente a no predecir el retorno, sobre una sonda independiente.
Se rechazan datos no finitos, capturas saturadas y ausencia de retorno medible.

Las ganancias físicas forman parte del camino identificado; modificarlas exige
recalibrar. Cambiar ganancia digital no invalida el modelo porque se referencia la
salida real después de ganancia, ruido y protección. La protección recorta a
±0,95: es un techo de salida, no una demostración de estabilidad.

El método se basa en [Patel y Panahi, EMBC 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7545262/).
Se pospone la recalibración automática hasta validar el detector. El selector
solo ofrece métodos implementados; adaptación continua y deep learning quedan
pendientes. La [referencia independiente](../Referencia%20ASNI%20AFC%20Patel/README.md)
ya comprueba el acuerdo numérico del estimador en campañas sintéticas a ambas tasas.
El laboratorio Python histórico es distinto; su función maximum_stable_gain calcula una cota de magnitud,
no un umbral de estabilidad medido.

## Compilar y verificar

Desde la raíz del repositorio:

    cmake -S RealtimeFeedbackEngine -B build -G "Visual Studio 18 2026" -A x64
    cmake --build build --config Release --parallel 4
    ctest --test-dir build -C Release --output-on-failure

Con Visual Studio 2022 usar el generador "Visual Studio 17 2022".
JUCE 8.0.10 se descarga en la primera configuración; ASIO usa el SDK incluido.
Ejecutable: build/RealtimeFeedbackEngine_artefacts/Release/RealtimeFeedbackEngine.exe.

PatelAfcTest verifica la solución Toeplitz contra un sistema conocido, retardos
mayores de un bloque, bloques de 1/64/128/256 muestras, validación independiente,
ausencia de retorno, saturación, cancelación en todas las fases, interlock de ruido,
reinicio de dispositivo, RMS y espectro blanco/rosa, cambio de ganancia física,
ganancia digital estable por encima del umbral de bypass y camino largo con ruido.
Audita asignaciones C++ de heap en el hilo de audio y mide p99 del caso largo
contra el período de 128 muestras en Release. La prueba sintética no certifica
ganancia acústica adicional ni ausencia de glitches en todos los dispositivos.
