#pragma once

#include <juce_audio_basics/juce_audio_basics.h>

class IProcessor
{
public:
    virtual ~IProcessor() = default;

    virtual void prepare(double sampleRate, int maximumBlockSize) noexcept = 0;
    virtual void stopped() noexcept {}
    virtual void callbackFinished(int, double) noexcept {}

    virtual void process(const juce::AudioBuffer<float>& input,
                         juce::AudioBuffer<float>& output) noexcept = 0;
};
