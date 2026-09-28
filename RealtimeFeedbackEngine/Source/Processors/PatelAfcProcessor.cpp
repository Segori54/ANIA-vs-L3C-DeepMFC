#include "PatelAfcProcessor.h"

#include <algorithm>
#include <chrono>
#include <cmath>

PatelAfcProcessor::PatelAfcProcessor() : PatelAfcProcessor(Config {}) {}
PatelAfcProcessor::PatelAfcProcessor(Config initialConfig) : config(initialConfig)
{
    config.filterLength = std::clamp(config.filterLength, 8, 4096);
    config.maximumDelayMilliseconds = std::clamp(config.maximumDelayMilliseconds, 1, 250);
    config.probeDurationMilliseconds = std::clamp(config.probeDurationMilliseconds, 100, 5000);
    config.validationDurationMilliseconds = std::clamp(config.validationDurationMilliseconds, 100, 2000);
    config.probeLevelDbfs = std::isfinite(config.probeLevelDbfs) ? std::clamp(config.probeLevelDbfs, -60.0f, -18.0f) : -30.0f;
    config.regularisation = std::isfinite(config.regularisation) ? std::clamp(config.regularisation, 1.0e-8f, 0.1f) : 1.0e-4f;
}
PatelAfcProcessor::~PatelAfcProcessor() { stopWorker(); capture.deviceStopped(); capture.wait(); }

void PatelAfcProcessor::stopWorker() noexcept
{
    workerStop.store(true);
    if (worker.joinable()) worker.join();
}

void PatelAfcProcessor::prepare(double newSampleRate, int) noexcept
{
    stopWorker(); // device lifecycle only, never called from process()
    capture.deviceStopped(); capture.wait();
    sampleRate = newSampleRate > 0.0 ? newSampleRate : 48000.0;
    estimatorConfig.maximumDelaySamples = static_cast<int>(sampleRate * config.maximumDelayMilliseconds / 1000.0);
    estimatorConfig.maximumFilterLength = std::clamp(static_cast<int>(std::lround(config.filterLength * sampleRate / 48000.0)), 8, 4096);
    estimatorConfig.regularisation = config.regularisation;
    flushSamples = estimatorConfig.maximumDelaySamples + estimatorConfig.maximumFilterLength;
    coefficients.assign(static_cast<std::size_t>(estimatorConfig.maximumFilterLength), 0.0f);
    reference.assign(static_cast<std::size_t>(flushSamples + 1), 0.0f);
    const auto makeProbe = [this] (int milliseconds, std::uint32_t seed)
    {
        const int count = std::max(2 * flushSamples, static_cast<int>(sampleRate * milliseconds / 1000.0));
        std::vector<float> values(static_cast<std::size_t>(count + flushSamples), 0.0f);
        MeasurementNoise source;
        source.reset(seed);
        const auto ramp = std::max(1, static_cast<int>(sampleRate * 0.01));
        double energy = 0.0;
        for (int n = 0; n < count; ++n)
        {
            const auto envelope = std::min(1.0f, static_cast<float>(std::min(n, count - 1 - n)) / static_cast<float>(ramp));
            values[static_cast<std::size_t>(n)] = source.next(MeasurementNoise::Colour::white) * envelope;
            energy += static_cast<double>(values[static_cast<std::size_t>(n)]) * values[static_cast<std::size_t>(n)];
        }
        const auto scale = static_cast<float>(std::pow(10.0, config.probeLevelDbfs / 20.0) / std::sqrt(energy / count));
        for (auto& value : values) value *= scale;
        return values;
    };
    probe = makeProbe(config.probeDurationMilliseconds, 0x517cc1b7u);
    validationProbe = makeProbe(config.validationDurationMilliseconds, 0x9e3779b9u);
    microphone.assign(probe.size(), 0.0f);
    validationMicrophone.assign(validationProbe.size(), 0.0f);
    workerModel = {};
    noise.reset();
    detector.prepare(sampleRate);
    rampStep = static_cast<float>(1.0 / (0.02 * sampleRate));
    resumeStep = static_cast<float>(1.0 / (0.01 * sampleRate));
    outputEnvelope = muted.load() ? 0.0f : 1.0f;
    resumeRequested.store(false);
    protectionLatched.store(false);
    gain = std::pow(10.0f, gainDb.load() / 20.0f);
    noiseAmplitude = std::pow(10.0f, noiseLevelDbfs.load() / 20.0f);
    noiseEnvelope = 0.0f;
    writeIndex = captureIndex = 0;
    activeLength = delaySamples = 0;
    calibrationId = activeModelId = jobCalibrationId = 0;
    state.store(State::bypass);
    result.store(patel::Result::none);
    calibrated.store(false);
    noiseControl.store(0);
    noiseActive.store(false);
    calibrationRequested.store(false);
    cancelRequested.store(false);
    recoverRequested.store(false);
    reportedDelay.store(0); reportedLength.store(0); validationDb.store(0.0f);
    detections.store(0); clippedSamples.store(0);
    job.store(Job::idle);
    workerStop.store(false);
    worker = std::thread([this] { workerLoop(); });
}

void PatelAfcProcessor::stopped() noexcept
{
    capture.deviceStopped();
    // Called after callbacks have stopped. A worker may still own captures;
    // leave those untouched until prepare() joins it.
    noiseControl.store(0);
    noiseActive.store(false);
    noiseEnvelope = 0.0f;
    calibrationRequested.store(false);
    if (calibrationState(state.load()))
    {
        result.store(patel::Result::cancelled);
        muted.store(true);
    }
    calibrated.store(false);
    state.store(State::bypass);
}

void PatelAfcProcessor::workerLoop() noexcept
{
    while (! workerStop.load())
    {
        if (job.load(std::memory_order_acquire) == Job::queued)
        {
            job.store(Job::working, std::memory_order_release);
            try { workerModel = patel::estimate(probe, microphone, validationProbe, validationMicrophone, estimatorConfig); }
            catch (...) { workerModel = {}; }
            capture.workerModel(workerModel, jobCalibrationId);
            job.store(Job::ready, std::memory_order_release);
        }
        else std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
}

bool PatelAfcProcessor::calibrationState(State value) noexcept
{
    return value == State::preparing || value == State::calibration || value == State::validating || value == State::estimating;
}
bool PatelAfcProcessor::isCalibrationBusy() const noexcept
{
    return (noiseControl.load() & 2u) != 0 || calibrationRequested.load()
        || calibrationState(state.load()) || job.load() != Job::idle;
}
void PatelAfcProcessor::requestCalibration() noexcept
{
    if (isCalibrationBusy() || isMuted()) return;
    noiseControl.store(2);
    calibrationRequested.store(true);
}
void PatelAfcProcessor::cancelCalibration() noexcept { cancelRequested.store(true); }
void PatelAfcProcessor::setMethod(Method value) noexcept { method.store(value); }
void PatelAfcProcessor::setGainDb(float value) noexcept { if (std::isfinite(value)) gainDb.store(std::clamp(value, -60.0f, 30.0f)); }
void PatelAfcProcessor::setMuted(bool value) noexcept
{
    muted.store(value);
    if (value)
    {
        noiseControl.fetch_and(~1u);
        if (isCalibrationBusy()) cancelRequested.store(true);
    }
    else { recoverRequested.store(true); resumeRequested.store(true); }
}
void PatelAfcProcessor::setNoiseEnabled(bool value) noexcept
{
    if (! value) { noiseControl.fetch_and(~1u); return; }
    if (isMuted()) return;
    unsigned expected = 0;
    noiseControl.compare_exchange_strong(expected, 1);
}
void PatelAfcProcessor::setNoiseColour(MeasurementNoise::Colour value) noexcept { noiseColour.store(value); }
void PatelAfcProcessor::setNoiseLevelDbfs(float value) noexcept { if (std::isfinite(value)) noiseLevelDbfs.store(std::clamp(value, -80.0f, -12.0f)); }

void PatelAfcProcessor::beginCalibration() noexcept
{
    ++calibrationId;
    noiseControl.store(2);
    calibrated.store(false);
    activeLength = 0;
    method.store(Method::patel);
    detector.reset();
    reportedDelay.store(0); reportedLength.store(0); validationDb.store(0.0f);
    captureIndex = 0;
    settlingRemaining = flushSamples + static_cast<int>(std::ceil(1.0f / rampStep)) + 1;
    result.store(patel::Result::running);
    state.store(State::preparing);
}

void PatelAfcProcessor::finishCalibration(patel::Result outcome) noexcept
{
    // Always consume noise requests before leaving the calibration state.
    noiseEnvelope = 0.0f;
    noiseActive.store(false);
    result.store(outcome);
    if (outcome == patel::Result::accepted)
    {
        calibrated.store(true);
        state.store(method.load() == Method::patel ? State::cancelling : State::bypass);
    }
    else
    {
        calibrated.store(false);
        activeLength = 0;
        muted.store(true);
        state.store(State::faultMuted);
    }
    // A cancelled worker retains ownership until ready; keep its gate locked.
    noiseControl.store(job.load() == Job::idle ? 0u : 2u);
}

float PatelAfcProcessor::estimateFeedback() const noexcept
{
    float estimate = 0.0f;
    auto index = (writeIndex + reference.size() - static_cast<std::size_t>(delaySamples)) % reference.size();
    for (int k = 0; k < activeLength; ++k)
    {
        estimate += coefficients[static_cast<std::size_t>(k)] * reference[index];
        index = index == 0 ? reference.size() - 1 : index - 1;
    }
    return estimate;
}
void PatelAfcProcessor::pushReference(float value) noexcept
{
    reference[writeIndex] = value;
    if (++writeIndex == reference.size()) writeIndex = 0;
}
float PatelAfcProcessor::protect(float value) noexcept
{
    if (! std::isfinite(value))
    {
        finishCalibration(patel::Result::invalid);
        return 0.0f;
    }
    if (std::abs(value) > 0.95f)
    {
        clippedSamples.fetch_add(1, std::memory_order_relaxed);
        protectionLatched.store(true);
    }
    return std::clamp(value, -0.95f, 0.95f);
}

void PatelAfcProcessor::process(const juce::AudioBuffer<float>& input, juce::AudioBuffer<float>& output) noexcept
{
    if (reference.empty()) { output.clear(); return; }
    capture.beginBlock(coefficients.data(), activeLength, delaySamples, activeModelId,
                       reference.data(), static_cast<int>(reference.size()), static_cast<int>(writeIndex), validationDb.load());
    if (resumeRequested.exchange(false)) outputEnvelope = 0.0f;
    const bool cancel = cancelRequested.exchange(false);
    const bool start = calibrationRequested.exchange(false);
    if (cancel || (muted.load() && (calibrationState(state.load()) || start)))
    {
        if (calibrationState(state.load()) || start) finishCalibration(patel::Result::cancelled);
    }
    else if (start && job.load() == Job::idle) beginCalibration();

    if (job.load(std::memory_order_acquire) == Job::ready)
    {
        if (state.load() == State::estimating)
        {
            const auto outcome = workerModel.result;
            reportedDelay.store(workerModel.delaySamples);
            reportedLength.store(static_cast<int>(workerModel.coefficients.size()));
            validationDb.store(workerModel.validationImprovementDb);
            if (outcome == patel::Result::accepted)
            {
                std::copy(workerModel.coefficients.begin(), workerModel.coefficients.end(), coefficients.begin());
                activeLength = static_cast<int>(workerModel.coefficients.size());
                delaySamples = workerModel.delaySamples;
                activeModelId = jobCalibrationId;
            }
            job.store(Job::idle, std::memory_order_release);
            finishCalibration(outcome);
        }
        else { job.store(Job::idle, std::memory_order_release); noiseControl.store(0); }
    }
    if (recoverRequested.exchange(false) && state.load() == State::faultMuted && ! isCalibrationBusy())
        state.store(State::bypass);
    if (! calibrationState(state.load()) && state.load() != State::faultMuted)
        state.store(method.load() == Method::patel && calibrated.load() ? State::cancelling : State::bypass);

    const auto blockGainDb = gainDb.load();
    const auto blockMethod = method.load();
    const auto targetGain = std::pow(10.0f, blockGainDb / 20.0f);
    const auto targetAmplitude = std::pow(10.0f, noiseLevelDbfs.load() / 20.0f);
    const auto colour = noiseColour.load();
    const auto count = std::min(input.getNumSamples(), output.getNumSamples());
    const auto* in = input.getNumChannels() > 0 ? input.getReadPointer(0) : nullptr;
    auto* out = output.getNumChannels() > 0 ? output.getWritePointer(0) : nullptr;
    if (out != nullptr)
    {
        for (int n = 0; n < count; ++n)
        {
            const float rawMic = in != nullptr ? in[n] : 0.0f;
            float mic = rawMic;
            if (! std::isfinite(mic)) { finishCalibration(patel::Result::invalid); mic = 0.0f; }
            if (std::abs(mic) >= 0.98f)
            {
                clippedSamples.fetch_add(1, std::memory_order_relaxed);
                if (calibrationState(state.load())) finishCalibration(patel::Result::clipped);
            }
            gain += rampStep * (targetGain - gain);
            noiseAmplitude += rampStep * (targetAmplitude - noiseAmplitude);
            const auto current = state.load();
            const bool silent = muted.load() || current == State::faultMuted;
            if (silent) { noiseControl.fetch_and(~1u); outputEnvelope = 0.0f; }
            else outputEnvelope = std::min(1.0f, outputEnvelope + resumeStep);
            const float envelopeTarget = ! silent && noiseControl.load() == 1 ? 1.0f : 0.0f;
            noiseEnvelope += std::clamp(envelopeTarget - noiseEnvelope, -rampStep, rampStep);
            float emitted = 0.0f;
            float estimated = 0.0f, cleaned = 0.0f, programmedProbe = 0.0f;
            bool cleanValid = false;
            if (! silent)
            {
                if (current == State::preparing)
                {
                    // Forward path open; fade old test noise, then wait a whole return window.
                    if (noiseEnvelope > 0.0f) emitted = noise.next(colour) * noiseAmplitude * noiseEnvelope;
                    if (--settlingRemaining <= 0) { captureIndex = 0; state.store(State::calibration); }
                }
                else if (current == State::calibration || current == State::validating)
                {
                    const bool validating = current == State::validating;
                    auto& captured = validating ? validationMicrophone : microphone;
                    const auto& excitation = validating ? validationProbe : probe;
                    captured[captureIndex] = mic;
                    emitted = excitation[captureIndex];
                    programmedProbe = emitted;
                    if (++captureIndex == excitation.size())
                    {
                        captureIndex = 0;
                        if (! validating) state.store(State::validating);
                        else { state.store(State::estimating); jobCalibrationId = calibrationId; job.store(Job::queued, std::memory_order_release); }
                    }
                }
                else if (current != State::estimating)
                {
                    estimated = current == State::cancelling ? estimateFeedback() : 0.0f;
                    cleaned = mic - estimated;
                    cleanValid = true;
                    emitted = gain * cleaned;
                    if (noiseEnvelope > 0.0f) emitted += noise.next(colour) * noiseAmplitude * noiseEnvelope;
                    if (detector.processSample(mic)) detections.fetch_add(1, std::memory_order_relaxed);
                }
            }
            out[n] = protect(emitted) * outputEnvelope;
            SessionCapture::Tags tags;
            tags.state = static_cast<int>(current); tags.result = static_cast<int>(result.load());
            tags.method = static_cast<int>(blockMethod); tags.calibration = calibrationId; tags.model = activeModelId;
            tags.muted = silent; tags.cleanValid = cleanValid; tags.noise = noiseEnvelope > 0;
            tags.limited = std::abs(emitted) > 0.95f; tags.targetGainDb = blockGainDb;
            capture.sample({rawMic, mic, estimated, cleaned, out[n], programmedProbe, gain}, tags);
            pushReference(out[n]); // actual post-gain, post-noise, post-protection DAC reference
        }
    }
    noiseActive.store(noiseEnvelope > 0.0f && ! muted.load());
    for (int channel = 1; channel < output.getNumChannels(); ++channel) output.clear(channel, 0, output.getNumSamples());
    if (out != nullptr && count < output.getNumSamples()) output.clear(0, count, output.getNumSamples() - count);
}

const char* PatelAfcProcessor::describeState(State value) noexcept
{
    switch (value)
    {
        case State::bypass: return "Bypass";
        case State::preparing: return "Fading noise / flushing return";
        case State::calibration: return "Identification probe";
        case State::validating: return "Independent validation probe";
        case State::estimating: return "Computing / validating model";
        case State::cancelling: return "Patel cancelling";
        case State::faultMuted: return "Muted: inspect calibration result";
    }
    return "Unknown";
}
