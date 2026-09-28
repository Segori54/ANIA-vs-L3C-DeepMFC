#pragma once

#include "HowlingDetector.h"
#include "IProcessor.h"
#include "MeasurementNoise.h"
#include "PatelEstimator.h"
#include "../Capture/SessionCapture.h"
#include <atomic>
#include <thread>
#include <vector>

class PatelAfcProcessor final : public IProcessor
{
public:
    enum class State { bypass, preparing, calibration, validating, estimating, cancelling, faultMuted };
    // Future methods share the post-output reference contract.
    enum class Method { bypass, patel };
    struct Config
    {
        int filterLength = 2048; // maximum effective FIR, excluding pure delay
        int maximumDelayMilliseconds = 100;
        float regularisation = 1.0e-4f;
        float probeLevelDbfs = -30.0f; // RMS, not peak
        int probeDurationMilliseconds = 1000;
        int validationDurationMilliseconds = 500;
    };
    PatelAfcProcessor();
    explicit PatelAfcProcessor(Config config);
    ~PatelAfcProcessor() override;
    void prepare(double sampleRate, int maximumBlockSize) noexcept override;
    void stopped() noexcept override;
    void callbackFinished(int samples, double ms) noexcept override { capture.endBlock(samples, ms); }
    SessionCapture& sessionCapture() noexcept { return capture; }
    patel::EstimatorConfig getEstimatorConfig() const { return estimatorConfig; }
    void process(const juce::AudioBuffer<float>& input, juce::AudioBuffer<float>& output) noexcept override;
    void requestCalibration() noexcept;
    void cancelCalibration() noexcept;
    void setMethod(Method method) noexcept;
    void setGainDb(float gain) noexcept;
    void setMuted(bool mute) noexcept;
    void panic() noexcept { setMuted(true); }
    bool isProtectionLatched() const noexcept { return protectionLatched.load(); }
    void resetProtectionIndicator() noexcept { protectionLatched.store(false); }
    void setNoiseEnabled(bool enabled) noexcept;
    void setNoiseColour(MeasurementNoise::Colour colour) noexcept;
    void setNoiseLevelDbfs(float level) noexcept;
    [[nodiscard]] State getState() const noexcept { return state.load(); }
    [[nodiscard]] Method getMethod() const noexcept { return method.load(); }
    [[nodiscard]] bool isCalibrationBusy() const noexcept;
    [[nodiscard]] bool isNoiseActive() const noexcept { return noiseActive.load(); }
    [[nodiscard]] bool isMuted() const noexcept { return muted.load() || state.load() == State::faultMuted; }
    [[nodiscard]] bool hasValidModel() const noexcept { return calibrated.load(); }
    [[nodiscard]] patel::Result getCalibrationResult() const noexcept { return result.load(); }
    [[nodiscard]] float getValidationImprovementDb() const noexcept { return validationDb.load(); }
    [[nodiscard]] int getDelaySamples() const noexcept { return reportedDelay.load(); }
    [[nodiscard]] int getFilterLength() const noexcept { return reportedLength.load(); }
    [[nodiscard]] int getDetectionCount() const noexcept { return detections.load(); }
    [[nodiscard]] int getClippedSampleCount() const noexcept { return clippedSamples.load(); }
    [[nodiscard]] float getGainDb() const noexcept { return gainDb.load(); }
    [[nodiscard]] float getNoiseLevelDbfs() const noexcept { return noiseLevelDbfs.load(); }
    [[nodiscard]] MeasurementNoise::Colour getNoiseColour() const noexcept { return noiseColour.load(); }
    [[nodiscard]] float getProbeLevelDbfs() const noexcept { return config.probeLevelDbfs; }
    [[nodiscard]] int getProbeDurationMilliseconds() const noexcept { return config.probeDurationMilliseconds; }
    static const char* describeState(State state) noexcept;
private:
    enum class Job { idle, queued, working, ready };
    static bool calibrationState(State state) noexcept;
    void stopWorker() noexcept;
    void workerLoop() noexcept;
    void beginCalibration() noexcept;
    void finishCalibration(patel::Result result) noexcept;
    float estimateFeedback() const noexcept;
    void pushReference(float sample) noexcept;
    float protect(float sample) noexcept;
    Config config;
    SessionCapture capture;
    int calibrationId = 0, activeModelId = 0, jobCalibrationId = 0;
    patel::EstimatorConfig estimatorConfig;
    std::vector<float> coefficients, reference;
    std::vector<float> probe, microphone, validationProbe, validationMicrophone;
    patel::Model workerModel;
    std::thread worker;
    std::atomic<bool> workerStop { false };
    std::atomic<Job> job { Job::idle };
    // Only the audio thread changes State. UI writes commands/parameters only.
    std::atomic<State> state { State::bypass };
    std::atomic<Method> method { Method::bypass };
    std::atomic<bool> calibrationRequested { false }, cancelRequested { false }, recoverRequested { false };
    std::atomic<bool> calibrated { false }, muted { false }, noiseActive { false };
    std::atomic<bool> resumeRequested { false }, protectionLatched { false };
    // bit 0: requested on; bit 1: calibration interlock. CAS prevents stale
    // enable requests being replayed when calibration releases the gate.
    std::atomic<unsigned> noiseControl { 0 };
    std::atomic<MeasurementNoise::Colour> noiseColour { MeasurementNoise::Colour::white };
    std::atomic<float> gainDb { -20.0f }, noiseLevelDbfs { -40.0f };
    std::atomic<patel::Result> result { patel::Result::none };
    std::atomic<float> validationDb { 0.0f };
    std::atomic<int> reportedDelay { 0 }, reportedLength { 0 }, detections { 0 }, clippedSamples { 0 };
    MeasurementNoise noise;
    HowlingDetector detector;
    std::size_t writeIndex = 0, captureIndex = 0;
    int activeLength = 0, delaySamples = 0, settlingRemaining = 0, flushSamples = 0;
    float gain = 0.1f, noiseAmplitude = 0.0f, noiseEnvelope = 0.0f, rampStep = 1.0f;
    double sampleRate = 48000.0;
    float outputEnvelope = 1.0f, resumeStep = 1.0f;
};
