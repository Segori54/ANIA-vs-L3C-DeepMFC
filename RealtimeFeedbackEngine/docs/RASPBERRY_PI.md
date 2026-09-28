# Raspberry Pi 4 / ALSA

## Preparación

Use Raspberry Pi OS de 64 bits y conecte una interfaz USB class-compliant. Instale
el compilador, CMake, Ninja y los paquetes de desarrollo que JUCE necesita:

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build libasound2-dev \
  libfreetype6-dev libfontconfig1-dev libx11-dev libxext-dev libxinerama-dev \
  libxrandr-dev libxcursor-dev
```

## Compilación

```bash
cmake -S . -B build-rpi -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-rpi --parallel 4
ctest --test-dir build-rpi --output-on-failure
```

Seleccione ALSA, 48 kHz, un canal de entrada/salida y mida bloques de 64, 128 y
256 muestras. El criterio de aceptación es p99 menor que 80 % del periodo del
bloque y 30 minutos sin misses/xruns. Guarde versión del sistema, interfaz,
firmware, gobernador de CPU y resultado de `results.csv`; no mezcle estos datos
con las mediciones de Windows.

La inferencia ONNX se habilitará sólo después de seleccionar el candidato ganador
y construir ONNX Runtime ARM64. CPU es la ruta principal; GPU queda fuera de la
comparación central.
