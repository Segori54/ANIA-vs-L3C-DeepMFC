#pragma once

#include <array>
#include <bit>
#include <cmath>
#include <cstdint>

// Deterministic Gaussian white noise and Voss-McCartney pink noise.
// Pink uses 16 octave-rate rows plus one white row, normalized to unit variance.
class MeasurementNoise
{
public:
    enum class Colour { white, pink };
    void reset(std::uint32_t seed = 0x12345678u) noexcept
    {
        random = seed != 0 ? seed : 1;
        counter = 0;
        spareReady = false;
        sum = 0.0f;
        for (auto& row : rows) { row = gaussian(); sum += row; }
    }
    float next(Colour colour) noexcept
    {
        if (colour == Colour::white) return gaussian();
        const auto row = std::countr_zero(++counter);
        if (row < static_cast<int>(rows.size()))
        {
            sum -= rows[static_cast<std::size_t>(row)];
            rows[static_cast<std::size_t>(row)] = gaussian();
            sum += rows[static_cast<std::size_t>(row)];
        }
        return (sum + gaussian()) / std::sqrt(17.0f);
    }
private:
    float uniform() noexcept
    {
        random ^= random << 13; random ^= random >> 17; random ^= random << 5;
        return static_cast<float>((static_cast<double>(random) + 0.5) / 4294967296.0);
    }
    float gaussian() noexcept
    {
        if (spareReady) { spareReady = false; return spare; }
        const auto radius = std::sqrt(-2.0f * std::log(uniform()));
        const auto angle = 6.28318530718f * uniform();
        spare = radius * std::sin(angle);
        spareReady = true;
        return radius * std::cos(angle);
    }
    std::array<float, 16> rows {};
    std::uint32_t random = 1, counter = 0;
    float sum = 0.0f, spare = 0.0f;
    bool spareReady = false;
};
