#include "PatelEstimator.h"

#include <juce_dsp/juce_dsp.h>
#include <algorithm>
#include <cmath>
#include <complex>
#include <numeric>

namespace patel
{
const char* describe(Result result) noexcept
{
    switch (result)
    {
        case Result::none: return "Not calibrated";
        case Result::running: return "Calibration in progress";
        case Result::accepted: return "Validated";
        case Result::noReturn: return "Rejected: no measurable return";
        case Result::clipped: return "Rejected: capture clipped";
        case Result::poorFit: return "Rejected: validation below 6 dB";
        case Result::cancelled: return "Cancelled; output muted";
        case Result::invalid: return "Rejected: invalid capture or model";
        case Result::outOfRange: return "Rejected: path exceeds capture/model window";
    }
    return "Unknown";
}

bool solveToeplitz(const std::vector<double>& r, const std::vector<double>& b,
                  std::vector<double>& x)
{
    if (r.empty() || r.size() != b.size() || ! std::isfinite(r[0]) || r[0] <= 0.0)
        return false;
    x.assign(r.size(), 0.0);
    std::vector<double> prediction(r.size(), 0.0), previous(r.size(), 0.0);
    prediction[0] = 1.0;
    double innovation = r[0];
    x[0] = b[0] / innovation;
    for (std::size_t order = 1; order < r.size(); ++order)
    {
        double reflection = r[order];
        for (std::size_t j = 1; j < order; ++j)
            reflection += prediction[j] * r[order - j];
        reflection = -reflection / innovation;
        if (! std::isfinite(reflection) || std::abs(reflection) >= 1.0)
            return false;
        std::copy(prediction.begin(), prediction.begin() + static_cast<std::ptrdiff_t>(order), previous.begin());
        for (std::size_t j = 1; j < order; ++j)
            prediction[j] = previous[j] + reflection * previous[order - j];
        prediction[order] = reflection;
        innovation *= 1.0 - reflection * reflection;
        if (innovation < r[0] * 1.0e-12)
            return false;
        double residual = b[order];
        for (std::size_t j = 0; j < order; ++j)
            residual -= r[order - j] * x[j];
        const auto correction = residual / innovation;
        for (std::size_t j = 0; j < order; ++j)
            x[j] += correction * prediction[order - j];
        x[order] = correction;
    }
    return std::all_of(x.begin(), x.end(), [] (double value) { return std::isfinite(value); });
}

namespace
{
std::vector<double> correlate(const std::vector<float>& y, const std::vector<float>& x, int lags)
{
    int order = 0;
    while ((std::size_t { 1 } << order) < x.size() + y.size() - 1)
        ++order;
    juce::dsp::FFT fft(order);
    const auto size = static_cast<std::size_t>(fft.getSize());
    std::vector<std::complex<float>> time(size), xf(size), yf(size);
    for (std::size_t i = 0; i < x.size(); ++i) time[i] = x[i];
    fft.perform(time.data(), xf.data(), false);
    std::fill(time.begin(), time.end(), 0.0f);
    for (std::size_t i = 0; i < y.size(); ++i) time[i] = y[i];
    fft.perform(time.data(), yf.data(), false);
    for (std::size_t i = 0; i < size; ++i) yf[i] *= std::conj(xf[i]);
    fft.perform(yf.data(), time.data(), true);
    std::vector<double> result(static_cast<std::size_t>(lags));
    for (int i = 0; i < lags; ++i) result[static_cast<std::size_t>(i)] = time[static_cast<std::size_t>(i)].real();
    return result;
}
double energy(const std::vector<float>& values)
{
    double sum = 0.0;
    for (const auto value : values) sum += static_cast<double>(value) * value;
    return sum;
}
}

Model estimate(const std::vector<float>& probe, const std::vector<float>& microphone,
               const std::vector<float>& validationProbe, const std::vector<float>& validationMicrophone,
               const EstimatorConfig& config)
{
    Model model;
    const int window = config.maximumDelaySamples + config.maximumFilterLength;
    if (config.maximumDelaySamples < 1 || config.maximumFilterLength < 1
        || probe.size() != microphone.size() || validationProbe.size() != validationMicrophone.size()
        || probe.size() < static_cast<std::size_t>(2 * window)
        || validationProbe.size() <= static_cast<std::size_t>(window))
        return model;
    for (const auto* capture : { &probe, &microphone, &validationProbe, &validationMicrophone })
        for (const auto value : *capture)
        {
            if (! std::isfinite(value)) return model;
            if (std::abs(value) >= 0.98f) { model.result = Result::clipped; return model; }
        }
    const auto probeEnergy = energy(probe);
    const auto observedEnergy = energy(validationMicrophone);
    if (probeEnergy < 1.0e-10 || observedEnergy / validationMicrophone.size() < 1.0e-12)
    { model.result = Result::noReturn; return model; }

    auto cross = correlate(microphone, probe, window);
    auto peak = std::max_element(cross.begin() + 1, cross.end(),
        [] (double a, double b) { return std::abs(a) < std::abs(b); });
    const auto threshold = std::abs(*peak) * 0.15;
    int onset = 1;
    while (onset < window - 1 && std::abs(cross[static_cast<std::size_t>(onset)]) < threshold) ++onset;
    // Keep 32 samples of pre-onset response. The subsequent energy trimming
    // removes only negligible leading energy, not the physical device delay.
    int delay = std::max(1, onset - 32);
    if (onset > config.maximumDelaySamples)
    { model.result = Result::outOfRange; return model; }
    const int length = config.maximumFilterLength;
    auto autocorrelation = correlate(probe, probe, length);
    autocorrelation[0] *= 1.0 + config.regularisation;
    std::vector<double> rhs(static_cast<std::size_t>(length)), fitted;
    for (int k = 0; k < length; ++k) rhs[static_cast<std::size_t>(k)] = cross[static_cast<std::size_t>(delay + k)];
    if (! solveToeplitz(autocorrelation, rhs, fitted)) return model;

    const auto total = std::inner_product(fitted.begin(), fitted.end(), fitted.begin(), 0.0);
    if (total < 1.0e-12) { model.result = Result::noReturn; return model; }
    const auto discardBudget = total * (1.0 - config.retainedEnergy) * 0.5;
    double discarded = 0.0;
    int first = 0, last = length - 1;
    while (first < last && discarded + fitted[static_cast<std::size_t>(first)] * fitted[static_cast<std::size_t>(first)] <= discardBudget)
    { discarded += fitted[static_cast<std::size_t>(first)] * fitted[static_cast<std::size_t>(first)]; ++first; }
    discarded = 0.0;
    while (last > first && discarded + fitted[static_cast<std::size_t>(last)] * fitted[static_cast<std::size_t>(last)] <= discardBudget)
    { discarded += fitted[static_cast<std::size_t>(last)] * fitted[static_cast<std::size_t>(last)]; --last; }
    model.delaySamples = delay + first;
    for (int k = first; k <= last; ++k) model.coefficients.push_back(static_cast<float>(fitted[static_cast<std::size_t>(k)]));

    double residualEnergy = 0.0;
    for (std::size_t n = 0; n < validationMicrophone.size(); ++n)
    {
        double predicted = 0.0;
        for (std::size_t k = 0; k < model.coefficients.size(); ++k)
        {
            const auto lag = static_cast<std::size_t>(model.delaySamples) + k;
            if (n >= lag) predicted += model.coefficients[k] * static_cast<double>(validationProbe[n - lag]);
        }
        const auto error = validationMicrophone[n] - predicted;
        residualEnergy += error * error;
    }
    model.validationImprovementDb = static_cast<float>(10.0 * std::log10(observedEnergy / std::max(residualEnergy, 1.0e-20)));
    model.result = std::isfinite(model.validationImprovementDb)
        && model.validationImprovementDb >= config.minimumImprovementDb ? Result::accepted : Result::poorFit;
    return model;
}
}
