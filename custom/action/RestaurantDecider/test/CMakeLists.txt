cmake_minimum_required(VERSION 3.31)
project(RestaurantDecider)

set(CMAKE_CXX_STANDARD 23)
add_compile_options(/utf-8)

find_package(Python3 COMPONENTS Development REQUIRED)
include_directories(.)
include_directories(F:/MAGTemp/MAG_Refactored/MFW-PyQt6/.venv/Lib/site-packages/pybind11/include)



add_executable(RestaurantDecider
        decider.cpp
        json.hpp
        setup.py
        assistant.hpp
        DataClasses.cppm
        ContainerAlias.hpp
        AssistFunctions.cppm)

target_link_libraries(RestaurantDecider PRIVATE Python3::Python)
target_link_directories(RestaurantDecider PRIVATE E:/Python/libs)
