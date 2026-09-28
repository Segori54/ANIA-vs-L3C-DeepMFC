"""Known paths generated in physical time, never estimated by the Engine."""
import numpy as np

CONDITIONS = ("simple", "reflections", "reverberant", "weak_onset", "noise40", "noise20",
              "no_return", "clipped", "nonfinite", "short160")
SEEDS = (1729, 2718, 3141, 5772, 8119)


def estimator_config(rate, short=False):
    return {"maximumDelaySamples": round(rate * (.010 if short else .100)),
            "maximumFilterLength": round(rate * (.010 if short else 2048 / 48000)),
            "regularisation": 1e-4, "retainedEnergy": .999, "minimumImprovementDb": 6.0}


def path_for(rate, condition):
    delay = round(rate * .004)
    duration = .005 if condition == "short160" else .030
    h = np.zeros(delay + round(rate * duration) + 1)
    h[delay] = .001 if condition == "weak_onset" else .25
    if condition in ("reflections", "reverberant", "weak_onset", "noise40", "noise20"):
        h[delay + round(rate * .006)] = -.12 if condition != "weak_onset" else .25
        h[delay + round(rate * .013)] = .07
    if condition == "reverberant":
        # Sample a continuous damped response; dt preserves its integral with rate.
        t = np.arange(len(h) - delay) / rate
        h[delay:] += 16000 / rate * .018 * np.exp(-t / .012) * (
            np.cos(2 * np.pi * 1300 * t) + .4 * np.sin(2 * np.pi * 2700 * t))
    if condition == "no_return":
        h[:] = 0
    return h.astype(np.float32), delay


def make_case(rate, condition, seed, settings=None):
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown condition: {condition}")
    short = condition == "short160"
    cfg = estimator_config(rate, short)
    if settings is not None and not short:
        cfg["maximumDelaySamples"] = int(settings["maximum_delay_samples"])
        cfg["maximumFilterLength"] = int(settings["maximum_filter_length"])
    tail = cfg["maximumDelaySamples"] + cfg["maximumFilterLength"]
    h, true_delay = path_for(rate, condition)
    rng_probe, rng_val, rng_noise = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(3)]

    def probe(duration, rng):
        count = round(rate * duration)
        x = rng.normal(size=count)
        ramp = round(rate * .01)
        envelope = np.minimum(1, np.minimum(np.arange(count), np.arange(count)[::-1]) / ramp)
        x *= envelope
        x *= 10**(-30 / 20) / np.sqrt(np.mean(x*x))
        return np.pad(x.astype(np.float32), (0, tail))

    identification_seconds = .160 if short else (settings["probe_seconds"] if settings else 1.0)
    validation_seconds = settings["validation_seconds"] if settings else .5
    p, vp = probe(identification_seconds, rng_probe), probe(validation_seconds, rng_val)
    m = np.convolve(p.astype(np.float64), h.astype(np.float64))[:len(p)]
    vm = np.convolve(vp.astype(np.float64), h.astype(np.float64))[:len(vp)]
    if condition in ("noise40", "noise20"):
        snr = int(condition[-2:])
        for signal in (m, vm):
            n = rng_noise.normal(size=len(signal))
            n *= np.sqrt(np.mean(signal**2)) / (10**(snr / 20) * np.sqrt(np.mean(n*n)))
            signal += n
    if condition == "clipped":
        m[20] = 1.0
    if condition == "nonfinite":
        m[20] = np.nan
    signals = dict(probe=p, microphone=m.astype(np.float32), validationProbe=vp,
                   validationMicrophone=vm.astype(np.float32))
    return signals, cfg, h, true_delay
