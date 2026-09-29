# Proyecto de entrenamiento AFC

Esta carpeta reúne el trabajo de datos y entrenamiento a 48 kHz para habla y canto.

| Ubicación | Contenido |
|---|---|
| `Abrir selector de voces.cmd` | Abre la GUI en Windows |
| `research/` | Código Python, GUI, pruebas, guías y laboratorio de investigación |
| `data/raw/` | Originales VCTK/GTSinger, licencias y procedencia |
| `outputs/training/` | Inventarios, ejemplos, checkpoints, modelos y registros |
| `cache/wheels/` | Descargas del instalador de PyTorch y fragmentos recuperables |

El entorno Python existente está en `../.venv/`, compartido con la carpeta madre.
El lanzador lo encuentra automáticamente. No se ha trasladado el entorno instalado:
sus ejecutables pueden contener rutas absolutas. Una instalación nueva sin ese
entorno compartido crea `.venv/` dentro de esta carpeta.

## Flujo de trabajo

1. **Revisar las muestras actuales.** Abrir la GUI y cargar
   `outputs/training/first-gpu-pilot/corpus.json`. Seleccionar una fila y reproducirla.
   El botón de doce clips obtiene/verifica las mismas muestras y vuelve a analizarlas.
2. **Ampliar el catálogo (próximo desarrollo).** Incorporar las grabaciones disponibles
   y sus metadatos para preparar la selección antes de descargar el corpus piloto.
   La GUI todavía no ofrece esta descarga ampliada.
3. **Elegir y descargar el piloto.** Buscar aproximadamente una hora por tipo,
   repartida entre personas; asignar personas a entrenamiento, validación y prueba
   antes de cortar fragmentos. Revisar canciones repetidas entre grupos.
4. **Analizar, escuchar y cerrar el inventario.** Verificar calidad técnica, escuchar
   una selección representativa, excluir problemas y guardar una versión del manifiesto.
   Escuchar un archivo no marca automáticamente todo el corpus como revisado.
5. **Generar y validar ejemplos de feedback.** Comprobar el simulador y la alineación
   de entradas/objetivos; usar caminos acústicos separados por grupo.
6. **Implementar L3C a 48 kHz y comprobar el procesamiento continuo.** Contrastar con
   el artículo y medir costo y latencia antes del entrenamiento grande. La GRU actual
   es un prototipo de infraestructura y aún no supera la referencia sin procesamiento.
7. **Entrenar el piloto y después migrar a Linux.** Guardar avances, validar habla y
   canto por separado y ampliar el entrenamiento solo al superar los criterios.
8. **Integrar y evaluar.** Exportar el modelo con sus estados, integrarlo al engine
   y comparar con Patel/ANIA usando material reservado y mediciones físicas.

La revisión del artículo y la implementación del modelo pueden avanzar mientras
se preparan los datos. No es necesario volver a entrenar para usar el selector.

## Comandos desde esta carpeta

En el equipo actual:

```powershell
..\.venv\Scripts\python.exe -m afc_lab.corpus_gui
..\.venv\Scripts\python.exe -m unittest discover -s research/tests -v
```

Tras copiar el proyecto a otro equipo, instalar nuevamente el entorno:

```powershell
python research/bootstrap_training.py
```

Consultar la [guía detallada](research/TRAINING.md) y los
[resultados de la primera comprobación](research/TRAINING_RESULTS.md).

## Rutas y evidencia histórica

El proyecto se trasladó dentro de la carpeta madre. Los registros históricos
conservan las rutas originales para no alterar hashes utilizados por checkpoints.
Los archivos de audio en los inventarios tienen rutas relativas a `data/raw/`.
La GUI resuelve la carpeta local cuando la antigua ya no existe y guarda la ruta
actual en selecciones nuevas. En los comandos de preparación se debe indicar
`--data-root data/raw` desde esta carpeta. Los resultados de doctor y pruebas
guardados antes del traslado describen la ejecución original.
