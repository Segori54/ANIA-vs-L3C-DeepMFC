#include <JuceHeader.h>

#include "MainComponent.h"

#include <iostream>

class ConsoleLogger final : public juce::Logger
{
public:
    void logMessage(const juce::String& message) override
    {
        std::cout << message << std::endl;
    }
};

class RealtimeFeedbackEngineApplication final : public juce::JUCEApplication
{
public:
    const juce::String getApplicationName() override { return "RealtimeFeedbackEngine"; }
    const juce::String getApplicationVersion() override { return "0.1.0"; }
    bool moreThanOneInstanceAllowed() override { return true; }

    void initialise(const juce::String& commandLine) override
    {
        logger = std::make_unique<ConsoleLogger>();
        juce::Logger::setCurrentLogger(logger.get());
        if (commandLine.contains("--ui-check"))
        {
            MainComponent component;
            const auto passed = component.verifyLayout();
            std::cout << "Responsive layout checks: " << (passed ? "PASS" : "FAIL") << std::endl;
            setApplicationReturnValue(passed ? 0 : 1);
            quit();
            return;
        }
        mainWindow = std::make_unique<MainWindow>(getApplicationName());
    }

    void shutdown() override
    {
        mainWindow.reset();
        juce::Logger::setCurrentLogger(nullptr);
        logger.reset();
    }

    void systemRequestedQuit() override
    {
        quit();
    }

private:
    class MainWindow final : public juce::DocumentWindow
    {
    public:
        explicit MainWindow(juce::String name)
            : DocumentWindow(std::move(name), juce::Colours::lightgrey, allButtons)
        {
            setUsingNativeTitleBar(true);
            setContentOwned(new MainComponent(), true);
            setResizable(true, false);
            const auto* display = juce::Desktop::getInstance().getDisplays().getPrimaryDisplay();
            const auto area = display != nullptr ? display->userArea : juce::Rectangle<int>(0, 0, 1280, 800);
            setResizeLimits(std::min(760, area.getWidth()), std::min(450, area.getHeight()), 10000, 10000);
            centreWithSize(std::min(1180, juce::roundToInt(area.getWidth() * 0.9)),
                           std::min(720, juce::roundToInt(area.getHeight() * 0.9)));
            setVisible(true);
        }

        void closeButtonPressed() override
        {
            JUCEApplication::getInstance()->systemRequestedQuit();
        }
    };

    std::unique_ptr<MainWindow> mainWindow;
    std::unique_ptr<ConsoleLogger> logger;
};

START_JUCE_APPLICATION(RealtimeFeedbackEngineApplication)
