import whisper
import deepl
import subprocess
import shutil
import tempfile
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional


def _find_ffmpeg() -> Optional[str]:
    """Locate ffmpeg, preferring ffmpeg-full (has libass) over the base build."""
    for candidate in (
        "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
        "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
    ):
        if os.path.exists(candidate):
            return candidate
    path = shutil.which("ffmpeg")
    if path:
        return path
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.exists(candidate):
            return candidate
    return None


def _has_libass(ffmpeg: str) -> bool:
    """Return True if this ffmpeg build has the subtitles (libass) filter."""
    try:
        r = subprocess.run([ffmpeg, "-filters"], capture_output=True, text=True, timeout=5)
        return "subtitles" in r.stdout
    except Exception:
        return False


# ASS color format: &HAABBGGRR (alpha, blue, green, red)
SUBTITLE_COLORS: dict[str, str] = {
    "White":  "&H00FFFFFF",
    "Yellow": "&H0000FFFF",
    "Cyan":   "&H00FFFF00",
    "Green":  "&H0000FF00",
}

FONT_FAMILIES: dict[str, str] = {
    "System Default": "",
    "Arial":          "Arial",
    "Helvetica Neue": "Helvetica Neue",
    "Impact":         "Impact",
    "Futura":         "Futura",
    "Georgia":        "Georgia",
}

BOLD_LEVELS: dict[str, int] = {
    "Off":    0,
    "Normal": 1,
    "Heavy":  900,
}

# CJK font candidates: key → (FreeType family name from face 0, [file_path_candidates])
# PingFang.ttc was removed from /System/Library/Fonts in macOS 15+ and only
# exists as PingFangUI.ttc in PrivateFrameworks — FreeType cannot open that file.
# STHeiti Medium.ttc and Hiragino Sans GB.ttc are publicly accessible and cover
# all common Traditional and Simplified Chinese characters respectively.
_CJK_FONTS: dict[str, tuple[str, list[str]]] = {
    "TC": ("Heiti TC",         ["/System/Library/Fonts/STHeiti Medium.ttc",
                                 "/System/Library/Fonts/STHeiti Light.ttc"]),
    "SC": ("Hiragino Sans GB", ["/System/Library/Fonts/Hiragino Sans GB.ttc"]),
    "JA": ("Hiragino Sans",    [
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans W3.ttc",
        "/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    ]),
    "KO": ("Apple SD Gothic Neo", [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/AppleSDGothicNeo.ttc",
    ]),
}


def _find_cjk_font(target_lang: str) -> tuple[Optional[str], str]:
    """Return (font_file_path_or_None, font_name) for the given CJK language."""
    lang_up = target_lang.upper()
    if "JA" in lang_up:
        key = "JA"
    elif "KO" in lang_up:
        key = "KO"
    elif "HANT" in lang_up or "TW" in lang_up or "HK" in lang_up:
        key = "TC"
    else:
        key = "SC"
    font_name, candidates = _CJK_FONTS[key]
    for p in candidates:
        if os.path.exists(p):
            return p, font_name
    return None, font_name


def _encode_ass_font(data: bytes) -> str:
    """
    Encode font bytes for the ASS [Fonts] section.
    libass uses a 6-bit encoding: each output char = (6-bit value) + 33.
    Embedding the font lets libass find glyphs without touching fontconfig.
    """
    pad = (-len(data)) % 3
    padded = data + b'\x00' * pad
    n = len(padded)
    out = bytearray(n // 3 * 4)
    for i in range(n // 3):
        b0 = padded[i * 3]
        b1 = padded[i * 3 + 1]
        b2 = padded[i * 3 + 2]
        out[i * 4]     = (b0 >> 2) + 33
        out[i * 4 + 1] = ((b0 & 3) << 4 | b1 >> 4) + 33
        out[i * 4 + 2] = ((b1 & 0xf) << 2 | b2 >> 6) + 33
        out[i * 4 + 3] = (b2 & 0x3f) + 33
    encoded = out.decode('latin-1')
    return '\n'.join(encoded[i:i + 80] for i in range(0, len(encoded), 80))


def _format_ass_time(secs: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cs"""
    h  = int(secs // 3600)
    m  = int((secs % 3600) // 60)
    s  = int(secs % 60)
    cs = int(round((secs % 1) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _make_ass_with_font(
    subtitle_blocks: list[dict],
    target_lang: str,
    font_size: int,
    margin_v: int,
    color: str,
    bold: int,
    log_fn=None,
) -> Optional[str]:
    """
    Generate a temp ASS subtitle file with the CJK font embedded in [Fonts].
    Embedding bypasses fontconfig entirely — libass reads the glyph data
    directly from the ASS file, so Homebrew's missing macOS font paths
    are irrelevant.  Returns the temp path (caller must os.unlink it),
    or None if the font file cannot be found/read.
    """
    def _log(msg):
        print(msg)
        if log_fn:
            log_fn(msg)

    font_path, font_name = _find_cjk_font(target_lang)
    _log(f"   [ASS] target_lang={target_lang!r} → font_name={font_name!r} font_path={font_path!r}")
    if not font_path:
        _log("   [ASS] ❌ No CJK font file found on disk — cannot embed font")
        return None

    try:
        with open(font_path, 'rb') as f:
            font_data = f.read()
        _log(f"   [ASS] Font file read OK: {len(font_data):,} bytes")
    except Exception as exc:
        _log(f"   [ASS] ❌ Failed to read font file: {exc}")
        return None

    font_encoded = _encode_ass_font(font_data)
    _log(f"   [ASS] Encoded font: {len(font_encoded):,} chars, first 40: {font_encoded[:40]!r}")
    hex_color = SUBTITLE_COLORS.get(color, "&H00FFFFFF")
    # ASS Style Bold field: -1 = bold, 0 = off, 900 = heavy
    ass_bold = "-1" if bold == 1 else str(bold)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "Collisions: Normal\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{hex_color},"
        f"&H000000FF,&H00000000,&H00000000,{ass_bold},0,0,0,"
        f"100,100,0,0,1,1,0.5,2,10,10,{margin_v},1\n"
        "\n"
        "[Fonts]\n"
        f"fontname: {font_name}\n"
        f"{font_encoded}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = []
    for block in subtitle_blocks:
        start = _format_ass_time(block['start'])
        end   = _format_ass_time(block['end'])
        text  = block['text'].replace('\\', '\\\\').replace('\n', '\\N')
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    content = header + '\n'.join(events) + '\n'

    try:
        fd, path = tempfile.mkstemp(suffix='.ass', prefix='legendar_')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        _log(f"   [ASS] ✅ ASS file written: {path}  ({len(content):,} bytes, {len(subtitle_blocks)} events)")
        return path
    except Exception as exc:
        _log(f"   [ASS] ❌ Failed to write ASS file: {exc}")
        return None


def _subtitle_style(target_lang: str, font_size: int = 10,
                    margin_v: int = 12, color: str = "White",
                    font_family: str = "", bold: int = 1) -> str:
    """Return ffmpeg force_style string (used for non-CJK or ASS fallback)."""
    lang_up = target_lang.upper()
    if any(k in lang_up for k in ("ZH", "JA", "KO")):
        _, font = _find_cjk_font(target_lang)
        fontname = rf"\,Fontname={font}"
    else:
        fname = FONT_FAMILIES.get(font_family, "")
        fontname = rf"\,Fontname={fname}" if fname else ""
    hex_color = SUBTITLE_COLORS.get(color, "&H00FFFFFF")
    return (rf"FontSize={font_size}{fontname}"
            rf"\,PrimaryColour={hex_color}\,Bold={bold}\,Outline=1\,Shadow=0.5\,MarginV={margin_v}")


try:
    from deep_translator import GoogleTranslator
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False


def format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"


def split_cjk_text_and_time(text: str, start_time: float, end_time: float, max_chars: int = 12) -> list:
    """Split CJK text by character count (no spaces in Chinese/Japanese)."""
    text = text.strip()
    if not text:
        return []
    chunks = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
    duration_per_chunk = (end_time - start_time) / len(chunks)
    blocks = []
    current_time = start_time
    for chunk in chunks:
        chunk_end = current_time + duration_per_chunk
        blocks.append({"text": chunk, "start": current_time, "end": chunk_end})
        current_time = chunk_end
    return blocks


def split_text_and_time(text: str, start_time: float, end_time: float, max_words: int = 4) -> list:
    words = text.split()
    if not words:
        return []
    chunks = [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]
    duration_per_chunk = (end_time - start_time) / len(chunks)
    blocks = []
    current_time = start_time
    for chunk in chunks:
        chunk_end = current_time + duration_per_chunk
        blocks.append({"text": chunk, "start": current_time, "end": chunk_end})
        current_time = chunk_end
    return blocks


# ── Language tables ────────────────────────────────────────────────────────────

DEEPL_LANGUAGES: dict[str, str] = {
    "Arabic":                "AR",
    "Bulgarian":             "BG",
    "Chinese (Simplified)":  "ZH-HANS",
    "Chinese (Traditional)": "ZH-HANT",
    "Czech":                 "CS",
    "Danish":                "DA",
    "Dutch":                 "NL",
    "English (US)":          "EN-US",
    "English (UK)":          "EN-GB",
    "Estonian":              "ET",
    "Finnish":               "FI",
    "French":                "FR",
    "German":                "DE",
    "Greek":                 "EL",
    "Hungarian":             "HU",
    "Indonesian":            "ID",
    "Italian":               "IT",
    "Japanese":              "JA",
    "Korean":                "KO",
    "Latvian":               "LV",
    "Lithuanian":            "LT",
    "Norwegian":             "NB",
    "Polish":                "PL",
    "Portuguese (Brazil)":   "PT-BR",
    "Portuguese (Portugal)": "PT-PT",
    "Romanian":              "RO",
    "Russian":               "RU",
    "Slovak":                "SK",
    "Slovenian":             "SL",
    "Spanish":               "ES",
    "Swedish":               "SV",
    "Turkish":               "TR",
    "Ukrainian":             "UK",
}

GOOGLE_LANGUAGES: dict[str, str] = {
    "Arabic":                "ar",
    "Bulgarian":             "bg",
    "Chinese (Simplified)":  "zh-CN",
    "Chinese (Traditional)": "zh-TW",
    "Czech":                 "cs",
    "Danish":                "da",
    "Dutch":                 "nl",
    "English":               "en",
    "Estonian":              "et",
    "Finnish":               "fi",
    "French":                "fr",
    "German":                "de",
    "Greek":                 "el",
    "Hindi":                 "hi",
    "Hungarian":             "hu",
    "Indonesian":            "id",
    "Italian":               "it",
    "Japanese":              "ja",
    "Korean":                "ko",
    "Latvian":               "lv",
    "Lithuanian":            "lt",
    "Norwegian":             "no",
    "Polish":                "pl",
    "Portuguese (Brazil)":   "pt",
    "Romanian":              "ro",
    "Russian":               "ru",
    "Slovak":                "sk",
    "Slovenian":             "sl",
    "Spanish":               "es",
    "Swedish":               "sv",
    "Turkish":               "tr",
    "Ukrainian":             "uk",
    "Vietnamese":            "vi",
}

WHISPER_LANGUAGES: dict[str, Optional[str]] = {
    "Auto-detect": None,
    "Arabic":      "ar",
    "Chinese":     "zh",
    "Dutch":       "nl",
    "English":     "en",
    "French":      "fr",
    "German":      "de",
    "Hindi":       "hi",
    "Indonesian":  "id",
    "Italian":     "it",
    "Japanese":    "ja",
    "Korean":      "ko",
    "Polish":      "pl",
    "Portuguese":  "pt",
    "Russian":     "ru",
    "Spanish":     "es",
    "Swedish":     "sv",
    "Turkish":     "tr",
    "Ukrainian":   "uk",
}


def _translate_deepl(texts: list[str], api_key: str, target_lang: str) -> list[str]:
    translator = deepl.Translator(api_key)
    results = translator.translate_text(texts, target_lang=target_lang)
    return [r.text for r in results]


def _translate_google(texts: list[str], target_lang: str) -> list[str]:
    if not _GOOGLE_AVAILABLE:
        raise RuntimeError("deep-translator not installed. Run: pip install deep-translator")

    def translate_one(text: str) -> str:
        try:
            result = GoogleTranslator(source="auto", target=target_lang).translate(text)
            return result or text
        except Exception:
            return text

    with ThreadPoolExecutor(max_workers=5) as executor:
        return list(executor.map(translate_one, texts))


def process_video(
    video_path: str,
    api_key: str,
    output_dir: str,
    target_lang: str = "PT-BR",
    source_lang: Optional[str] = "en",
    service: str = "deepl",
    stop_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    subtitle_font_size: int = 10,
    subtitle_margin: int = 12,
    subtitle_color: str = "White",
    subtitle_font_family: str = "",
    subtitle_bold: int = 1,
    keep_srt: bool = False,
) -> Optional[str]:
    """
    Transcribes, translates and embeds subtitles into a video.

    progress_callback(percent, description):
      percent = -1  →  switch UI to indeterminate (pulsing) mode
      percent 0-100 →  normal progress
    """

    def log(msg: str):
        print(msg)
        if log_callback:
            log_callback(msg)

    def progress(pct: float, desc: str):
        if progress_callback:
            progress_callback(pct, desc)

    def stopped() -> bool:
        return stop_event is not None and stop_event.is_set()

    if not os.path.exists(video_path):
        log(f"❌ File not found: {video_path}")
        return None

    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(video_path))[0]
    safe_name = base_name.replace(" ", "_")
    lang_tag = target_lang.replace("-", "").upper()
    srt_path = os.path.join(output_dir, f"{safe_name}_subtitle.srt")
    final_path = os.path.join(output_dir, f"{safe_name}_{lang_tag}.mp4")

    # ── Step 1: Transcribe ────────────────────────────────────────────────────
    if stopped():
        return None

    src_label = source_lang or "auto"
    log("🎧 Loading Whisper model...")
    progress(3, "Loading Whisper model...")

    model = whisper.load_model("base", device="cpu")

    log(f"🎧 Transcribing audio (source: {src_label}) — please wait, this takes 1-3 min...")
    progress(-1, "Transcribing audio…")

    transcribe_opts: dict = {"fp16": False}
    if source_lang:
        transcribe_opts["language"] = source_lang

    try:
        result = model.transcribe(video_path, **transcribe_opts)
    except Exception as e:
        log(f"❌ Transcription failed: {e}")
        return None

    if stopped():
        return None

    segments = result["segments"]
    detected = result.get("language", src_label)
    log(f"✅ Transcription done — {len(segments)} segments (detected: {detected})")
    progress(50, "Transcription complete")

    # ── Step 2: Translate ─────────────────────────────────────────────────────
    if stopped():
        return None

    log(f"🌐 Translating {len(segments)} segments → {target_lang} via {service}...")
    progress(52, f"Translating ({service})…")

    texts = [seg["text"].strip() for seg in segments]

    try:
        if service == "deepl":
            translated_texts = _translate_deepl(texts, api_key, target_lang)
        else:
            translated_texts = _translate_google(texts, target_lang)
    except deepl.AuthorizationException:
        log("❌ Invalid DeepL API key.")
        return None
    except Exception as e:
        log(f"❌ Translation error: {e}")
        return None

    if stopped():
        return None

    log("✅ Translation complete")
    progress(65, "Translation complete")

    # ── Step 3: Write SRT (and collect blocks for CJK ASS generation) ─────────
    log("📝 Writing subtitle file...")
    progress(67, "Writing subtitles…")

    lang_up = target_lang.upper()
    is_cjk = any(k in lang_up for k in ("ZH", "JA", "KO"))

    all_blocks: list[dict] = []
    srt_counter = 1
    with open(srt_path, "w", encoding="utf-8") as srt_file:
        for i, segment in enumerate(segments):
            if is_cjk:
                blocks = split_cjk_text_and_time(
                    translated_texts[i], segment["start"], segment["end"], max_chars=12
                )
            else:
                blocks = split_text_and_time(
                    translated_texts[i], segment["start"], segment["end"], max_words=4
                )
            all_blocks.extend(blocks)
            for block in blocks:
                srt_file.write(f"{srt_counter}\n")
                srt_file.write(f"{format_time(block['start'])} --> {format_time(block['end'])}\n")
                srt_file.write(f"{block['text']}\n\n")
                srt_counter += 1

    progress(70, "Subtitle file ready")

    # ── Step 4: Encode with ffmpeg ────────────────────────────────────────────
    if stopped():
        return None

    ffmpeg = _find_ffmpeg()
    if ffmpeg is None:
        log("❌ ffmpeg not found. Install it with: brew install ffmpeg")
        return None

    log("🎬 Encoding video with embedded subtitles...")
    progress(72, "Encoding video…")

    ass_path: Optional[str] = None
    try:
        if _has_libass(ffmpeg):
            # ── Burn-in subtitles (libass available) ──────────────────────────
            log("🎬 Encoding with burned-in subtitles…")

            if is_cjk:
                # CoreText (used by this ffmpeg build) resolves CJK font names
                # to /System/Library/PrivateFrameworks/.../PingFangUI.ttc which
                # FreeType cannot open (permission-restricted private framework).
                # Embedding the font in the ASS [Fonts] section gives libass the
                # glyph data directly in memory — no file access, no CoreText.
                log("🔤 Embedding CJK font in ASS file (bypasses CoreText restriction)…")
                ass_path = _make_ass_with_font(
                    subtitle_blocks=all_blocks,
                    target_lang=target_lang,
                    font_size=subtitle_font_size,
                    margin_v=subtitle_margin,
                    color=subtitle_color,
                    bold=subtitle_bold,
                    log_fn=log,
                )

            if ass_path:
                ass_escaped = (
                    ass_path.replace("\\", "/")
                             .replace(":", "\\:")
                             .replace("'", "\\'")
                )
                vf = f"ass={ass_escaped}"
                log(f"   [CJK] Using embedded-font ASS filter")
            else:
                srt_escaped = (
                    srt_path.replace("\\", "/")
                             .replace(":", "\\:")
                             .replace("'", "\\'")
                )
                style = _subtitle_style(
                    target_lang, subtitle_font_size, subtitle_margin,
                    subtitle_color, subtitle_font_family, subtitle_bold,
                )
                vf = f"subtitles={srt_escaped}:force_style={style}"

            command = [
                ffmpeg, "-y",
                "-i", video_path,
                "-vf", vf,
                "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                "-c:a", "copy",
                final_path,
            ]
        else:
            # ── Soft subtitles (no libass — stream copy, much faster) ─────────
            log("🎬 Embedding subtitles as selectable track (soft subs — no re-encoding)…")
            log("   Tip: for burned-in subs, run: brew reinstall ffmpeg")
            command = [
                ffmpeg, "-y",
                "-i", video_path,
                "-i", srt_path,
                "-c:v", "copy",
                "-c:a", "copy",
                "-c:s", "mov_text",
                "-map", "0:v:0",
                "-map", "0:a?",
                "-map", "1:s:0",
                final_path,
            ]

        log(f"   [CMD] {' '.join(command)}")
        proc = subprocess.Popen(
            command,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace",
        )

        duration_seconds = None
        duration_re = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
        time_re = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
        diag_lines: list[str] = []   # keep only diagnostic lines, max 200

        for line in proc.stderr:
            if stopped():
                proc.kill()
                log("⏹ Stopped.")
                return None

            line = line.rstrip()
            line_lower = line.lower()
            is_diag = any(kw in line_lower for kw in (
                "error", "invalid", "no such", "failed",
                "glyph", "missing", "fallback", "not found",
            ))
            if is_diag:
                log(f"   [ffmpeg] {line}")
                if len(diag_lines) < 200:
                    diag_lines.append(line)

            if duration_seconds is None:
                m = duration_re.search(line)
                if m:
                    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                    duration_seconds = h * 3600 + mi * 60 + s

            m = time_re.search(line)
            if m and duration_seconds:
                h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                current = h * 3600 + mi * 60 + s
                ratio = min(current / duration_seconds, 1.0)
                progress(72 + ratio * 28, f"Encoding… {int(ratio * 100)}%")

        proc.wait()

        if os.path.exists(final_path):
            log(f"🎉 Done! Saved to: {final_path}")
            progress(100, "Done!")
            if not keep_srt and os.path.exists(srt_path):
                try:
                    os.remove(srt_path)
                except Exception:
                    pass
            return final_path
        else:
            log("❌ ffmpeg encoding failed. Relevant output:")
            for line in diag_lines[-50:]:
                log(f"  ffmpeg: {line}")
            return None

    finally:
        if ass_path:
            try:
                os.unlink(ass_path)
            except Exception:
                pass


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Auto subtitle generator")
    parser.add_argument("video", nargs="?", help="Filename in ~/Movies/to_share_videos")
    parser.add_argument("--target", default="PT-BR")
    parser.add_argument("--source", default="en")
    parser.add_argument("--service", default="deepl", choices=["deepl", "google"])
    args = parser.parse_args()

    input_dir = os.path.expanduser("~/Movies/to_share_videos")
    output_dir = os.path.expanduser("~/Movies/subtitled_videos")

    api_key = os.environ.get("DEEPL_API_KEY", "").strip()
    if args.service == "deepl" and not api_key:
        api_key = input("DeepL API key: ").strip()

    filename = args.video or input("Video filename (e.g. video.mp4): ").strip("'\"")
    video_path = os.path.join(input_dir, filename)
    src = None if args.source == "auto" else args.source

    process_video(
        video_path, api_key, output_dir,
        target_lang=args.target, source_lang=src, service=args.service,
    )
