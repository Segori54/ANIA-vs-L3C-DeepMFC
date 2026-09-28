import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "file:///C:/Users/Mat%C3%ADas%20Arancibia/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const OUT = "D:/Universidad/Tesis/Codex/presentation-package";
const RENDER = `${OUT}/rendered`;

const C = {
  ink: "#111827",
  muted: "#5B6472",
  faint: "#E8EDF3",
  panel: "#F3F5F7",
  blue: "#1769E0",
  cyan: "#55C3F0",
  pale: "#DCEEFF",
  green: "#16845B",
  amber: "#C57816",
  red: "#C84040",
  white: "#FFFFFF",
};

function box(slide, x, y, w, h, fill = C.panel, line = "none", radius = "rounded-xl") {
  return slide.shapes.add({
    geometry: "roundRect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: line, width: line === "none" ? 0 : 1 },
    borderRadius: radius,
  });
}

function txt(slide, value, x, y, w, h, size = 24, color = C.ink, bold = false, align = "left") {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = value;
  shape.text.style = {
    fontSize: size,
    typeface: "Arial",
    color,
    bold,
    alignment: align,
    verticalAlignment: "middle",
  };
  return shape;
}

function circle(slide, x, y, d, fill, label, labelColor = C.white, size = 22) {
  const s = slide.shapes.add({
    geometry: "ellipse",
    position: { left: x, top: y, width: d, height: d },
    fill,
    line: { style: "solid", fill, width: 0 },
  });
  txt(slide, label, x, y, d, d, size, labelColor, true, "center");
  return s;
}

function pill(slide, label, x, y, w, fill, color = C.ink) {
  box(slide, x, y, w, 34, fill);
  txt(slide, label, x + 8, y, w - 16, 34, 16, color, true, "center");
}

function baseSlide(presentation, number, title, kicker = "TESIS · AFC EN TIEMPO REAL") {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  txt(slide, title, 58, 24, 1120, 110, 38, C.ink, true);
  slide.shapes.add({ geometry: "rect", position: { left: 48, top: 139, width: 1184, height: 2 }, fill: C.faint, line: { style: "solid", fill: C.faint, width: 0 } });
  txt(slide, String(number).padStart(2, "0"), 1174, 674, 58, 24, 16, C.muted, false, "right");
  return slide;
}

function note(slide, body, sources = []) {
  const sourceBlock = sources.length ? `\n\n[Sources]\n${sources.map((s) => `- ${s}`).join("\n")}\n[/Sources]` : "";
  slide.speakerNotes.textFrame.setText(body + sourceBlock);
  slide.speakerNotes.setVisible(true);
}

function buildDeck() {
  const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });

  // 1 — sparse cover, Codex Grid slide-01 silhouette.
  {
    const s = p.slides.add();
    s.background.fill = C.white;
    pill(s, "PRUEBA DE CONCEPTO · ANTEPROYECTO", 48, 44, 330, C.pale, C.blue);
    txt(s, "Cancelación de feedback\nacústico en tiempo real", 48, 126, 760, 164, 56, C.ink, true);
    txt(s, "Filtros adaptativos, aprendizaje profundo e híbridos\nbajo el mismo presupuesto de latencia", 48, 312, 770, 88, 27, C.muted);
    box(s, 884, 106, 300, 430, C.panel);
    circle(s, 966, 156, 136, C.blue, "AFC", C.white, 34);
    txt(s, "48 kHz", 922, 326, 222, 48, 34, C.ink, true, "center");
    txt(s, "mono · bloques 64/128/256", 912, 376, 242, 56, 18, C.muted, false, "center");
    pill(s, "SIMULACIÓN + JUCE", 922, 462, 222, C.white, C.blue);
    txt(s, "Matías Arancibia · 2026", 48, 626, 520, 32, 20, C.ink, true);
    txt(s, "Universidad Austral de Chile", 48, 660, 520, 24, 16, C.muted);
    note(s,
      "Apertura (45–55 s). El objetivo de esta presentación es mostrar que la tesis ya cuenta con una plataforma experimental y una prueba de concepto reproducible. Todavía no presentamos un ganador: mostramos cómo podremos comparar de forma justa tres familias de solución bajo restricciones reales de latencia.");
  }

  // 2 — problem loop and research question.
  {
    const s = baseSlide(p, 2, "El feedback obliga a elegir entre ganancia, estabilidad y calidad");
    const mic = box(s, 70, 220, 210, 112, C.pale);
    const proc = box(s, 390, 220, 220, 112, C.panel);
    const spk = box(s, 720, 220, 210, 112, C.pale);
    const room = box(s, 1010, 220, 190, 112, "#FFF1DE");
    s.shapes.connect(mic, proc, { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.blue, width: 4 }, tail: { type: "arrow", width: "med", length: "med" } });
    s.shapes.connect(proc, spk, { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.blue, width: 4 }, tail: { type: "arrow", width: "med", length: "med" } });
    s.shapes.connect(spk, room, { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.amber, width: 4 }, tail: { type: "arrow", width: "med", length: "med" } });
    s.shapes.connect(room, mic, { kind: "curved", fromSide: "bottom", toSide: "bottom", line: { style: "dashed", fill: C.red, width: 4 }, tail: { type: "arrow", width: "med", length: "med" } });
    txt(s, "Micrófono", 86, 239, 178, 72, 25, C.ink, true, "center");
    txt(s, "Ganancia +\nprocesamiento", 406, 233, 188, 84, 22, C.ink, true, "center");
    txt(s, "Parlante", 736, 239, 178, 72, 25, C.ink, true, "center");
    txt(s, "Camino\nacústico", 1025, 233, 160, 84, 22, C.ink, true, "center");
    txt(s, "El sonido vuelve al micrófono, se amplifica otra vez y puede crecer hasta el howling.", 70, 376, 1130, 55, 24, C.muted, false, "center");
    box(s, 70, 477, 1130, 126, C.ink);
    txt(s, "Pregunta de investigación", 96, 493, 280, 30, 18, C.cyan, true);
    txt(s, "¿Qué estrategia entrega más ganancia estable sin sacrificar calidad, latencia ni coste?", 96, 526, 1050, 55, 28, C.white, true);
    note(s,
      "Problema y pregunta (65–75 s). El feedback acústico no es sólo un pitido: limita cuánta ganancia útil puede entregar un refuerzo sonoro. La tesis compara estrategias por cuatro ejes simultáneos —estabilidad, calidad, latencia y coste— porque optimizar uno solo puede ocultar un sistema impracticable.",
      ["https://pmc.ncbi.nlm.nih.gov/articles/PMC7545262/"]);
  }

  // 3 — three strategies, Codex Grid slide-06 silhouette.
  {
    const s = baseSlide(p, 3, "Tres estrategias, un solo protocolo de comparación");
    const cols = [58, 432, 806];
    const data = [
      ["01", "Patel / NLMS", "Calibración con sonda y FIR congelado. Reestimación sólo en pruebas controladas.", "IMPLEMENTADO · PARIDAD PENDIENTE", C.blue],
      ["02", "ML causal", "MLP, GRU y DeepMFC compacto. El ganador se elige por la frontera calidad–coste.", "ARQUITECTURAS LISTAS · SIN ENTRENAR", C.cyan],
      ["03", "Híbrido", "Patel elimina la componente predecible; una red residual trata el remanente.", "DISEÑADO · DEPENDE DEL GANADOR ML", C.green],
    ];
    data.forEach((d, i) => {
      box(s, cols[i], 184, 348, 408, C.panel);
      circle(s, cols[i] + 24, 210, 58, d[4], d[0], C.white, 19);
      txt(s, d[1], cols[i] + 24, 289, 298, 48, 28, C.ink, true);
      txt(s, d[2], cols[i] + 24, 350, 298, 128, 21, C.muted);
      pill(s, d[3], cols[i] + 24, 519, 298, C.white, d[4]);
    });
    txt(s, "Misma entrada mono · 48 kHz · misma segmentación · mismas métricas · mismo hardware final", 90, 620, 1100, 38, 22, C.blue, true, "center");
    note(s,
      "Estrategias (70–80 s). Patel representa la línea clásica de identificación del camino acústico mediante una sonda breve. La línea ML considera tres candidatos causales, pero no se atribuyen resultados antes del entrenamiento. El híbrido es una hipótesis de trabajo: separar cancelación estructurada y corrección residual puede ofrecer una mejor relación entre calidad y coste.",
      ["https://pmc.ncbi.nlm.nih.gov/articles/PMC7545262/", "https://www.repository.cam.ac.uk/bitstreams/5c9a8add-b599-4286-b5cc-53db4f9d13c1/download"]);
  }

  // 4 — platform / UI mock.
  {
    const s = baseSlide(p, 4, "Ya existe una plataforma experimental operativa");
    box(s, 54, 170, 742, 452, "#101820");
    txt(s, "AFC REALTIME LAB", 82, 192, 280, 28, 18, C.cyan, true);
    pill(s, "48 000 Hz", 568, 190, 100, "#243442", C.white);
    pill(s, "MONO", 680, 190, 80, "#243442", C.white);
    const states = ["BYPASS", "CALIBRATION", "CANCELLING", "RECALIBRATION"];
    states.forEach((st, i) => pill(s, st, 82 + i * 166, 250, 150, i === 2 ? C.blue : "#243442", C.white));
    txt(s, "ESTADO ACTUAL", 82, 306, 190, 22, 16, "#9FB2C2", true);
    txt(s, "CANCELLING", 82, 331, 260, 44, 31, C.white, true);
    txt(s, "FIR estimado", 82, 405, 210, 24, 18, "#9FB2C2");
    for (let i = 0; i < 14; i++) {
      const h = 16 + ((i * 29) % 58);
      s.shapes.add({ geometry: "rect", position: { left: 86 + i * 29, top: 500 - h, width: 17, height: h }, fill: i < 7 ? C.cyan : C.blue, line: { style: "solid", fill: "none", width: 0 } });
    }
    txt(s, "callback p50 / p95 / p99", 514, 405, 240, 24, 18, "#9FB2C2");
    txt(s, "telemetría en vivo", 514, 439, 240, 34, 23, C.white, true);
    pill(s, "SIN LOCKS", 514, 506, 112, "#243442", C.cyan);
    pill(s, "SIN ALLOC", 638, 506, 112, "#243442", C.cyan);
    const items = [
      ["Simulador", "Lazo cerrado y cambios de camino"],
      ["Métricas", "SI-SDR, ΔSNR, ERLE y coste"],
      ["Evidencia", "WAV, CSV, JSON y semilla"],
      ["Aplicación", "JUCE/ASIO y telemetría"],
    ];
    items.forEach((it, i) => {
      const y = 174 + i * 106;
      circle(s, 842, y + 4, 48, i < 3 ? C.blue : C.green, "✓", C.white, 22);
      txt(s, it[0], 908, y, 290, 35, 23, C.ink, true);
      txt(s, it[1], 908, y + 38, 290, 52, 18, C.muted);
    });
    pill(s, "IMPLEMENTADO Y VERIFICADO", 842, 590, 356, C.pale, C.blue);
    note(s,
      "Plataforma (70–80 s). Aquí conviene abrir brevemente la aplicación real. Ya están implementados el audio mono a 48 kHz, la máquina de estados, la referencia interna del parlante, la telemetría de ejecución y el laboratorio reproducible. La cifra p99 se muestra en vivo como telemetría; no se presenta todavía como resultado final de Raspberry Pi.");
  }

  // 5 — demo flow.
  {
    const s = baseSlide(p, 5, "La prueba de concepto recorre el ciclo completo");
    const xs = [56, 296, 536, 776, 1016];
    const labels = [
      ["1", "CONFIGURAR", "YAML + semilla"],
      ["2", "SIMULAR", "Lazo cerrado"],
      ["3", "PROCESAR", "Bypass / Patel"],
      ["4", "ESCUCHAR", "Audio A/B"],
      ["5", "MEDIR", "Calidad + coste"],
    ];
    const cards = labels.map((d, i) => box(s, xs[i], 253, 184, 176, i === 3 ? C.pale : C.panel));
    for (let i = 0; i < cards.length - 1; i++) {
      s.shapes.connect(cards[i], cards[i + 1], { kind: "straight", fromSide: "right", toSide: "left", line: { style: "solid", fill: C.blue, width: 4 }, tail: { type: "arrow", width: "med", length: "med" } });
    }
    labels.forEach((d, i) => {
      circle(s, xs[i] + 62, 194, 60, i === 3 ? C.blue : C.ink, d[0], C.white, 21);
      txt(s, d[1], xs[i] + 12, 276, 160, 36, 19, C.blue, true, "center");
      txt(s, d[2], xs[i] + 12, 326, 160, 60, 21, C.ink, true, "center");
    });
    box(s, 92, 492, 1096, 100, C.ink);
    txt(s, "DEMO SEGURA", 116, 507, 180, 28, 18, C.cyan, true);
    txt(s, "Estados y telemetría en vivo · efecto audible pre-renderizado · respaldo local", 116, 539, 1020, 36, 25, C.white, true);
    note(s,
      "Demo guiada (20–25 s antes de reproducir audio). La misma configuración produce la señal, el lazo, las salidas y las métricas. Luego reproducir en este orden: objetivo, sin procesamiento, Patel manual y Patel ante cambio de camino. Todas las pistas fueron igualadas a −20 dBFS RMS y tienen el mismo inicio temporal. No se genera howling físico durante la exposición.");
  }

  // 6 — preliminary results with native chart.
  {
    const s = baseSlide(p, 6, "Resultados preliminares: factibilidad, no conclusión científica");
    pill(s, "SIMULACIÓN · SEÑAL SINTÉTICA · PARÁMETROS NO CONGELADOS", 58, 154, 588, "#FFF1DE", C.amber);
    s.charts.add("bar", {
      position: { left: 54, top: 210, width: 690, height: 385 },
      categories: ["Sin proceso", "Patel manual", "Patel + cambio"],
      series: [
        { name: "SI-SDR (dB)", values: [15.07, 24.76, 17.48], fill: C.blue },
        { name: "ΔSNR (dB)", values: [0.00, 7.85, 7.29], fill: C.cyan },
        { name: "ERLE (dB)", values: [0.00, 7.85, 7.29], fill: C.green },
      ],
      hasLegend: true,
      legend: { position: "bottom", overlay: false, textStyle: { fontSize: 15, fill: C.muted } },
      dataLabels: { showValue: true, position: "outEnd", textStyle: { fontSize: 14, fill: C.ink, bold: true } },
      chartFill: C.white,
      chartLine: { style: "solid", fill: C.white, width: 0 },
      plotAreaFill: { type: "none" },
      plotAreaLine: { style: "solid", fill: C.white, width: 0 },
      xAxis: { textStyle: { fontSize: 14, fill: C.ink }, line: { style: "solid", fill: C.faint, width: 1 } },
      yAxis: { min: 0, max: 30, majorUnit: 5, title: { text: "dB", textStyle: { fontSize: 15, fill: C.muted } }, textStyle: { fontSize: 13, fill: C.muted }, majorGridlines: { style: "solid", fill: C.faint, width: 1 } },
      barOptions: { direction: "column", grouping: "clustered", gapWidth: 80 },
    });
    const calls = [
      ["+9,70 dB", "SI-SDR manual\nvs. sin proceso", C.blue],
      ["7,85 dB", "feedback reducido\n(ERLE manual)", C.green],
      ["0,24–0,26", "RTF en Python\n(no callback JUCE)", C.amber],
    ];
    calls.forEach((d, i) => {
      box(s, 790, 207 + i * 130, 402, 108, C.panel);
      txt(s, d[0], 814, 219 + i * 130, 180, 42, 30, d[2], true);
      txt(s, d[1], 1000, 214 + i * 130, 166, 62, 18, C.ink, true);
    });
    txt(s, "Condición: 48 kHz · 8 s · SNR 20 dB · margen 1,5 dB · FIR real 512 / estimado 128 · semilla 20260826", 58, 621, 1130, 44, 18, C.muted, false, "center");
    note(s,
      "Resultados preliminares (75–90 s). La figura muestra una sola condición determinista de simulación. En ella, Patel manual mejora el SI-SDR aproximadamente 9,7 dB y reduce la componente de feedback cerca de 7,85 dB. El cambio de camino degrada el resultado y hace visible la necesidad de detección y recalibración. El RTF pertenece al simulador Python y no debe confundirse con el p99 del callback JUCE. Estos números demuestran que la cadena funciona; no comparan todavía contra ML ni permiten generalizar.",
      ["file:demo/evidencia/manifest.json", "file:demo/evidencia/results.csv"]);
  }

  // 7 — roadmap and close.
  {
    const s = baseSlide(p, 7, "El próximo hito: de plataforma a comparación científica");
    const steps = [
      ["1", "DATASETS", "VCTK · VocalSet · MUSDB18-HQ", "Separación por identidad"],
      ["2", "PATEL", "Barrido de sonda y taps", "Congelar en validación"],
      ["3", "ML + ONNX", "MLP · GRU · DeepMFC", "Frontera calidad–coste"],
      ["4", "RASPBERRY PI 4", "64 / 128 / 256 muestras", "30 min sin xruns"],
    ];
    steps.forEach((d, i) => {
      const x = 56 + i * 294;
      box(s, x, 190, 260, 274, i === 3 ? C.pale : C.panel);
      circle(s, x + 22, 211, 50, i === 3 ? C.green : C.blue, d[0], C.white, 18);
      txt(s, d[1], x + 22, 282, 216, 32, 21, C.blue, true);
      txt(s, d[2], x + 22, 327, 216, 58, 19, C.ink, true);
      txt(s, d[3], x + 22, 393, 216, 42, 17, C.muted);
    });
    box(s, 56, 509, 1136, 116, C.ink);
    txt(s, "APORTE DE LA TESIS", 82, 524, 260, 24, 17, C.cyan, true);
    txt(s, "Una comparación reproducible entre estabilidad, calidad, latencia y coste — incluso si ML no supera a Patel.", 82, 552, 1055, 56, 27, C.white, true);
    note(s,
      "Cierre (60–70 s). El siguiente trabajo es cerrar los recursos externos, congelar Patel con validación, entrenar y seleccionar el candidato ML, exportarlo a ONNX y medir en Raspberry Pi 4. El resultado científicamente valioso no depende de que ML gane: la contribución es una comparación reproducible que muestre qué se obtiene y qué se paga en estabilidad, calidad, latencia y coste.",
      ["https://www.cstr.ed.ac.uk/downloads/", "https://zenodo.org/records/1492453/files/114_Paper.pdf", "https://sigsep.github.io/datasets/musdb.html"]);
  }

  return p;
}

async function writeBlob(path, blob) {
  await fs.writeFile(path, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  await fs.mkdir(RENDER, { recursive: true });
  await fs.mkdir(`${OUT}/demo/evidencia`, { recursive: true });
  await fs.mkdir(`${OUT}/demo/respaldo`, { recursive: true });
  const presentation = buildDeck();
  for (const [i, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(i + 1).padStart(2, "0")}`;
    await writeBlob(`${RENDER}/${stem}.png`, await presentation.export({ slide, format: "png", scale: 1 }));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(`${RENDER}/${stem}.layout.json`, await layout.text());
  }
  await writeBlob(`${RENDER}/montage.webp`, await presentation.export({ format: "webp", montage: true, scale: 1 }));
  await fs.copyFile(`${RENDER}/slide-06.png`, `${OUT}/demo/evidencia/figura_resultados_preliminares.png`);
  await fs.copyFile(`${RENDER}/slide-04.png`, `${OUT}/demo/respaldo/captura_telemetria.png`);
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(`${OUT}/AFC_Tesis_Pitch.pptx`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
