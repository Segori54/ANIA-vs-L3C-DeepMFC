#pragma once
#include <algorithm>
#include <cmath>
namespace ui_rules
{
inline double steppedGain(double gain, int direction, double step)
{
    return std::clamp((std::round(gain * 10.0) + direction * std::round(step * 10.0)) / 10.0, -60.0, 30.0);
}
}
