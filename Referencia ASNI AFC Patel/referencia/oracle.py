"""Direct correlations and dense solutions, independent of FFT and Levinson."""
import numpy as np


def correlate(y, f, lags):
    y, f = np.asarray(y, dtype=np.float64), np.asarray(f, dtype=np.float64)
    if y.ndim != 1 or f.ndim != 1 or lags < 0:
        raise ValueError("Expected mono vectors and nonnegative lag count")
    result = np.zeros(lags, dtype=np.float64)
    for lag in range(min(lags, len(y))):
        count = min(len(f), len(y) - lag)
        result[lag] = np.dot(y[lag:lag + count], f[:count])
    return result


def toeplitz(r):
    r = np.asarray(r, dtype=np.float64)
    indices = np.arange(len(r))
    return r[np.abs(indices[:, None] - indices[None, :])]


def solve(r, b):
    matrix = toeplitz(r)
    solution = np.linalg.solve(matrix, np.asarray(b, dtype=np.float64))
    residual = np.linalg.norm(matrix @ solution - b) / max(np.linalg.norm(b), 1e-30)
    return solution, float(residual)


def predict(probe, coefficients, delay=0):
    probe, coefficients = np.asarray(probe, dtype=np.float64), np.asarray(coefficients, dtype=np.float64)
    if delay < 0:
        raise ValueError("Negative delay")
    result = np.zeros(len(probe), dtype=np.float64)
    if len(coefficients) and delay < len(probe):
        result[delay:] = np.convolve(probe, coefficients)[:len(probe) - delay]
    return result


class CausalReplay:
    """Stateful causal FIR. Output never depends on a future input sample."""
    def __init__(self, coefficients, delay=0):
        self.h = np.r_[np.zeros(delay), np.asarray(coefficients, dtype=np.float64)]
        if not len(self.h):
            self.h = np.zeros(1)
        self.history = np.zeros(len(self.h) - 1)

    def process(self, block):
        block = np.asarray(block, dtype=np.float64)
        if not len(block):
            return block.copy()
        extended = np.r_[self.history, block]
        # 'valid' contains only windows ending at samples in this block.
        result = np.convolve(extended, self.h, mode="valid")
        if len(self.history):
            self.history = extended[-len(self.history):].copy()
        return result


def complete(model):
    return np.r_[np.zeros(model["delaySamples"]), np.asarray(model["coefficients"], dtype=np.float64)]


def relative_error(actual, expected):
    n = max(len(actual), len(expected))
    a = np.pad(np.asarray(actual, dtype=np.float64), (0, n - len(actual)))
    b = np.pad(np.asarray(expected, dtype=np.float64), (0, n - len(expected)))
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-30))


def improvement(mic, predicted):
    mic = np.asarray(mic, dtype=np.float64)
    return float(10 * np.log10(np.dot(mic, mic) / max(np.sum((mic - predicted)**2), 1e-20)))


def paper_core(probe, microphone, order):
    r = correlate(probe, probe, order)
    b = correlate(microphone, probe, order)
    h, residual = solve(r, b)
    return {"delaySamples": 0, "coefficients": h.tolist(), "residual": residual}


def engine_matched(signals, cfg):
    p, m, vp, vm = [np.asarray(signals[k], dtype=np.float64) for k in
                    ("probe", "microphone", "validationProbe", "validationMicrophone")]
    model = {"result": "invalid", "delaySamples": 0, "coefficients": [], "validationImprovementDb": 0.0}
    length, max_delay = cfg["maximumFilterLength"], cfg["maximumDelaySamples"]
    window = length + max_delay
    if max_delay < 1 or length < 1 or len(p) != len(m) or len(vp) != len(vm) or len(p) < 2 * window or len(vp) <= window:
        return model
    for capture in (p, m, vp, vm):
        # Preserve the C++ scan order for captures containing multiple defects.
        bad = np.flatnonzero(~np.isfinite(capture) | (np.abs(capture) >= .98))
        if len(bad):
            if np.isfinite(capture[bad[0]]):
                model["result"] = "clipped"
            return model
    if np.dot(p, p) < 1e-10 or np.dot(vm, vm) / len(vm) < 1e-12:
        model["result"] = "noReturn"
        return model
    cross = correlate(m, p, window)
    threshold = .15 * np.max(np.abs(cross[1:]))
    candidates = np.flatnonzero(np.abs(cross[1:]) >= threshold)
    onset = int(candidates[0] + 1) if len(candidates) else window - 1
    if onset > max_delay:
        model["result"] = "outOfRange"
        return model
    delay = max(1, onset - 32)
    r = correlate(p, p, length)
    r[0] *= 1 + cfg["regularisation"]
    try:
        fitted, residual = solve(r, cross[delay:delay + length])
    except np.linalg.LinAlgError:
        return model
    energy = fitted * fitted
    if not np.all(np.isfinite(fitted)) or energy.sum() < 1e-12:
        model["result"] = "noReturn" if np.all(np.isfinite(fitted)) else "invalid"
        return model
    budget = energy.sum() * (1 - cfg["retainedEnergy"]) / 2
    first = int(np.searchsorted(np.cumsum(energy), budget, side="right"))
    first = min(first, length - 1)
    discarded_right = int(np.searchsorted(np.cumsum(energy[::-1]), budget, side="right"))
    last = max(first, length - 1 - discarded_right)
    # Match the model's storage type, not the solver arithmetic.
    h = fitted[first:last + 1].astype(np.float32)
    delay += first
    db = improvement(vm, predict(vp, h, delay))
    model.update(result="accepted" if np.isfinite(db) and db >= cfg["minimumImprovementDb"] else "poorFit",
                 delaySamples=delay, coefficients=h.tolist(), validationImprovementDb=db,
                 onset=onset, pretrimDelay=max(1, onset - 32), residual=residual)
    return model
