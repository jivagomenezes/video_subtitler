# Video Subtitle

Automatically transcribe, translate, and hard-embed subtitles into any video — directly from your Mac, with no ongoing cost beyond the DeepL API.

**How it works:**
1. [Whisper](https://github.com/openai/whisper) (OpenAI, runs locally) transcribes the audio
2. [DeepL API](https://www.deepl.com/pro-api) translates the text into your chosen language
3. [ffmpeg](https://ffmpeg.org) burns the subtitles into the video

Supports **34 target languages** and **19 source languages** (with auto-detection).

---

## Requirements

| Tool | Purpose |
|------|---------|
| Python 3.10+ | Runtime |
| [ffmpeg](https://ffmpeg.org/download.html) | Video encoding |
| [DeepL API key](https://www.deepl.com/pro-api) | Translation (free tier: 500k chars/month) |

Install ffmpeg with Homebrew:
```bash
brew install ffmpeg
```

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/video-subtitle.git
cd video-subtitle

# 2. Create a virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install openai-whisper deepl Pillow

# 3. The Whisper model downloads automatically on first run (~150 MB for "base")
```

---

## Option A — Mac App (GUI)

The graphical interface lets you pick a video, choose languages, and track progress with a real-time log and progress bar.

### Features

- Select any video file (MP4, MOV, AVI, MKV, WebM…)
- Choose source language or use **auto-detect**
- Choose any of the 34 DeepL target languages
- Real-time progress bar and log
- UI in **English** and **Portuguese** — auto-detected from your Mac's language, or toggle with the button in the top-right corner
- Settings (API key, languages, folder) saved between sessions

---

### A1 — Download the DMG (no git clone needed)

> Best for users who just want the app without touching code.

1. Download **`VideoSubtitle.dmg`** from the [Releases](../../releases) page
2. Open the DMG, drag **Video Subtitle** to your Applications folder
3. Install ffmpeg if you haven't already: `brew install ffmpeg`
4. Launch the app — on first run it automatically installs its Python dependencies (~2 min, requires internet)

---

### A2 — Build from source

```bash
source venv/bin/activate
bash build_app.sh
```

This creates **`Video Subtitle.app`** in the project folder. Drag it to `/Applications` to install.

> **Note:** The app requires the project folder to stay in its original location (it uses the local `venv`). If you move the project, re-run `build_app.sh`.

### Build a distributable DMG (for sharing)

```bash
bash build_release.sh
```

This creates a `release/` folder containing:
- `Video Subtitle.app` — self-contained, no project folder dependency
- `VideoSubtitle.dmg` — ready to share or upload to GitHub Releases

The released app bundles `app.py` and `legendar.py` inside the `.app` itself and installs its Python dependencies into `~/Library/Application Support/VideoSubtitle/` on first launch. Source files are refreshed from the bundle on every launch, so updating the DMG updates the app.

---

## Option B — Terminal (CLI)

Useful for automation or batch processing.

```bash
source venv/bin/activate

# Basic usage — place video in ~/Movies/to_share_videos/
python legendar.py video.mp4

# Specify languages
python legendar.py video.mp4 --target ES --source en

# Auto-detect source language
python legendar.py video.mp4 --target FR --source auto

# Pass API key via environment variable (avoids the prompt)
export DEEPL_API_KEY="your-key-here"
python legendar.py video.mp4 --target PT-BR
```

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `video` | _(prompted)_ | Filename inside `~/Movies/to_share_videos/` |
| `--target` | `PT-BR` | DeepL target language code |
| `--source` | `en` | Whisper source language code (`auto` for auto-detect) |

Output is saved to `~/Movies/subtitled_videos/`.

---

## Supported Languages

### Target languages (DeepL)

| Language | Code | Language | Code |
|----------|------|----------|------|
| Arabic | AR | Japanese | JA |
| Bulgarian | BG | Korean | KO |
| Chinese (Simplified) | ZH-HANS | Latvian | LV |
| Chinese (Traditional) | ZH-HANT | Lithuanian | LT |
| Czech | CS | Norwegian | NB |
| Danish | DA | Polish | PL |
| Dutch | NL | **Portuguese (Brazil)** | **PT-BR** |
| English (US) | EN-US | Portuguese (Portugal) | PT-PT |
| English (UK) | EN-GB | Romanian | RO |
| Estonian | ET | Russian | RU |
| Finnish | FI | Slovak | SK |
| French | FR | Slovenian | SL |
| German | DE | Spanish | ES |
| Greek | EL | Swedish | SV |
| Hungarian | HU | Turkish | TR |
| Indonesian | ID | Ukrainian | UK |
| Italian | IT | | |

### Source languages (Whisper)

Arabic, Chinese, Dutch, English, French, German, Hindi, Indonesian, Italian, Japanese, Korean, Polish, Portuguese, Russian, Spanish, Swedish, Turkish, Ukrainian — or **Auto-detect**.

---

## Project Structure

```
video-subtitle/
├── app.py            # GUI application
├── legendar.py       # Core processing module (also usable as CLI)
├── create_icon.py    # Generates icon.icns from scratch (run once)
├── build_app.sh      # Creates the clickable .app bundle
├── setup.py          # Alternative: py2app configuration
└── venv/             # Python virtual environment (not committed)
```

---

## Tips

- **Free DeepL tier** gives 500,000 characters/month — enough for hours of video.
- The **Whisper "base" model** is fast and accurate for clear speech. For noisy audio, change `"base"` to `"small"` or `"medium"` in `legendar.py`.
- Output videos are named `<original>_<LANGCODE>.mp4` (e.g. `myvideo_PTBR.mp4`).

---

## Technical notes

### CJK subtitle rendering (Chinese, Japanese, Korean)

On macOS 15+, the standard CJK system font (`PingFang.ttc`) was removed from `/System/Library/Fonts/` and moved to a private framework that FreeType cannot access. This would cause all CJK characters to render as square boxes (tofu).

**Workaround:** For CJK languages, the app generates an [ASS](https://fileformats.fandom.com/wiki/SubStation_Alpha) subtitle file instead of SRT and **embeds the font binary** directly in the `[Fonts]` section of the ASS file. libass reads the glyph data from memory and never asks the OS for a font — completely bypassing the CoreText restriction.

Fonts used:
| Language | Font file | FreeType family name |
|----------|-----------|---------------------|
| Chinese Traditional | `STHeiti Medium.ttc` | `Heiti TC` |
| Chinese Simplified | `Hiragino Sans GB.ttc` | `Hiragino Sans GB` |
| Japanese | `ヒラギノ角ゴシック W3.ttc` | `Hiragino Sans` |
| Korean | `AppleSDGothicNeo.ttc` | `Apple SD Gothic Neo` |

All of these are in the publicly readable `/System/Library/Fonts/`.

### CJK text splitting

Chinese and Japanese text contains no spaces, so word-based splitting produces lines that overflow the frame. The app instead splits CJK text by character count (default: 12 characters per line).

---

## License

MIT
