#include "AudioMonitor.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>

namespace { float db(float amplitude) { return amplitude > 1.0e-6f ? 20.0f * std::log10(amplitude) : -120.0f; } }
AudioMonitor::AudioMonitor() : queue(queueCapacity) {}
AudioMonitor::~AudioMonitor() { stop(); }
void AudioMonitor::stop()
{
    stopRequested.store(true);
    if (worker.joinable()) worker.join();
    std::lock_guard lock(snapshotMutex);
    published.running = false;
    ++published.version;
}
void AudioMonitor::prepare(double sampleRate)
{
    stop();
    rate = sampleRate > 0 ? sampleRate : 48000;
    peakDecay = static_cast<float>(std::pow(10.0, -1.0 / rate)); // 20 dB/s
    for (auto& meter : meters)
    {
        meter.squares.assign(static_cast<std::size_t>(std::max(1.0, std::round(rate * 0.3))), 0.0);
        meter.index = 0; meter.sum = 0; meter.peak = 0; meter.hold = 0;
        meter.rmsDb.store(-120); meter.peakDb.store(-120); meter.clip.store(false);
    }
    read.store(0); write.store(0); dropped.store(0); sequence = 0; clearClips.store(false);
    {
        std::lock_guard lock(snapshotMutex);
        published.sampleRate = rate;
        published.columns = static_cast<int>(std::ceil(10.0 * rate / hopSize));
        published.newestColumn = -1; published.droppedSamples = 0;
        for (auto& spectrum : published.spectrum) spectrum.fill(-120.0f);
        for (auto& history : published.history)
            history.assign(static_cast<std::size_t>(published.columns * historyBins), std::numeric_limits<float>::quiet_NaN());
        published.running = true;
        ++published.version;
    }
    stopRequested.store(false);
    worker = std::thread([this] { work(); });
}
AudioMonitor::Level AudioMonitor::level(int channel) const noexcept
{
    const auto& meter = meters[static_cast<std::size_t>(std::clamp(channel, 0, 1))];
    return { meter.rmsDb.load(), meter.peakDb.load(), meter.clip.load() };
}
void AudioMonitor::copySnapshot(Snapshot& destination)
{
    std::lock_guard lock(snapshotMutex);
    if (destination.version != published.version) destination = published;
    destination.droppedSamples = dropped.load();
}
void AudioMonitor::push(const float* input, const float* output, int count) noexcept
{
    if (meters[0].squares.empty()) return;
    if (clearClips.exchange(false)) for (auto& meter : meters) meter.clip.store(false);
    auto cursor = write.load(std::memory_order_relaxed);
    const auto available = read.load(std::memory_order_acquire) + queueCapacity;
    std::uint64_t lost = 0;
    for (int n = 0; n < count; ++n)
    {
        float values[2] { input != nullptr ? input[n] : 0.0f, output != nullptr ? output[n] : 0.0f };
        for (int ch = 0; ch < 2; ++ch)
        {
            auto& meter = meters[static_cast<std::size_t>(ch)];
            if (! std::isfinite(values[ch])) { meter.clip.store(true); values[ch] = 0; }
            const auto magnitude = std::abs(values[ch]);
            if (magnitude >= 1.0f) meter.clip.store(true);
            const double square = static_cast<double>(values[ch]) * values[ch];
            meter.sum += square - meter.squares[meter.index];
            meter.squares[meter.index] = square;
            if (++meter.index == meter.squares.size()) meter.index = 0;
            if (magnitude >= meter.peak) { meter.peak = magnitude; meter.hold = static_cast<int>(rate); }
            else if (meter.hold > 0) --meter.hold;
            else meter.peak *= peakDecay;
        }
        if (cursor < available)
        {
            queue[static_cast<std::size_t>(cursor % queueCapacity)] = { values[0], values[1], sequence };
            ++cursor;
        }
        else ++lost;
        ++sequence;
    }
    for (auto& meter : meters)
    {
        meter.rmsDb.store(db(static_cast<float>(std::sqrt(std::max(0.0, meter.sum) / meter.squares.size()))));
        meter.peakDb.store(db(meter.peak));
    }
    if (lost != 0) dropped.fetch_add(lost, std::memory_order_relaxed);
    write.store(cursor, std::memory_order_release);
}
void AudioMonitor::spectrumOf(const std::array<float, fftSize>& samples, std::array<float, bins>& values,
                              juce::dsp::FFT& fft, std::array<float, 2 * fftSize>& scratch) noexcept
{
    double windowSum = 0;
    for (int n = 0; n < fftSize; ++n)
    {
        const auto window = static_cast<float>(0.5 - 0.5 * std::cos(juce::MathConstants<double>::twoPi * n / (fftSize - 1)));
        scratch[static_cast<std::size_t>(n)] = samples[static_cast<std::size_t>(n)] * window;
        windowSum += window;
    }
    std::fill(scratch.begin() + fftSize, scratch.end(), 0.0f);
    fft.performRealOnlyForwardTransform(scratch.data());
    for (int k = 0; k < bins; ++k)
    {
        const auto factor = k == 0 || k == fftSize / 2 ? 1.0 : 2.0;
        values[static_cast<std::size_t>(k)] = db(static_cast<float>(factor * std::hypot(
            scratch[static_cast<std::size_t>(2 * k)], scratch[static_cast<std::size_t>(2 * k + 1)]) / windowSum));
    }
}
void AudioMonitor::work()
{
    juce::dsp::FFT fft(12);
    std::array<std::array<float, fftSize>, 2> rolling {}, frame {};
    std::array<std::array<float, bins>, 2> spectra {};
    std::array<float, 2 * fftSize> scratch {};
    int position = 0, filled = 0, hop = 0;
    std::uint64_t expected = 0, previousFrame = 0;
    bool haveFrame = false;
    auto cursor = read.load();
    while (! stopRequested.load())
    {
        const auto end = write.load(std::memory_order_acquire);
        if (cursor == end) { std::this_thread::sleep_for(std::chrono::milliseconds(2)); continue; }
        while (cursor < end && ! stopRequested.load())
        {
            const auto pair = queue[static_cast<std::size_t>(cursor++ % queueCapacity)];
            if (pair.sequence != expected) { filled = hop = position = 0; }
            expected = pair.sequence + 1;
            rolling[0][static_cast<std::size_t>(position)] = pair.input;
            rolling[1][static_cast<std::size_t>(position)] = pair.output;
            position = (position + 1) % fftSize;
            filled = std::min(fftSize, filled + 1);
            // Frame times stay on the original sample clock, including gaps.
            hop = static_cast<int>((pair.sequence + 1) % hopSize);
            if (filled < fftSize || hop != 0) continue;
            for (int ch = 0; ch < 2; ++ch)
            {
                for (int n = 0; n < fftSize; ++n)
                    frame[static_cast<std::size_t>(ch)][static_cast<std::size_t>(n)] = rolling[static_cast<std::size_t>(ch)][static_cast<std::size_t>((position + n) % fftSize)];
                spectrumOf(frame[static_cast<std::size_t>(ch)], spectra[static_cast<std::size_t>(ch)], fft, scratch);
            }
            const auto frameNumber = (pair.sequence + 1) / hopSize;
            {
                std::lock_guard lock(snapshotMutex);
                const auto columns = static_cast<std::uint64_t>(published.columns);
                const auto firstGap = haveFrame ? std::max(previousFrame + 1, frameNumber > columns ? frameNumber - columns : 0) : frameNumber;
                for (auto missing = firstGap; missing < frameNumber; ++missing)
                    for (auto& history : published.history)
                        std::fill_n(history.begin() + static_cast<std::ptrdiff_t>((missing % columns) * historyBins), historyBins,
                                    std::numeric_limits<float>::quiet_NaN());
                const auto column = static_cast<int>(frameNumber % columns);
                const auto maximumFrequency = std::min(20000.0, rate * 0.5);
                for (int ch = 0; ch < 2; ++ch)
                    for (int row = 0; row < historyBins; ++row)
                    {
                        const auto low = 20.0 * std::pow(maximumFrequency / 20.0, static_cast<double>(row) / historyBins);
                        const auto high = 20.0 * std::pow(maximumFrequency / 20.0, static_cast<double>(row + 1) / historyBins);
                        const int startBin = std::clamp(static_cast<int>(std::round(low * fftSize / rate)), 1, bins - 1);
                        const int endBin = std::clamp(static_cast<int>(std::round(high * fftSize / rate)), startBin, bins - 1);
                        const auto& spectrum = spectra[static_cast<std::size_t>(ch)];
                        published.history[static_cast<std::size_t>(ch)][static_cast<std::size_t>(column * historyBins + row)] =
                            *std::max_element(spectrum.begin() + startBin, spectrum.begin() + endBin + 1);
                    }
                published.spectrum = spectra;
                published.newestColumn = column;
                ++published.version;
            }
            previousFrame = frameNumber; haveFrame = true;
        }
        read.store(cursor, std::memory_order_release);
    }
}
