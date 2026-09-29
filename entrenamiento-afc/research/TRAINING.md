# Proyecto de entrenamiento AFC a 48 kHz

## Estado y límites

Este documento es el punto de entrada del proyecto de entrenamiento aprobado.
La fase 1 se cierra **solo** cuando `doctor --smoke` termina con `passed: true`
en CUDA y deja evidencia. Una instalación o un ensayo CPU no cumple ese criterio.
Los archivos locales de resultados están en `outputs/training/`, fuera de Git.

**Verificación realizada el 29/09/2026:** la fase 1 pasó en la GTX 1650 Ti.
También terminó la prueba acotada de datos reales, entrenamiento, reanudación
y exportación. Ver [resultados y límites medidos](TRAINING_RESULTS.md).
Esto cierra la comprobación del laboratorio; las fases científicas posteriores
mantienen los criterios de aceptación de la tabla.

La GRU disponible sirve para comprobar la cadena de datos, entrenamiento y
exportación. **No es L3C-DeepMFC**. No se habilita un nuevo procesador en el
Engine ni se presenta una comparación científica hasta validar el modelo final.

| Fase | Implementación/evidencia requerida | Estado inicial de esta entrega |
|---|---|---|
| 1. Entorno Lenovo | Inventario, CUDA, aprendizaje, checkpoint y reanudación | Superada en GPU; evidencia en first-gpu-pilot/phase1 |
| 2. Voces | VCTK + GTSinger, revisión, una hora por tipo y particiones | Doce originales descargados (seis por corpus); corpus piloto completo pendiente |
| 3. Simulador | Ecuación causal, retardo explícito, casos fijos/cambiantes | Generador inicial comprobable; representatividad PA/monitores pendiente |
| 4. L3C | Reproducción contrastada y adaptación 48 kHz | Pendiente; los modelos existentes siguen siendo exploratorios |
| 5. Piloto | Minibatches, validación, reanudación, voces nuevas | Entrenador GRU de infraestructura implementado; aprobación de calidad pendiente |
| 6. Linux | Mismo código/datos; entrenamiento mayor y ajuste en lazo | Bootstrap portable; ejecución en el otro equipo pendiente |
| 7. Engine | ONNX con estados, frontend coherente, IProcessor y plazos | Pendiente del modelo y su presupuesto de latencia |
| 8. Evaluación | Modelo congelado, prueba reservada y montaje real | Pendiente |

## 1. Preparar y comprobar el equipo

Desde `entrenamiento-afc/`, en Windows (entorno compartido del equipo actual):

```powershell
python research/bootstrap_training.py
..\.venv\Scripts\python.exe -m unittest discover -s research/tests -v
```

En Linux, clonar/copiar código y datos y ejecutar `python3 research/bootstrap_training.py`.
No copiar `.venv` entre sistemas. No se cambia el controlador NVIDIA ni se
instalan paquetes de Arch automáticamente. El doctor comprueba compatibilidad real.
La combinación de partida es Python 3.14 y PyTorch 2.10.0 + CUDA 12.8.
El inventario y `requirements-resolved.txt` registran las versiones efectivas;
la GPU Linux requiere su propia prueba antes de aprobar migración.

El doctor realiza 80 actualizaciones sobre datos sintéticos pequeños. Guarda un
checkpoint a mitad, continúa y compara con otra ejecución que recupera modelo,
optimizador y generadores aleatorios. Exige error máximo de parámetros <= 1e-6
y error final menor al 25% del inicial. Esto prueba el equipo, **no AFC**.
No cae silenciosamente a CPU si CUDA falla.

Para repetir sin reinstalar:

```powershell
..\.venv\Scripts\python.exe -m afc_lab.doctor --smoke --output outputs/training/phase1-repeat
```

Para una prueba acotada de toda la infraestructura disponible (CUDA, clips
originales de ambos corpus, pares, cuatro épocas GRU con reanudación y exportación ONNX):

```powershell
..\.venv\Scripts\python.exe research/run_training_smoke.py
```

Cada ejecución crea un directorio nuevo con `status.json` y un log por etapa.
Aunque todas sus etapas pasen, `quality_approved` y `engine_release` quedan falsos:
no es el entrenamiento de L3C ni la campaña científica.

El descargador `afc_lab.download` puede recuperar descargas HTTPS por rangos,
comprobar SHA-256 y conservar su procedencia. Sus fragmentos quedan en `.parts`;
considerar ese espacio adicional. Nunca promueve un archivo con hash incorrecto.

## 2. Preparar originales e inventario

### Interfaz gráfica local

En Windows, hacer doble clic en `Abrir selector de voces.cmd` dentro de
`entrenamiento-afc/`. Alternativamente:

```powershell
..\.venv\Scripts\python.exe -m afc_lab.corpus_gui
```

1. Usar **Abrir inventario** con
   `outputs/training/first-gpu-pilot/corpus.json` para revisar la muestra existente.
2. Filtrar por tipo o grupo; indicar minutos por tipo y pulsar **Selección automática**.
3. Marcar filas y usar **Incluir / excluir filas marcadas** para ajustar la selección.
4. **Reproducir** escucha la fila marcada dentro de la GUI, con pausa, continuación,
   parada, progreso y volumen. WAV y FLAC se decodifican a float32; el volumen
   solo afecta la escucha y no modifica los originales. Se usa la salida de audio
   predeterminada del sistema. **Guardar selección** exporta un manifiesto
   compatible con el generador de pares.

**Analizar originales** inventaría la carpeta local, conservando las reglas de
identidad, duplicados y canciones. Las descargas y el análisis se ejecutan en
segundo plano con registro de progreso. **Obtener/verificar 12 clips de prueba** obtiene únicamente
las doce muestras técnicas disponibles; el catálogo y la descarga del corpus
ampliado aún están pendientes. No muestra un porcentaje de descarga estimado.

La GUI conserva exclusiones y particiones del inventario y no permite aprobar
automáticamente la revisión auditiva. Guardar una selección incompleta es posible
y queda indicado en el JSON. Cambiar de carpeta borra la selección en pantalla;
guardar antes si se desea conservarla. En Linux se necesita Tk disponible para
el Python del entorno y PortAudio para la reproducción con sounddevice.
Si el entorno ya estaba instalado antes de agregar el reproductor, ejecutar
`python -m pip install "sounddevice>=0.5,<0.6"` con el Python de `.venv`.

Directorios locales, ignorados por Git:

```text
data/raw/vctk/.../p225/p225_001_mic1.flac
data/raw/gtsinger/Spanish/ES-Bass-1/Vibrato/canción/Control_Group/0000.wav
data/raw/gtsinger/Spanish/ES-Bass-1/Vibrato/canción/Paired_Speech_Group/0000.wav
```

Conservar licencias y originales. No normalizar ni convertir a PCM16.
Se acepta PCM24/FLAC nativo; se rechazan tasas distintas de 48 kHz y estéreo
sin una elección de canal explícita. VCTK usa mic1 para no duplicar la misma frase.

Fuentes oficiales:
- VCTK 0.92: https://datashare.ed.ac.uk/handle/10283/3443
- GTSinger: https://huggingface.co/datasets/GTSinger/GTSinger
- Licencia GTSinger: https://github.com/AaronZ345/GTSinger/blob/main/dataset_license.md

Para comprobar el importador con seis originales pequeños (tres personas,
habla y canto), sin confundirlos con el piloto de dos horas:

```powershell
..\.venv\Scripts\python.exe -m afc_lab.fetch_samples --data-root data/raw
..\.venv\Scripts\python.exe -m afc_lab.fetch_vctk_samples --data-root data/raw
..\.venv\Scripts\python.exe -m afc_lab.corpus --data-root data/raw --output outputs/training/corpus-smoke.json --seconds-per-kind 3600
```

El segundo comando extrae dos FLAC originales por hablante para tres hablantes
de VCTK mediante rangos del ZIP oficial, sin descargar los 11,7 GB completos.
Comprueba el ETag de cada rango y el CRC de cada entrada, y registra SHA-256 de
los archivos extraídos. No afirma verificar el MD5 del archivo ZIP completo.

El inventario registra hash, duración, pico, RMS, subtipo, identidad, canción,
idioma, técnica y exclusiones. Las rutas son relativas al `--data-root`, que puede
cambiar en Linux. Las particiones usan hash fijo por identidad (80/10/10 en
expectativa), sin mover personas existentes al ampliar el corpus. La semilla
de datos por defecto es 18, fijada antes de entrenar para cubrir los tres grupos
con los seis clips iniciales; no se ajusta según resultados. Se rechaza un
inventario sin cobertura suficiente, en lugar de forzar cuotas. Las canciones
compartidas y duplicados entre grupos se conservan solo en el grupo más reservado
(prueba > validación > entrenamiento), excluyendo las otras copias.
El nombre normalizado de canción no detecta traducciones ni títulos alternativos:
requiere auditoría manual antes de congelar el corpus definitivo.
Congelar el inventario antes de seleccionar modelos; si nuevas canciones obligan
a excluir ejemplos antes usados, no reutilizar pesos entrenados con esos ejemplos
para evaluar la nueva partición reservada.

`coverage_complete` indica si hay habla y canto en los tres grupos.
`duration_target_met` indica si se alcanzó el tiempo pedido; `complete` permanece
falso mientras `listening_review` esté pendiente. Los seis clips no constituyen
una hora por tipo ni una revisión perceptual aprobada.

## 3. Generar pares causales

```powershell
..\.venv\Scripts\python.exe -m afc_lab.training_pairs outputs/training/corpus-smoke.json --data-root data/raw --output outputs/training/pairs-train --split train --limit 100 --seconds 1
..\.venv\Scripts\python.exe -m afc_lab.training_pairs outputs/training/corpus-smoke.json --data-root data/raw --output outputs/training/pairs-validation --split validation --limit 100 --seconds 1
```

Convención explícita: `mic[n] = voz[n] + sum(h[k]*parlante[n-k])` y
`parlante[n] = ganancia*mic[n-D]`, con `D=96` muestras para estos ejemplos.
El objetivo de la red es la voz **antes de la ganancia**. Ganancia y retardo se
aplican fuera de la red; se guarda también la salida ideal del parlante.
Este retardo de simulación no es una medición de latencia real.

Las trayectorias tienen semillas distintas por grupo. Se incluyen casos fijos,
cambiantes, sin feedback y silencio si hay suficientes grabaciones. La ganancia
conservadora inicial satisface una cota de norma L1; no se denomina MSG medido.
No hay limitador para ocultar inestabilidad; se rechazan ejemplos fuera de escala.
Este generador crea pares estables; **no implementa aún entrenamiento de la red
en circuito cerrado** ni modela un PA real validado. El histórico Patel Python
no se usa como oráculo del Engine.

## 4–5. Piloto de infraestructura

```powershell
..\.venv\Scripts\python.exe -m afc_lab.pilot --train outputs/training/pairs-train --validation outputs/training/pairs-validation --output outputs/training/gru-smoke --epochs 5 --batch-size 2
..\.venv\Scripts\python.exe -m afc_lab.pilot --train outputs/training/pairs-train --validation outputs/training/pairs-validation --output outputs/training/gru-smoke --epochs 10 --batch-size 2 --resume outputs/training/gru-smoke/latest.pt
```

Mantener configuración, manifiestos y tamaños de grupo al reanudar. `--epochs`
es el total final, no épocas adicionales. Se guardan `latest.pt`, `best.pt`,
`config.json` y `history.jsonl`, con métricas por habla/canto y escenario.
Se puede trasladar un checkpoint a otra GPU, pero no se promete igualdad bit a
bit entre hardware o sistemas. Conservar los datos originales y manifiestos.

La GRU usa ventana de 20 ms / salto de 5 ms como frontend conservador exploratorio.
**No satisface por ello el presupuesto de 10 ms del proyecto** y no se activa en
el Engine. La arquitectura y reconstrucción de baja latencia de L3C requieren
implementación y pruebas específicas antes de pasar a la fase 7.

Para comprobar la exportación de este prototipo sin habilitarlo en audio en vivo:

```powershell
..\.venv\Scripts\python.exe -m afc_lab.export_pilot outputs/training/gru-smoke/best.pt outputs/training/gru-smoke/prototype.onnx
```

Se comprueban salida y estado entre PyTorch/ONNX y entre secuencia completa y
fragmentos individuales. El JSON del modelo incluye `engine_release: false` y
percentiles de inferencia en CPU; estos percentiles **no son latencia total**.

## Criterios de cierre posteriores

Contrastar https://www.isca-archive.org/interspeech_2025/hao25_interspeech.pdf;
registrar cambios respecto del artículo (24 -> 48 kHz, dominio voz/canto y PA).
Validar espectro, reconstrucción, estados y equivalencia continuo/bloques.
Revisar conservación de señal sin feedback, silencios, cambios de trayectoria,
ganancia útil y resultados separados por tipo. Una caída de MSE no certifica AFC.

La exportación final debe especificar estados de entrada/salida, ventanas,
normalización, tasa, ganancia y retardo. La integración C++ debe cargar fuera del
callback, comprobar plazos y medir latencia completa con el dispositivo.
El límite propuesto de 10 ms incluye interfaz, buffers, algoritmo y colas;
necesita medición física y prueba de comodidad en monitores.
