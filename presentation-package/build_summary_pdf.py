from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


OUT = Path(r"D:\Universidad\Tesis\Codex\presentation-package\AFC_Tesis_Resumen.pdf")
W, H = landscape(A4)

INK = HexColor("#111827")
MUTED = HexColor("#5B6472")
PANEL = HexColor("#F3F5F7")
FAINT = HexColor("#E8EDF3")
BLUE = HexColor("#1769E0")
CYAN = HexColor("#55C3F0")
PALE = HexColor("#DCEEFF")
GREEN = HexColor("#16845B")
AMBER = HexColor("#C57816")
WHITE = HexColor("#FFFFFF")

pdfmetrics.registerFont(TTFont("ArialDoc", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("ArialDoc-Bold", r"C:\Windows\Fonts\arialbd.ttf"))


def text(c: canvas.Canvas, value: str, x: float, y: float, size: float, color=INK, bold=False) -> None:
    c.setFillColor(color)
    c.setFont("ArialDoc-Bold" if bold else "ArialDoc", size)
    c.drawString(x, y, value)


def wrapped(c: canvas.Canvas, value: str, x: float, y: float, width: float, size: float, leading: float, color=INK, bold=False) -> float:
    font = "ArialDoc-Bold" if bold else "ArialDoc"
    words = value.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if stringWidth(candidate, font, size) <= width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    c.setFillColor(color)
    c.setFont(font, size)
    for index, item in enumerate(lines):
        c.drawString(x, y - index * leading, item)
    return y - len(lines) * leading


def panel(c: canvas.Canvas, x: float, y: float, width: float, height: float, fill=PANEL) -> None:
    c.setFillColor(fill)
    c.setStrokeColor(fill)
    c.roundRect(x, y, width, height, 9, fill=1, stroke=0)


def status(c: canvas.Canvas, x: float, y: float, label: str, fill, width: float) -> None:
    c.setFillColor(fill)
    c.roundRect(x, y, width, 18, 9, fill=1, stroke=0)
    c.setFillColor(WHITE if fill != PALE else BLUE)
    c.setFont("ArialDoc-Bold", 7.2)
    c.drawCentredString(x + width / 2, y + 5.2, label)


def build() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=(W, H))
    c.setTitle("Resumen de tesis - Cancelación de feedback acústico")
    c.setAuthor("Matias Arancibia")
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Header.
    text(c, "PRUEBA DE CONCEPTO DE TESIS", 34, H - 38, 9, BLUE, True)
    text(c, "Cancelación de feedback acústico en tiempo real", 34, H - 72, 24, INK, True)
    text(c, "Comparación reproducible de filtros adaptativos, ML causal e híbridos bajo latencia controlada", 34, H - 96, 12, MUTED)
    c.setStrokeColor(FAINT)
    c.setLineWidth(1)
    c.line(34, H - 112, W - 34, H - 112)

    # Problem and research question.
    panel(c, 34, H - 244, 350, 112, PALE)
    text(c, "PROBLEMA", 50, H - 154, 9, BLUE, True)
    wrapped(c, "El sonido del parlante vuelve al micrófono, se amplifica y limita la ganancia útil antes del howling.", 50, H - 177, 316, 13, 17, INK, True)
    text(c, "Pregunta", 50, H - 222, 8, MUTED, True)
    wrapped(c, "¿Qué estrategia ofrece más estabilidad sin sacrificar calidad, latencia ni coste?", 103, H - 222, 260, 9.5, 12, MUTED)

    # Three strategies.
    text(c, "TRES ESTRATEGIAS, UN PROTOCOLO", 410, H - 139, 10, INK, True)
    cards = [
        ("Patel / NLMS", "Sonda breve y FIR congelado", "IMPLEMENTADO*", BLUE),
        ("ML causal", "MLP, GRU y DeepMFC compacto", "LISTO PARA ENTRENAR", CYAN),
        ("Híbrido", "Patel más red residual", "PENDIENTE DEL ML", GREEN),
    ]
    for i, (title, body, label, color) in enumerate(cards):
        x = 410 + i * 132
        panel(c, x, H - 244, 122, 92)
        c.setFillColor(color)
        c.circle(x + 16, H - 170, 7, fill=1, stroke=0)
        text(c, title, x + 28, H - 174, 10.5, INK, True)
        wrapped(c, body, x + 12, H - 195, 98, 8.7, 11, MUTED)
        status(c, x + 8, H - 235, label, PALE, 106)

    # Current state.
    text(c, "QUÉ YA ESTÁ DISPONIBLE", 34, H - 278, 10, INK, True)
    state_items = [
        ("Simulador", "lazo cerrado y cambio de camino"),
        ("Aplicación JUCE", "48 kHz mono, estados y telemetría"),
        ("Métricas", "SI-SDR, Delta SNR, ERLE, RTF y percentiles"),
        ("Reproducibilidad", "YAML, semilla, WAV, CSV y JSON"),
    ]
    for i, (head, body) in enumerate(state_items):
        x = 34 + (i % 2) * 177
        y = H - 345 - (i // 2) * 65
        panel(c, x, y, 166, 53)
        c.setFillColor(BLUE)
        c.circle(x + 18, y + 27, 9, fill=1, stroke=0)
        text(c, "OK", x + 11.4, y + 24, 6.5, WHITE, True)
        text(c, head, x + 34, y + 31, 10.5, INK, True)
        wrapped(c, body, x + 34, y + 17, 122, 8.2, 10, MUTED)

    # Preliminary result.
    text(c, "RESULTADO PRELIMINAR EN SIMULACIÓN", 410, H - 278, 10, INK, True)
    panel(c, 410, H - 422, 386, 126)
    labels = ["Sin proceso", "Patel manual", "Patel + cambio"]
    values = [15.07, 24.76, 17.48]
    for i, (label, value) in enumerate(zip(labels, values)):
        y = H - 329 - i * 32
        text(c, label, 424, y, 8.5, MUTED)
        c.setFillColor(FAINT)
        c.roundRect(500, y - 2, 205, 11, 5, fill=1, stroke=0)
        c.setFillColor(BLUE)
        c.roundRect(500, y - 2, 205 * value / 30.0, 11, 5, fill=1, stroke=0)
        text(c, f"{value:.2f} dB", 715, y, 8.5, INK, True)
    text(c, "+9.70 dB SI-SDR con Patel manual", 424, H - 411, 10, BLUE, True)
    text(c, "Delta SNR / ERLE manual: 7.85 dB", 608, H - 411, 9, GREEN, True)

    # Next milestone and caveat.
    panel(c, 34, 42, W - 68, 94, INK)
    text(c, "PRÓXIMO HITO", 52, 112, 9, CYAN, True)
    text(c, "Datasets -> barrido Patel -> selección ML -> ONNX -> Raspberry Pi 4", 52, 88, 15, WHITE, True)
    wrapped(c, "La contribución es comparar estabilidad, calidad, latencia y coste. El resultado sigue siendo válido si ML no supera a Patel.", 52, 65, 500, 9.5, 12, WHITE)
    status(c, W - 237, 78, "SIMULACIÓN - NO RESULTADO FINAL", AMBER, 185)

    # Human-readable sources.
    c.setFillColor(MUTED)
    c.setFont("ArialDoc", 6.8)
    c.drawRightString(W - 34, 24, "Fuentes: Patel et al., PMC7545262 | DeepMFC, Cambridge Repository | Configuración y semilla: evidencia local del paquete | *Paridad pendiente")

    c.showPage()
    c.save()


if __name__ == "__main__":
    build()
