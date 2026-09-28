#include "SessionCapture.h"
#include <juce_cryptography/juce_cryptography.h>
#include <algorithm>
#include <bit>
#include <chrono>
#include <cmath>
#include <stdexcept>

namespace {
static_assert(std::atomic<std::uint64_t>::is_always_lock_free && std::atomic<int>::is_always_lock_free);
juce::var object() { return new juce::DynamicObject(); }
void set(juce::var& v, const char* key, const juce::var& x) { v.getDynamicObject()->setProperty(key, x); }
void json(const juce::File& file, const juce::var& v) {
    if (!file.replaceWithText(juce::JSON::toString(v, false, 17))) throw std::runtime_error("JSON write failed");
}
void text(juce::OutputStream& stream, const juce::String& s) {
    if (!stream.write(s.toRawUTF8(), s.getNumBytesAsUTF8())) throw std::runtime_error("Write failed");
}
std::unique_ptr<juce::FileOutputStream> open(const juce::File& file) {
    auto s = file.createOutputStream();
    if (!s || s->failedToOpen()) throw std::runtime_error("Open failed");
    return s;
}
const char* resultName(int r) {
    switch (static_cast<patel::Result>(r)) {
        case patel::Result::accepted: return "accepted"; case patel::Result::noReturn: return "noReturn";
        case patel::Result::clipped: return "clipped"; case patel::Result::poorFit: return "poorFit";
        case patel::Result::cancelled: return "cancelled"; case patel::Result::outOfRange: return "outOfRange";
        case patel::Result::running: return "running"; case patel::Result::none: return "none";
        default: return "invalid";
    }
}
// Minimal IEEE float WAV writer: avoids PCM quantisation in audio-format helpers.
class FloatWav {
public:
    FloatWav(const juce::File& f, int rate) : stream(open(f)) {
        stream->write("RIFF", 4); stream->writeInt(0); stream->write("WAVEfmt ", 8);
        stream->writeInt(16); stream->writeShort(3); stream->writeShort(7);
        stream->writeInt(rate); stream->writeInt(rate * 28); stream->writeShort(28); stream->writeShort(32);
        stream->write("data", 4); stream->writeInt(0);
    }
    void append(const std::vector<float>& values) {
        static_assert(std::endian::native == std::endian::little);
        if (!stream->write(values.data(), values.size() * 4)) throw std::runtime_error("WAV write failed");
        bytes += static_cast<int>(values.size() * 4);
    }
    void close() {
        if (!stream) return;
        stream->setPosition(4); stream->writeInt(36 + bytes);
        stream->setPosition(40); stream->writeInt(bytes); stream->flush();
        if (stream->getStatus().failed()) throw std::runtime_error("WAV close failed");
        stream.reset();
    }
private: std::unique_ptr<juce::FileOutputStream> stream; int bytes=0;
};
}

SessionCapture::~SessionCapture() { deviceStopped(); wait(); }
bool SessionCapture::start(const juce::File& root, double rate, juce::var metadata, const patel::EstimatorConfig& c) {
    return start(root, rate, metadata, c, Options{});
}
bool SessionCapture::start(const juce::File& root, double rate, juce::var metadata, const patel::EstimatorConfig& c, Options opt) {
    if (busy() || (rate != 16000 && rate != 48000) || !root.isDirectory()) return false;
    wait();
    options=opt; rateHz=rate; config=c;
    folder=root.getChildFile(rate == 16000 ? "16khz" : "48khz").getChildFile("sesiones_reales")
        .getChildFile(juce::Time::getCurrentTime().formatted("%Y%m%d-%H%M%S") + "_" + juce::Uuid().toString());
    write=0; read=0; modelWrite=0; modelRead=0; observationWrite=0; observationRead=0;
    written=0; produced=0; errorCode=0; stopRequested=false; audioDone=false; snapshotReady=false; allowModels=false;
    sampleIndex=0; blockActive=false; historyCount=0; initialModel={}; reason=StopReason::manual;
    queue.resize(static_cast<std::size_t>(std::max(256.0, rate * opt.queueSeconds * 2))); // samples plus worst-case block records
    manifest=object(); set(manifest,"schema_version",1); set(manifest,"kind","real_session");
    set(manifest,"complete",false); set(manifest,"sample_rate",rate); set(manifest,"metadata",metadata);
    auto cfg=object(); set(cfg,"maximumDelaySamples",c.maximumDelaySamples); set(cfg,"maximumFilterLength",c.maximumFilterLength);
    set(cfg,"regularisation",c.regularisation); set(cfg,"retainedEnergy",c.retainedEnergy); set(cfg,"minimumImprovementDb",c.minimumImprovementDb);
    set(manifest,"config",cfg);
    juce::Array<juce::var> names;
    for (auto n : {"microphone_raw","microphone_used","feedback","clean","output","probe","gain"}) names.add(n);
    set(manifest,"channels",names);
    set(manifest,"callback_timing_scope","callback_before_capture_commit; integration benchmark includes entire callback");
    try {
        if (folder.getChildFile("modelos").createDirectory().failed()) throw std::runtime_error("Directory failed");
        json(folder.getChildFile("manifest.json"),manifest);
        state=Status::preparing;
        writer=std::thread([this]{writerLoop();});
    } catch (...) { errorCode=2; state=Status::incomplete; return false; }
    return true;
}
void SessionCapture::requestStop(StopReason r) noexcept { reason=r; stopRequested.store(true,std::memory_order_release); }
void SessionCapture::deviceStopped() noexcept {
    if (!busy()) return;
    requestStop(StopReason::deviceStopped); allowModels=false; blockActive=false; audioDone=true;
    state=Status::saving;
}
void SessionCapture::wait() { if(writer.joinable()) writer.join(); }
void SessionCapture::fail(int code) noexcept {
    errorCode=code; reason=code == 1 ? StopReason::overflow : StopReason::diskError;
    stopRequested=true; allowModels=false;
}
bool SessionCapture::beginBlock(const float* h,int length,int delay,int id,const float* history,int size,int index,float validationDb) noexcept {
    blockActive=false;
    auto s=status();
    if (s != Status::preparing && s != Status::recording) return false;
    if (stopRequested.load()) { allowModels=false; audioDone=true; state=Status::saving; return false; }
    if (s == Status::preparing) {
        if (length > 4096 || size > static_cast<int>(initialHistory.size())) { fail(1); audioDone=true; state=Status::saving; return false; }
        initialModel.length=length; initialModel.delay=delay; initialModel.id=id;
        initialModel.db=validationDb;
        initialModel.result=static_cast<int>(length ? patel::Result::accepted : patel::Result::none);
        std::copy_n(h,length,initialModel.coefficients.begin()); historyCount=size;
        for(int i=0;i<size;++i) initialHistory[static_cast<std::size_t>(i)]=history[(index+i)%size];
        snapshotReady.store(true,std::memory_order_release); allowModels=true; state=Status::recording;
    }
    blockActive=true; return true;
}
bool SessionCapture::push(const Packet& p) noexcept {
    auto w=write.load(std::memory_order_relaxed);
    if(w-read.load(std::memory_order_acquire)>=queue.size()) { fail(1); return false; }
    queue[static_cast<std::size_t>(w%queue.size())]=p; write.store(w+1,std::memory_order_release); return true;
}
void SessionCapture::sample(const std::array<float,7>& values,const Tags& tags) noexcept {
    if(!blockActive || errorCode.load()!=0) return;
    Packet p; p.values=values; p.tags=tags; p.index=sampleIndex;
    if(push(p)) ++sampleIndex;
}
void SessionCapture::endBlock(int samples,double ms) noexcept {
    if (!blockActive) return;
    produced.store(sampleIndex);
    if(errorCode.load()==0) { Packet p; p.block=samples; p.index=sampleIndex; p.ms=ms; push(p); }
    if(stopRequested.load()) { allowModels=false; audioDone=true; if(status()!=Status::incomplete) state=Status::saving; }
    blockActive=false;
}
void SessionCapture::workerModel(const patel::Model& model,int id) noexcept {
    publishing.fetch_add(1);
    if(allowModels.load()) {
        auto w=modelWrite.load();
        if(w-modelRead.load(std::memory_order_acquire)>=models.size() || model.coefficients.size()>4096) fail(1);
        else {
            auto& m=models[static_cast<std::size_t>(w%models.size())]; m.length=static_cast<int>(model.coefficients.size());
            m.delay=model.delaySamples; m.id=id; m.result=static_cast<int>(model.result); m.db=model.validationImprovementDb;
            std::copy(model.coefficients.begin(),model.coefficients.end(),m.coefficients.begin());
            modelWrite.store(w+1,std::memory_order_release);
        }
    }
    publishing.fetch_sub(1);
}
void SessionCapture::observation(const juce::String& s) {
    if(status()!=Status::recording) return;
    auto w=observationWrite.load();
    if(w-observationRead.load(std::memory_order_acquire)>=observations.size()) { fail(1); return; }
    observations[w%observations.size()]={s,produced.load()}; observationWrite.store(w+1,std::memory_order_release);
}
void SessionCapture::writerLoop() noexcept {
    try {
        auto events=open(folder.getChildFile("events.jsonl")), blocks=open(folder.getChildFile("blocks.csv")), telemetry=open(folder.getChildFile("telemetry.csv"));
        text(*blocks,"sequence,start_sample,samples,callback_ms\n");
        text(*telemetry,"sample,kind,callback_ms,input_rms,output_rms,limited,detail\n");
        juce::Array<juce::var> segments, calibrations, activations;
        auto saveModel=[&](const ModelPacket& m) {
            auto v=object(); set(v,"id",m.id); set(v,"delaySamples",m.delay); set(v,"result",resultName(m.result));
            set(v,"validationImprovementDb",std::isfinite(m.db)?juce::var(m.db):juce::var());
            juce::Array<juce::var> h; juce::String csv="k,h\n";
            for(int k=0;k<m.length;++k) { h.add(double(m.coefficients[k])); csv+=juce::String(k)+","+juce::String(double(m.coefficients[k]),17)+"\n"; }
            set(v,"coefficients",h); set(v,"config",manifest["config"]);
            auto file=folder.getChildFile("modelos").getChildFile("model_"+juce::String(m.id));
            json(file.withFileExtension("json"),v);
            if(!file.withFileExtension("csv").replaceWithText(csv)) throw std::runtime_error("Model CSV failed");
        };
        bool initialSaved=false, haveTags=false; Tags last;
        std::uint64_t count=0, blockSequence=0, segmentStart=0, blockStart=0;
        std::uint64_t segmentLimit=static_cast<std::uint64_t>(std::max(1.0,options.segmentSeconds*rateHz));
        int segmentNumber=0; juce::String segmentName;
        std::unique_ptr<FloatWav> wav;
        std::vector<float> buffer; buffer.reserve(7*2048);
        double inputEnergy=0,outputEnergy=0;
        auto flush=[&] { if(wav && !buffer.empty()) { wav->append(buffer); buffer.clear(); } };
        auto closeSegment=[&] {
            if(!wav) return;
            flush(); wav->close(); wav.reset();
            auto v=object(); set(v,"file",segmentName); set(v,"start_sample",static_cast<juce::int64>(segmentStart));
            set(v,"samples",static_cast<juce::int64>(count-segmentStart)); segments.add(v);
        };
        while(true) {
            if(snapshotReady.load(std::memory_order_acquire) && !initialSaved) {
                saveModel(initialModel);
                auto h=open(folder.getChildFile("initial_history.f32"));
                if(!h->write(initialHistory.data(),static_cast<std::size_t>(historyCount)*4)) throw std::runtime_error("History write failed");
                set(manifest,"history_samples",historyCount); set(manifest,"initial_model",initialModel.id); initialSaved=true;
            }
            auto mr=modelRead.load();
            while(mr<modelWrite.load(std::memory_order_acquire)) { saveModel(models[mr%models.size()]); modelRead.store(++mr,std::memory_order_release); }
            auto r=read.load(); int batch=0;
            while(r<write.load(std::memory_order_acquire) && ++batch<=4096) {
                auto p=queue[static_cast<std::size_t>(r%queue.size())]; read.store(++r,std::memory_order_release);
                if(p.block) {
                    text(*blocks,juce::String(static_cast<juce::int64>(blockSequence++))+","+juce::String(static_cast<juce::int64>(blockStart))+","+juce::String(p.block)+","+juce::String(p.ms,6)+"\n");
                    text(*telemetry,juce::String(static_cast<juce::int64>(blockStart))+",callback,"+juce::String(p.ms,6)+","+juce::String(std::sqrt(inputEnergy/std::max(1,p.block)),9)+","+juce::String(std::sqrt(outputEnergy/std::max(1,p.block)),9)+","+juce::String(last.limited?1:0)+",\n");
                    inputEnergy=outputEnergy=0; blockStart=p.index; continue;
                }
                if(options.failAfterSamples>=0 && count>=static_cast<std::uint64_t>(options.failAfterSamples)) throw std::runtime_error("Injected disk failure");
                if(!wav) { segmentStart=count; segmentName="audio_"+juce::String(++segmentNumber).paddedLeft('0',4)+".wav"; wav=std::make_unique<FloatWav>(folder.getChildFile(segmentName),static_cast<int>(rateHz)); }
                if(!haveTags || !(last==p.tags)) {
                    auto e=object(); set(e,"sample",static_cast<juce::int64>(count)); set(e,"state",p.tags.state); set(e,"result",resultName(p.tags.result));
                    set(e,"method",p.tags.method); set(e,"calibration",p.tags.calibration); set(e,"model",p.tags.model);
                    set(e,"muted",p.tags.muted); set(e,"clean_valid",p.tags.cleanValid); set(e,"noise",p.tags.noise);
                    set(e,"limited",p.tags.limited); set(e,"target_gain_db",p.tags.targetGainDb);
                    text(*events,juce::JSON::toString(e,true,17)+"\n");
                    if(p.tags.model>0 && (!haveTags || last.model!=p.tags.model)) {
                        auto activation=object(); set(activation,"model",p.tags.model);
                        set(activation,"sample",static_cast<juce::int64>(count)); activations.add(activation);
                    }
                    if(p.tags.calibration>0 && p.tags.result!=static_cast<int>(patel::Result::running)
                        && p.tags.result!=static_cast<int>(patel::Result::none)
                        && !folder.getChildFile("modelos/model_"+juce::String(p.tags.calibration)+".json").existsAsFile()) {
                        ModelPacket rejected; rejected.id=p.tags.calibration; rejected.result=p.tags.result; saveModel(rejected);
                    }
                    if(!haveTags || last.state!=p.tags.state || last.calibration!=p.tags.calibration || last.result!=p.tags.result) calibrations.add(e);
                    last=p.tags; haveTags=true;
                }
                buffer.insert(buffer.end(),p.values.begin(),p.values.end()); ++count;
                if(std::isfinite(p.values[0])) inputEnergy+=double(p.values[0])*p.values[0];
                outputEnergy+=double(p.values[4])*p.values[4];
                if(buffer.size()>=7*1024) flush();
                if(count-segmentStart>=segmentLimit) closeSegment();
            }
            written.store(count);
            auto o=observationRead.load();
            while(o<observationWrite.load(std::memory_order_acquire)) {
                auto& entry=observations[o%observations.size()];
                text(*telemetry,juce::String(static_cast<juce::int64>(entry.sample))+",observation,,,,,\""+entry.text.replace("\"","\"\"").replace("\n"," ")+"\"\n");
                observationRead.store(++o,std::memory_order_release);
            }
            if(audioDone.load() && publishing.load()==0 && read.load()==write.load() && modelRead.load()==modelWrite.load()) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(std::max(1,options.writerDelayMs)));
        }
        closeSegment(); events->flush(); blocks->flush(); telemetry->flush();
        if(events->getStatus().failed() || blocks->getStatus().failed() || telemetry->getStatus().failed()) throw std::runtime_error("Metadata flush failed");
        events.reset(); blocks.reset(); telemetry.reset();
        json(folder.getChildFile("calibraciones.json"),calibrations);
        for (auto activation:activations) {
            auto file=folder.getChildFile("modelos/model_"+activation["model"].toString()+".json");
            auto model=juce::JSON::parse(file);
            if(model.isObject()) { set(model,"activation_sample",activation["sample"]); json(file,model); }
        }
        set(manifest,"segments",segments); set(manifest,"samples",static_cast<juce::int64>(count));
        set(manifest,"stop_reason",static_cast<int>(reason.load()));
        bool complete=errorCode.load()==0 && initialSaved;
        set(manifest,"complete",complete); set(manifest,"error_code",errorCode.load());
        auto hashes=object();
        for(auto file:folder.findChildFiles(juce::File::findFiles,true))
            if(file.getFileName()!="manifest.json") hashes.getDynamicObject()->setProperty(file.getRelativePathFrom(folder).replaceCharacter('\\','/'),juce::SHA256(file).toHexString());
        set(manifest,"sha256",hashes); json(folder.getChildFile("manifest.json"),manifest);
        state=complete?Status::saved:Status::incomplete;
    } catch (...) {
        fail(2); set(manifest,"complete",false); set(manifest,"error_code",2);
        try { json(folder.getChildFile("manifest.json"),manifest); } catch (...) {}
        // Do not allow GUI restart/reallocation until the producer has acknowledged
        // the failure at a block boundary (or the device lifecycle stopped it).
        while(!audioDone.load(std::memory_order_acquire)) std::this_thread::sleep_for(std::chrono::milliseconds(1));
        state=Status::incomplete;
    }
}
