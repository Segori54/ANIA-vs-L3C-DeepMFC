#pragma once

#include <vector>

namespace patel
{
enum class Result { none, running, accepted, noReturn, clipped, poorFit, cancelled, invalid, outOfRange };
const char* describe(Result result) noexcept;

struct Model
{
    // h[k] multiplies output[n - delaySamples - k]; delaySamples is >= 1.
    int delaySamples = 0;
    std::vector<float> coefficients;
    float validationImprovementDb = 0.0f;
    Result result = Result::invalid;
};

struct EstimatorConfig
{
    int maximumDelaySamples = 4800;
    int maximumFilterLength = 2048;
    double regularisation = 1.0e-4;
    double retainedEnergy = 0.999;
    double minimumImprovementDb = 6.0;
};

// Generalized Levinson recursion for a symmetric positive-definite Toeplitz
// system with an arbitrary right hand side. O(P^2), no explicit inverse.
bool solveToeplitz(const std::vector<double>& correlation,
                   const std::vector<double>& rhs, std::vector<double>& solution);

// Worker-thread only. All captures include the complete post-probe return tail.
Model estimate(const std::vector<float>& probe, const std::vector<float>& microphone,
               const std::vector<float>& validationProbe,
               const std::vector<float>& validationMicrophone,
               const EstimatorConfig& config);
}
