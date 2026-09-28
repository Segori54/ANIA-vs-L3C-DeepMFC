#pragma once

#include <array>
#include <cstddef>

class HowlingDetector
{
public:
    void prepare(double newSampleRate) noexcept;
    bool processSample(float sample) noexcept;
    void reset() noexcept;

private:
    static constexpr std::size_t frameSize = 1024;
    static constexpr std::array<float, 16> frequencies {
        200.0f, 260.0f, 340.0f, 440.0f, 570.0f, 740.0f, 960.0f, 1250.0f,
        1620.0f, 2100.0f, 2720.0f, 3530.0f, 4580.0f, 5940.0f, 7000.0f, 8000.0f
    };

    std::array<float, frameSize> frame {};
    std::size_t writeIndex = 0;
    double sampleRate = 48000.0;
    int persistentFrames = 0;
};
