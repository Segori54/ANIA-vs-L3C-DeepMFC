#pragma once
#include <juce_gui_basics/juce_gui_basics.h>
#include "../Monitoring/AudioMonitor.h"

class LevelMeter final : public juce::Component
{
public:
    explicit LevelMeter(juce::String name) : title(std::move(name)) {}
    void update(AudioMonitor::Level value, bool limited) { level = value; protection = limited; repaint(); }
    void paint(juce::Graphics&) override;
private:
    juce::String title;
    AudioMonitor::Level level;
    bool protection = false;
};

class AnalyzerPanel final : public juce::Component
{
public:
    explicit AnalyzerPanel(AudioMonitor& source);
    void refresh();
    void paint(juce::Graphics&) override;
    void resized() override;
    void setSpectrogram(bool enabled);
private:
    void drawSpectrum(juce::Graphics&, juce::Rectangle<int>);
    void drawSpectrogram(juce::Graphics&, juce::Rectangle<int>, int channel);
    void rebuildImages();
    AudioMonitor& monitor;
    AudioMonitor::Snapshot snapshot;
    std::array<juce::Image, 2> images;
    std::array<juce::Colour, 256> palette;
    juce::ComboBox mode;
    juce::ToggleButton inputToggle { "Input" }, outputToggle { "Output" };
    bool spectrogram = false;
    std::uint64_t imageVersion = 0;
};

class DevicePanel final : public juce::Component
{
public:
    DevicePanel(juce::ComboBox& host, juce::ComboBox& input, juce::ComboBox& output);
    int preferredHeight() const { return expanded ? 140 : 34; }
    void setSummary(const juce::String& summary) { toggle.setButtonText((expanded ? "- Audio: " : "+ Audio: ") + summary); }
    void setExpanded(bool value);
    std::function<void()> onLayout;
    void resized() override;
private:
    bool expanded = false;
    juce::TextButton toggle;
    juce::ComboBox &hostBox, &inputBox, &outputBox;
    juce::Label hostLabel { {}, "Host" }, inputLabel { {}, "Input" }, outputLabel { {}, "Output" };
};

class DisclosurePanel final : public juce::Component
{
public:
    DisclosurePanel(juce::String title, int bodyHeight);
    int preferredHeight() const { return expanded ? 32 + height : 32; }
    void setText(const juce::String& text) { body.setText(text, juce::dontSendNotification); }
    void setExpanded(bool value);
    std::function<void()> onLayout;
    void resized() override;
private:
    juce::String title;
    int height;
    bool expanded = false;
    juce::TextButton toggle;
    juce::Label body;
};
