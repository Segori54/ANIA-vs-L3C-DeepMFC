#pragma once
#include <juce_dsp/juce_dsp.h>
#include <array>
#include <atomic>
#include <cstdint>
#include <mutex>
#include <thread>
#include <vector>

// Audio producer -> analysis worker -> GUI. No locks/allocations in push().
class AudioMonitor
{
public:
    static constexpr int fftSize = 4096, hopSize = 1024, bins = fftSize / 2 + 1;
    static constexpr int historyBins = 256, queueCapacity = 65536;
    struct Level { float rmsDb = -120, peakDb = -120; bool clipped = false; };
    struct Snapshot
    {
        double sampleRate = 48000;
        std::uint64_t version = 0, droppedSamples = 0;
        int columns = 469, newestColumn = -1;
        bool running = false;
        std::array<std::array<float, bins>, 2> spectrum {};
        // Time-major ring, logarithmically spaced frequency rows; NaN is a gap.
        std::array<std::vector<float>, 2> history;
    };
    AudioMonitor();
    ~AudioMonitor();
    void prepare(double sampleRate);
    void stop(); // device lifecycle, not audio callback
    void push(const float* input, const float* output, int count) noexcept;
    Level level(int channel) const noexcept;
    void resetClips() noexcept { clearClips.store(true); }
    void copySnapshot(Snapshot& destination);
    static void spectrumOf(const std::array<float, fftSize>& samples, std::array<float, bins>& db,
                           juce::dsp::FFT& fft, std::array<float, 2 * fftSize>& scratch) noexcept;
private:
    struct Pair { float input, output; std::uint64_t sequence; };
    struct Meter
    {
        std::vector<double> squares;
        std::size_t index = 0;
        double sum = 0;
        float peak = 0;
        int hold = 0;
        std::atomic<float> rmsDb { -120 }, peakDb { -120 };
        std::atomic<bool> clip { false };
    };
    void work();
    std::array<Meter, 2> meters;
    std::vector<Pair> queue;
    alignas(64) std::atomic<std::uint64_t> write { 0 };
    alignas(64) std::atomic<std::uint64_t> read { 0 };
    std::atomic<std::uint64_t> dropped { 0 };
    std::uint64_t sequence = 0;
    double rate = 48000;
    float peakDecay = 1;
    std::atomic<bool> stopRequested { true }, clearClips { false };
    std::thread worker;
    std::mutex snapshotMutex; // worker and GUI only
    Snapshot published;
};
