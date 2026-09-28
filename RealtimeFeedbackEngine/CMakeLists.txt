cmake_minimum_required(VERSION 3.22)

project(RealtimeFeedbackEngine VERSION 0.1.0 LANGUAGES C CXX)

set(ASIO_SDK_PATH
    "${CMAKE_CURRENT_SOURCE_DIR}/ThirdParty/ASIO-SDK_2.3.4/ASIOSDK"
    CACHE PATH "Path to the official Steinberg ASIO SDK")

if (WIN32)
    if (NOT EXISTS "${ASIO_SDK_PATH}/common/iasiodrv.h")
        message(FATAL_ERROR
            "Official Steinberg ASIO SDK not found. Expected: ${ASIO_SDK_PATH}/common/iasiodrv.h")
    endif()

    message(STATUS "Using official Steinberg ASIO SDK: ${ASIO_SDK_PATH}")
endif()

include(FetchContent)

FetchContent_Declare(
    JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG 8.0.10
    GIT_SHALLOW TRUE
)

FetchContent_MakeAvailable(JUCE)

get_filename_component(REFERENCE_CAPTURE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../Referencia ASNI AFC Patel" ABSOLUTE)
set(CAPTURE_SOURCE_TEXT "")
foreach(source Source/Capture/SessionCapture.cpp Source/Capture/SessionCapture.h Source/AudioEngine.cpp Source/AudioEngine.h Source/Processors/PatelAfcProcessor.cpp Source/Processors/PatelAfcProcessor.h Source/Processors/PatelEstimator.cpp Source/Processors/PatelEstimator.h)
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/${source}")
    file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/${source}" HASH)
    string(APPEND CAPTURE_SOURCE_TEXT "${source}:${HASH}\n")
endforeach()
string(SHA256 CAPTURE_SOURCE_HASH "${CAPTURE_SOURCE_TEXT}")
configure_file(Source/Capture/CaptureBuild.h.in "${CMAKE_CURRENT_BINARY_DIR}/capture_generated/CaptureBuild.h" @ONLY)

juce_add_gui_app(RealtimeFeedbackEngine
    PRODUCT_NAME "RealtimeFeedbackEngine"
    COMPANY_NAME "RealtimeFeedbackEngine"
    VERSION "0.1.0"
)

juce_generate_juce_header(RealtimeFeedbackEngine)

target_sources(RealtimeFeedbackEngine PRIVATE
    Source/main.cpp
    Source/Capture/SessionCapture.cpp
    Source/MainComponent.h
    Source/MainComponent.cpp
    Source/Monitoring/AudioMonitor.cpp
    Source/UI/MonitorComponents.cpp
    Source/AudioEngine.h
    Source/AudioEngine.cpp
    Source/Processors/IProcessor.h
    Source/Processors/DelayProcessor.h
    Source/Processors/DelayProcessor.cpp
    Source/Processors/NLMSProcessor.h
    Source/Processors/NLMSProcessor.cpp
    Source/Processors/HowlingDetector.h
    Source/Processors/HowlingDetector.cpp
    Source/Processors/PatelAfcProcessor.h
    Source/Processors/PatelAfcProcessor.cpp
    Source/Processors/PatelEstimator.cpp
    Source/Processors/PatelEstimator.h
    Source/Processors/MeasurementNoise.h
    Source/Processors/PassthroughProcessor.h
    Source/Processors/PassthroughProcessor.cpp
    Source/Config/AudioConfig.h
)

target_compile_features(RealtimeFeedbackEngine PRIVATE cxx_std_20)
target_include_directories(RealtimeFeedbackEngine PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/capture_generated")

target_compile_definitions(RealtimeFeedbackEngine PRIVATE
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
)

if (WIN32)
    target_compile_definitions(RealtimeFeedbackEngine PRIVATE
        JUCE_ASIO=1
    )

    target_include_directories(RealtimeFeedbackEngine PRIVATE
        "${ASIO_SDK_PATH}/common"
    )
endif()

target_link_libraries(RealtimeFeedbackEngine PRIVATE
    juce::juce_audio_utils
    juce::juce_dsp
    juce::juce_cryptography
    juce::juce_audio_devices
    juce::juce_gui_extra
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
    juce::juce_recommended_lto_flags
)

enable_testing()

juce_add_console_app(NLMSIdentificationTest
    PRODUCT_NAME "NLMSIdentificationTest"
)

target_sources(NLMSIdentificationTest PRIVATE
    Tests/NLMSIdentificationTest.cpp
    Source/Processors/IProcessor.h
    Source/Processors/NLMSProcessor.h
    Source/Processors/NLMSProcessor.cpp
)

target_compile_features(NLMSIdentificationTest PRIVATE cxx_std_20)

target_link_libraries(NLMSIdentificationTest PRIVATE
    juce::juce_audio_basics
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)

add_test(NAME NLMSIdentificationTest COMMAND NLMSIdentificationTest)

juce_add_console_app(PatelAfcTest PRODUCT_NAME "PatelAfcTest")

target_sources(PatelAfcTest PRIVATE
    Source/Monitoring/AudioMonitor.cpp
    Source/Processors/PatelEstimator.cpp
    Tests/PatelAfcTest.cpp
    Source/Capture/SessionCapture.cpp
    Source/Processors/IProcessor.h
    Source/Processors/HowlingDetector.h
    Source/Processors/HowlingDetector.cpp
    Source/Processors/PatelAfcProcessor.h
    Source/Processors/PatelAfcProcessor.cpp
)

target_compile_features(PatelAfcTest PRIVATE cxx_std_20)

target_link_libraries(PatelAfcTest PRIVATE
    juce::juce_cryptography
    juce::juce_dsp
    juce::juce_audio_basics
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags
)

add_test(NAME PatelAfcTest COMMAND PatelAfcTest)
add_test(NAME ResponsiveLayoutTest COMMAND RealtimeFeedbackEngine --ui-check)

juce_add_console_app(AudioMonitorTest PRODUCT_NAME "AudioMonitorTest")
target_sources(AudioMonitorTest PRIVATE Tests/AudioMonitorTest.cpp Source/Monitoring/AudioMonitor.cpp)
target_compile_features(AudioMonitorTest PRIVATE cxx_std_20)
target_link_libraries(AudioMonitorTest PRIVATE juce::juce_dsp juce::juce_recommended_config_flags juce::juce_recommended_warning_flags)
add_test(NAME AudioMonitorTest COMMAND AudioMonitorTest)

juce_add_console_app(SessionCaptureTest PRODUCT_NAME "SessionCaptureTest")
target_sources(SessionCaptureTest PRIVATE Tests/SessionCaptureTest.cpp Source/Capture/SessionCapture.cpp
    Source/AudioEngine.cpp Source/Monitoring/AudioMonitor.cpp Source/Processors/PatelEstimator.cpp
    Source/Processors/PatelAfcProcessor.cpp Source/Processors/HowlingDetector.cpp)
target_include_directories(SessionCaptureTest PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/capture_generated")
target_compile_features(SessionCaptureTest PRIVATE cxx_std_20)
target_compile_definitions(SessionCaptureTest PRIVATE CAPTURE_TESTING=1 JUCE_USE_CURL=0)
target_link_libraries(SessionCaptureTest PRIVATE juce::juce_audio_devices juce::juce_dsp juce::juce_cryptography juce::juce_recommended_config_flags)
add_test(NAME SessionCaptureTest COMMAND SessionCaptureTest)

# These offline tests do not use networking. JUCE otherwise enables curl on
# Linux, while these targets intentionally do not link it.
foreach(test_target NLMSIdentificationTest PatelAfcTest AudioMonitorTest)
    target_compile_definitions(${test_target} PRIVATE JUCE_USE_CURL=0)
endforeach()
