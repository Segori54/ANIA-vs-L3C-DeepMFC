#include "../Source/Monitoring/AudioMonitor.h"
#include "../Source/UI/UiRules.h"
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <new>
#include <stdexcept>

thread_local bool auditing = false;
thread_local int allocations = 0;
void* operator new(std::size_t size)
{
    if (auditing) ++allocations;
    if (auto* result = std::malloc(size == 0 ? 1 : size)) return result;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete[](void* p) noexcept { ::operator delete(p); }
void operator delete[](void* p, std::size_t) noexcept { ::operator delete(p); }
namespace
{
void require(bool value, const char* message) { if (! value) throw std::runtime_error(message); }
void push(AudioMonitor& monitor, const float* in, const float* out, int n)
{
    auditing = true; monitor.push(in, out, n); auditing = false;
}
void testLevels()
{
    AudioMonitor monitor; monitor.prepare(48000);
    std::vector<float> signal(48000), silence(48000, 0.0f);
    for (int n = 0; n < 48000; ++n) signal[static_cast<std::size_t>(n)] = 0.5f * std::sin(juce::MathConstants<float>::twoPi * n / 48.0f);
    push(monitor, signal.data(), silence.data(), 48000);
    require(std::abs(monitor.level(0).rmsDb + 9.0309f) < 0.02, "RMS sine calibration");
    require(std::abs(monitor.level(0).peakDb + 6.0206f) < 0.02, "sample peak calibration");
    require(monitor.level(1).rmsDb <= -100, "output silence");
    push(monitor, silence.data(), silence.data(), 48000);
    require(std::abs(monitor.level(0).peakDb + 6.0206f) < 0.1, "one second peak hold");
    push(monitor, silence.data(), silence.data(), 24000);
    require(std::abs(monitor.level(0).peakDb + 16.0206f) < 0.1, "20 dB/s peak decay");
    require(monitor.level(0).rmsDb <= -100, "300 ms RMS cleared");
    float clip = 1.0f;
    push(monitor, &clip, &clip, 1); push(monitor, silence.data(), silence.data(), 200);
    require(monitor.level(0).clipped && monitor.level(1).clipped, "clip latch");
    monitor.resetClips(); push(monitor, silence.data(), silence.data(), 1);
    require(! monitor.level(0).clipped, "clip reset");
}
void testSpectrum()
{
    juce::dsp::FFT fft(12);
    std::array<float, AudioMonitor::fftSize> sine {};
    std::array<float, 2 * AudioMonitor::fftSize> scratch {};
    std::array<float, AudioMonitor::bins> spectrum {};
    for (int n = 0; n < AudioMonitor::fftSize; ++n)
        sine[static_cast<std::size_t>(n)] = std::sin(juce::MathConstants<float>::twoPi * 128 * n / AudioMonitor::fftSize);
    AudioMonitor::spectrumOf(sine, spectrum, fft, scratch);
    require(std::abs(spectrum[128]) < 0.01, "Hann coherent gain normalization");
    require(std::max_element(spectrum.begin(), spectrum.end()) - spectrum.begin() == 128, "FFT peak bin");
    for (auto& value : sine) value *= 0.1f;
    AudioMonitor::spectrumOf(sine, spectrum, fft, scratch);
    require(std::abs(spectrum[128] + 20.0f) < 0.02, "FFT amplitude scaling");
}
void testQueueGaps()
{
    // This checks queue contents, not throughput. Allow slower ARM systems and
    // emulators enough time to finish the analysis without changing assertions.
    constexpr int snapshotWaitAttempts = 2000;
    AudioMonitor monitor; monitor.prepare(48000);
    std::vector<float> signal(AudioMonitor::queueCapacity * 2, 0.01f);
    push(monitor, signal.data(), signal.data(), static_cast<int>(signal.size()));
    AudioMonitor::Snapshot snapshot;
    for (int retry = 0; retry < snapshotWaitAttempts; ++retry)
    {
        monitor.copySnapshot(snapshot);
        if (snapshot.newestColumn == 64) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    require(snapshot.newestColumn == 64 && snapshot.droppedSamples == AudioMonitor::queueCapacity, "queue overflow count / drain");
    push(monitor, signal.data(), signal.data(), AudioMonitor::fftSize);
    for (int retry = 0; retry < snapshotWaitAttempts; ++retry)
    {
        monitor.copySnapshot(snapshot);
        if (snapshot.newestColumn == 132) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    require(snapshot.newestColumn == 132, "sample clock lost after queue gap");
    for (int ch = 0; ch < 2; ++ch)
    {
        require(std::isnan(snapshot.history[static_cast<std::size_t>(ch)][100 * AudioMonitor::historyBins]), "gap painted as continuous data");
        require(std::isfinite(snapshot.history[static_cast<std::size_t>(ch)][132 * AudioMonitor::historyBins]), "no valid history after gap");
    }
    monitor.prepare(44100); monitor.copySnapshot(snapshot);
    require(snapshot.sampleRate == 44100 && snapshot.newestColumn == -1 && snapshot.droppedSamples == 0, "device restart retained analysis");
}
void testGain()
{
    double value = -20;
    for (int n = 0; n < 100; ++n) value = ui_rules::steppedGain(value, 1, 0.1);
    require(value == -10, "decimal gain drift");
    require(ui_rules::steppedGain(29.9, 1, 5) == 30 && ui_rules::steppedGain(-59.9, -1, 1) == -60, "gain boundaries");
    require(ui_rules::steppedGain(-10.3, 1, 5) == -5.3, "gain step unexpectedly quantized baseline");
}
}
int main()
{
    try { testLevels(); testSpectrum(); testQueueGaps(); testGain(); require(allocations == 0, "audio monitor allocated in callback"); }
    catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
    std::cout << "Meter, FFT calibration, SPSC discontinuities, gain steps and RT allocation tests passed\n";
}
