#pragma once
#include <JuceHeader.h>
#include "AudioEngine.h"
#include "Processors/PatelAfcProcessor.h"
#include "UI/MonitorComponents.h"

class MainComponent final : public juce::Component, private juce::Timer
{
public:
    MainComponent();
    ~MainComponent() override;
    void paint(juce::Graphics&) override;
    void resized() override;
    bool keyPressed(const juce::KeyPress&) override;
    void mouseDown(const juce::MouseEvent&) override;
    // Non-audio verification hooks used by --ui-check.
    bool verifyLayout();
private:
    void timerCallback() override;
    void toggleAudio();
    void updateRunButton();
    void refreshDeviceChoices();
    void appendMeasurement(const juce::String&);
    void startMeasurementLog();
    void panic();
    void changeGain(int direction);
    bool interactiveFocus(const juce::Component*) const;
    void refreshStatus();
    void toggleCapture();
    void chooseCaptureDestination();
    juce::AudioDeviceManager deviceManager;
    PatelAfcProcessor afcProcessor;
    AudioEngine audioEngine;
    juce::ComboBox deviceTypeBox, inputDeviceBox, outputDeviceBox;
    juce::Viewport viewport;
    juce::Component content;
    DevicePanel devicePanel;
    LevelMeter inputMeter { "Input" }, outputMeter { "Output" };
    AnalyzerPanel analyzer;
    DisclosurePanel diagnostics { "Diagnostics", 106 }, help { "Measurement procedure / shortcuts", 122 };
    juce::StringArray deviceTypeNames;
    juce::String selectedDeviceType, selectedInputDevice, selectedOutputDevice;
    juce::TextButton runButton { "Run" }, calibrateButton { "Calibrate AFC" }, cancelButton { "Cancel" };
    juce::TextButton muteButton { "PANIC / Mute [Space]" };
    juce::ComboBox methodBox, noiseColourBox, observationBox, gainStepBox;
    juce::ToggleButton noiseButton { "Test noise" };
    juce::Slider gainSlider, noiseLevelSlider;
    juce::TextButton gainUp, gainDown, resetMeters { "Reset CLIP / LIMIT" };
    juce::Label gainLabel, noiseLabel, splLabel, calibrationLabel, footerLabel;
    juce::TextEditor splEditor;
    juce::TextButton recordButton { "Record" }, logButton { "Logs" };
    juce::File logFile;
    std::unique_ptr<juce::FileOutputStream> logStream;
    juce::String logStatus { "Log starts with Run" };
    double lastTelemetryMs = 0;
    PatelAfcProcessor::State lastLoggedState = PatelAfcProcessor::State::bypass;
    bool audioIsRunning = false;
    juce::TextButton captureButton { "Iniciar captura" }, captureFolderButton { "Abrir carpeta" }, captureDestinationButton { "Cambiar destino" };
    juce::Label captureLabel;
    juce::ComboBox sampleRateBox;
    juce::File captureRoot, captureSettings;
    std::unique_ptr<juce::FileChooser> captureChooser;
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(MainComponent)
};
