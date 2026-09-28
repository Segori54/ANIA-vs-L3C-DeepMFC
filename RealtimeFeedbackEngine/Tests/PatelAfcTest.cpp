#include "../Source/Processors/PatelAfcProcessor.h"
#include "../Source/Monitoring/AudioMonitor.h"
#include <juce_dsp/juce_dsp.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <new>
#include <stdexcept>
#include <thread>
#include <vector>

// Audit C++ heap allocations on the calling audio thread, excluding the worker.
thread_local bool auditingAudio = false;
thread_local int audioAllocations = 0;
void* operator new(std::size_t size)
{
    if (auditingAudio) ++audioAllocations;
    if (auto* memory = std::malloc(size == 0 ? 1 : size)) return memory;
    throw std::bad_alloc();
}
void operator delete(void* memory) noexcept { std::free(memory); }
void operator delete(void* memory, std::size_t) noexcept { std::free(memory); }
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete[](void* memory) noexcept { ::operator delete(memory); }
void operator delete[](void* memory, std::size_t) noexcept { ::operator delete(memory); }

namespace
{
void require(bool condition, const char* message)
{
    if (! condition) throw std::runtime_error(message);
}
PatelAfcProcessor::Config testConfig()
{
    PatelAfcProcessor::Config config;
    config.filterLength = 128;
    config.maximumDelayMilliseconds = 30;
    config.probeDurationMilliseconds = 400;
    config.validationDurationMilliseconds = 200;
    return config;
}
struct Rig
{
    explicit Rig(int blockSize, PatelAfcProcessor::Config config = testConfig())
        : processor(config), input(1, blockSize), output(1, blockSize), block(blockSize), history(32768, 0.0f)
    {
        processor.prepare(48000.0, block);
        monitor.prepare(48000.0);
        source.reset(991u);
    }
    void tick()
    {
        for (int n = 0; n < block; ++n)
        {
            const auto now = sample + n;
            float feedback = 0.0f;
            for (int k = 0; k < static_cast<int>(path.size()); ++k)
                if (now >= delay + k)
                    feedback += path[static_cast<std::size_t>(k)] * history[static_cast<std::size_t>(now - delay - k) % history.size()];
            input.setSample(0, n, physicalGain * feedback + sourceLevel * source.next(MeasurementNoise::Colour::white) + forcedInput);
        }
        const auto start = std::chrono::steady_clock::now();
        auditingAudio = true;
        processor.process(input, output);
        monitor.push(input.getReadPointer(0), output.getReadPointer(0), block);
        auditingAudio = false;
        const auto elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
        times.push_back(elapsed);
        for (int n = 0; n < block; ++n)
        {
            const auto value = output.getSample(0, n);
            require(std::isfinite(value), "non-finite output");
            history[static_cast<std::size_t>(sample + n) % history.size()] = value;
        }
        sample += block;
    }
    void run(int samples)
    {
        for (int i = 0; i < samples; i += block) tick();
    }
    void calibrate(bool attackNoise = true)
    {
        processor.requestCalibration();
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(15);
        do
        {
            if (attackNoise) processor.setNoiseEnabled(true);
            tick();
            const auto state = processor.getState();
            if (state == PatelAfcProcessor::State::calibration || state == PatelAfcProcessor::State::validating
                || state == PatelAfcProcessor::State::estimating)
                require(! processor.isNoiseActive(), "test noise active during calibration");
            if (state == PatelAfcProcessor::State::estimating) std::this_thread::sleep_for(std::chrono::milliseconds(1));
            require(std::chrono::steady_clock::now() < deadline, "calibration worker timed out");
        } while (processor.isCalibrationBusy());
    }
    double residualRms(float physical = 1.0f)
    {
        physicalGain = physical;
        double sum = 0.0;
        int count = 0;
        for (int b = 0; b < 120; ++b)
        {
            tick();
            for (int n = 0; n < block; ++n) { const auto v = output.getSample(0, n); sum += v * v; ++count; }
        }
        return std::sqrt(sum / count);
    }
    PatelAfcProcessor processor;
    AudioMonitor monitor;
    juce::AudioBuffer<float> input, output;
    int block, sample = 0, delay = 576;
    std::vector<float> history;
    std::vector<double> times;
    MeasurementNoise source;
    float physicalGain = 1.0f, sourceLevel = 0.0f, forcedInput = 0.0f;
    std::vector<float> path { 0.45f, -0.18f, 0.08f };
};

void toeplitzRecursion()
{
    const std::vector<double> r { 2.0, 0.7, 0.3, 0.1 };
    const std::vector<double> expected { 0.4, -0.2, 0.1, 0.7 };
    std::vector<double> b(4, 0.0), solution;
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) b[static_cast<std::size_t>(i)] += r[static_cast<std::size_t>(std::abs(i - j))] * expected[static_cast<std::size_t>(j)];
    require(patel::solveToeplitz(r, b, solution), "Toeplitz solver failed");
    for (int i = 0; i < 4; ++i) require(std::abs(solution[static_cast<std::size_t>(i)] - expected[static_cast<std::size_t>(i)]) < 1.0e-10, "Toeplitz inaccurate");
    require(! patel::solveToeplitz({1.0, 2.0}, {1.0, 0.0}, solution), "singular/indefinite system accepted");
}

void delayedCalibrationAndGain()
{
    for (const int block : { 1, 64, 128, 256 })
    {
        Rig rig(block);
        rig.processor.setNoiseColour(MeasurementNoise::Colour::pink);
        rig.processor.setNoiseEnabled(true);
        rig.run(2400);
        require(rig.processor.isNoiseActive(), "generator did not start");
        rig.calibrate();
        require(rig.processor.hasValidModel(), patel::describe(rig.processor.getCalibrationResult()));
        require(std::abs(rig.processor.getDelaySamples() - rig.delay) <= 1, "incorrect separated delay");
        require(rig.processor.getFilterLength() <= 6, "effective FIR did not trim quiet tail");
        require(rig.processor.getValidationImprovementDb() > 35.0f, "poor identification accuracy");
        rig.run(3000);
        require(! rig.processor.isNoiseActive(), "generator restarted after successful calibration");
        rig.processor.setGainDb(6.0f); // beyond uncorrected pure-path loop threshold
        rig.sourceLevel = 0.003f;
        rig.run(12000);
        require(rig.processor.getClippedSampleCount() == 0, "gain change broke post-output reference");
        require(rig.residualRms() < 0.01, "closed-loop output differs from amplified source");
        std::sort(rig.times.begin(), rig.times.end());
        std::cout << "block=" << block << " validation=" << rig.processor.getValidationImprovementDb()
                  << " dB p99=" << rig.times[rig.times.size() * 99 / 100] << " ms\n";
    }
}

void changedPhysicalGain()
{
    Rig rig(128);
    rig.calibrate();
    require(rig.processor.hasValidModel(), "initial model invalid");
    rig.sourceLevel = 0.0002f;
    rig.processor.setGainDb(6.0f);
    rig.run(12000);
    const auto before = rig.residualRms();
    const auto after = rig.residualRms(4.0f);
    require(after > before * 10.0, "physical gain mismatch not reproduced");
}

void panicAndResume()
{
    Rig rig(128);
    rig.physicalGain = 0;
    rig.forcedInput = 0.2f;
    rig.processor.setGainDb(0);
    rig.processor.setNoiseEnabled(true);
    rig.run(20000);
    rig.processor.panic();
    rig.tick();
    require(rig.output.getMagnitude(0, rig.block) == 0, "panic did not cut the entire next block");
    for (int i = 0; i < 5; ++i) { rig.processor.panic(); rig.tick(); }
    require(rig.processor.isMuted() && ! rig.processor.isNoiseActive(), "repeated panic unmuted/restarted noise");
    rig.processor.setMuted(false);
    rig.tick();
    require(rig.output.getSample(0, 0) > 0 && rig.output.getSample(0, 0) < 0.001f, "resume starts without fade");
    require(std::abs(rig.output.getSample(0, 127) - 0.2f * 128 / 480) < 0.0001f, "resume fade is not 10 ms");
    rig.run(512);
    require(std::abs(rig.output.getSample(0, 127) - 0.2f) < 0.0001f && ! rig.processor.isNoiseActive(), "resume restored generator or wrong gain");
    for (const auto phase : { PatelAfcProcessor::State::preparing, PatelAfcProcessor::State::calibration,
        PatelAfcProcessor::State::validating, PatelAfcProcessor::State::estimating })
    {
        Rig calibration(128);
        calibration.processor.requestCalibration();
        do { calibration.tick(); } while (calibration.processor.getState() != phase);
        calibration.processor.panic(); calibration.tick();
        require(calibration.output.getMagnitude(0, 128) == 0, "panic failed during probe");
        require(calibration.processor.getCalibrationResult() == patel::Result::cancelled, "panic did not cancel calibration");
        require(! calibration.processor.isNoiseActive(), "panic retained test noise");
    }
}

void stableGainImprovementAndLongNoisyPath()
{
    Rig bypass(128);
    bypass.processor.setGainDb(6.0f);
    bypass.sourceLevel = 0.003f;
    bypass.run(48000);
    require(bypass.processor.getClippedSampleCount() > 0, "baseline did not reach instability");
    // The calibrated rigs above remain unclipped at exactly this gain and path.
    Rig noisy(128, PatelAfcProcessor::Config {});
    noisy.delay = 900;
    noisy.path.resize(1800);
    MeasurementNoise taps;
    taps.reset(177u);
    for (std::size_t i = 3; i < noisy.path.size(); ++i)
        noisy.path[i] = taps.next(MeasurementNoise::Colour::white) * 0.03f * std::exp(-static_cast<float>(i) / 1100.0f);
    noisy.sourceLevel = 0.001f;
    noisy.calibrate();
    require(noisy.processor.hasValidModel(), "long noisy path rejected");
    require(noisy.processor.getValidationImprovementDb() > 15.0f, "poor noisy path prediction");
    require(noisy.processor.getFilterLength() > 1500, "long tail was lost");
    noisy.times.clear();
    noisy.run(48000);
    std::sort(noisy.times.begin(), noisy.times.end());
    const auto p99 = noisy.times[noisy.times.size() * 99 / 100];
    std::cout << "long FIR=" << noisy.processor.getFilterLength() << " validation="
              << noisy.processor.getValidationImprovementDb() << " dB p99=" << p99 << " ms (period 2.667 ms)\n";
#ifdef NDEBUG
    require(p99 < 128.0 * 1000.0 / 48000.0, "long FIR callback misses real-time budget");
#endif
}

void failuresAndCancellation()
{
    {
        Rig rig(128);
        rig.physicalGain = 0.0f;
        rig.calibrate();
        require(! rig.processor.hasValidModel() && rig.processor.isMuted(), "missing return accepted");
        require(! rig.processor.isNoiseActive(), "noise restarted after rejection");
        rig.processor.setMuted(false); rig.tick(); rig.run(2000);
        require(! rig.processor.isNoiseActive(), "noise replayed after unmute");
        rig.processor.setNoiseEnabled(true); rig.run(2000);
        require(rig.processor.isNoiseActive(), "manual noise restart failed");
    }
    for (const auto phase : { PatelAfcProcessor::State::preparing, PatelAfcProcessor::State::calibration,
        PatelAfcProcessor::State::validating, PatelAfcProcessor::State::estimating })
    {
        Rig rig(128);
        rig.processor.setNoiseEnabled(true);
        rig.run(2000);
        rig.processor.requestCalibration();
        do { rig.tick(); } while (rig.processor.getState() != phase);
        rig.processor.cancelCalibration();
        rig.processor.setNoiseEnabled(true);
        rig.tick();
        require(rig.processor.getCalibrationResult() == patel::Result::cancelled, "cancellation did not win");
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(15);
        while (rig.processor.isCalibrationBusy())
        {
            rig.tick();
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            require(std::chrono::steady_clock::now() < deadline, "cancel worker timeout");
        }
        rig.processor.setMuted(false); rig.run(2000);
        require(! rig.processor.isNoiseActive() && ! rig.processor.hasValidModel(), "cancelled model or noise reactivated");
    }
    {
        Rig rig(128);
        rig.processor.requestCalibration();
        rig.forcedInput = 1.0f;
        rig.tick();
        require(rig.processor.getCalibrationResult() == patel::Result::clipped, "clipped calibration not rejected");
        rig.processor.setNoiseEnabled(true); rig.tick();
        require(! rig.processor.isNoiseActive(), "noise after clipped calibration");
        rig.forcedInput = std::numeric_limits<float>::quiet_NaN();
        rig.tick();
        require(rig.processor.isMuted(), "nonfinite input not muted");
    }
    {
        Rig rig(128);
        rig.processor.requestCalibration();
        rig.processor.cancelCalibration();
        rig.processor.setNoiseEnabled(true);
        rig.tick();
        require(rig.processor.getCalibrationResult() == patel::Result::cancelled, "simultaneous commands not cancelled");
    }
}

void independentValidationRejectsChangedPath()
{
    Rig rig(128);
    rig.processor.requestCalibration();
    do { rig.tick(); } while (rig.processor.getState() != PatelAfcProcessor::State::validating);
    rig.physicalGain = -1.0f;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(15);
    while (rig.processor.isCalibrationBusy())
    {
        rig.tick();
        if (rig.processor.getState() == PatelAfcProcessor::State::estimating) std::this_thread::sleep_for(std::chrono::milliseconds(1));
        require(std::chrono::steady_clock::now() < deadline, "validation timeout");
    }
    require(rig.processor.getCalibrationResult() == patel::Result::poorFit, "independent changed-path validation accepted");
}

void measurementNoiseLevels()
{
    for (const auto colour : { MeasurementNoise::Colour::white, MeasurementNoise::Colour::pink })
    {
        Rig rig(128);
        rig.physicalGain = 0.0f;
        rig.processor.setNoiseColour(colour);
        rig.processor.setNoiseLevelDbfs(-30.0f);
        rig.processor.setNoiseEnabled(true);
        rig.run(48000);
        double energy = 0.0;
        int count = 0;
        for (int b = 0; b < 3750; ++b)
        {
            rig.tick();
            for (int n = 0; n < rig.block; ++n) { const double x = rig.output.getSample(0, n); energy += x * x; ++count; }
        }
        const auto db = 10.0 * std::log10(energy / count);
        require(std::abs(db + 30.0) < 1.2, "noise RMS normalization incorrect");
        rig.processor.setNoiseEnabled(false);
        rig.run(2000);
        require(! rig.processor.isNoiseActive(), "noise stop ramp did not finish");
        require(rig.output.getMagnitude(0, rig.block) == 0.0f, "noise stop not silent");
    }
}

void noiseSpectraAndDeviceRestart()
{
    juce::dsp::FFT fft(13);
    const int size = fft.getSize();
    std::vector<float> frame(static_cast<std::size_t>(2 * size));
    for (const auto colour : { MeasurementNoise::Colour::white, MeasurementNoise::Colour::pink })
    {
        MeasurementNoise noise;
        noise.reset(712u);
        double low = 0.0, high = 0.0;
        for (int block = 0; block < 64; ++block)
        {
            for (int i = 0; i < size; ++i)
                frame[static_cast<std::size_t>(i)] = noise.next(colour)
                    * static_cast<float>(0.5 - 0.5 * std::cos(6.28318530718 * i / (size - 1)));
            fft.performRealOnlyForwardTransform(frame.data());
            for (int k = 1; k < size / 2; ++k)
            {
                const auto frequency = k * 48000.0 / size;
                const double power = frame[static_cast<std::size_t>(2 * k)] * frame[static_cast<std::size_t>(2 * k)]
                    + frame[static_cast<std::size_t>(2 * k + 1)] * frame[static_cast<std::size_t>(2 * k + 1)];
                if (frequency >= 200 && frequency < 400) low += power / 200.0;
                if (frequency >= 800 && frequency < 1600) high += power / 800.0;
            }
        }
        const auto slope = 10.0 * std::log10(high / low);
        require(colour == MeasurementNoise::Colour::white ? std::abs(slope) < 1.0 : slope < -4.5 && slope > -8.5,
                "white/pink spectral density incorrect");
    }
    Rig rig(128);
    rig.processor.setNoiseEnabled(true); rig.run(2000);
    rig.processor.requestCalibration(); rig.tick();
    rig.processor.stopped();
    rig.processor.prepare(48000.0, 128);
    rig.run(2000);
    require(! rig.processor.hasValidModel() && ! rig.processor.isNoiseActive(), "device restart retained stale noise/model");
}
}

int main()
{
    try
    {
        toeplitzRecursion();
        delayedCalibrationAndGain();
        changedPhysicalGain();
        panicAndResume();
        stableGainImprovementAndLongNoisyPath();
        failuresAndCancellation();
        independentValidationRejectsChangedPath();
        measurementNoiseLevels();
        noiseSpectraAndDeviceRestart();
        require(audioAllocations == 0, "heap allocation detected in audio callback");
        std::cout << "Patel estimator, holdout validation, gain, noise interlock and RT allocation tests passed\n";
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
