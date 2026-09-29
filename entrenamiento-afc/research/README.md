# AFC Research Lab

## Proyecto de entrenamiento por fases

Ver [TRAINING.md](TRAINING.md) para preparar Windows/Linux, comprobar entrenamiento
y reanudación en GPU, auditar originales de voz/canto y generar pares causales.
Los ensayos GRU de infraestructura no son una implementación de L3C-DeepMFC.

## Papel dentro de la tesis y estado

Este laboratorio prepara la comparación ANIA frente a L3C-DeepMFC del
[proyecto de tesis](../README.md): simulación del lazo, preparación de datos,
métricas y candidatos de aprendizaje profundo. Al 28 de septiembre de 2026,
existen las herramientas y arquitecturas; el corpus definitivo, entrenamiento,
implementación fiel de L3C-DeepMFC e integración neuronal en el banco C++ siguen pendientes.
Los resultados sintéticos preliminares no son una comparación final entre métodos.

El estimador Patel histórico de este paquete utiliza mínimos cuadrados y no debe
usarse como oráculo del Engine. La equivalencia del estimador C++ se valida con la
[referencia independiente](../Referencia%20ASNI%20AFC%20Patel/README.md).
La ganancia máxima calculada en simulación no reemplaza un umbral acústico medido.
Las particiones por identidad y la reserva de grabaciones propias para evaluación
externa deben mantenerse al construir la campaña definitiva.

## Preparación

Desde la raíz del repositorio, instalar `python -m pip install -e research`.
Ejecutar los comandos siguientes desde `research/`. Las dependencias de métricas
y redes son opcionales y no se consideran resultados verificados por su mera instalación.

Laboratorio reproducible para comparar cancelación de feedback acústico a 48 kHz.
El núcleo sólo requiere Python y NumPy. Los modelos neuronales, la exportación ONNX y
las métricas externas se habilitan mediante dependencias opcionales.

## Uso rápido

```powershell
python -m afc_lab.cli run configs/smoke.yaml
python -m afc_lab.cli batch configs/patel_sweep.yaml
python -m unittest discover -s tests -v
```

Los archivos `.yaml` incluidos usan sintaxis JSON, que también es YAML válido. Si
PyYAML está instalado se aceptan archivos YAML generales.

Cada ejecución crea un directorio con:

- `manifest.json`: configuración efectiva, semilla y versión del esquema;
- `results.csv` y `summary.json`: métricas por método;
- `audio/*.wav`: fuente, objetivo, entrada de micrófono y salidas;
- `metrics.svg`: gráfico autocontenido para inspección rápida.

## Dependencias opcionales

```powershell
python -m pip install -r requirements-ml.txt
```

PyTorch implementa tres candidatos: MLP espectral, GRU causal y una variante
compacta inspirada en DeepMFC. `python -m afc_lab.train --help` describe el formato
NPZ, el entrenamiento, la exportación ONNX y la comprobación numérica automática.

`dataset.py` impide fuga de identidades mediante particiones deterministas por
hablante/cantante/canción. `external_metrics.py` adapta STOI/ESTOI, PESQ (sólo a
8/16 kHz) y ViSQOL sin convertir silenciosamente tasas de muestreo. `runtime.py`
reporta p50/p95/p99, RTF y fracción del presupuesto de bloque.

El barrido completo es deliberadamente grande: úsese para la campaña congelada,
no como smoke test. Las grabaciones propias deben figurar sólo en el split externo.
