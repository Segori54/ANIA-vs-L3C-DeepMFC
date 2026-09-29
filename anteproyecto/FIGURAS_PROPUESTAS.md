# Figuras propuestas

Las sugerencias también aparecen en recuadros dentro del PDF. No representan resultados ya obtenidos. Conviene exportar diagramas y gráficos a PDF vectorial e incorporarlos con `\includegraphics`; para fotografías, usar PNG o JPEG con resolución suficiente.

| Figura | Qué preparar | Dónde irá | Evidencia o referencia |
|---|---|---|---|
| Lazo acústico | Diagrama de micrófono, suma de voz y retorno, procesador, ganancia y parlante; flecha del camino acústico y puntos de captura | Marco teórico | Elaboración propia con la notación de las ecuaciones |
| ANIA y L3C-DeepMFC | Dos diagramas de operación y una línea temporal de calibración/inferencia; distinguir la variante manual | Marco teórico | Patel y Panahi (2020), Hao et al. (2025); citar cualquier adaptación |
| Montaje | Fotografía y planta con distancias, orientación y nombres de equipos; fuente de voz independiente | Metodología | Montaje físico real, una vez fijada la geometría |
| Banco de audio | Captura legible de JUCE con parámetros y versión; destacar captura y monitorización | Metodología o avances | Aplicación local; evitar presentarla como resultado acústico |
| Identificación | Camino sintético conocido frente a estimación Python/C++, error y configuración | Avances preliminares | Campaña numérica; indicar tasa, semilla, sonda y caso |
| Estabilidad | ASG por geometría con repeticiones e incertidumbre, indicando límites impuestos por protección | Resultados futuros | Campaña física pendiente |
| Calidad | Calidad frente a ganancia, con nivel útil conservado y latencia identificada | Resultados futuros | Referencias válidas y métricas compatibles |
| Recuperación | Línea temporal del cambio del camino, calidad/energía residual y eventos de recalibración | Resultados futuros | Cambios reproducibles y eventos exportados |
| Tiempo real | Percentil 99 y máximo observado frente a plazo del bloque, separando PC y Pi 4 | Resultados futuros | Sesiones sostenidas; incluir fallos y configuración |

Prioridad para presentar el anteproyecto: lazo acústico, comparación de métodos y montaje. Las curvas de desempeño corresponden a la tesis y deben completarse con mediciones, no con valores ficticios.

Referencias para investigar diagramas:

- [Patel y Panahi, texto completo](https://pmc.ncbi.nlm.nih.gov/articles/PMC7545262/)
- [L3C-DeepMFC, artículo original](https://www.isca-archive.org/interspeech_2025/hao25_interspeech.pdf)

Para ocultar todos los recuadros editoriales, sustituir `\propuestasfigurastrue` por `\propuestasfigurasfalse` en `main.tex`.
