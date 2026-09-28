"""Reproducible experiments. Every result includes its input and source provenance."""
import platform
import shutil
import sys
from time import perf_counter

import numpy as np

from .fixtures import make_case
from .oracle import (CausalReplay, complete, engine_matched, improvement, paper_core,
                     predict, relative_error, solve, toeplitz)
from .storage import (ROOT, Bridge, csv_rows, digest, load_signal, new_id, read_json,
                      save_model, save_signal, write_json)


def provenance(directory, bridge):
    sources = list((ROOT / "referencia").glob("*.py")) + list((ROOT / "comparador_cpp").glob("*"))
    engine_dir = ROOT.parent / "RealtimeFeedbackEngine/Source/Processors"
    sources += [engine_dir / "PatelEstimator.cpp", engine_dir / "PatelEstimator.h"]
    hashes = {}
    for path in sources:
        if path.is_file():
            relative = path.relative_to(ROOT.parent)
            dest = directory / "sources" / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            hashes[str(relative)] = digest(path)
    return {"python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
            "cpp_executable": str(bridge.executable), "cpp_sha256": digest(bridge.executable),
            "source_sha256": hashes, "timings": "offline; not audio callback latency"}


def mathematical_checks(bridge, directory, rate, seeds, tolerances):
    rows = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        for n in (1, 4, 16, 64):
            r = .7 ** np.arange(n, dtype=np.float64)
            truth = rng.normal(size=n)
            b = toeplitz(r) @ truth
            oracle, residual = solve(r, b)
            cpp = bridge.call({"operation": "solve", "r": r.tolist(), "b": b.tolist()},
                              directory / f"solve_{seed}_{n}")
            oracle_error = relative_error(oracle, truth)
            cpp_error = relative_error(cpp["solution"], oracle) if cpp["ok"] else 1e99
            rows.append({"profile": "known_system", "seed": seed, "order": n,
                         "oracle_error": oracle_error, "cpp_error": cpp_error, "residual": residual,
                         "passed": oracle_error <= tolerances["oracle"] and cpp_error <= tolerances["cpp_solver"]})
        order = round(.004 * rate)
        truth = np.zeros(order)
        truth[round(.001 * rate)] = .25
        truth[round(.003 * rate)] = -.12
        p = np.pad(rng.normal(0, .03, round(.160 * rate)).astype(np.float32), (0, order))
        m = np.convolve(p.astype(np.float64), truth)[:len(p)].astype(np.float32)
        model = paper_core(p, m, order)
        # Same equation, independent solution through the public C++ solver API.
        from .oracle import correlate
        r, b = correlate(p, p, order), correlate(m, p, order)
        cpp = bridge.call({"operation": "solve", "r": r.tolist(), "b": b.tolist()},
                          directory / f"paper_core_{seed}")
        save_model(directory / f"paper_core_{seed}" / "oracle_model.json", model)
        write_json(directory / f"paper_core_{seed}" / "capture.json", {
            "probe": save_signal(directory / f"paper_core_{seed}" / "probe.f32", p, rate),
            "microphone": save_signal(directory / f"paper_core_{seed}" / "microphone.f32", m, rate)})
        error = relative_error(cpp["solution"], model["coefficients"])
        truth_error = relative_error(model["coefficients"], truth)
        rows.append({"profile": "paper_core", "seed": seed, "order": order,
                     "oracle_error": truth_error, "cpp_error": error, "residual": model["residual"],
                     "passed": cpp["ok"] and error <= tolerances["cpp_solver"] and truth_error <= 1e-6})
    csv_rows(directory / "checks.csv", rows)
    return rows


def block_check(signal, model):
    reference = predict(signal, model["coefficients"], model["delaySamples"])
    errors = []
    for partition in ((1,), (64,), (128,), (256,), (1, 17, 64, 3, 256, 129)):
        replay, parts, pos, i = CausalReplay(model["coefficients"], model["delaySamples"]), [], 0, 0
        while pos < len(signal):
            size = partition[i % len(partition)]
            parts.append(replay.process(signal[pos:pos + size]))
            pos += size
            i += 1
        errors.append(relative_error(np.concatenate(parts), reference))
    return max(errors)


def run(rate, executable=None):
    if rate not in (16000, 48000):
        raise ValueError("Only 16000 and 48000 Hz are supported")
    bridge = Bridge(executable)
    base = ROOT / f"{rate // 1000}khz"
    settings = read_json(base / "configuracion.json")
    if settings["sample_rate"] != rate:
        raise ValueError("Configuration sample rate mismatch")
    if settings["pre_onset_margin_samples"] != 32:
        raise ValueError("The current Engine uses a fixed 32-sample onset margin")
    run_id = new_id()
    result_dir = base / "resultados" / run_id
    result_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "run_id": run_id, "status": "running", "config": settings,
                "provenance": provenance(result_dir, bridge)}
    write_json(result_dir / "manifest.json", manifest)
    tol = settings["tolerances"]
    math_rows = mathematical_checks(bridge, result_dir / "mathematics", rate, settings["seeds"], tol)
    rows = []
    for condition in settings["conditions"]:
        for seed in settings["seeds"]:
            case_id = f"{condition}_{seed}"
            print(f"{rate} Hz | {case_id}", flush=True)
            signals, cfg, truth, true_delay = make_case(rate, condition, seed, settings)
            captures = base / "capturas" / run_id / case_id
            descriptors = {k: save_signal(captures / f"{k}.f32", v, rate) for k, v in signals.items()}
            # Both sides read the stored/quantized bytes, rather than unrounded generators.
            signals = {k: load_signal(v) for k, v in descriptors.items()}
            truth_spec = save_signal(captures / "true_path.f32", truth, rate)
            write_json(captures / "manifest.json", {"schema_version": 1, "sample_rate": rate,
                "seed": seed, "condition": condition, "signals": descriptors, "true_path": truth_spec,
                "true_delay_samples": true_delay, "config": cfg,
                "probe_active_samples": round(rate * (.160 if condition == "short160" else settings["probe_seconds"])),
                "validation_active_samples": round(rate * settings["validation_seconds"]), "tail_samples": sum((cfg["maximumDelaySamples"], cfg["maximumFilterLength"]))})
            start = perf_counter()
            oracle = engine_matched(signals, cfg)
            oracle_seconds = perf_counter() - start
            start = perf_counter()
            cpp = bridge.call({"operation": "estimate", "sample_rate": rate, "config": cfg, "signals": descriptors},
                              result_dir / "cpp" / case_id)
            cpp_seconds = perf_counter() - start
            models = base / "modelos" / run_id / case_id
            models.mkdir(parents=True)
            save_model(models / "oracle.json", oracle)
            save_model(models / "cpp.json", cpp)
            row = {"rate": rate, "condition": condition, "seed": seed, "run_id": run_id,
                   "oracle_result": oracle["result"], "cpp_result": cpp["result"],
                   "oracle_seconds_offline": oracle_seconds, "cpp_process_seconds_offline": cpp_seconds,
                   "model_path": str((models / "cpp.json").relative_to(ROOT))}
            checks = {"status_agreement": oracle["result"] == cpp["result"]}
            expected = {"no_return": "noReturn", "clipped": "clipped", "nonfinite": "invalid"}.get(condition, "accepted")
            checks["expected_status"] = oracle["result"] == cpp["result"] == expected
            if oracle["coefficients"] and cpp["coefficients"]:
                full_o, full_c = complete(oracle), complete(cpp)
                error = relative_error(full_c, full_o)
                db_diff = abs(cpp["validationImprovementDb"] - oracle["validationImprovementDb"])
                cpp_prediction = predict(signals["validationProbe"], cpp["coefficients"], cpp["delaySamples"])
                replay_error = block_check(signals["validationProbe"][:2048], cpp)
                row.update(response_relative_error=error, validation_db_difference=db_diff,
                           cpp_validation_db=cpp["validationImprovementDb"], oracle_validation_db=oracle["validationImprovementDb"],
                           recomputed_cpp_validation_db=improvement(signals["validationMicrophone"], cpp_prediction),
                           truth_relative_error=relative_error(full_c, truth),
                           cpp_delay_samples=cpp["delaySamples"], cpp_delay_ms=1000 * cpp["delaySamples"] / rate,
                           truth_delay_ms=1000 * true_delay / rate, cpp_taps=len(cpp["coefficients"]), replay_error=replay_error)
                checks["response_agreement"] = error <= tol["identification"]
                checks["causal_blocks"] = replay_error <= tol["replay"]
                if condition in ("noise40", "noise20"):
                    checks["noisy_prediction"] = db_diff <= tol["noisy_prediction_db"]
                if condition in ("simple", "reflections", "short160"):
                    checks["known_delay"] = abs(cpp["delaySamples"] - true_delay) <= tol["delay_samples"]
                # Weak starts and energetic trimming need not preserve the first physical tap.
                row["note"] = ("Inicio fisico debil: evaluar respuesta completa, no exigir D identico al primer tap."
                               if condition == "weak_onset" else "")
            row["passed"] = all(checks.values())
            row["failed_checks"] = ";".join(k for k, v in checks.items() if not v)
            write_json(result_dir / f"{case_id}.json", {"metrics": row, "checks": checks})
            rows.append(row)
            csv_rows(result_dir / "results.csv", rows)
    passed = all(r["passed"] for r in rows + math_rows)
    manifest.update(status="completed", passed=passed, case_count=len(rows), math_check_count=len(math_rows))
    write_json(result_dir / "manifest.json", manifest)
    write_json(result_dir / "results.json", rows)
    write_json(base / "latest.json", {"run_id": run_id})
    failures = [f"{r['condition']}/{r['seed']}: {r['failed_checks']}" for r in rows if not r["passed"]]
    report = [f"# Campaña {rate} Hz", "", f"Ejecución: {run_id}", "",
              f"Pruebas matemáticas: {sum(r['passed'] for r in math_rows)}/{len(math_rows)}.",
              f"Casos comparados con C++: {sum(r['passed'] for r in rows)}/{len(rows)}.", "",
              f"Máximo error relativo de respuesta C++/oráculo: {max((r.get('response_relative_error', 0) for r in rows)):.6g}.",
              f"Máximo error relativo del solucionador C++: {max(r['cpp_error'] for r in math_rows):.6g}.", "",
              "## Discrepancias", "", *(failures or ["Ninguna dentro de los criterios fijados."]), "",
              "## Alcance", "", "Identificación sintética y comparación numérica. Los tiempos son offline e incluyen",
              "arranque/intercambio de archivos en C++. No se ha validado audio físico, callback, detector",
              "ni adaptación automática. Coincidencia con el oráculo no implica exactitud física perfecta."]
    (result_dir / "informe.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Finalizado {rate}: {sum(r['passed'] for r in rows)}/{len(rows)} casos. {result_dir}", flush=True)
    return passed, run_id


def response_at(h, rate, frequencies):
    return np.exp(-2j * np.pi * frequencies[:, None] * np.arange(len(h))[None, :] / rate) @ h


def compare(run_ids=None):
    records, manifests = {}, {}
    for rate in (16000, 48000):
        base = ROOT / f"{rate // 1000}khz"
        run_id = run_ids[rate] if run_ids else read_json(base / "latest.json")["run_id"]
        directory = base / "resultados" / run_id
        manifest = read_json(directory / "manifest.json")
        if manifest["status"] != "completed":
            raise ValueError("Cannot compare incomplete campaigns")
        manifests[rate] = manifest
        records[rate] = {(r["condition"], r["seed"]): r for r in read_json(directory / "results.json")}
    if records[16000].keys() != records[48000].keys():
        raise ValueError("Campaigns do not contain the same conditions/seeds")
    if manifests[16000]["provenance"]["source_sha256"] != manifests[48000]["provenance"]["source_sha256"]:
        raise ValueError("Campaigns used different source versions; rerun both rates")
    out = ROOT / "resumen_comparacion" / new_id()
    out.mkdir(parents=True, exist_ok=False)
    frequencies = np.linspace(100, 7000, 256)
    paired = []
    for key, a in records[16000].items():
        b = records[48000][key]
        row = {"condition": key[0], "seed": key[1], "passed_16": a["passed"], "passed_48": b["passed"],
               "status_16": a["cpp_result"], "status_48": b["cpp_result"]}
        if "cpp_validation_db" in a and "cpp_validation_db" in b:
            h16, h48 = complete(read_json(ROOT / a["model_path"])), complete(read_json(ROOT / b["model_path"]))
            f16, f48 = response_at(h16, 16000, frequencies), response_at(h48, 48000, frequencies)
            mag16, mag48 = 20 * np.log10(np.maximum(np.abs(f16), 1e-12)), 20 * np.log10(np.maximum(np.abs(f48), 1e-12))
            row.update(validation_db_16=a["cpp_validation_db"], validation_db_48=b["cpp_validation_db"],
                       validation_delta_db=b["cpp_validation_db"] - a["cpp_validation_db"],
                       delay_ms_16=a["cpp_delay_ms"], delay_ms_48=b["cpp_delay_ms"],
                       magnitude_rms_difference_db=float(np.sqrt(np.mean((mag16 - mag48)**2))),
                       truth_error_16=a["truth_relative_error"], truth_error_48=b["truth_relative_error"])
            csv_rows(out / "frequencies" / f"{key[0]}_{key[1]}.csv", [
                {"frequency_hz": float(f), "magnitude_db_16": float(m16), "magnitude_db_48": float(m48),
                 "phase_radians_16": float(np.angle(v16)), "phase_radians_48": float(np.angle(v48))}
                for f, m16, m48, v16, v48 in zip(frequencies, mag16, mag48, f16, f48)])
        paired.append(row)
    csv_rows(out / "comparacion.csv", paired)
    write_json(out / "manifest.json", {"schema_version": 1, "campaigns": manifests, "common_band_hz": [100, 7000],
                                        "cross_rate_comparison": "descriptive, not a live-audio equivalence test"})
    lines = ["# Comparación 16 y 48 kHz", "", "| Condición | Aprobados 16 kHz | Aprobados 48 kHz | Δ predicción dB (48−16), media |",
             "|---|---:|---:|---:|"]
    for condition in manifests[16000]["config"]["conditions"]:
        group = [r for r in paired if r["condition"] == condition]
        values = [r["validation_delta_db"] for r in group if "validation_delta_db" in r]
        delta = f"{np.mean(values):.4f}" if values else "N/A"
        lines.append(f"| {condition} | {sum(r['passed_16'] for r in group)}/{len(group)} | {sum(r['passed_48'] for r in group)}/{len(group)} | {delta} |")
    lines += ["", "## Interpretación y límites", "",
              "Aprobado significa acuerdo numérico y controles sintéticos definidos, no validación acústica.",
              "Los errores respecto del camino verdadero se conservan separados del acuerdo Python/C++.",
              "Las diferencias entre tasas son descriptivas: se comparan realizaciones independientes y",
              "discretizaciones de un mismo diseño temporal. No se exige igualdad tap a tap.",
              "Banda común: 100–7000 Hz; magnitudes y fases completas en frequencies/.",
              "El margen de inicio del Engine conserva 32 muestras: 2 ms a 16 kHz y 0.667 ms a 48 kHz.",
              "La ventana FIR es 683/16000 = 42.6875 ms y 2048/48000 = 42.6667 ms.",
              "Pendiente: exportación en vivo, dispositivo a ambas tasas, estabilidad, calidad de voz,",
              "plazos del callback y detector/recalibración automática. Los tiempos medidos aquí son offline.",
              "", "## Ejecuciones utilizadas", ""]
    for rate, manifest in manifests.items():
        lines.append(f"- {rate} Hz: {manifest['run_id']}; matemáticas: {manifest['math_check_count']}; aprobado: {manifest['passed']}.")
    (out / "informe.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(ROOT / "resumen_comparacion/latest.json", {"comparison_id": out.name})
    print(f"Comparación guardada: {out}", flush=True)
    return all(m["passed"] for m in manifests.values()), out
