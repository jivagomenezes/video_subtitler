#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_release.sh — Builds a self-contained "Video Subtitle.app" + DMG
#
# Unlike build_app.sh (which requires the project folder to stay in place),
# this creates an app that:
#   1. Bundles app.py, legendar.py, and icon inside the .app itself
#   2. On first launch, creates a venv in ~/Library/Application Support/VideoSubtitle/
#      and installs all Python dependencies automatically
#   3. Can be distributed as a standalone DMG — no git clone needed
#
# Requirements: Python 3.10+, ffmpeg (brew install ffmpeg), internet on first run
# Run from the project directory: bash build_release.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

APP_NAME="Video Subtitle"
APP_BUNDLE="${APP_NAME}.app"
DMG_NAME="VideoSubtitle.dmg"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE_DIR="${PROJECT_DIR}/release"

echo "📦 Building self-contained ${APP_BUNDLE}..."

# ── 1. Generate icon if missing ───────────────────────────────────────────────
if [ ! -f "${PROJECT_DIR}/icon.icns" ]; then
    echo "🎨 Generating icon..."
    source "${PROJECT_DIR}/venv/bin/activate"
    python "${PROJECT_DIR}/create_icon.py"
    deactivate
fi

# ── 2. Create bundle structure ────────────────────────────────────────────────
mkdir -p "${RELEASE_DIR}"
rm -rf "${RELEASE_DIR}/${APP_BUNDLE}"
mkdir -p "${RELEASE_DIR}/${APP_BUNDLE}/Contents/MacOS"
mkdir -p "${RELEASE_DIR}/${APP_BUNDLE}/Contents/Resources"

# ── 3. Copy app source files into Resources ───────────────────────────────────
cp "${PROJECT_DIR}/app.py"         "${RELEASE_DIR}/${APP_BUNDLE}/Contents/Resources/"
cp "${PROJECT_DIR}/legendar.py"    "${RELEASE_DIR}/${APP_BUNDLE}/Contents/Resources/"
cp "${PROJECT_DIR}/create_icon.py" "${RELEASE_DIR}/${APP_BUNDLE}/Contents/Resources/"
if [ -f "${PROJECT_DIR}/icon.icns" ]; then
    cp "${PROJECT_DIR}/icon.icns"  "${RELEASE_DIR}/${APP_BUNDLE}/Contents/Resources/"
fi

# ── 4. Smart launcher (self-contained, no project folder dependency) ──────────
cat > "${RELEASE_DIR}/${APP_BUNDLE}/Contents/MacOS/VideoSubtitle" << 'LAUNCHER'
#!/usr/bin/env bash
# Add Homebrew paths so ffmpeg is found regardless of how the .app is launched
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

RESOURCES="$(dirname "$0")/../Resources"
SUPPORT_DIR="$HOME/Library/Application Support/VideoSubtitle"
VENV_DIR="$SUPPORT_DIR/venv"
APP_DIR="$SUPPORT_DIR/app"
LOG_FILE="$SUPPORT_DIR/setup.log"

# ── First-run setup ───────────────────────────────────────────────────────────
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    mkdir -p "$SUPPORT_DIR" "$APP_DIR"

    osascript -e 'display notification "First launch: installing dependencies (this takes a few minutes)..." with title "Video Subtitle"' 2>/dev/null || true

    # Copy latest source from bundle
    cp "$RESOURCES/app.py"         "$APP_DIR/"
    cp "$RESOURCES/legendar.py"    "$APP_DIR/"
    cp "$RESOURCES/create_icon.py" "$APP_DIR/"
    [ -f "$RESOURCES/icon.icns" ] && cp "$RESOURCES/icon.icns" "$APP_DIR/"

    # Create venv and install dependencies
    python3 -m venv "$VENV_DIR" >"$LOG_FILE" 2>&1
    source "$VENV_DIR/bin/activate"
    pip install --quiet openai-whisper deepl Pillow >>"$LOG_FILE" 2>&1

    osascript -e 'display notification "Setup complete! Starting Video Subtitle..." with title "Video Subtitle"' 2>/dev/null || true
else
    source "$VENV_DIR/bin/activate"
    # Always sync latest source files from bundle (picks up updates)
    cp "$RESOURCES/app.py"      "$APP_DIR/"
    cp "$RESOURCES/legendar.py" "$APP_DIR/"
fi

python "$APP_DIR/app.py"
LAUNCHER
chmod +x "${RELEASE_DIR}/${APP_BUNDLE}/Contents/MacOS/VideoSubtitle"

# ── 5. Info.plist ─────────────────────────────────────────────────────────────
cat > "${RELEASE_DIR}/${APP_BUNDLE}/Contents/Info.plist" << 'PLIST'
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

# ── 6. Create DMG ─────────────────────────────────────────────────────────────
echo "💿 Creating ${DMG_NAME}..."

# Create a temporary folder for DMG contents
DMG_STAGING="${RELEASE_DIR}/dmg_staging"
rm -rf "${DMG_STAGING}"
mkdir -p "${DMG_STAGING}"
cp -r "${RELEASE_DIR}/${APP_BUNDLE}" "${DMG_STAGING}/"
# Add a symlink to /Applications for easy drag-and-drop install
ln -s /Applications "${DMG_STAGING}/Applications"

# Build the DMG
hdiutil create \
    -volname "${APP_NAME}" \
    -srcfolder "${DMG_STAGING}" \
    -ov \
    -format UDZO \
    "${RELEASE_DIR}/${DMG_NAME}" \
    > /dev/null

# Cleanup staging
rm -rf "${DMG_STAGING}"

echo ""
echo "✅ Release build complete!"
echo ""
echo "   App:  ${RELEASE_DIR}/${APP_BUNDLE}"
echo "   DMG:  ${RELEASE_DIR}/${DMG_NAME}"
echo ""
echo "To distribute: share ${DMG_NAME}"
echo "  Users open the DMG, drag 'Video Subtitle' to Applications, and launch."
echo "  On first launch, the app auto-installs Python dependencies (~2 min)."
echo "  Requires: Python 3.10+ and 'brew install ffmpeg' on the target Mac."
