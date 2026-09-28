#pragma once

namespace audio_config
{
inline constexpr double preferredSampleRate = 48000.0;
inline constexpr int preferredBlockSize = 128;
inline constexpr int inputChannels = 1;
inline constexpr int outputChannels = 1;
inline constexpr int maximumAddedLatencyMilliseconds = 1000;
}
