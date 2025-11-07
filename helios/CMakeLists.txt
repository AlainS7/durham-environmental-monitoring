cmake_minimum_required(VERSION 3.20)
project(Aquila VERSION 1.0.0 LANGUAGES CXX CUDA)

# C++ Standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler flags
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra")
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -march=native")
set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -g -O0")

# CUDA flags
set(CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS} -arch=sm_70")  # Adjust for your GPU

# Find required packages
find_package(CUDA REQUIRED)
find_package(Threads REQUIRED)

# TensorRT
set(TENSORRT_ROOT "/usr/local/tensorrt" CACHE PATH "TensorRT installation directory")
find_path(TENSORRT_INCLUDE_DIR NvInfer.h
    HINTS ${TENSORRT_ROOT}/include
    PATH_SUFFIXES include
)
find_library(TENSORRT_LIBRARY nvinfer
    HINTS ${TENSORRT_ROOT}/lib
    PATH_SUFFIXES lib lib64
)
find_library(TENSORRT_PLUGIN_LIBRARY nvinfer_plugin
    HINTS ${TENSORRT_ROOT}/lib
    PATH_SUFFIXES lib lib64
)

if(NOT TENSORRT_INCLUDE_DIR OR NOT TENSORRT_LIBRARY)
    message(FATAL_ERROR "TensorRT not found. Set TENSORRT_ROOT to TensorRT installation directory.")
endif()

message(STATUS "TensorRT found: ${TENSORRT_ROOT}")
message(STATUS "  Include: ${TENSORRT_INCLUDE_DIR}")
message(STATUS "  Library: ${TENSORRT_LIBRARY}")

# Include directories
include_directories(
    ${CMAKE_SOURCE_DIR}/include
    ${CUDA_INCLUDE_DIRS}
    ${TENSORRT_INCLUDE_DIR}
)

# Source files
set(AQUILA_SOURCES
    src/main.cpp
    src/model_runtime.cpp
    src/preprocessing.cpp
    src/api_server.cpp
    src/logger.cpp
    src/metrics.cpp
)

# Main executable
add_executable(aquila_server ${AQUILA_SOURCES})

target_link_libraries(aquila_server
    ${CUDA_LIBRARIES}
    ${TENSORRT_LIBRARY}
    ${TENSORRT_PLUGIN_LIBRARY}
    ${CMAKE_THREAD_LIBS_INIT}
    # Add Crow dependencies when implemented
)

# Benchmark executable
add_executable(aquila_benchmark
    src/benchmark.cpp
    src/model_runtime.cpp
    src/preprocessing.cpp
    src/logger.cpp
)

target_link_libraries(aquila_benchmark
    ${CUDA_LIBRARIES}
    ${TENSORRT_LIBRARY}
    ${TENSORRT_PLUGIN_LIBRARY}
    ${CMAKE_THREAD_LIBS_INIT}
)

# Tests
enable_testing()
add_subdirectory(tests)

# Install
install(TARGETS aquila_server aquila_benchmark
    RUNTIME DESTINATION bin
)

install(DIRECTORY ${CMAKE_SOURCE_DIR}/config/
    DESTINATION etc/aquila
    FILES_MATCHING PATTERN "*.yaml"
)

# Print configuration
message(STATUS "")
message(STATUS "========== Aquila Configuration ==========")
message(STATUS "Build Type: ${CMAKE_BUILD_TYPE}")
message(STATUS "CUDA Version: ${CUDA_VERSION}")
message(STATUS "CUDA Arch: ${CMAKE_CUDA_FLAGS}")
message(STATUS "C++ Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "==========================================")
message(STATUS "")
