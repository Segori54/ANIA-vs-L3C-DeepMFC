#include "PatelEstimator.h"
#include "build_info.h"
#include <juce_core/juce_core.h>
#include <bit>
#include <cmath>
#include <iostream>
#include <stdexcept>

using juce::var;
var field(const var& obj, const char* name)
{
    if (!obj.isObject() || !obj.hasProperty(name)) throw std::runtime_error(std::string("Missing field: ") + name);
    return obj[name];
}
double number(const var& obj, const char* name)
{
    auto v = field(obj, name);
    if (!(v.isDouble() || v.isInt() || v.isInt64()) || !std::isfinite(double(v)))
        throw std::runtime_error(std::string("Invalid number: ") + name);
    return double(v);
}
int integer(const var& obj, const char* name, int minimum, int maximum)
{
    double n = number(obj, name);
    if (n < minimum || n > maximum || std::floor(n) != n) throw std::runtime_error("Integer outside allowed range");
    return int(n);
}
std::vector<double> doubles(const var& v)
{
    auto* a = v.getArray();
    if (a == nullptr || a->size() > 8192) throw std::runtime_error("Invalid vector");
    std::vector<double> out;
    for (auto& x : *a)
    {
        if (!(x.isDouble() || x.isInt() || x.isInt64()) || !std::isfinite(double(x))) throw std::runtime_error("Invalid vector value");
        out.push_back(double(x));
    }
    return out;
}
template<typename T> var array(const std::vector<T>& values)
{
    juce::Array<var> a;
    for (auto x : values) a.add(double(x));
    return a;
}
std::vector<float> signal(const var& spec, int rate)
{
    if (field(spec, "dtype").toString() != "<f4" || integer(spec, "sample_rate", 1, 192000) != rate)
        throw std::runtime_error("Signal format/rate mismatch");
    const int count = integer(spec, "samples", 0, 10000000);
    juce::MemoryBlock bytes;
    juce::File file(field(spec, "path").toString());
    if (!file.loadFileAsData(bytes) || bytes.getSize() != std::size_t(count) * 4) throw std::runtime_error("Signal byte count mismatch");
    std::vector<float> out(std::size_t(count), 0.0f);
    auto* data = static_cast<const unsigned char*>(bytes.getData());
    for (int i = 0; i < count; ++i)
    {
        auto bits = juce::ByteOrder::littleEndianInt(data + std::size_t(i) * 4);
        out[std::size_t(i)] = std::bit_cast<float>(static_cast<std::uint32_t>(bits));
    }
    return out;
}
const char* resultName(patel::Result r)
{
    switch(r) {
        case patel::Result::accepted: return "accepted";
        case patel::Result::noReturn: return "noReturn";
        case patel::Result::clipped: return "clipped";
        case patel::Result::poorFit: return "poorFit";
        case patel::Result::outOfRange: return "outOfRange";
        default: return "invalid";
    }
}
int main(int argc, char** argv)
{
    if (argc != 3) { std::cerr << "Usage: patel_compare request.json response.json\n"; return 2; }
    try {
        var request;
        auto parsed = juce::JSON::parse(juce::File(juce::String::fromUTF8(argv[1])).loadFileAsString(), request);
        if (parsed.failed()) throw std::runtime_error(parsed.getErrorMessage().toStdString());
        integer(request, "schema_version", 1, 1);
        auto response = new juce::DynamicObject();
        var result(response);
        response->setProperty("schema_version", 1);
        auto build = new juce::DynamicObject();
        build->setProperty("estimator_cpp_sha256", ESTIMATOR_CPP_SHA256);
        build->setProperty("estimator_h_sha256", ESTIMATOR_HPP_SHA256);
        build->setProperty("compiler", REFERENCE_COMPILER);
        response->setProperty("build", var(build));
        auto operation = field(request, "operation").toString();
        if (operation == "solve") {
            auto r = doubles(field(request, "r")), b = doubles(field(request, "b"));
            std::vector<double> x;
            bool ok = patel::solveToeplitz(r, b, x);
            response->setProperty("ok", ok);
            response->setProperty("solution", ok ? array(x) : var(juce::Array<var>()));
        } else if (operation == "estimate") {
            int rate = integer(request, "sample_rate", 1, 192000);
            auto c = field(request, "config");
            patel::EstimatorConfig cfg;
            cfg.maximumDelaySamples = integer(c, "maximumDelaySamples", 1, 48000);
            cfg.maximumFilterLength = integer(c, "maximumFilterLength", 1, 8192);
            cfg.regularisation = number(c, "regularisation");
            cfg.retainedEnergy = number(c, "retainedEnergy");
            cfg.minimumImprovementDb = number(c, "minimumImprovementDb");
            if (cfg.regularisation < 0 || cfg.retainedEnergy <= 0 || cfg.retainedEnergy > 1) throw std::runtime_error("Invalid estimator config");
            auto signals = field(request, "signals");
            auto p = signal(field(signals, "probe"), rate), m = signal(field(signals, "microphone"), rate);
            auto vp = signal(field(signals, "validationProbe"), rate), vm = signal(field(signals, "validationMicrophone"), rate);
            auto model = patel::estimate(p, m, vp, vm, cfg);
            response->setProperty("result", resultName(model.result));
            response->setProperty("delaySamples", model.delaySamples);
            response->setProperty("coefficients", array(model.coefficients));
            response->setProperty("validationImprovementDb", model.validationImprovementDb);
        } else throw std::runtime_error("Unknown operation");
        if (!juce::File(juce::String::fromUTF8(argv[2])).replaceWithText(juce::JSON::toString(result, false, 17)))
            throw std::runtime_error("Cannot write response");
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 2; }
}
