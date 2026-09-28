#pragma once

#include "Processors/IProcessor.h"
#include "Monitoring/AudioMonitor.h"

#include <juce_audio_devices/juce_audio_devices.h>

#include <array>
#include <atomic>
#include <cmath>

class AudioEngine final : private juce::AudioIODeviceCallback
{
public:
    explicit AudioEngine(IProcessor& processorToUse) noexcept;
    ~AudioEngine() override;

    bool initialise(juce::AudioDeviceManager& deviceManager,
                    juce::String deviceType,
                    juce::String inputDeviceName,
                    juce::String outputDeviceName, double requestedRate = 48000.0);
    static bool rateMatches(double requested, double actual) noexcept { return (requested == 16000.0 || requested == 48000.0) && std::abs(requested - actual) < 0.5; }
#ifdef CAPTURE_TESTING
    void prepareOffline(double rate, int block) { currentSampleRate=rate; currentBlockSize=block; processor.prepare(rate,block); monitor.prepare(rate); }
    void callbackOffline(const float* in, float* out, int samples) { juce::AudioIODeviceCallbackContext c; audioDeviceIOCallbackWithContext(&in,1,&out,1,samples,c); }
#endif
    void shutdown() noexcept;
    bool isDeviceActive() const noexcept { return deviceActive.load(); }
    AudioMonitor& getMonitor() noexcept { return monitor; }

    [[nodiscard]] juce::String getCurrentDeviceType() const;
    [[nodiscard]] juce::String getCurrentDeviceName() const;
    [[nodiscard]] double getCurrentSampleRate() const noexcept;
    [[nodiscard]] int getCurrentBlockSize() const noexcept;
    [[nodiscard]] int getInputLatencySamples() const noexcept;
    [[nodiscard]] int getOutputLatencySamples() const noexcept;
    [[nodiscard]] float getInputLevelDbfs(int channel) const noexcept;
    [[nodiscard]] float getOutputLevelDbfs(int channel) const noexcept;
    [[nodiscard]] juce::String getStatusMessage() const;
    [[nodiscard]] double getCallbackTimeP50Milliseconds() const noexcept;
    [[nodiscard]] double getCallbackTimeP95Milliseconds() const noexcept;
    [[nodiscard]] double getCallbackTimeP99Milliseconds() const noexcept;
    [[nodiscard]] int getCallbackDeadlineMisses() const noexcept;

private:
    void audioDeviceIOCallbackWithContext(const float* const* inputChannelData,
                                          int totalNumInputChannels,
                                          float* const* outputChannelData,
                                          int totalNumOutputChannels,
                                          int numSamples,
                                          const juce::AudioIODeviceCallbackContext& context) override;
    void audioDeviceAboutToStart(juce::AudioIODevice* device) override;
    void audioDeviceStopped() override;
    static void updateLevels(const float* const* channelData,
                             int numChannels,
                             int numSamples,
                             std::array<std::atomic<float>, 32>& levels) noexcept;
    [[nodiscard]] double getCallbackPercentile(double percentile) const noexcept;

    IProcessor& processor;
    std::atomic<bool> deviceActive {false};
    AudioMonitor monitor;
    juce::AudioDeviceManager* deviceManager = nullptr;
    juce::String currentDeviceType { "No active device" };
    juce::String currentDeviceName { "No active device" };
    double currentSampleRate = 0.0;
    int currentBlockSize = 0;
    int inputLatencySamples = 0;
    int outputLatencySamples = 0;
    std::array<std::atomic<float>, 32> inputLevelsDbfs;
    std::array<std::atomic<float>, 32> outputLevelsDbfs;
    static constexpr std::size_t timingWindowSize = 2048;
    std::array<std::atomic<std::uint32_t>, timingWindowSize> callbackMicroseconds {};
    std::atomic<std::uint64_t> callbackCount { 0 };
    std::atomic<int> callbackDeadlineMisses { 0 };
    juce::String statusMessage { "Waiting to initialise audio device" };
};
