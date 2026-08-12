[app]
title = Image2SVG
package.name = image2svg
package.domain = art.janintibo
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy==2.3.0,pillow,android
orientation = portrait
fullscreen = 0
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True
p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
android.build_tools_version = 34.0.0
android.accept_sdk_license = True
