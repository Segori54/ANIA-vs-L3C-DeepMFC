# Anteproyecto de tesis — borrador del 28 de septiembre de 2026

Archivo principal: `main.tex`. Capítulos editables: `Texs/`. Se conserva el título, logo, autores, profesores, disposición de portada, fuente Times, tamaño 12 pt, márgenes de una pulgada y organización por archivos del original.

Cambios técnicos mínimos: se retiraron opciones inválidas de mathptmx, se eliminó el conflicto subfig/subcaption y se ajustó el encabezado para el documento de una cara. La fecha se actualizó en portada y encabezados. Se permitieron transiciones continuas entre algunas secciones para evitar páginas con un solo párrafo, manteniendo los márgenes y la tipografía.

El texto propone una comparación ANIA / L3C-DeepMFC y distingue resultados esperados de avances internos. Las propuestas de figuras aparecen como recuadros; para ocultarlas, cambiar `\propuestasfigurastrue` por `\propuestasfigurasfalse` en main.tex.

## Decisiones para la siguiente revisión

- Confirmar con el profesor el cronograma propuesto hasta el 19 de marzo de 2027. La fecha original del 30 de octubre de 2026 no se trata como plazo confirmado.
- Confirmar si se conserva el título amplio de la portada o se explicitan ANIA y L3C-DeepMFC.
- Concretar equipos, geometrías, corpus y tolerancias después del piloto.
- Ampliar el estado del arte y las referencias de métricas al cerrar el protocolo. Las referencias centrales y las de SI-SDR y STOI fueron verificadas en publicaciones o páginas de sus autores.
- Los conteos preliminares se transcribieron del estado del repositorio; esta edición del documento no vuelve a ejecutar las campañas científicas.

## Edición y compilación

Abrir esta carpeta en Visual Studio Code. Ejecutar la tarea «Compilar anteproyecto» (Terminal > Ejecutar tarea), o `powershell -ExecutionPolicy Bypass -File .\compilar.ps1` desde esta carpeta. El script usa el compilador portátil guardado en `../local-builds/latex-tools/tectonic.exe`. La primera compilación descarga los paquetes necesarios; después reutiliza la caché local. El PDF se escribe en `pdf/main.pdf`.

Para Overleaf, subir main.tex y las carpetas Texs e Imágenes, y seleccionar main.tex como documento principal. El contenido no depende de los scripts locales.

El compilador utilizado es Tectonic 0.17.0 para Windows x64, obtenido de su publicación oficial: https://github.com/tectonic-typesetting/tectonic/releases/tag/tectonic%400.17.0 . SHA-256 del ZIP: f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f.
