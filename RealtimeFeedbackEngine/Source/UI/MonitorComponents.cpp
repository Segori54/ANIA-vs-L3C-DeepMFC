#include "MonitorComponents.h"
#include <cmath>

namespace
{
const juce::Colour panel(0xff252c34), inputColour(0xff5ec9ee), outputColour(0xffffc268);
float heightFor(float db) { return juce::jlimit(0.0f, 1.0f, (db + 90.0f) / 90.0f); }
juce::String reading(float db) { return db <= -100 ? "-inf" : juce::String(db, 1); }
}
void LevelMeter::paint(juce::Graphics& g)
{
    g.setColour(panel); g.fillRoundedRectangle(getLocalBounds().toFloat(), 6);
    auto bounds = getLocalBounds().reduced(8);
    g.setFont(15); g.setColour(juce::Colours::white);
    g.drawText(title, bounds.removeFromTop(24), juce::Justification::centred);
    auto bottom = bounds.removeFromBottom(76);
    auto bar = bounds.withTrimmedLeft(35).withSizeKeepingCentre(22, bounds.getHeight() - 12).toFloat();
    g.setColour(juce::Colour(0xff10151b)); g.fillRect(bar);
    for (const int db : { 0, -6, -12, -18, -30, -45, -60, -75, -90 })
    {
        const float y = bar.getBottom() - heightFor(static_cast<float>(db)) * bar.getHeight();
        g.setColour(juce::Colour(0xff99a7b5)); g.setFont(11);
        g.drawText(juce::String(db), 1, juce::roundToInt(y) - 7, juce::roundToInt(bar.getX()) - 5, 14, juce::Justification::centredRight);
        g.drawHorizontalLine(juce::roundToInt(y), bar.getRight() + 2, bar.getRight() + 6);
    }
    auto fill = bar; fill.setTop(bar.getBottom() - heightFor(level.rmsDb) * bar.getHeight());
    g.setColour(inputColour.withAlpha(0.85f)); g.fillRect(fill);
    const auto peakY = bar.getBottom() - heightFor(level.peakDb) * bar.getHeight();
    g.setColour(outputColour); g.fillRect(bar.getX() - 2, peakY - 1, bar.getWidth() + 4, 2.0f);
    g.setFont(11); g.setColour(juce::Colours::white);
    g.drawText("RMS " + reading(level.rmsDb), bottom.removeFromTop(17), juce::Justification::centred);
    g.drawText("PK " + reading(level.peakDb), bottom.removeFromTop(17), juce::Justification::centred);
    g.setColour(juce::Colours::lightgrey); g.drawText("dBFS", bottom.removeFromTop(16), juce::Justification::centred);
    g.setColour(level.clipped ? juce::Colours::red : juce::Colour(0xff536170));
    g.drawText("CLIP", bottom.removeFromTop(13), juce::Justification::centred);
    if (title == "Output")
    {
        g.setColour(protection ? juce::Colours::orange : juce::Colour(0xff536170));
        g.drawText("LIMIT", bottom, juce::Justification::centred);
    }
}

AnalyzerPanel::AnalyzerPanel(AudioMonitor& source) : monitor(source)
{
    mode.addItem("Spectrum", 1); mode.addItem("Spectrograms", 2);
    mode.setSelectedId(1, juce::dontSendNotification);
    mode.onChange = [this] { setSpectrogram(mode.getSelectedId() == 2); };
    inputToggle.setToggleState(true, juce::dontSendNotification);
    outputToggle.setToggleState(true, juce::dontSendNotification);
    inputToggle.setColour(juce::ToggleButton::textColourId, inputColour);
    outputToggle.setColour(juce::ToggleButton::textColourId, outputColour);
    inputToggle.onClick = outputToggle.onClick = [this] { repaint(); };
    addAndMakeVisible(mode); addAndMakeVisible(inputToggle); addAndMakeVisible(outputToggle);
    for (int i = 0; i < 256; ++i)
    {
        const float t = i / 255.0f;
        palette[static_cast<std::size_t>(i)] = t < 0.5f ? juce::Colour(0xff101722).interpolatedWith(inputColour, t * 2)
            : inputColour.interpolatedWith(juce::Colour(0xffffe58a), (t - 0.5f) * 2);
    }
    for (auto& values : snapshot.spectrum) values.fill(-120);
}
void AnalyzerPanel::setSpectrogram(bool enabled)
{
    spectrogram = enabled;
    mode.setSelectedId(enabled ? 2 : 1, juce::dontSendNotification);
    inputToggle.setVisible(! enabled); outputToggle.setVisible(! enabled);
    if (enabled) rebuildImages();
    repaint();
}
void AnalyzerPanel::resized()
{
    mode.setBounds(10, 7, 145, 26);
    inputToggle.setBounds(166, 7, 85, 26); outputToggle.setBounds(260, 7, 90, 26);
}
void AnalyzerPanel::refresh()
{
    monitor.copySnapshot(snapshot);
    if (spectrogram && imageVersion != snapshot.version) rebuildImages();
    repaint();
}
void AnalyzerPanel::rebuildImages()
{
    if (snapshot.history[0].empty()) return;
    for (int ch = 0; ch < 2; ++ch)
    {
        auto& image = images[static_cast<std::size_t>(ch)];
        if (image.getWidth() != snapshot.columns) image = juce::Image(juce::Image::RGB, snapshot.columns, AudioMonitor::historyBins, true);
        juce::Image::BitmapData pixels(image, juce::Image::BitmapData::writeOnly);
        for (int x = 0; x < snapshot.columns; ++x)
        {
            const auto column = (snapshot.newestColumn + 1 + x) % snapshot.columns;
            for (int row = 0; row < AudioMonitor::historyBins; ++row)
            {
                const auto value = snapshot.history[static_cast<std::size_t>(ch)][static_cast<std::size_t>(column * AudioMonitor::historyBins + row)];
                const auto colour = std::isfinite(value) ? palette[static_cast<std::size_t>(juce::jlimit(0, 255, juce::roundToInt((value + 100.0f) * 2.55f)))] : juce::Colours::black;
                pixels.setPixelColour(x, AudioMonitor::historyBins - 1 - row, colour);
            }
        }
    }
    imageVersion = snapshot.version;
}
void AnalyzerPanel::paint(juce::Graphics& g)
{
    g.setColour(panel); g.fillRoundedRectangle(getLocalBounds().toFloat(), 6);
    auto area = getLocalBounds().reduced(10); area.removeFromTop(32);
    auto footer = area.removeFromBottom(30);
    g.setFont(11); g.setColour(juce::Colours::lightgrey);
    g.drawText("FFT 4096 / Hann / hop 1024 | " + juce::String(snapshot.sampleRate / AudioMonitor::fftSize, 2)
        + " Hz | " + juce::String(1000 * AudioMonitor::fftSize / snapshot.sampleRate, 1) + " ms", footer.removeFromTop(15), juce::Justification::centredLeft);
    g.drawText(juce::String(snapshot.running ? "Live" : "Stopped") + " | display drops: " + juce::String(snapshot.droppedSamples)
        + " samples | dBFS amplitude/bin", footer, juce::Justification::centredLeft);
    if (! spectrogram) drawSpectrum(g, area);
    else
    {
        auto first = area.removeFromTop(area.getHeight() / 2); first.removeFromBottom(3);
        drawSpectrogram(g, first, 0); drawSpectrogram(g, area, 1);
    }
}
void AnalyzerPanel::drawSpectrum(juce::Graphics& g, juce::Rectangle<int> area)
{
    auto plot = area.reduced(42, 12).withTrimmedBottom(10);
    g.setColour(juce::Colour(0xff10151b)); g.fillRect(plot);
    const auto maxHz = std::min(20000.0, snapshot.sampleRate * 0.5);
    const auto xFor = [&] (double frequency) { return plot.getX() + static_cast<float>(std::log(frequency / 20) / std::log(maxHz / 20)) * plot.getWidth(); };
    const auto yFor = [&] (float db) { return plot.getBottom() - juce::jlimit(0.0f, 1.0f, (db + 100) / 100) * plot.getHeight(); };
    g.setFont(11);
    for (int db = 0; db >= -100; db -= 20)
    {
        const auto y = juce::roundToInt(yFor(static_cast<float>(db)));
        g.setColour(juce::Colour(0xff303b46)); g.drawHorizontalLine(y, static_cast<float>(plot.getX()), static_cast<float>(plot.getRight()));
        g.setColour(juce::Colours::lightgrey); g.drawText(juce::String(db), plot.getX() - 38, y - 7, 32, 14, juce::Justification::centredRight);
    }
    for (const int hz : { 20, 100, 1000, 10000, 20000 })
    {
        if (hz > maxHz) continue;
        const auto x = juce::roundToInt(xFor(hz));
        g.setColour(juce::Colour(0xff303b46)); g.drawVerticalLine(x, static_cast<float>(plot.getY()), static_cast<float>(plot.getBottom()));
        g.setColour(juce::Colours::lightgrey); g.drawText(hz >= 1000 ? juce::String(hz / 1000) + "k" : juce::String(hz), x - 20, plot.getBottom() + 3, 40, 16, juce::Justification::centred);
    }
    for (int ch = 0; ch < 2; ++ch)
    {
        if (! (ch == 0 ? inputToggle : outputToggle).getToggleState()) continue;
        juce::Path line;
        bool first = true;
        for (int k = 1; k < AudioMonitor::bins; ++k)
        {
            const auto hz = k * snapshot.sampleRate / AudioMonitor::fftSize;
            if (hz < 20 || hz > maxHz) continue;
            const auto x = xFor(hz), y = yFor(snapshot.spectrum[static_cast<std::size_t>(ch)][static_cast<std::size_t>(k)]);
            if (first) { line.startNewSubPath(x, y); first = false; } else line.lineTo(x, y);
        }
        g.setColour(ch == 0 ? inputColour : outputColour); g.strokePath(line, juce::PathStrokeType(1.3f));
    }
}
void AnalyzerPanel::drawSpectrogram(juce::Graphics& g, juce::Rectangle<int> area, int channel)
{
    g.setColour(channel == 0 ? inputColour : outputColour); g.setFont(12);
    g.drawText(channel == 0 ? "Input" : "Output", area.removeFromTop(17), juce::Justification::centredLeft);
    auto plot = area.withTrimmedLeft(42).withTrimmedRight(47).withTrimmedBottom(20);
    g.setColour(juce::Colours::black); g.fillRect(plot);
    const auto& image = images[static_cast<std::size_t>(channel)];
    if (image.isValid()) g.drawImage(image, plot.toFloat());
    const auto maxHz = std::min(20000.0, snapshot.sampleRate * 0.5);
    g.setFont(10); g.setColour(juce::Colours::lightgrey);
    for (const int hz : { 20, 100, 1000, 10000, 20000 })
    {
        if (hz > maxHz) continue;
        const auto y = plot.getBottom() - static_cast<int>(std::log(hz / 20.0) / std::log(maxHz / 20) * plot.getHeight());
        g.drawText(hz >= 1000 ? juce::String(hz / 1000) + "k" : juce::String(hz), plot.getX() - 40, y - 6, 35, 12, juce::Justification::centredRight);
    }
    g.drawText("-10 s", plot.getX(), plot.getBottom() + 3, 50, 14, juce::Justification::centredLeft);
    g.drawText("now", plot.getRight() - 45, plot.getBottom() + 3, 45, 14, juce::Justification::centredRight);
    for (int y = 0; y < plot.getHeight(); ++y)
    {
        g.setColour(palette[static_cast<std::size_t>(255 - y * 255 / std::max(1, plot.getHeight() - 1))]);
        g.drawHorizontalLine(plot.getY() + y, static_cast<float>(plot.getRight() + 7), static_cast<float>(plot.getRight() + 15));
    }
    g.setColour(juce::Colours::lightgrey);
    g.drawText("0", plot.getRight() + 18, plot.getY(), 27, 13, juce::Justification::centredLeft);
    g.drawText("-100", plot.getRight() + 18, plot.getBottom() - 13, 30, 13, juce::Justification::centredLeft);
}

DevicePanel::DevicePanel(juce::ComboBox& host, juce::ComboBox& input, juce::ComboBox& output)
    : hostBox(host), inputBox(input), outputBox(output)
{
    addAndMakeVisible(toggle);
    for (auto* child : std::initializer_list<juce::Component*> { &hostBox, &inputBox, &outputBox, &hostLabel, &inputLabel, &outputLabel }) addChildComponent(child);
    toggle.onClick = [this] { setExpanded(! expanded); };
}
void DevicePanel::setExpanded(bool value)
{
    expanded = value;
    for (auto* child : std::initializer_list<juce::Component*> { &hostBox, &inputBox, &outputBox, &hostLabel, &inputLabel, &outputLabel }) child->setVisible(expanded);
    if (onLayout) onLayout();
}
void DevicePanel::resized()
{
    toggle.setBounds(0, 0, getWidth(), 30);
    int y = 38;
    for (auto pair : { std::pair { &hostLabel, &hostBox }, { &inputLabel, &inputBox }, { &outputLabel, &outputBox } })
    { pair.first->setBounds(8, y, 65, 28); pair.second->setBounds(78, y, getWidth() - 86, 28); y += 33; }
}
DisclosurePanel::DisclosurePanel(juce::String name, int bodyHeight) : title(std::move(name)), height(bodyHeight)
{
    toggle.setButtonText("+ " + title); addAndMakeVisible(toggle); addChildComponent(body);
    body.setFont(juce::Font(juce::FontOptions(13))); body.setJustificationType(juce::Justification::topLeft);
    toggle.onClick = [this] { setExpanded(! expanded); };
}
void DisclosurePanel::setExpanded(bool value)
{
    expanded = value; toggle.setButtonText((expanded ? "- " : "+ ") + title); body.setVisible(expanded);
    if (onLayout) onLayout();
}
void DisclosurePanel::resized()
{
    toggle.setBounds(0, 0, getWidth(), 28); body.setBounds(8, 34, getWidth() - 16, height - 4);
}
