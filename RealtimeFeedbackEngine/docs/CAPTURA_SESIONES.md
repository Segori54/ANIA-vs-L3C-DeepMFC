# Captura de sesiones reales

La captura guarda el audio del micrófono. Es independiente de Run, de Calibrate AFC
y del botón Observación. No activa ruido, cancelación ni recalibración automática.

## Primera sesión física

1. Mantener fijas geometría y ganancias físicas; desactivar monitorización directa.
2. Con audio detenido, seleccionar dispositivo y 16 kHz o 48 kHz. Run verifica la
   frecuencia efectiva: si el dispositivo no admite la solicitada, no arranca audio.
   No hay remuestreo automático. Se solicitan 128 muestras (8 ms o 2.67 ms).
3. Seleccionar Cambiar destino si es necesario. El destino inicial es la carpeta
   Referencia ASNI AFC Patel del workspace; la selección queda junto al ejecutable
   en capture-settings.json. No seleccionar una carpeta que contenga información
   ajena al ensayo. Cada captura crea un directorio nuevo sin sobrescribir sesiones.
4. Pulsar Iniciar captura y esperar Grabando. El indicador muestra duración y estado.
5. Pulsar Calibrate AFC. Esperar el resultado; mantener el modelo y el montaje.
   El ruido de ensayo queda apagado al terminar la calibración, como antes.
6. Realizar el ensayo y registrar observaciones y SPL opcional con Observación.
   Para evaluar estabilidad, comparar bypass/Patel y modificar sólo ganancia digital.
7. Pulsar Finalizar captura. El audio continúa. Esperar Guardada y Abrir carpeta.
   Stop/disconexión también cierran la captura. Una captura incompleta no se aprueba.
8. Desde Referencia ASNI AFC Patel ejecutar:

   `python -m referencia audit-session --session "RUTA_DE_LA_SESION"`

El informe se guarda en resumen_comparacion/audit_<id>, fuera de la sesión original.
Audita archivos, cronología, modelos y resta causal; no certifica calidad perceptual
ni ganancia acústica estable. Repetir el montaje a ambas tasas sin ocultar diferencias
de latencia. No es obligatorio que un dispositivo admita 16 kHz nativos.

## Qué contienen los archivos

- manifest.json: integridad, dispositivo, parámetros efectivos, build/hash, canales,
  segmentos, historial inicial y SHA-256 de cada archivo exportado. Se escribe como
  incompleto al comenzar y sólo cambia a completo tras cerrar y verificar escrituras.
- audio_0001.wav y siguientes: segmentos de 60 s, IEEE float32, siete canales,
  sin normalización, compresión ni remuestreo. Aproximadamente 80.6 MB/min a 48 kHz.
- initial_history.f32: salida anterior a la captura, orden cronológico, float32
  little-endian. Permite auditar capturas iniciadas con un modelo ya activo.
- blocks.csv: secuencia y posición en muestras del callback, duración y tiempo medido.
- events.jsonl: cambios efectivos con índice exacto de muestra, estado, método,
  modelo/calibración, mute, ganancia solicitada, ruido y actuación de protección.
- modelos/: parámetros y coeficientes JSON/CSV, resultado de validación y posición
  de activación cuando la hubo. Un modelo aceptado por el trabajador puede no llegar
  a activarse si se cancela; la cronología del audio es la autoridad sobre su uso.
- calibraciones.json: transiciones de estado/resultado con sus índices. Los estados
  identification=2 y validation=3 delimitan sondas y sus colas. Cada límite final es
  la siguiente transición o el final de captura. Cancelaciones quedan explícitas.
- telemetry.csv: RMS, límite de salida, tiempos y observaciones; el tiempo de la
  observación GUI corresponde a la última frontera de bloque producida.

Orden de canales: microphone_raw, microphone_used, feedback, clean, output, probe,
gain. Los primeros dos distinguen entrada original de saneamiento de no finitos.
`clean_valid` indica dónde existen feedback/clean; fuera de esos intervalos ambos
son cero. En bypass válido: feedback=0 y clean=microphone_used.
`output` es la referencia digital posterior a ganancia, ruido, protección y rampa;
no es una medición analógica del altavoz. `probe` conserva la sonda programada que
utilizó el estimador. Los datos float32 conservan su escala y bits.

La captura de rechazo por clipping puede estar completa e íntegra. Eso no convierte
su calibración en aceptada. La auditoría lo distingue de archivos perdidos/corruptos.

## Tiempo real y fallos

La cola preasignada cubre al menos ocho segundos, contando también registros de
bloque. El callback sólo copia datos y usa atómicos lock-free; no espera al disco,
no serializa JSON ni reserva memoria. Un escritor persistente drena audio y dos
colas separadas para modelos del trabajador y observaciones de GUI.

Cola llena, metadatos perdidos o error de disco paran la captura y marcan fallo;
el audio continúa. No se rellenan huecos ni se concatenan discontinuidades como
si fueran audio continuo. Guardando indica cierre/drenaje; Guardada confirma cierre.
En un cierre inesperado el manifest sigue incompleto aunque existan WAV parciales.

El tiempo en blocks.csv cubre el callback hasta antes de publicar su registro final
de captura. El benchmark de integración mide la llamada completa, incluida esa
publicación, con el mismo modelo, fuente y ritmo en los casos apagado/encendido.
Ni ese benchmark sintético ni p99 por debajo del plazo garantizan ausencia de
glitches de hardware. Registrar también máximos y deadlines en la sesión real.

## Pruebas

Compilar la aplicación y SessionCaptureTest, ejecutar CTest; luego las pruebas
Python de la referencia. SessionCaptureTest genera sesiones sintéticas bajo
Referencia ASNI AFC Patel/build/session_capture_tests y un latest.txt que localiza
la campaña reciente. No abre dispositivos físicos. summary.json contiene tiempos
del callback completo y asignaciones; python_audits.json contiene la reconstrucción.

Se ensayan ambas tasas, inicio con modelo/historial, varios modelos por captura,
rechazo de validación independiente, cancelación, clipping, detención de dispositivo,
desborde y fallo de disco inyectado. La prueba usa segmentos de 0.25 s para forzar
límites dentro de las sondas; la aplicación utiliza 60 s.

La ventana FIR máxima normal conserva unos 42.67 ms: 683 taps a 16 kHz, 2048 a
48 kHz. El margen de inicio de 32 muestras conserva la política actual del Engine.
El detector experimental existente no dispara recalibración; su ampliación sigue
fuera de esta etapa.
