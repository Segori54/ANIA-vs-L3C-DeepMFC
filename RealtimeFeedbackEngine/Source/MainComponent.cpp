#include "MainComponent.h"
#include "UI/UiRules.h"
#include "CaptureBuild.h"

MainComponent::MainComponent()
    : audioEngine(afcProcessor), devicePanel(deviceTypeBox, inputDeviceBox, outputDeviceBox),
      analyzer(audioEngine.getMonitor())
{
    setWantsKeyboardFocus(true);
    addMouseListener(this, true);
    viewport.setViewedComponent(&content, false);
    viewport.setScrollBarsShown(true, false);
    addAndMakeVisible(viewport);
    deviceTypeBox.onChange = [this]
    {
        const auto index = deviceTypeBox.getSelectedItemIndex();
        if (juce::isPositiveAndBelow(index, deviceTypeNames.size()))
        {
            selectedDeviceType = deviceTypeNames[index];
            selectedInputDevice.clear(); selectedOutputDevice.clear();
            refreshDeviceChoices(); refreshStatus();
        }
    };
    inputDeviceBox.onChange = [this] { selectedInputDevice = inputDeviceBox.getText(); refreshStatus(); };
    outputDeviceBox.onChange = [this] { selectedOutputDevice = outputDeviceBox.getText(); refreshStatus(); };
    refreshDeviceChoices();
    captureSettings = juce::File::getSpecialLocation(juce::File::currentExecutableFile).getParentDirectory().getChildFile("capture-settings.json");
    auto preferences = juce::JSON::parse(captureSettings);
    captureRoot = juce::File(preferences.hasProperty("root") ? preferences["root"].toString() : juce::String(DEFAULT_CAPTURE_ROOT));
    sampleRateBox.addItem("16 kHz", 16000); sampleRateBox.addItem("48 kHz", 48000);
    sampleRateBox.setSelectedId(48000, juce::dontSendNotification);
    captureButton.onClick = [this] { toggleCapture(); };
    captureDestinationButton.onClick = [this] { chooseCaptureDestination(); };
    captureFolderButton.onClick = [this] { auto f=afcProcessor.sessionCapture().directory(); if(f.isDirectory()) f.startAsProcess(); };
    for(auto* c : std::initializer_list<juce::Component*> {&captureButton,&captureFolderButton,&captureDestinationButton,&sampleRateBox,&captureLabel}) addAndMakeVisible(c);
    devicePanel.onLayout = diagnostics.onLayout = help.onLayout = [this] { resized(); refreshStatus(); };
    runButton.onClick = [this] { toggleAudio(); };
    calibrateButton.onClick = [this] { afcProcessor.requestCalibration(); appendMeasurement("calibration_requested"); refreshStatus(); };
    cancelButton.onClick = [this] { afcProcessor.cancelCalibration(); };
    methodBox.addItem("Bypass", 1); methodBox.addItem("Patel (validated FIR)", 2);
    methodBox.setSelectedId(1, juce::dontSendNotification);
    methodBox.onChange = [this] { afcProcessor.setMethod(methodBox.getSelectedId() == 2
        ? PatelAfcProcessor::Method::patel : PatelAfcProcessor::Method::bypass); };
    // No keyboard activation of Resume: Space always latches mute on the background.
    muteButton.setWantsKeyboardFocus(false);
    muteButton.setMouseClickGrabsKeyboardFocus(false);
    muteButton.onClick = [this]
    {
        if (afcProcessor.isMuted()) { afcProcessor.setMuted(false); appendMeasurement("resume"); }
        else panic();
        grabKeyboardFocus(); refreshStatus();
    };
    gainLabel.setText("Digital gain", juce::dontSendNotification);
    gainSlider.setRange(-60.0, 30.0, 0.1);
    gainSlider.setSliderStyle(juce::Slider::LinearHorizontal);
    gainSlider.setTextBoxStyle(juce::Slider::TextBoxLeft, false, 84, 28);
    gainSlider.setValue(afcProcessor.getGainDb(), juce::dontSendNotification);
    gainSlider.setTextValueSuffix(" dB");
    gainSlider.valueFromTextFunction = [] (const juce::String& text) { return text.replaceCharacter(',', '.').getDoubleValue(); };
    gainSlider.onValueChange = [this] { afcProcessor.setGainDb(static_cast<float>(gainSlider.getValue())); };
    gainUp.setButtonText(juce::String::charToString(0x2191));
    gainDown.setButtonText(juce::String::charToString(0x2193));
    gainUp.onClick = [this] { changeGain(1); grabKeyboardFocus(); };
    gainDown.onClick = [this] { changeGain(-1); grabKeyboardFocus(); };
    gainStepBox.addItem("0.1 dB", 1); gainStepBox.addItem("1 dB", 2); gainStepBox.addItem("5 dB", 3);
    gainStepBox.setSelectedId(2, juce::dontSendNotification);
    noiseColourBox.addItem("White noise", 1); noiseColourBox.addItem("Pink noise", 2);
    noiseColourBox.setSelectedId(1, juce::dontSendNotification);
    noiseColourBox.onChange = [this] { afcProcessor.setNoiseColour(noiseColourBox.getSelectedId() == 2
        ? MeasurementNoise::Colour::pink : MeasurementNoise::Colour::white); };
    noiseButton.onClick = [this] { afcProcessor.setNoiseEnabled(noiseButton.getToggleState()); };
    noiseLabel.setText("Noise RMS", juce::dontSendNotification);
    noiseLevelSlider.setRange(-80.0, -12.0, 1.0);
    noiseLevelSlider.setSliderStyle(juce::Slider::LinearHorizontal);
    noiseLevelSlider.setTextBoxStyle(juce::Slider::TextBoxLeft, false, 88, 28);
    noiseLevelSlider.setValue(afcProcessor.getNoiseLevelDbfs(), juce::dontSendNotification);
    noiseLevelSlider.setTextValueSuffix(" dBFS");
    noiseLevelSlider.onValueChange = [this] { afcProcessor.setNoiseLevelDbfs(static_cast<float>(noiseLevelSlider.getValue())); };
    splLabel.setText("SPL (optional)", juce::dontSendNotification);
    splEditor.setInputRestrictions(7, "0123456789.,");
    splEditor.setTextToShowWhenEmpty("dB SPL", juce::Colours::grey);
    observationBox.addItem("Stable (10 s)", 1); observationBox.addItem("Howling onset", 2); observationBox.addItem("Clipping limit", 3);
    observationBox.setSelectedId(1, juce::dontSendNotification);
    recordButton.setButtonText("Observacion");
    recordButton.onClick = [this] { appendMeasurement("observation"); afcProcessor.sessionCapture().observation(observationBox.getText()+"; SPL="+splEditor.getText()); };
    logButton.onClick = [this] { if (logFile.existsAsFile()) logFile.revealToUser(); };
    resetMeters.onClick = [this] { audioEngine.getMonitor().resetClips(); afcProcessor.resetProtectionIndicator(); };
    help.setText("Keep interface/speaker gains and geometry fixed; direct monitoring OFF. Sweep digital gain and observe 10 s per step; repeat 3 times.\n"
        "Space on background = latched PANIC. Resume only with the button (10 ms fade). Click background to use Up/Down with the selected gain step.\n"
        "Calibration disables test noise and leaves it OFF. SPL is complementary; keep meter position, weighting and integration fixed.\n"
        "RMS: 300 ms; sample peak: 1 s hold, 20 dB/s fall. CLIP = >= 0 dBFS; LIMIT = output protection acted.\n"
        "Spectrum is amplitude/bin, not SPL or a delay-aligned transfer function. Noise-bin levels depend on FFT bandwidth. Black spectrogram columns = missing data.");
    for (auto* c : std::initializer_list<juce::Component*> { &runButton, &calibrateButton, &cancelButton,
        &methodBox, &muteButton, &calibrationLabel, &footerLabel }) addAndMakeVisible(c);
    for (auto* c : std::initializer_list<juce::Component*> { &gainLabel, &gainSlider, &gainUp, &gainDown, &gainStepBox,
        &noiseColourBox, &noiseButton, &noiseLabel, &noiseLevelSlider, &splLabel, &splEditor, &observationBox,
        &recordButton, &logButton, &devicePanel, &inputMeter, &outputMeter, &analyzer, &diagnostics, &help, &resetMeters })
        content.addAndMakeVisible(c);
    calibrationLabel.setFont(juce::Font(juce::FontOptions(13))); footerLabel.setFont(juce::Font(juce::FontOptions(12)));
    setSize(1180, 720);
    refreshStatus();
    startTimerHz(30);
}

MainComponent::~MainComponent()
{
    stopTimer(); audioEngine.shutdown(); audioIsRunning = false;
    viewport.setViewedComponent(nullptr, false);
}
void MainComponent::paint(juce::Graphics& g)
{
    g.fillAll(juce::Colour(0xff171d24));
    g.setColour(juce::Colours::white); g.setFont(20);
    g.drawText("RealtimeFeedbackEngine", 14, 6, 360, 26, juce::Justification::centredLeft);
    g.setFont(12); g.setColour(afcProcessor.isMuted() ? juce::Colours::orange : juce::Colour(0xff9bb1c3));
    g.drawText(afcProcessor.isMuted() ? "OUTPUT MUTED" : "Space: panic | click background for shortcuts",
               380, 6, getWidth() - 396, 26, juce::Justification::centredRight);
}
void MainComponent::resized()
{
    const int width = getWidth();
    int x = 12;
    const auto header = [&x] (juce::Component& c, int w) { c.setBounds(x, 37, w, 30); x += w + 8; };
    header(runButton, 70); header(muteButton, 190); header(methodBox, 178);
    header(calibrateButton, 120); header(cancelButton, 85);
    calibrationLabel.setBounds(12, 71, width - 24, 24);
    footerLabel.setBounds(12, getHeight() - 26, width - 24, 24);
    captureButton.setBounds(12, 101, 160, 30); captureFolderButton.setBounds(180, 101, 120, 30);
    captureDestinationButton.setBounds(308, 101, 140, 30); sampleRateBox.setBounds(456, 101, 100, 30);
    captureLabel.setBounds(12, 135, width-24, 28);
    viewport.setBounds(12, 171, width - 24, std::max(1, getHeight() - 203));
    // Reserve scrollbar width even when absent, avoiding relayout oscillation.
    const int cw = std::max(700, viewport.getWidth() - viewport.getScrollBarThickness());
    const int controlsHeight = 3 * 38 + devicePanel.preferredHeight() + 8;
    const int disclosuresHeight = diagnostics.preferredHeight() + help.preferredHeight() + 12;
    const int monitorHeight = std::max(300, viewport.getHeight() - controlsHeight - disclosuresHeight - 30);
    const int total = controlsHeight + monitorHeight + 30 + disclosuresHeight;
    content.setSize(cw, total);
    int y = 0;
    gainLabel.setBounds(0, y, 90, 30);
    gainSlider.setBounds(94, y, cw - 306, 30);
    gainDown.setBounds(cw - 205, y, 34, 30); gainUp.setBounds(cw - 165, y, 34, 30);
    gainStepBox.setBounds(cw - 121, y, 121, 30); y += 38;
    noiseColourBox.setBounds(0, y, 132, 30); noiseButton.setBounds(142, y, 102, 30);
    noiseLabel.setBounds(253, y, 86, 30); noiseLevelSlider.setBounds(343, y, cw - 343, 30); y += 38;
    splLabel.setBounds(0, y, 104, 30); splEditor.setBounds(108, y, 82, 30);
    observationBox.setBounds(202, y, 173, 30); recordButton.setBounds(385, y, 103, 30);
    logButton.setBounds(498, y, 65, 30); y += 38;
    devicePanel.setBounds(0, y, cw, devicePanel.preferredHeight()); y += devicePanel.preferredHeight() + 8;
    inputMeter.setBounds(0, y, 100, monitorHeight); outputMeter.setBounds(110, y, 100, monitorHeight);
    analyzer.setBounds(222, y, cw - 222, monitorHeight); y += monitorHeight + 4;
    resetMeters.setBounds(0, y, 210, 24); y += 26;
    diagnostics.setBounds(0, y, cw, diagnostics.preferredHeight()); y += diagnostics.preferredHeight() + 6;
    help.setBounds(0, y, cw, help.preferredHeight());
}
bool MainComponent::interactiveFocus(const juce::Component* component) const
{
    for (auto* c = component; c != nullptr && c != this; c = c->getParentComponent())
        if (dynamic_cast<const juce::TextEditor*>(c) != nullptr || dynamic_cast<const juce::ComboBox*>(c) != nullptr
            || dynamic_cast<const juce::Slider*>(c) != nullptr || dynamic_cast<const juce::Button*>(c) != nullptr
            || dynamic_cast<const juce::ScrollBar*>(c) != nullptr) return true;
    return false;
}
void MainComponent::mouseDown(const juce::MouseEvent& event)
{
    if (! interactiveFocus(event.eventComponent)) grabKeyboardFocus();
}
bool MainComponent::keyPressed(const juce::KeyPress& key)
{
    if (! hasKeyboardFocus(true) || interactiveFocus(juce::Component::getCurrentlyFocusedComponent())
        || juce::Component::getCurrentlyModalComponent() != nullptr || key.getModifiers().isAnyModifierKeyDown()) return false;
    if (key.getKeyCode() == juce::KeyPress::spaceKey) { panic(); return true; }
    if (key.getKeyCode() == juce::KeyPress::upKey || key.getKeyCode() == juce::KeyPress::downKey)
    {
        changeGain(key.getKeyCode() == juce::KeyPress::upKey ? 1 : -1); return true;
    }
    return false;
}
void MainComponent::panic()
{
    const bool alreadyMuted = afcProcessor.isMuted();
    afcProcessor.panic();
    if (! alreadyMuted) appendMeasurement("panic");
    refreshStatus();
}
void MainComponent::changeGain(int direction)
{
    if (afcProcessor.isCalibrationBusy()) return;
    const double step = gainStepBox.getSelectedId() == 1 ? 0.1 : gainStepBox.getSelectedId() == 3 ? 5.0 : 1.0;
    gainSlider.setValue(ui_rules::steppedGain(gainSlider.getValue(), direction, step), juce::sendNotificationSync);
}
void MainComponent::refreshStatus()
{
    if (audioIsRunning && !audioEngine.isDeviceActive()) {
        audioIsRunning=false; logStream.reset(); updateRunButton();
        deviceTypeBox.setEnabled(true); inputDeviceBox.setEnabled(true); outputDeviceBox.setEnabled(true);
    }
    const auto busy = afcProcessor.isCalibrationBusy();
    auto& cap = afcProcessor.sessionCapture();
    auto cs = cap.status();
    calibrateButton.setEnabled(audioIsRunning && ! busy && ! afcProcessor.isMuted() && cs != SessionCapture::Status::preparing);
    captureButton.setButtonText(cs == SessionCapture::Status::recording ? "Finalizar captura" : "Iniciar captura");
    captureButton.setEnabled(cs == SessionCapture::Status::recording || (audioIsRunning && !busy && !cap.busy()));
    captureDestinationButton.setEnabled(!cap.busy());
    captureFolderButton.setEnabled(cap.directory().isDirectory());
    sampleRateBox.setEnabled(!audioIsRunning && !cap.busy());
    const char* label = "Sin captura";
    switch(cs) {
        case SessionCapture::Status::preparing: label="Preparando"; break;
        case SessionCapture::Status::recording: label="Grabando"; break;
        case SessionCapture::Status::saving: label="Guardando"; break;
        case SessionCapture::Status::saved: label="Guardada"; break;
        case SessionCapture::Status::incomplete: label="Captura incompleta"; break;
        default: break;
    }
    captureLabel.setText(juce::String(label) + " | " + juce::String(cap.seconds(),1) + " s | Guarda audio del microfono"
        + (cs == SessionCapture::Status::incomplete ? " | " + cap.error() : ""), juce::dontSendNotification);
    captureLabel.setColour(juce::Label::textColourId, cs == SessionCapture::Status::recording ? juce::Colours::lightgreen
        : cs == SessionCapture::Status::incomplete ? juce::Colours::orange : juce::Colours::lightgrey);
    cancelButton.setEnabled(audioIsRunning && busy);
    methodBox.setEnabled(! busy);
    methodBox.setSelectedId(afcProcessor.getMethod() == PatelAfcProcessor::Method::patel ? 2 : 1, juce::dontSendNotification);
    noiseButton.setEnabled(audioIsRunning && ! busy && ! afcProcessor.isMuted());
    noiseButton.setToggleState(afcProcessor.isNoiseActive(), juce::dontSendNotification);
    noiseColourBox.setEnabled(! busy && ! afcProcessor.isNoiseActive());
    noiseLevelSlider.setEnabled(! busy); gainSlider.setEnabled(! busy);
    gainUp.setEnabled(! busy); gainDown.setEnabled(! busy); gainStepBox.setEnabled(! busy);
    muteButton.setButtonText(afcProcessor.isMuted() ? "MUTED - Resume" : "PANIC / Mute [Space]");
    muteButton.setColour(juce::TextButton::buttonColourId, afcProcessor.isMuted() ? juce::Colour(0xff745224) : juce::Colour(0xff8c3037));
    recordButton.setEnabled(audioIsRunning && ! busy && logStream != nullptr);
    calibrationLabel.setText(juce::String(PatelAfcProcessor::describeState(afcProcessor.getState())) + " | "
        + patel::describe(afcProcessor.getCalibrationResult()) + " | delay " + juce::String(afcProcessor.getDelaySamples())
        + " samples | FIR " + juce::String(afcProcessor.getFilterLength()) + " | validation "
        + juce::String(afcProcessor.getValidationImprovementDb(), 1) + " dB", juce::dontSendNotification);
    devicePanel.setSummary(audioIsRunning ? audioEngine.getCurrentDeviceName() + " | "
        + juce::String(audioEngine.getCurrentSampleRate(), 0) + " Hz | " + juce::String(audioEngine.getCurrentBlockSize()) + " samples"
        : selectedDeviceType + " / " + selectedOutputDevice + " (stopped)");
    const double rate = audioEngine.getCurrentSampleRate();
    const int latency = audioEngine.getInputLatencySamples() + audioEngine.getOutputLatencySamples();
    diagnostics.setText("Device latency: input " + juce::String(audioEngine.getInputLatencySamples()) + " + output "
        + juce::String(audioEngine.getOutputLatencySamples()) + " samples = " + juce::String(rate > 0 ? latency * 1000.0 / rate : 0.0, 2)
        + " ms (reported, not acoustic measurement).\nCallback p50 / p95 / p99: "
        + juce::String(audioEngine.getCallbackTimeP50Milliseconds(), 3) + " / "
        + juce::String(audioEngine.getCallbackTimeP95Milliseconds(), 3) + " / "
        + juce::String(audioEngine.getCallbackTimeP99Milliseconds(), 3) + " ms | misses: "
        + juce::String(audioEngine.getCallbackDeadlineMisses()) + "\nClipped samples: "
        + juce::String(afcProcessor.getClippedSampleCount()) + " | tonal detections (experimental): "
        + juce::String(afcProcessor.getDetectionCount()) + "\n" + logStatus);
    footerLabel.setText(audioEngine.getStatusMessage(), juce::dontSendNotification);
    repaint();
}
void MainComponent::timerCallback()
{
    refreshStatus();
    inputMeter.update(audioEngine.getMonitor().level(0), false);
    outputMeter.update(audioEngine.getMonitor().level(1), afcProcessor.isProtectionLatched());
    analyzer.refresh();
    const auto now = juce::Time::getMillisecondCounterHiRes();
    if (audioIsRunning && (now - lastTelemetryMs >= 1000.0 || afcProcessor.getState() != lastLoggedState))
    {
        appendMeasurement("telemetry"); lastTelemetryMs = now; lastLoggedState = afcProcessor.getState();
    }
}
void MainComponent::toggleAudio()
{
    if (audioIsRunning)
    {
        audioEngine.shutdown(); appendMeasurement("stop"); logStream.reset(); audioIsRunning = false;
    }
    else
    {
        audioIsRunning = audioEngine.initialise(deviceManager, selectedDeviceType, selectedInputDevice, selectedOutputDevice, sampleRateBox.getSelectedId());
        if (audioIsRunning) startMeasurementLog();
    }
    deviceTypeBox.setEnabled(! audioIsRunning); inputDeviceBox.setEnabled(! audioIsRunning); outputDeviceBox.setEnabled(! audioIsRunning);
    updateRunButton(); refreshStatus();
}
void MainComponent::updateRunButton() { runButton.setButtonText(audioIsRunning ? "Stop" : "Run"); }

void MainComponent::chooseCaptureDestination()
{
    captureChooser = std::make_unique<juce::FileChooser>("Carpeta para sesiones de validacion", captureRoot);
    captureChooser->launchAsync(juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectDirectories,
        [safe = juce::Component::SafePointer<MainComponent>(this)] (const juce::FileChooser& chooser)
        {
            if (!safe || !chooser.getResult().isDirectory()) return;
            safe->captureRoot = chooser.getResult();
            juce::var preferences(new juce::DynamicObject());
            preferences.getDynamicObject()->setProperty("root",safe->captureRoot.getFullPathName());
            safe->captureSettings.replaceWithText(juce::JSON::toString(preferences));
            safe->refreshStatus();
        });
}
void MainComponent::toggleCapture()
{
    auto& cap = afcProcessor.sessionCapture();
    if (cap.status() == SessionCapture::Status::recording) { cap.requestStop(); refreshStatus(); return; }
    if (!audioIsRunning || afcProcessor.isCalibrationBusy() || cap.busy()) return;
    if (!captureRoot.isDirectory()) { chooseCaptureDestination(); return; }
    juce::var meta(new juce::DynamicObject());
    auto* m=meta.getDynamicObject();
    m->setProperty("source_hash",CAPTURE_SOURCE_HASH); m->setProperty("compiler",CAPTURE_COMPILER);
    m->setProperty("app_version","0.1.0"); m->setProperty("host",selectedDeviceType);
    m->setProperty("input_device",selectedInputDevice); m->setProperty("output_device",selectedOutputDevice);
    m->setProperty("requested_rate",sampleRateBox.getSelectedId()); m->setProperty("effective_rate",audioEngine.getCurrentSampleRate());
    m->setProperty("requested_block",128); m->setProperty("effective_block",audioEngine.getCurrentBlockSize());
    m->setProperty("input_latency_samples",audioEngine.getInputLatencySamples()); m->setProperty("output_latency_samples",audioEngine.getOutputLatencySamples());
    m->setProperty("probe_rms_dbfs",afcProcessor.getProbeLevelDbfs()); m->setProperty("probe_duration_ms",afcProcessor.getProbeDurationMilliseconds());
    m->setProperty("latency_kind","driver_reported_not_acoustic");
    cap.start(captureRoot,audioEngine.getCurrentSampleRate(),meta,afcProcessor.getEstimatorConfig());
    refreshStatus();
}

bool MainComponent::verifyLayout()
{
    bool valid = true;
    const auto contained = [&valid] (juce::Component& parent)
    {
        for (auto* child : parent.getChildren())
            if (child->isVisible() && ! parent.getLocalBounds().contains(child->getBounds())) valid = false;
    };
    for (const auto size : { juce::Point<int>(1180, 720), { 1000, 620 }, { 800, 480 }, { 1500, 850 } })
    {
        setSize(size.x, size.y);
        for (const bool expand : { false, true })
        {
            devicePanel.setExpanded(expand); diagnostics.setExpanded(expand); help.setExpanded(expand);
            analyzer.setSpectrogram(expand);
            contained(*this); contained(content); contained(devicePanel); contained(analyzer);
            valid = valid && inputMeter.getRight() < outputMeter.getX() && outputMeter.getRight() < analyzer.getX();
        }
    }
    devicePanel.setExpanded(false); diagnostics.setExpanded(false); help.setExpanded(false);
    analyzer.setSpectrogram(false); setSize(1180, 720);
    return valid;
}

void MainComponent::refreshDeviceChoices()
{
    deviceTypeNames.clear();
    deviceTypeBox.clear(juce::dontSendNotification);

    for (auto* type : deviceManager.getAvailableDeviceTypes())
    {
        type->scanForDevices();
        deviceTypeNames.add(type->getTypeName());
        deviceTypeBox.addItem(type->getTypeName(), deviceTypeNames.size());
    }

    if (selectedDeviceType.isEmpty())
    {
        for (int index = 0; index < deviceTypeNames.size(); ++index)
        {
            if (deviceTypeNames[index].equalsIgnoreCase("ASIO"))
            {
                selectedDeviceType = deviceTypeNames[index];
                break;
            }
        }
    }

    if (selectedDeviceType.isEmpty() && deviceTypeNames.size() > 0)
        selectedDeviceType = deviceManager.getCurrentAudioDeviceType();
    if (selectedDeviceType.isEmpty() && deviceTypeNames.size() > 0)
        selectedDeviceType = deviceTypeNames[0];

    const auto typeIndex = deviceTypeNames.indexOf(selectedDeviceType);
    if (typeIndex >= 0)
        deviceTypeBox.setSelectedItemIndex(typeIndex, juce::dontSendNotification);

    juce::StringArray inputNames, outputNames;
    for (auto* type : deviceManager.getAvailableDeviceTypes())
    {
        if (type->getTypeName() == selectedDeviceType)
        {
            inputNames = type->getDeviceNames(true);
            outputNames = type->getDeviceNames(false);
            break;
        }
    }

    inputDeviceBox.clear(juce::dontSendNotification);
    outputDeviceBox.clear(juce::dontSendNotification);
    for (int i = 0; i < inputNames.size(); ++i)
        inputDeviceBox.addItem(inputNames[i], i + 1);
    for (int i = 0; i < outputNames.size(); ++i)
        outputDeviceBox.addItem(outputNames[i], i + 1);

    const auto preferredDevice = [] (const juce::StringArray& names)
    {
        for (const auto& name : names)
            if (name.equalsIgnoreCase("Focusrite USB ASIO"))
                return name;
        return names.isEmpty() ? juce::String() : names[0];
    };

    if (selectedInputDevice.isEmpty() || inputNames.indexOf(selectedInputDevice) < 0)
        selectedInputDevice = preferredDevice(inputNames);
    if (selectedOutputDevice.isEmpty() || outputNames.indexOf(selectedOutputDevice) < 0)
        selectedOutputDevice = preferredDevice(outputNames);

    inputDeviceBox.setText(selectedInputDevice, juce::dontSendNotification);
    outputDeviceBox.setText(selectedOutputDevice, juce::dontSendNotification);
}

void MainComponent::startMeasurementLog()
{
    const auto directory = juce::File::getSpecialLocation(juce::File::currentExecutableFile)
        .getParentDirectory().getChildFile("measurements");
    if (directory.createDirectory().failed())
    {
        logStatus = "Cannot create measurement log folder";
        return;
    }
    logFile = directory.getNonexistentChildFile(juce::Time::getCurrentTime().formatted("%Y%m%d-%H%M%S"), ".csv", false);
    logStream = logFile.createOutputStream();
    if (logStream == nullptr || logStream->failedToOpen())
    {
        logStream.reset();
        logStatus = "Cannot open measurement log";
        return;
    }
    logStream->writeText("timestamp_iso8601,event,host,input_device,output_device,sample_rate,block_samples,input_latency_samples,output_latency_samples,method,state,calibration_result,delay_samples,fir_taps,validation_db,gain_db,noise_active,noise_colour,noise_dbfs_rms,muted,input_dbfs,output_dbfs,clipped_samples,tonal_detections,callback_p99_ms,deadline_misses,spl_db,observation\n", false, false, nullptr);
    logStatus = "Log: " + logFile.getFileName() + " (beside executable)";
    lastTelemetryMs = juce::Time::getMillisecondCounterHiRes();
    appendMeasurement("start");
}

void MainComponent::appendMeasurement(const juce::String& event)
{
    if (logStream == nullptr) return;
    const auto quote = [] (juce::String value) { return "\"" + value.replace("\"", "\"\"") + "\""; };
    const bool observation = event == "observation";
    juce::StringArray row {
        juce::Time::getCurrentTime().toISO8601(true), event, audioEngine.getCurrentDeviceType(),
        selectedInputDevice, selectedOutputDevice,
        juce::String(audioEngine.getCurrentSampleRate(), 0), juce::String(audioEngine.getCurrentBlockSize()),
        juce::String(audioEngine.getInputLatencySamples()), juce::String(audioEngine.getOutputLatencySamples()),
        afcProcessor.getMethod() == PatelAfcProcessor::Method::patel ? "patel" : "bypass",
        PatelAfcProcessor::describeState(afcProcessor.getState()), patel::describe(afcProcessor.getCalibrationResult()),
        juce::String(afcProcessor.getDelaySamples()), juce::String(afcProcessor.getFilterLength()),
        juce::String(afcProcessor.getValidationImprovementDb(), 2), juce::String(afcProcessor.getGainDb(), 1),
        afcProcessor.isNoiseActive() ? "1" : "0",
        afcProcessor.getNoiseColour() == MeasurementNoise::Colour::white ? "white" : "pink",
        juce::String(afcProcessor.getNoiseLevelDbfs(), 1), afcProcessor.isMuted() ? "1" : "0",
        juce::String(audioEngine.getInputLevelDbfs(0), 2), juce::String(audioEngine.getOutputLevelDbfs(0), 2),
        juce::String(afcProcessor.getClippedSampleCount()), juce::String(afcProcessor.getDetectionCount()),
        juce::String(audioEngine.getCallbackTimeP99Milliseconds(), 3), juce::String(audioEngine.getCallbackDeadlineMisses()),
        observation ? splEditor.getText().replaceCharacter(',', '.') : "",
        observation ? observationBox.getText() : ""
    };
    for (auto& field : row) field = quote(field);
    if (! logStream->writeText(row.joinIntoString(",") + "\n", false, false, nullptr))
        logStatus = "Measurement log write failed";
    logStream->flush(); // GUI thread only
}
