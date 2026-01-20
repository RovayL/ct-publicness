cmake_minimum_required(VERSION 3.16)
project(PublicDataPass LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(LLVM REQUIRED CONFIG)
message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")

include_directories(SYSTEM ${LLVM_INCLUDE_DIRS})
add_definitions(${LLVM_DEFINITIONS})

# Build as a loadable module for opt -load-pass-plugin
add_library(PublicDataPass MODULE PublicDataPass.cpp)

# Make the output name nice (no "lib" prefix)
set_target_properties(PublicDataPass PROPERTIES PREFIX "")

# ---- IMPORTANT PART: link against the single shared libLLVM, NOT component libs ----
# LLVM_LIBRARY_DIRS is provided by LLVMConfig.cmake
find_library(LLVM_DYLIB
  NAMES LLVM libLLVM.so libLLVM.so.18 libLLVM-18
  PATHS ${LLVM_LIBRARY_DIRS}
)

if (NOT LLVM_DYLIB)
  message(FATAL_ERROR "Could not find shared libLLVM (libLLVM.so) in: ${LLVM_LIBRARY_DIRS}")
endif()

message(STATUS "Linking against: ${LLVM_DYLIB}")
target_link_libraries(PublicDataPass PRIVATE ${LLVM_DYLIB})
