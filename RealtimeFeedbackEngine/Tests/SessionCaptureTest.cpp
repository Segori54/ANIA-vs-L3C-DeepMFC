#include "../Source/Processors/PatelAfcProcessor.h"
#include "../Source/AudioEngine.h"
#include "CaptureBuild.h"
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <new>
#include <thread>
#include <cmath>

thread_local bool auditHeap=false;
thread_local int allocations=0;
void* operator new(std::size_t n) { if(auditHeap) ++allocations; if(auto p=std::malloc(n?n:1)) return p; throw std::bad_alloc(); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p,std::size_t) noexcept { std::free(p); }
void* operator new[](std::size_t n) { return ::operator new(n); }
void operator delete[](void* p) noexcept { ::operator delete(p); }
void operator delete[](void* p,std::size_t) noexcept { ::operator delete(p); }
void require(bool value,const char* error) { if(!value) throw std::runtime_error(error); }
struct Rig {
    PatelAfcProcessor processor;
    AudioEngine engine {processor};
    std::array<float,128> input{},output{};
    std::vector<float> history=std::vector<float>(32768,0);
    std::uint64_t index=0;
    int delay;
    double rate;
    float forced=0, pathGain=.2f;
    std::vector<double> times;
    Rig(double r) : delay(static_cast<int>(r*.02)),rate(r) { engine.prepareOffline(r,128); }
    void tick(bool pace=true) {
        for(int i=0;i<128;++i) {
            auto n=index+static_cast<std::uint64_t>(i);
            input[i]=forced+(n>=static_cast<unsigned>(delay)?pathGain*history[(n-delay)%history.size()]:0);
        }
        auto start=std::chrono::steady_clock::now();
        auditHeap=true; engine.callbackOffline(input.data(),output.data(),128); auditHeap=false;
        times.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
        for(int i=0;i<128;++i) { require(std::isfinite(output[i]),"nonfinite output"); history[(index+i)%history.size()]=output[i]; }
        index+=128;
        if(pace) std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    void calibrate() {
        processor.requestCalibration();
        auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(15);
        do { tick(); require(std::chrono::steady_clock::now()<deadline,"calibration timed out"); } while(processor.isCalibrationBusy());
        require(processor.hasValidModel(),"model rejected");
    }
    void start(const juce::File& root,SessionCapture::Options options=SessionCapture::Options{}) {
        juce::var meta(new juce::DynamicObject()); meta.getDynamicObject()->setProperty("synthetic_test",true);
        meta.getDynamicObject()->setProperty("source_hash",CAPTURE_SOURCE_HASH);
        require(processor.sessionCapture().start(root,rate,meta,processor.getEstimatorConfig(),options),"capture start failed");
    }
    juce::File finish() {
        processor.sessionCapture().requestStop(); tick(); processor.sessionCapture().wait();
        require(processor.sessionCapture().status()==SessionCapture::Status::saved,"capture not saved");
        return processor.sessionCapture().directory();
    }
};
int main() {
    try {
        require(AudioEngine::rateMatches(16000,16000),"16 kHz not accepted");
        require(!AudioEngine::rateMatches(16000,48000),"rate mismatch accepted");
        require(!AudioEngine::rateMatches(48000,44100),"rate fallback accepted");
        auto root=juce::File(DEFAULT_CAPTURE_ROOT).getChildFile("build/session_capture_tests").getChildFile(juce::Uuid().toString());
        require(root.createDirectory().wasOk(),"test root failed");
        juce::Array<juce::var> sessions,benchmarks;
        for(double rate:{16000.0,48000.0}) {
            Rig rig(rate);
            for(int i=0;i<100;++i) rig.tick(false);
            auto off=rig.times; rig.times.clear();
            SessionCapture::Options opts; opts.segmentSeconds=.25; // force boundaries across blocks/calibration
            rig.start(root,opts); rig.calibrate();
            rig.forced=.01f;
            rig.times.clear();
            for(int i=0;i<100;++i) rig.tick();
            auto on=rig.times;
            rig.processor.sessionCapture().observation("Stable; SPL=60");
            sessions.add(rig.finish().getFullPathName());
            rig.times.clear();
            for(int i=0;i<100;++i) rig.tick();
            off=rig.times; // matched model/source/pace; only capture differs
            // Existing active model + nonzero history; repeated capture in same Run.
            rig.start(root); for(int i=0;i<20;++i) rig.tick();
            rig.processor.setGainDb(-10); for(int i=0;i<20;++i) rig.tick();
            rig.processor.setMuted(true); rig.tick(); rig.processor.setMuted(false); rig.tick();
            sessions.add(rig.finish().getFullPathName());
            // New model activation within one capture, then holdout path mismatch.
            rig.forced=0; rig.start(root); rig.tick(); rig.calibrate();
            for(int i=0;i<10;++i) rig.tick();
            rig.processor.requestCalibration();
            auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(15);
            do {
                if(rig.processor.getState()==PatelAfcProcessor::State::validating) rig.pathGain=.01f;
                rig.tick(); require(std::chrono::steady_clock::now()<deadline,"rejection timeout");
            } while(rig.processor.isCalibrationBusy());
            require(rig.processor.getCalibrationResult()==patel::Result::poorFit,"changed path not rejected");
            sessions.add(rig.finish().getFullPathName()); rig.processor.setMuted(false); rig.pathGain=.2f;
            // Cancel a calibration while capturing.
            rig.start(root); rig.tick(); rig.processor.requestCalibration();
            for(int i=0;i<40;++i) rig.tick();
            rig.processor.cancelCalibration(); rig.tick();
            sessions.add(rig.finish().getFullPathName()); rig.processor.setMuted(false);
            // Saturated calibration remains an integral diagnostic capture.
            rig.start(root); rig.tick(); rig.processor.requestCalibration(); rig.forced=1;
            rig.tick(); rig.forced=0; rig.tick(); sessions.add(rig.finish().getFullPathName());
            rig.processor.setMuted(false);
            rig.start(root); rig.tick(); rig.processor.stopped(); rig.processor.sessionCapture().wait();
            require(rig.processor.sessionCapture().status()==SessionCapture::Status::saved,"device stop did not close capture");
            sessions.add(rig.processor.sessionCapture().directory().getFullPathName());
            auto stats=[&](std::vector<double> values) {
                std::sort(values.begin(),values.end()); juce::var s(new juce::DynamicObject());
                for(auto q:{50,95,99,100}) s.getDynamicObject()->setProperty("p"+juce::String(q),values[std::min(values.size()-1,values.size()*q/100)]);
                int misses=0; for(auto t:values) if(t>128000/rate) ++misses;
                s.getDynamicObject()->setProperty("misses",misses); return s;
            };
            juce::var b(new juce::DynamicObject()); b.getDynamicObject()->setProperty("rate",rate);
            b.getDynamicObject()->setProperty("off",stats(off)); b.getDynamicObject()->setProperty("on",stats(on)); benchmarks.add(b);
        }
        for(bool disk:{false,true}) {
            Rig rig(48000); SessionCapture::Options opt;
            if(disk) opt.failAfterSamples=256; else { opt.queueSeconds=.001; opt.writerDelayMs=200; }
            rig.start(root,opt);
            for(int i=0;i<100;++i) rig.tick(false);
            rig.processor.sessionCapture().requestStop(); rig.tick(); rig.processor.sessionCapture().wait();
            require(rig.processor.sessionCapture().status()==SessionCapture::Status::incomplete,"failure was not marked incomplete");
            sessions.add(rig.processor.sessionCapture().directory().getFullPathName());
            rig.tick(); // audio still works after writer failure
        }
        require(allocations==0,"allocation in callback");
        juce::var summary(new juce::DynamicObject()); summary.getDynamicObject()->setProperty("sessions",sessions);
        summary.getDynamicObject()->setProperty("benchmarks",benchmarks); summary.getDynamicObject()->setProperty("callback_allocations",allocations);
        root.getChildFile("summary.json").replaceWithText(juce::JSON::toString(summary));
        juce::File(DEFAULT_CAPTURE_ROOT).getChildFile("build/session_capture_tests/latest.txt").replaceWithText(root.getFullPathName());
        std::cout<<"Session capture tests PASS: "<<root.getFullPathName()<<"\n";
        return 0;
    } catch(const std::exception& e) { std::cerr<<e.what()<<"\n"; return 1; }
}
