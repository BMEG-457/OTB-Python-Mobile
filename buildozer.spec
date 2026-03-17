[app]

# App identity
title = OTB EMG App
package.name = otbemgapp
package.domain = org.bmeg457

# Entry point
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.include_patterns = assets/*

# Dependencies
# scipy, matplotlib, and kivy_matplotlib_widget have been removed.
# IIR filtering, peak detection, and resampling are implemented in
# app/processing/iir_filter.py using numpy only.
# The EMG plot widget uses Kivy's canvas directly (no matplotlib).
requirements = python3,kivy==2.3.0,numpy

# Android permissions
# WRITE/READ_EXTERNAL_STORAGE: required on Android 9/10 (API 28-29) to write to
# /sdcard/Documents/OTB_EMG/ so recordings are visible in the file manager.
# These are standard runtime permissions shown as a system dialog on first launch.
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# Android API targets
# targetSdkVersion=28: apps targeting API 28 or lower receive legacy storage
# behaviour on Android 10 automatically — requestLegacyExternalStorage is not
# needed and buildozer's manifest attribute injection is avoided entirely.
android.api = 28
android.minapi = 21

# Build for both 64-bit and 32-bit ARM devices
android.archs = arm64-v8a, armeabi-v7a

# Force landscape for the wider plot area
orientation = landscape

# App version
version = 0.1

[buildozer]
log_level = 2
warn_on_root = 1
build_dir = /home/fettuccinifelix/.buildozer/otb-mobile
