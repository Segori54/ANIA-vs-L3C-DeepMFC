#pragma once
#include <juce_core/juce_core.h>
#include "../Processors/PatelEstimator.h"
#include <array>
#include <atomic>
#include <thread>
#include <vector>

// Each ring has exactly one producer. All filesystem/JSON work belongs to writerLoop.
class SessionCapture
{
public:
    enum class Status { idle, preparing, recording, saving, saved, incomplete };
    enum class StopReason { manual, deviceStopped, overflow, diskError, shutdown };
    struct Tags
    {
        int state = 0, result = 0, method = 0, calibration = 0, model = 0;
        bool muted = false, cleanValid = false, noise = false, limited = false;
        float targetGainDb = 0;
        bool operator==(const Tags&) const = default;
    };
    struct Options { double queueSeconds = 8, segmentSeconds = 60; int writerDelayMs = 0; std::int64_t failAfterSamples = -1; };
    SessionCapture() = default;
    ~SessionCapture();
    bool start(const juce::File& root, double rate, juce::var metadata, const patel::EstimatorConfig&);
    bool start(const juce::File& root, double rate, juce::var metadata, const patel::EstimatorConfig&, Options);
    void requestStop(StopReason = StopReason::manual) noexcept;
    void deviceStopped() noexcept; // only after callbacks stop
    void wait(); // never on audio thread
    Status status() const noexcept { return state.load(std::memory_order_acquire); }
    bool busy() const noexcept { auto s = status(); return s == Status::preparing || s == Status::recording || s == Status::saving; }
    double seconds() const noexcept { return static_cast<double>(written.load()) / rateHz; }
    juce::File directory() const { return folder; } // GUI-owned, unchanged while busy
    juce::String error() const { return errorCode.load() == 1 ? "Cola llena / metadatos perdidos" : "Error de escritura o captura interrumpida"; }
    bool beginBlock(const float* coefficients, int length, int delay, int modelId,
                    const float* history, int historySize, int writeIndex, float validationDb) noexcept;
    void sample(const std::array<float, 7>&, const Tags&) noexcept;
    void endBlock(int samples, double milliseconds) noexcept;
    void workerModel(const patel::Model&, int calibration) noexcept;
    void observation(const juce::String&); // GUI, separate queue (text can allocate here)
private:
    struct Packet { std::array<float, 7> values {}; Tags tags; std::uint64_t index = 0; int block = 0; double ms = 0; };
    struct ModelPacket { std::array<float, 4096> coefficients {}; int length=0, delay=0, id=0, result=0; float db=0; };
    struct Observation { juce::String text; std::uint64_t sample=0; };
    void fail(int code) noexcept;
    void writerLoop() noexcept;
    bool push(const Packet&) noexcept;
    std::vector<Packet> queue;
    std::array<ModelPacket, 8> models;
    std::array<Observation, 64> observations;
    ModelPacket initialModel;
    std::array<float, 16384> initialHistory {};
    int historyCount = 0;
    std::atomic<std::uint64_t> write {0}, read {0}, modelWrite {0}, modelRead {0}, observationWrite {0}, observationRead {0};
    std::atomic<std::uint64_t> written {0};
    std::atomic<std::uint64_t> produced {0};
    std::atomic<int> publishing {0}, errorCode {0};
    std::atomic<Status> state {Status::idle};
    std::atomic<StopReason> reason {StopReason::manual};
    std::atomic<bool> stopRequested {false}, audioDone {false}, allowModels {false}, snapshotReady {false};
    std::thread writer;
    juce::File folder;
    juce::var manifest;
    patel::EstimatorConfig config;
    Options options;
    double rateHz = 48000;
    std::uint64_t sampleIndex = 0;
    bool blockActive = false;
};
