# Primera comprobación del laboratorio — 29/09/2026

La fase 1 está comprobada en el Lenovo. El equipo puede entrenar en GPU,
guardar el entrenamiento y recuperarlo. La adaptación L3C-DeepMFC y la
comparación científica siguen pendientes.

## Equipo y entorno

- NVIDIA GTX 1650 Ti, 4 GB; aproximadamente 15,37 GiB de RAM utilizable.
- Entorno aislado `.venv`, Python 3.14.6, PyTorch 2.10.0+cu128, CUDA 12.8.
- Versiones completas e inventario: `outputs/training/first-gpu-pilot/phase1/`.
- Las dependencias se instalaron en el entorno del proyecto.

## Evidencia obtenida

La prueba sintética de 80 actualizaciones en GPU redujo el error de
0,29836 a 0,00002758. Al recuperar pesos, optimizador y generadores aleatorios,
la diferencia máxima respecto de continuar sin interrupción fue **0,0**.
Este resultado comprueba entrenamiento y recuperación; no mide cancelación.

La ejecución `outputs/training/first-gpu-pilot/status.json` registra nueve
etapas terminadas: comprobación GPU, descarga GTSinger, descarga VCTK,
inventario, pares de entrenamiento, pares de validación, entrenamiento,
reanudación y exportación.

Se descargaron doce originales de seis personas, con habla y canto a 48 kHz.
Se asignaron personas a entrenamiento, validación y prueba. Hay 34,11 segundos
de habla y 28,95 segundos de canto en el inventario; todavía no se alcanza
una hora por tipo ni se ha aprobado la escucha del corpus. Los originales
de prueba no se usaron para entrenar ni seleccionar pesos.

La prueba usó ocho ejemplos de entrenamiento y ocho de validación de un
segundo, con cuatro escenarios: camino fijo, cambio de camino, señal limpia
y silencio. El prototipo GRU realizó cuatro épocas, guardando después de la
segunda y reanudando las dos restantes.

**No superó el criterio de calidad del piloto.** Al terminar, el error espectral
medio de validación fue 0,06107 en habla y 0,06078 en canto; sin procesamiento,
los valores fueron 0,0001186 y 0,00006689, respectivamente. Menor es mejor.
Estos promedios incluyen los cuatro escenarios. El error de entrenamiento
descendió, pero eso no basta: el prototipo aún degrada los casos de validación.
No se han medido ganancia adicional antes del acople ni calidad perceptual.

La exportación del prototipo a ONNX verificó salidas y estados recurrentes:

- Diferencia máxima PyTorch/ONNX: 6,04 × 10⁻⁷.
- Diferencia máxima entre secuencia y procesamiento por fragmentos: 0,0.
- Inferencia CPU por trama: mediana 0,0494 ms, percentil 99 de 0,0701 ms,
  en una medición corta de 200 ejecuciones tras calentamiento.

Estos tiempos excluyen análisis espectral, reconstrucción, buffers e interfaz.
No son la latencia total ni una prueba sostenida del callback de audio.
El frontend exploratorio usa ventanas de 20 ms y no cumple el presupuesto
de 10 ms del proyecto. El modelo se marca `engine_release: false`.

Las **23 pruebas automatizadas pasaron**, sin omisiones, mediante:

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s research/tests -v
```

## Próxima etapa

Ampliar y revisar el corpus piloto, y contrastar la arquitectura del artículo
antes de implementar L3C a 48 kHz. El generador actual necesita validación de
representatividad para PA y monitores. Quedan pendientes entrenamiento en lazo
cerrado, ejecución en el equipo Linux, síntesis continua de baja latencia,
integración C++ y evaluación simulada y física contra Patel/ANIA.

Para repetir la comprobación técnica en un directorio nuevo:

```powershell
..\.venv\Scripts\python.exe research/run_training_smoke.py --output outputs/training/repeat-gpu-pilot
```

Los resultados de ejecución, originales y modelos quedan fuera de Git. Conservar
estos archivos junto a la versión del código para reproducir el ensayo.
