"""Read-only audit of SessionCapture's IEEE float WAVs and sample timeline."""
import csv
import json
import struct
from pathlib import Path
import numpy as np
from .oracle import engine_matched, complete, relative_error
from .storage import ROOT, digest, new_id, read_json, write_json

CHANNELS = ["microphone_raw", "microphone_used", "feedback", "clean", "output", "probe", "gain"]


def read_float_wav(path):
    data = Path(path).read_bytes()
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE" or struct.unpack_from("<I", data, 4)[0] + 8 != len(data):
        raise ValueError("Invalid/incomplete WAV container")
    offset, fmt, audio = 12, None, None
    while offset + 8 <= len(data):
        kind, size = struct.unpack_from("<4sI", data, offset)
        payload = data[offset+8:offset+8+size]
        if len(payload) != size:
            raise ValueError("Truncated WAV chunk")
        if kind == b"fmt ":
            fmt = struct.unpack_from("<HHIIHH", payload)
        if kind == b"data":
            audio = payload
        offset += 8 + size + size % 2
    if fmt is None or audio is None or fmt[0] != 3 or fmt[1] != 7 or fmt[4:] != (28, 32) or len(audio) % 28:
        raise ValueError("Expected seven-channel IEEE float32 WAV")
    if fmt[3] != fmt[2] * 28:
        raise ValueError("Invalid WAV byte rate")
    return fmt[2], np.frombuffer(audio, dtype="<f4").reshape(-1, 7)


def safe_file(root, relative):
    file = (root / relative).resolve()
    if not file.is_relative_to(root.resolve()):
        raise ValueError("Path outside session")
    return file


def audit_data(session):
    session = Path(session).resolve()
    manifest = read_json(session / "manifest.json")
    checks, diagnostics = {}, []
    checks["complete"] = manifest.get("complete") is True
    if not checks["complete"]:
        return {"passed": False, "checks": checks, "diagnostics": ["Session is incomplete; not eligible for approval."]}
    if manifest.get("schema_version") != 1 or manifest.get("channels") != CHANNELS:
        raise ValueError("Unsupported session schema/channels")
    hashes = manifest.get("sha256", {})
    files = {str(p.relative_to(session)).replace("\\", "/") for p in session.rglob("*") if p.is_file() and p.name != "manifest.json"}
    if files != set(hashes):
        raise ValueError("Hash inventory mismatch")
    for name, expected in hashes.items():
        if digest(safe_file(session, name)) != expected:
            raise ValueError(f"Hash mismatch: {name}")
    checks["hashes"] = True
    chunks, expected_start = [], 0
    for segment in manifest["segments"]:
        rate, data = read_float_wav(safe_file(session, segment["file"]))
        if rate != manifest["sample_rate"] or segment["start_sample"] != expected_start or len(data) != segment["samples"]:
            raise ValueError("WAV segment continuity/rate mismatch")
        expected_start += len(data)
        chunks.append(data)
    if expected_start != manifest["samples"] or not chunks:
        raise ValueError("Missing audio")
    audio = np.concatenate(chunks)
    checks["segments"] = True
    checks["microphone_sanitization"] = bool(np.array_equal(np.where(np.isfinite(audio[:,0]),audio[:,0],np.float32(0)),audio[:,1]))
    with (session / "blocks.csv").open(encoding="utf-8") as f:
        blocks = list(csv.DictReader(f))
    pos = 0
    for i, block in enumerate(blocks):
        if int(block["sequence"]) != i or int(block["start_sample"]) != pos or int(block["samples"]) <= 0:
            raise ValueError("Block sequence gap")
        pos += int(block["samples"])
    checks["blocks"] = pos == len(audio)
    events = [json.loads(line) for line in (session / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    if not events or events[0]["sample"] != 0 or any(a["sample"] >= b["sample"] for a,b in zip(events, events[1:])) or events[-1]["sample"] >= len(audio):
        raise ValueError("Invalid event timeline")
    history = np.fromfile(session / "initial_history.f32", dtype="<f4")
    if len(history) != manifest["history_samples"]:
        raise ValueError("History size mismatch")
    output = np.r_[history, audio[:,4]].astype(np.float64)
    models = {int(read_json(p)["id"]): read_json(p) for p in (session / "modelos").glob("*.json")}
    for model in models.values():
        coeff=np.asarray(model["coefficients"])
        if not np.all(np.isfinite(coeff)) or model["delaySamples"]<0:
            raise ValueError("Invalid exported model")
    residual_sum = prediction_sum = 0.0
    clean_max_error = 0.0
    cal_ranges = {}
    for i, event in enumerate(events):
        begin, end = event["sample"], events[i+1]["sample"] if i+1 < len(events) else len(audio)
        if event["state"] in (2,3):
            cal_ranges.setdefault(event["calibration"], {}).setdefault(event["state"], []).append((begin,end))
        if not event["clean_valid"]:
            if np.any(audio[begin:end,2:4] != 0):
                raise ValueError("Invalid internal channels should be zero")
            continue
        if event["state"] == 5:
            if event["model"] not in models:
                raise ValueError("Missing active model")
            model = models[event["model"]]
            h, delay = np.asarray(model["coefficients"],dtype=np.float64), model["delaySamples"]
            prediction = np.zeros(end-begin)
            for k, value in enumerate(h):
                start = len(history)+begin-delay-k
                if start < 0:
                    raise ValueError("Insufficient initial history")
                prediction += value * output[start:start+end-begin]
        else:
            prediction = np.zeros(end-begin)
        captured = audio[begin:end,2].astype(np.float64)
        residual_sum += float(np.sum((prediction-captured)**2))
        prediction_sum += float(np.sum(prediction**2))
        clean = (audio[begin:end,1] - audio[begin:end,2]).astype(np.float32)
        clean_max_error = max(clean_max_error,float(np.max(np.abs(clean-audio[begin:end,3]))))
    replay_error = float(np.sqrt(residual_sum/max(prediction_sum,1e-30)))
    checks["causal_replay"] = replay_error <= 1e-4
    checks["subtraction"] = clean_max_error <= 1e-7
    cal_results = []
    for cal_id, ranges in cal_ranges.items():
        states = {}
        for state, intervals in ranges.items():
            if any(a[1] != b[0] for a,b in zip(intervals,intervals[1:])):
                raise ValueError("Non-contiguous calibration stage")
            states[state] = (intervals[0][0],intervals[-1][1])
        model = models.get(cal_id)
        outcomes=[e["result"] for e in events if e["calibration"]==cal_id and e["result"] not in ("running","none")]
        if model is None or 2 not in states or 3 not in states or (outcomes and outcomes[-1] in ("cancelled","clipped","invalid")):
            diagnostics.append(f"Calibration {cal_id}: partial/cancelled, no complete estimator comparison.")
            continue
        a,b = states[2]; c,d = states[3]
        signals = dict(probe=audio[a:b,5],microphone=audio[a:b,1],validationProbe=audio[c:d,5],validationMicrophone=audio[c:d,1])
        oracle = engine_matched(signals,manifest["config"])
        error = relative_error(complete(model),complete(oracle))
        db_delta=abs(model["validationImprovementDb"]-oracle["validationImprovementDb"])
        ok = model["result"] == oracle["result"] and error <= 1e-3 and db_delta<=.1
        cal_results.append({"id":cal_id,"result":model["result"],"oracle_result":oracle["result"],"response_relative_error":error,"validation_db_difference":db_delta,"passed":ok})
    checks["calibrations"] = all(c["passed"] for c in cal_results)
    checks["finite_processed_audio"] = bool(np.all(np.isfinite(audio[:,1:])))
    return {"passed":all(checks.values()),"checks":checks,"diagnostics":diagnostics,
            "samples":len(audio),"rate":manifest["sample_rate"],"replay_relative_error":replay_error,
            "subtraction_max_error":clean_max_error,"calibrations":cal_results,
            "raw_nonfinite_samples":int(np.count_nonzero(~np.isfinite(audio[:,0]))),
            "clipped_input_samples":int(np.count_nonzero(np.abs(audio[:,0])>=.98)),
            "callback_ms":{k:float(np.percentile([float(b['callback_ms']) for b in blocks],p)) for k,p in (("p50",50),("p95",95),("p99",99),("max",100))},
            "deadline_misses":sum(float(b["callback_ms"])>1000*int(b["samples"])/manifest["sample_rate"] for b in blocks)}


def audit_session(session):
    try:
        result = audit_data(session)
    except (OSError, ValueError, KeyError, struct.error) as exc:
        result = {"passed":False,"checks":{"integrity":False},"diagnostics":[str(exc)]}
    directory = ROOT / "resumen_comparacion" / ("audit_"+new_id())
    result["session"] = str(Path(session).resolve())
    write_json(directory / "audit.json", result)
    lines = ["# Auditoria de sesion real", "", "Resultado: " + ("APROBADA" if result["passed"] else "NO APROBADA"), "", f"Sesion: {result['session']}", ""]
    lines += [f"- {k}: {'OK' if v else 'FALLO'}" for k,v in result["checks"].items()]
    lines += ["", *result.get("diagnostics",[]), "", "Valida integridad y reconstruccion numerica; no certifica ganancia estable ni calidad perceptual."]
    (directory / "informe.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"Auditoria: {directory}")
    return result["passed"], directory
