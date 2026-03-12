"""
py2app build configuration.

Usage:
    pip install py2app
    python setup.py py2app
"""

from setuptools import setup

APP = ["app.py"]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "icon.icns",
    "packages": [
        "whisper",
        "deepl",
        "tiktoken",
        "numpy",
    ],
    "excludes": [
        "matplotlib",
        "scipy",
        "pandas",
        "PIL",       # only needed for icon generation, not the app
        "IPython",
        "jupyter",
    ],
    "plist": {
        "CFBundleName":             "Video Subtitle",
        "CFBundleDisplayName":      "Video Subtitle",
        "CFBundleIdentifier":       "com.videosubtitle.app",
        "CFBundleVersion":          "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleIconFile":         "icon",
        "LSMinimumSystemVersion":   "12.0",
        "NSHighResolutionCapable":  True,
        "NSRequiresAquaSystemAppearance": False,  # supports dark mode
    },
}

setup(
    app=APP,
    name="Video Subtitle",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
