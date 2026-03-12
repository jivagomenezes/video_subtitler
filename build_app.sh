#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_app.sh — Creates "Video Subtitle.app" without py2app
# The .app simply launches app.py using the local venv.
# Works on macOS 12+. Must be run from the project directory.
# ─────────────────────────────────────────────────────────────────────────────
set -e

APP_NAME="Video Subtitle"
APP_BUNDLE="${APP_NAME}.app"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "📦 Building ${APP_BUNDLE}..."

# 1. Generate icon (requires Pillow)
if [ ! -f "${PROJECT_DIR}/icon.icns" ]; then
    echo "🎨 Generating icon..."
    source "${PROJECT_DIR}/venv/bin/activate"
    python "${PROJECT_DIR}/create_icon.py"
    deactivate
fi

# 2. Create bundle structure
rm -rf "${PROJECT_DIR}/${APP_BUNDLE}"
mkdir -p "${PROJECT_DIR}/${APP_BUNDLE}/Contents/MacOS"
mkdir -p "${PROJECT_DIR}/${APP_BUNDLE}/Contents/Resources"

# 3. Launcher script (runs inside the bundle, activates the project venv)
cat > "${PROJECT_DIR}/${APP_BUNDLE}/Contents/MacOS/VideoSubtitle" << LAUNCHER
#!/usr/bin/env bash
# Add Homebrew paths so ffmpeg is found regardless of how the .app is launched
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:\$PATH"
source "${PROJECT_DIR}/venv/bin/activate"
python "${PROJECT_DIR}/app.py"
LAUNCHER
chmod +x "${PROJECT_DIR}/${APP_BUNDLE}/Contents/MacOS/VideoSubtitle"

# 4. Info.plist
cat > "${PROJECT_DIR}/${APP_BUNDLE}/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>VideoSubtitle</string>
    <key>CFBundleIdentifier</key>
    <string>com.videosubtitle.app</string>
    <key>CFBundleName</key>
    <string>Video Subtitle</string>
    <key>CFBundleDisplayName</key>
    <string>Video Subtitle</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
</dict>
</plist>
PLIST

# 5. Copy icon
if [ -f "${PROJECT_DIR}/icon.icns" ]; then
    cp "${PROJECT_DIR}/icon.icns" "${PROJECT_DIR}/${APP_BUNDLE}/Contents/Resources/icon.icns"
fi

echo ""
echo "✅ Done!  ${PROJECT_DIR}/${APP_BUNDLE}"
echo ""
echo "To install: drag '${APP_BUNDLE}' to /Applications"
echo "Note: the app requires the project folder to stay at:"
echo "      ${PROJECT_DIR}"
