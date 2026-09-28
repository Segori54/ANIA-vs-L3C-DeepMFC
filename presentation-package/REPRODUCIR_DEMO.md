# Reproducción exacta del experimento de presentación

Desde la raíz del repositorio:

```powershell
python -m research.afc_lab.cli run research/configs/presentation_demo.yaml
python -m research.afc_lab.presentation_export outputs/presentation-demo/raw presentation-package/demo
```

La configuración congelada también se incluye en `demo/evidencia/presentation_demo.yaml`. La semilla es `20260826` y la muestra es una señal sintética determinista tipo voz, reservada sólo para demostración y excluida de cualquier entrenamiento.

Los datos numéricos se encuentran en:

- `demo/evidencia/manifest.json`
- `demo/evidencia/results.csv`
- `demo/evidencia/summary.json`

Interpretación permitida: resultado preliminar en simulación. No representa una campaña estadística, una comparación contra ML ni desempeño validado en Raspberry Pi.
