#include "HowlingDetector.h"

#include <algorithm>
#include <cmath>
#include <numbers>

void HowlingDetector::prepare(double newSampleRate) noexcept
{
    sampleRate = newSampleRate > 0.0 ? newSampleRate : 48000.0;
    reset();
}

void HowlingDetector::reset() noexcept
{
    frame.fill(0.0f);
    writeIndex = 0;
    persistentFrames = 0;
}

bool HowlingDetector::processSample(float sample) noexcept
{
    frame[writeIndex++] = sample;
    if (writeIndex < frame.size())
        return false;
    writeIndex = 0;

    double totalPower = 1.0e-12;
    for (const auto value : frame)
        totalPower += static_cast<double>(value) * value;

    double peakPower = 0.0;
    for (const auto frequency : frequencies)
    {
        const auto omega = 2.0 * std::numbers::pi * frequency / sampleRate;
        const auto coefficient = 2.0 * std::cos(omega);
        double previous = 0.0;
        double previous2 = 0.0;
        for (const auto value : frame)
        {
            const auto current = value + coefficient * previous - previous2;
            previous2 = previous;
            previous = current;
        }
        peakPower = std::max(peakPower,
                             previous2 * previous2 + previous * previous
                                 - coefficient * previous * previous2);
    }

    const auto concentrationDb = 10.0 * std::log10(peakPower / totalPower + 1.0e-12);
    persistentFrames = concentrationDb > 15.0 && totalPower > 1.0e-5
        ? persistentFrames + 1
        : 0;
    return persistentFrames == 3;
}
