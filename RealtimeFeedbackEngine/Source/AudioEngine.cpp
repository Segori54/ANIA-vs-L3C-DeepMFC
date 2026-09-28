#include "AudioEngine.h"

#include "Config/AudioConfig.h"


#include <iostream>
#include <cmath>
#include <algorithm>
#include <chrono>

AudioEngine::AudioEngine(IProcessor& processorToUse) noexcept
    : processor(processorToUse)
{
    for (auto& level : inputLevelsDbfs)
        level.store(-100.0f, std::memory_order_relaxed);
    for (auto& level : outputLevelsDbfs)
        level.store(-100.0f, std::memory_order_relaxed);
    for (auto& duration : callbackMicroseconds)
        duration.store(0, std::memory_order_relaxed);
}

AudioEngine::~AudioEngine()
{
    shutdown();
}

bool AudioEngine::initialise(juce::AudioDeviceManager& manager,
                             juce::String deviceType,
                             juce::String inputDeviceName,
                             juce::String outputDeviceName, double requestedRate)
{
    shutdown();

    currentDeviceType = "No active device";
    currentDeviceName = "No active device";
    currentSampleRate = 0.0;
    currentBlockSize = 0;
    inputLatencySamples = 0;
    outputLatencySamples = 0;
    statusMessage = "Opening audio device";

    if (deviceType.isNotEmpty())
        manager.setCurrentAudioDeviceType(deviceType, false);

    juce::AudioDeviceManager::AudioDeviceSetup selectedSetup;
    selectedSetup.inputDeviceName = inputDeviceName;
    selectedSetup.outputDeviceName = outputDeviceName;
    selectedSetup.sampleRate = requestedRate;
    selectedSetup.bufferSize = audio_config::preferredBlockSize;

    std::cout << "Requested sample rate: " << selectedSetup.sampleRate << " Hz" << std::endl
              << "Requested block size: " << selectedSetup.bufferSize << " samples" << std::endl
              << "Opening audio device..." << std::endl;

    const auto error = manager.initialise(audio_config::inputChannels,
                                          audio_config::outputChannels,
                                          nullptr,
                                          true,
                                          {},
                                          &selectedSetup);

    if (error.isNotEmpty())
    {
        const auto failedSetup = manager.getAudioDeviceSetup();
        currentDeviceType = manager.getCurrentAudioDeviceType();
        statusMessage = "Audio device unavailable: " + error;
        std::cerr << "Audio initialization failed" << std::endl
                  << "Audio error/status: " << error << std::endl
                  << "Selected audio device type: " << manager.getCurrentAudioDeviceType() << std::endl
                  << "Selected input device: " << failedSetup.inputDeviceName << std::endl
                  << "Selected output device: " << failedSetup.outputDeviceName << std::endl
                  << "Selected sample rate: " << failedSetup.sampleRate << " Hz" << std::endl
                  << "Selected block size: " << failedSetup.bufferSize << " samples" << std::endl;
        return false;
    }

    auto* device = manager.getCurrentAudioDevice();
    const auto actualSetup = manager.getAudioDeviceSetup();
    if (device == nullptr || !rateMatches(requestedRate, device->getCurrentSampleRate()))
    {
        statusMessage = "Frecuencia incompatible: solicitada " + juce::String(requestedRate, 0)
            + " Hz; efectiva " + juce::String(device ? device->getCurrentSampleRate() : 0.0, 0) + " Hz";
        manager.closeAudioDevice();
        return false;
    }
    const auto printDeviceNames = [] (const char* label, const juce::StringArray& names)
    {
        std::cout << label << "\n";
        if (names.isEmpty())
        {
            std::cout << "    <none>\n";
            return;
        }

        for (int index = 0; index < names.size(); ++index)
            std::cout << "    " << names[index] << "\n";
    };

    std::cout << "Current audio device type: " << manager.getCurrentAudioDeviceType() << "\n";
    std::cout << "Current audio device name: "
              << (device != nullptr ? device->getName() : juce::String("<none>")) << "\n";
    std::cout << "Available device types:\n";

    for (auto* availableType : manager.getAvailableDeviceTypes())
    {
        availableType->scanForDevices();
        std::cout << "  " << availableType->getTypeName() << "\n";
        printDeviceNames("    Available output devices:", availableType->getDeviceNames(false));
        printDeviceNames("    Available input devices:", availableType->getDeviceNames(true));
    }

    std::cout << "Selected input device: "
              << (actualSetup.inputDeviceName.isNotEmpty() ? actualSetup.inputDeviceName
                                                            : juce::String("<none>")) << "\n"
              << "Selected output device: "
              << (actualSetup.outputDeviceName.isNotEmpty() ? actualSetup.outputDeviceName
                                                             : juce::String("<none>")) << "\n"
              << "Current sample rate: " << actualSetup.sampleRate << " Hz\n"
              << "Current block size: " << actualSetup.bufferSize << " samples\n";

    if (device != nullptr)
    {
        std::cout << "Input latency: " << device->getInputLatencyInSamples() << " samples\n"
                  << "Output latency: " << device->getOutputLatencyInSamples() << " samples\n";
    }

    currentDeviceType = manager.getCurrentAudioDeviceType();
    currentDeviceName = device != nullptr ? device->getName() : "No active device";
    currentSampleRate = actualSetup.sampleRate;
    currentBlockSize = actualSetup.bufferSize;
    inputLatencySamples = device != nullptr ? device->getInputLatencyInSamples() : 0;
    outputLatencySamples = device != nullptr ? device->getOutputLatencyInSamples() : 0;
    statusMessage = device != nullptr ? "Audio device running" : "Audio device did not open";

    std::cout << "Audio device diagnostics complete. Starting audio callback." << std::endl;

    manager.addAudioCallback(this);
    deviceManager = &manager;

    return device != nullptr;
}

juce::String AudioEngine::getCurrentDeviceType() const
{
    return currentDeviceType;
}

juce::String AudioEngine::getCurrentDeviceName() const
{
    return currentDeviceName;
}

double AudioEngine::getCurrentSampleRate() const noexcept
{
    return currentSampleRate;
}

int AudioEngine::getCurrentBlockSize() const noexcept
{
    return currentBlockSize;
}

int AudioEngine::getInputLatencySamples() const noexcept
{
    return inputLatencySamples;
}

int AudioEngine::getOutputLatencySamples() const noexcept
{
    return outputLatencySamples;
}

float AudioEngine::getInputLevelDbfs(int channel) const noexcept
{
    return juce::isPositiveAndBelow(channel, static_cast<int>(inputLevelsDbfs.size()))
        ? inputLevelsDbfs[static_cast<size_t>(channel)].load(std::memory_order_relaxed)
        : -100.0f;
}

float AudioEngine::getOutputLevelDbfs(int channel) const noexcept
{
    return juce::isPositiveAndBelow(channel, static_cast<int>(outputLevelsDbfs.size()))
        ? outputLevelsDbfs[static_cast<size_t>(channel)].load(std::memory_order_relaxed)
        : -100.0f;
}

juce::String AudioEngine::getStatusMessage() const
{
    return statusMessage;
}

double AudioEngine::getCallbackPercentile(double percentile) const noexcept
{
    std::array<std::uint32_t, timingWindowSize> snapshot {};
    const auto count = static_cast<std::size_t>(std::min<std::uint64_t>(
        callbackCount.load(std::memory_order_acquire), timingWindowSize));
    if (count == 0)
        return 0.0;
    for (std::size_t index = 0; index < count; ++index)
        snapshot[index] = callbackMicroseconds[index].load(std::memory_order_relaxed);
    std::sort(snapshot.begin(), snapshot.begin() + static_cast<std::ptrdiff_t>(count));
    const auto rank = static_cast<std::size_t>(std::clamp(percentile, 0.0, 1.0) * (count - 1));
    return snapshot[rank] / 1000.0;
}

double AudioEngine::getCallbackTimeP50Milliseconds() const noexcept { return getCallbackPercentile(0.50); }
double AudioEngine::getCallbackTimeP95Milliseconds() const noexcept { return getCallbackPercentile(0.95); }
double AudioEngine::getCallbackTimeP99Milliseconds() const noexcept { return getCallbackPercentile(0.99); }
int AudioEngine::getCallbackDeadlineMisses() const noexcept
{
    return callbackDeadlineMisses.load(std::memory_order_relaxed);
}

void AudioEngine::shutdown() noexcept
{
    deviceActive.store(false);
    if (deviceManager == nullptr)
        return;

    deviceManager->removeAudioCallback(this);
    deviceManager->closeAudioDevice();
    deviceManager = nullptr;
}

void AudioEngine::audioDeviceIOCallbackWithContext(const float* const* inputChannelData,
                                                   int totalNumInputChannels,
                                                   float* const* outputChannelData,
                                                   int totalNumOutputChannels,
                                                   int numSamples,
                                                   const juce::AudioIODeviceCallbackContext& context)
{
    juce::ignoreUnused(context);
    const auto callbackStart = std::chrono::steady_clock::now();

    updateLevels(inputChannelData, totalNumInputChannels, numSamples, inputLevelsDbfs);

    // These AudioBuffer objects refer directly to device-owned callback memory.
    // The external-data constructors do not allocate; ownership remains with the device.
    juce::AudioBuffer<float> inputBuffer(const_cast<float* const*>(inputChannelData),
                                         totalNumInputChannels,
                                         numSamples);
    juce::AudioBuffer<float> outputBuffer(outputChannelData,
                                          totalNumOutputChannels,
                                          numSamples);

    processor.process(inputBuffer, outputBuffer);

    updateLevels(outputChannelData, totalNumOutputChannels, numSamples, outputLevelsDbfs);
    monitor.push(totalNumInputChannels > 0 ? inputChannelData[0] : nullptr,
                 totalNumOutputChannels > 0 ? outputChannelData[0] : nullptr, numSamples);

    const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - callbackStart).count();
    const auto count = callbackCount.fetch_add(1, std::memory_order_acq_rel);
    callbackMicroseconds[static_cast<std::size_t>(count % timingWindowSize)].store(
        static_cast<std::uint32_t>(std::max<std::int64_t>(0, elapsed)), std::memory_order_release);
    const auto periodMicroseconds = currentSampleRate > 0.0
        ? static_cast<double>(numSamples) * 1.0e6 / currentSampleRate : 0.0;
    if (periodMicroseconds > 0.0 && elapsed > periodMicroseconds)
        callbackDeadlineMisses.fetch_add(1, std::memory_order_relaxed);
    processor.callbackFinished(numSamples, static_cast<double>(elapsed) / 1000.0);
}

void AudioEngine::updateLevels(const float* const* channelData,
                               int numChannels,
                               int numSamples,
                               std::array<std::atomic<float>, 32>& levels) noexcept
{
    for (int channel = 0; channel < static_cast<int>(levels.size()); ++channel)
    {
        if (channel >= numChannels || channelData == nullptr || channelData[channel] == nullptr
            || numSamples <= 0)
        {
            levels[static_cast<size_t>(channel)].store(-100.0f, std::memory_order_relaxed);
            continue;
        }

        double sumSquares = 0.0;
        const auto* samples = channelData[channel];
        for (int sample = 0; sample < numSamples; ++sample)
            sumSquares += static_cast<double>(samples[sample]) * samples[sample];

        const auto rms = std::sqrt(sumSquares / static_cast<double>(numSamples));
        const auto dbfs = rms > 0.00001 ? 20.0 * std::log10(rms) : -100.0;
        levels[static_cast<size_t>(channel)].store(static_cast<float>(dbfs),
                                                   std::memory_order_relaxed);
    }
}

void AudioEngine::audioDeviceAboutToStart(juce::AudioIODevice* device)
{
    if (device != nullptr)
    {
        currentSampleRate = device->getCurrentSampleRate();
        currentBlockSize = device->getCurrentBufferSizeSamples();
        inputLatencySamples = device->getInputLatencyInSamples();
        outputLatencySamples = device->getOutputLatencyInSamples();
        callbackCount.store(0);
        callbackDeadlineMisses.store(0);
        for (auto& duration : callbackMicroseconds) duration.store(0);
        processor.prepare(device->getCurrentSampleRate(), device->getCurrentBufferSizeSamples());
        monitor.prepare(device->getCurrentSampleRate());
        deviceActive.store(true);
    }
}

void AudioEngine::audioDeviceStopped()
{
    deviceActive.store(false);
    processor.stopped();
    monitor.stop();
}
