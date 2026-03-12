"""
Video Subtitle — Mac App
Dark-mode UI with rounded accent buttons and consistent styling.
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import queue
import locale
import time
import os
import json
import subprocess

import legendar

CONFIG_PATH = os.path.expanduser("~/.config/video_subtitle/config.json")

# ── Color palette (single dark theme) ─────────────────────────────────────────
C = {
    "bg":      "#1C1C1E",   # window / frame background
    "surface": "#2C2C2E",   # inputs, cards
    "surface2":"#3A3A3C",   # hover, borders
    "text":    "#FFFFFF",
    "text2":   "#8E8E93",   # secondary / placeholder
    "sep":     "#38383A",   # separator lines
    "log_bg":  "#111111",
    "log_fg":  "#D1D1D6",
    "log_sel": "#1A3F6F",
    "accent":  "#0A84FF",   # Start button / progress
    "acc_dn":  "#0068CC",   # Start hover
    "stop":    "#FF453A",   # Stop button
    "stop_dn": "#CC362E",
    "success": "#30D158",
    "error":   "#FF453A",
    "warn":    "#FF9F0A",
}

SYS_FONT = ".AppleSystemUIFont"   # SF Pro on macOS

# ── i18n ───────────────────────────────────────────────────────────────────────
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title":    "Legendar",
        "subtitle": "Video Subtitle  ·  Transcribe, translate and subtitle any video",
        "video":    "Video File",
        "v_hint":   "No file selected — click Choose…",
        "choose":   "Choose…",
        "service":  "Translation Service",
        "key":      "DeepL API Key",
        "key_hint": "(not required with Google Translate)",
        "src":      "Video Language",
        "tgt":      "Subtitle Language",
        "output":   "Output Folder",
        "o_hint":   "No folder selected — click Choose…",
        "start":    "▶  Start",
        "stop":     "■  Stop",
        "open":     "Open Folder",
        "ready":    "Ready",
        "txing":    "Transcribing audio…",
        "done":     "Done!",
        "failed":   "Failed — check the log",
        "stopped":  "Stopped",
        "no_video": "Please select a video file.",
        "no_key":   "DeepL API key is required.",
        "starting": "Starting…",
        "lang_btn": "Português",
        "warn":     "Warning",
        "sub_style":    "Subtitle Style",
        "font_size":    "Font Size",
        "pos_label":    "Margin",
        "pos_hint":     "lower value = closer to bottom edge",
        "sub_color":    "Color",
        "font_family":  "Font",
        "bold_label":   "Bold",
        "keep_srt":     "Keep subtitle file (.srt)",
    },
    "pt": {
        "title":    "Legendar",
        "subtitle": "Video Subtitle  ·  Transcreve, traduz e legenda qualquer vídeo",
        "video":    "Arquivo de Vídeo",
        "v_hint":   "Nenhum arquivo — clique em Escolher…",
        "choose":   "Escolher…",
        "service":  "Serviço de Tradução",
        "key":      "Chave DeepL API",
        "key_hint": "(não necessária com Google Tradutor)",
        "src":      "Idioma do Vídeo",
        "tgt":      "Idioma da Legenda",
        "output":   "Pasta de Saída",
        "o_hint":   "Nenhuma pasta — clique em Escolher…",
        "start":    "▶  Iniciar",
        "stop":     "■  Parar",
        "open":     "Abrir Pasta",
        "ready":    "Pronto",
        "txing":    "Transcrevendo áudio…",
        "done":     "Concluído!",
        "failed":   "Falhou — veja o log",
        "stopped":  "Parado",
        "no_video": "Selecione um arquivo de vídeo.",
        "no_key":   "A chave DeepL é necessária.",
        "starting": "Iniciando…",
        "lang_btn": "English",
        "warn":     "Atenção",
        "sub_style":    "Estilo da Legenda",
        "font_size":    "Tamanho",
        "pos_label":    "Margem",
        "pos_hint":     "valor menor = mais próximo do rodapé",
        "sub_color":    "Cor",
        "font_family":  "Fonte",
        "bold_label":   "Negrito",
        "keep_srt":     "Manter arquivo de legenda (.srt)",
    },
}

SERVICE_OPTIONS = ["DeepL", "Google Translate"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def detect_system_lang() -> str:
    try:
        code = locale.getdefaultlocale()[0] or ""
        return "pt" if code.lower().startswith("pt") else "en"
    except Exception:
        return "en"


def tilde_path(path: str) -> str:
    home = os.path.expanduser("~")
    return ("~" + path[len(home):]) if path.startswith(home) else path


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(data: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _darken(hex_color: str, f: float = 0.18) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#{:02x}{:02x}{:02x}".format(
        max(0, int(r * (1 - f))), max(0, int(g * (1 - f))), max(0, int(b * (1 - f)))
    )


def _round_rect(canvas, x0, y0, x1, y1, r, **kw):
    """Draw a smooth rounded rectangle using a polygon with smooth=True."""
    pts = [
        x0+r, y0,   x1-r, y0,
        x1,   y0,   x1,   y0+r,
        x1,   y1-r, x1,   y1,
        x1-r, y1,   x0+r, y1,
        x0,   y1,   x0,   y1-r,
        x0,   y0+r, x0,   y0,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RoundedButton(tk.Canvas):
    """A Canvas-based button with rounded corners and hover effect."""

    def __init__(self, parent, text, command, bg, width=120, height=38,
                 radius=10, font=None, **kw):
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        super().__init__(parent, width=width, height=height,
                         cursor="hand2", bg=C["bg"], **kw)
        self._bg     = bg
        self._hov    = _darken(bg)
        self._cmd    = command
        self._en     = True
        self._r      = radius
        self._font   = font or (SYS_FONT, 13, "bold")

        self._shape = _round_rect(self, 1, 1, width - 1, height - 1, radius, fill=bg, outline="")
        self._label = self.create_text(width // 2, height // 2,
                                       text=text, fill="white",
                                       font=self._font)

        self.bind("<Button-1>", lambda e: self._click())
        self.bind("<Enter>",    lambda e: self._fill(self._hov if self._en else "#555"))
        self.bind("<Leave>",    lambda e: self._fill(self._bg if self._en else "#555"))

    def _click(self):
        if self._en and self._cmd:
            self._cmd()

    def _fill(self, color):
        self.itemconfigure(self._shape, fill=color)

    def set_enabled(self, enabled: bool):
        self._en = enabled
        self._fill(self._bg if enabled else "#555555")
        self.configure(cursor="hand2" if enabled else "")

    def set_text(self, text: str):
        self.itemconfigure(self._label, text=text)

    def configure(self, **kw):
        if "text" in kw:
            self.set_text(kw.pop("text"))
        if "state" in kw:
            self.set_enabled(kw.pop("state") != "disabled")
        if kw:
            super().configure(**kw)


# ── Main App ───────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Legendar")
        self.resizable(False, False)
        self.configure(bg=C["bg"])

        # State
        self._video_path  = ""
        self._output_path = ""
        self._q: queue.Queue = queue.Queue()
        self._processing  = False
        self._stop_event  = threading.Event()

        # Tk vars
        self._video_disp  = tk.StringVar()
        self._key_var     = tk.StringVar()
        self._out_disp    = tk.StringVar()
        self._service_var = tk.StringVar(value="DeepL")
        self._src_var     = tk.StringVar(value="English")
        self._tgt_var     = tk.StringVar(value="Portuguese (Brazil)")
        self._font_size_var   = tk.StringVar(value="10")
        self._margin_var      = tk.StringVar(value="12")
        self._sub_color_var   = tk.StringVar(value="White")
        self._font_family_var = tk.StringVar(value="System Default")
        self._bold_var        = tk.StringVar(value="Normal")
        self._keep_srt_var    = tk.BooleanVar(value=False)

        # Load config
        config = load_config()
        if "api_key"    in config: self._key_var.set(config["api_key"])
        if "service"    in config: self._service_var.set(config["service"])
        if "src_lang"   in config: self._src_var.set(config["src_lang"])
        if "tgt_lang"   in config: self._tgt_var.set(config["tgt_lang"])
        if "output_dir" in config:
            self._output_path = config["output_dir"]
            self._out_disp.set(tilde_path(config["output_dir"]))
        if "sub_font_size"   in config: self._font_size_var.set(str(config["sub_font_size"]))
        if "sub_margin"      in config: self._margin_var.set(str(config["sub_margin"]))
        if "sub_color"       in config: self._sub_color_var.set(config["sub_color"])
        if "sub_font_family" in config: self._font_family_var.set(config["sub_font_family"])
        if "sub_bold"        in config: self._bold_var.set(config["sub_bold"])
        if "keep_srt"        in config: self._keep_srt_var.set(config["keep_srt"])

        saved_lang = config.get("ui_lang", "")
        self._lang = saved_lang if saved_lang in STRINGS else detect_system_lang()

        self._setup_ttk_style()
        self._build_ui()
        self._apply_strings()
        self._on_service_change()
        self.after(100, self._drain)

    # ── TTK dark style (clam theme — fully customisable) ──────────────────────
    def _setup_ttk_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".",
            background=C["bg"], foreground=C["text"],
            fieldbackground=C["surface"], bordercolor=C["sep"],
            darkcolor=C["surface"], lightcolor=C["surface"],
            troughcolor=C["bg"], selectbackground=C["accent"],
            selectforeground="white", insertcolor=C["text"],
            relief="flat",
        )
        s.configure("TFrame",    background=C["bg"])
        s.configure("TLabel",    background=C["bg"], foreground=C["text"])
        s.configure("TEntry",    fieldbackground=C["surface"], foreground=C["text"],
                                 insertcolor=C["text"], bordercolor=C["sep"],
                                 padding=(8, 5))
        s.configure("TCombobox", fieldbackground=C["surface"], foreground=C["text"],
                                 selectbackground=C["surface"],
                                 selectforeground=C["text"],
                                 arrowcolor=C["text2"], bordercolor=C["sep"],
                                 padding=(6, 5))
        s.map("TCombobox",
            fieldbackground=[("readonly", C["surface"])],
            selectbackground=[("readonly", C["surface"])],
            selectforeground=[("readonly", C["text"])],
        )
        s.configure("TButton",
            background=C["surface2"], foreground=C["text"],
            bordercolor=C["sep"], relief="flat", padding=(10, 6),
        )
        s.map("TButton", background=[("active", C["surface"])])
        s.configure("TProgressbar",
            background=C["accent"], troughcolor=C["surface"],
            borderwidth=0, thickness=6,
        )
        s.configure("Vertical.TScrollbar",
            background=C["surface2"], bordercolor=C["bg"],
            arrowcolor=C["text2"], troughcolor=C["bg"],
        )
        s.configure("TCheckbutton",
            background=C["bg"], foreground=C["text2"], focuscolor=C["bg"],
        )
        s.map("TCheckbutton",
            background=[("active", C["bg"])],
            foreground=[("active", C["text"])],
        )

    # ── Build UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        F = SYS_FONT
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=24, pady=20)

        # ── Header ─────────────────────────────────────────────────────────────
        hdr = ttk.Frame(outer)
        hdr.pack(fill="x", pady=(0, 2))

        self._lbl_title = ttk.Label(hdr, font=(F, 20, "bold"))
        self._lbl_title.pack(side="left")

        self._lang_btn = RoundedButton(hdr, text="", command=self._toggle_lang,
                                       bg=C["surface2"], width=100, height=30, radius=8)
        self._lang_btn.pack(side="right")

        self._lbl_sub = ttk.Label(outer, font=(F, 12), foreground=C["text2"])
        self._lbl_sub.pack(anchor="w", pady=(2, 16))

        # ── Video file ─────────────────────────────────────────────────────────
        self._lbl_video = ttk.Label(outer, font=(F, 12, "bold"))
        self._lbl_video.pack(anchor="w")
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(4, 14))
        ttk.Entry(row, textvariable=self._video_disp, state="readonly",
                  width=50, foreground=C["text2"]).pack(side="left", fill="x", expand=True)
        self._btn_video = RoundedButton(row, text="", command=self._pick_file,
                                        bg=C["surface2"], width=90, height=32, radius=8)
        self._btn_video.pack(side="left", padx=(8, 0))

        # ── Separator ──────────────────────────────────────────────────────────
        tk.Frame(outer, height=1, bg=C["sep"]).pack(fill="x", pady=(0, 14))

        # ── Service row ────────────────────────────────────────────────────────
        svc = ttk.Frame(outer)
        svc.pack(fill="x", pady=(0, 10))
        self._lbl_svc = ttk.Label(svc, font=(F, 12, "bold"), width=22, anchor="w")
        self._lbl_svc.pack(side="left")
        self._svc_combo = ttk.Combobox(svc, textvariable=self._service_var,
                                        values=SERVICE_OPTIONS, state="readonly", width=24)
        self._svc_combo.pack(side="left")
        self._service_var.trace_add("write", lambda *_: self._on_service_change())

        # ── API Key row ────────────────────────────────────────────────────────
        key_row = ttk.Frame(outer)
        key_row.pack(fill="x", pady=(0, 10))
        self._lbl_key = ttk.Label(key_row, font=(F, 12, "bold"), width=22, anchor="w")
        self._lbl_key.pack(side="left")
        self._key_entry = ttk.Entry(key_row, textvariable=self._key_var,
                                     show="•", width=26)
        self._key_entry.pack(side="left")
        self._key_hint = ttk.Label(key_row, font=(F, 11), foreground=C["text2"])
        self._key_hint.pack(side="left", padx=(10, 0))

        # ── Language dropdowns ─────────────────────────────────────────────────
        lang_row = ttk.Frame(outer)
        lang_row.pack(fill="x", pady=(0, 10))

        src_f = ttk.Frame(lang_row)
        src_f.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self._lbl_src = ttk.Label(src_f, font=(F, 12, "bold"))
        self._lbl_src.pack(anchor="w")
        ttk.Combobox(src_f, textvariable=self._src_var,
                     values=list(legendar.WHISPER_LANGUAGES.keys()),
                     state="readonly", width=24).pack(fill="x", pady=(4, 0))

        tgt_f = ttk.Frame(lang_row)
        tgt_f.pack(side="left", fill="x", expand=True)
        self._lbl_tgt = ttk.Label(tgt_f, font=(F, 12, "bold"))
        self._lbl_tgt.pack(anchor="w")
        self._tgt_combo = ttk.Combobox(tgt_f, textvariable=self._tgt_var,
                                        values=list(legendar.DEEPL_LANGUAGES.keys()),
                                        state="readonly", width=24)
        self._tgt_combo.pack(fill="x", pady=(4, 0))

        # ── Subtitle style ─────────────────────────────────────────────────────
        tk.Frame(outer, height=1, bg=C["sep"]).pack(fill="x", pady=(4, 10))

        self._lbl_sub_style = ttk.Label(outer, font=(F, 12, "bold"))
        self._lbl_sub_style.pack(anchor="w", pady=(0, 4))

        style_row = ttk.Frame(outer)
        style_row.pack(fill="x", pady=(0, 8))

        # Font size
        fs_f = ttk.Frame(style_row)
        fs_f.pack(side="left", padx=(0, 20))
        self._lbl_font_size = ttk.Label(fs_f, font=(F, 11), foreground=C["text2"])
        self._lbl_font_size.pack(anchor="w")
        ttk.Combobox(fs_f, textvariable=self._font_size_var,
                     values=["8", "10", "12", "14", "16", "18", "20"],
                     state="readonly", width=6).pack(pady=(2, 0))

        # Margin / position
        pos_f = ttk.Frame(style_row)
        pos_f.pack(side="left", padx=(0, 20))
        self._lbl_pos = ttk.Label(pos_f, font=(F, 11), foreground=C["text2"])
        self._lbl_pos.pack(anchor="w")
        ttk.Combobox(pos_f, textvariable=self._margin_var,
                     values=["5", "8", "12", "16", "20", "30", "40"],
                     state="readonly", width=6).pack(pady=(2, 0))

        # Color
        col_f = ttk.Frame(style_row)
        col_f.pack(side="left")
        self._lbl_sub_color = ttk.Label(col_f, font=(F, 11), foreground=C["text2"])
        self._lbl_sub_color.pack(anchor="w")
        ttk.Combobox(col_f, textvariable=self._sub_color_var,
                     values=["White", "Yellow", "Cyan", "Green"],
                     state="readonly", width=9).pack(pady=(2, 0))

        # Style row 2: Font family + Bold
        style_row2 = ttk.Frame(outer)
        style_row2.pack(fill="x", pady=(0, 4))

        ff_f = ttk.Frame(style_row2)
        ff_f.pack(side="left", padx=(0, 20))
        self._lbl_font_family = ttk.Label(ff_f, font=(F, 11), foreground=C["text2"])
        self._lbl_font_family.pack(anchor="w")
        ttk.Combobox(ff_f, textvariable=self._font_family_var,
                     values=list(legendar.FONT_FAMILIES.keys()),
                     state="readonly", width=16).pack(pady=(2, 0))

        bold_f = ttk.Frame(style_row2)
        bold_f.pack(side="left")
        self._lbl_bold = ttk.Label(bold_f, font=(F, 11), foreground=C["text2"])
        self._lbl_bold.pack(anchor="w")
        ttk.Combobox(bold_f, textvariable=self._bold_var,
                     values=list(legendar.BOLD_LEVELS.keys()),
                     state="readonly", width=9).pack(pady=(2, 0))

        self._pos_hint = ttk.Label(outer, font=(F, 10), foreground=C["text2"])
        self._pos_hint.pack(anchor="w", pady=(4, 2))

        self._keep_srt_chk = ttk.Checkbutton(outer, variable=self._keep_srt_var)
        self._keep_srt_chk.pack(anchor="w", pady=(0, 8))

        # ── Output folder ──────────────────────────────────────────────────────
        tk.Frame(outer, height=1, bg=C["sep"]).pack(fill="x", pady=(4, 14))
        self._lbl_out = ttk.Label(outer, font=(F, 12, "bold"))
        self._lbl_out.pack(anchor="w")
        out_row = ttk.Frame(outer)
        out_row.pack(fill="x", pady=(4, 18))
        ttk.Entry(out_row, textvariable=self._out_disp, state="readonly",
                  width=50, foreground=C["text2"]).pack(side="left", fill="x", expand=True)
        self._btn_out = RoundedButton(out_row, text="", command=self._pick_output,
                                      bg=C["surface2"], width=90, height=32, radius=8)
        self._btn_out.pack(side="left", padx=(8, 0))

        # ── Progress ───────────────────────────────────────────────────────────
        tk.Frame(outer, height=1, bg=C["sep"]).pack(fill="x", pady=(0, 12))

        status_row = ttk.Frame(outer)
        status_row.pack(fill="x")
        self._status = ttk.Label(status_row, font=(F, 12), foreground=C["text2"])
        self._status.pack(side="left", fill="x", expand=True)
        self._elapsed = ttk.Label(status_row, font=(F, 11), foreground=C["text2"])
        self._elapsed.pack(side="right")

        self._bar = ttk.Progressbar(outer, mode="determinate", length=580, maximum=100)
        self._bar.pack(fill="x", pady=(6, 12))

        # ── Log ────────────────────────────────────────────────────────────────
        self._log = scrolledtext.ScrolledText(
            outer, height=7, width=72, state="disabled",
            font=(SYS_FONT, 11),
            bg=C["log_bg"], fg=C["log_fg"],
            insertbackground=C["text"],
            selectbackground=C["log_sel"],
            relief="flat", borderwidth=0,
        )
        self._log.pack(fill="both", pady=(0, 16))

        # ── Buttons ────────────────────────────────────────────────────────────
        btn_row = ttk.Frame(outer)
        btn_row.pack(fill="x")

        left = ttk.Frame(btn_row)
        left.pack(side="left")

        self._open_btn = RoundedButton(left, text="", command=self._open_output,
                                       bg=C["surface2"], width=110, height=38, radius=10)
        self._open_btn.pack(side="left", padx=(0, 10))
        self._open_btn.set_enabled(False)

        self._stop_btn = RoundedButton(
            left, text="■  Stop", command=self._stop,
            bg=C["stop"], width=110, height=38,
        )
        self._stop_btn.pack(side="left")
        self._stop_btn.set_enabled(False)

        self._start_btn = RoundedButton(
            btn_row, text="▶  Start", command=self._start,
            bg=C["accent"], width=120, height=38,
        )
        self._start_btn.pack(side="right")

    # ── Strings ────────────────────────────────────────────────────────────────
    def _s(self, k): return STRINGS[self._lang].get(k, k)

    def _apply_strings(self):
        s = self._s
        self._lbl_title.configure(text=s("title"))
        self._lbl_sub.configure(text=s("subtitle"))
        self._lbl_video.configure(text=s("video"))
        self._btn_video.configure(text=s("choose"))
        self._lbl_svc.configure(text=s("service"))
        self._lbl_key.configure(text=s("key"))
        self._lbl_src.configure(text=s("src"))
        self._lbl_tgt.configure(text=s("tgt"))
        self._lbl_out.configure(text=s("output"))
        self._btn_out.configure(text=s("choose"))
        self._open_btn.configure(text=s("open"))
        self._stop_btn.set_text(s("stop"))
        self._start_btn.set_text(s("start"))
        self._lbl_sub_style.configure(text=s("sub_style"))
        self._lbl_font_size.configure(text=s("font_size"))
        self._lbl_pos.configure(text=s("pos_label"))
        self._pos_hint.configure(text=s("pos_hint"))
        self._lbl_sub_color.configure(text=s("sub_color"))
        self._lbl_font_family.configure(text=s("font_family"))
        self._lbl_bold.configure(text=s("bold_label"))
        self._keep_srt_chk.configure(text=s("keep_srt"))
        self._lang_btn.configure(text=s("lang_btn"))
        if not self._processing:
            self._status.configure(text=s("ready"), foreground=C["text2"])
        if not self._video_path:
            self._video_disp.set(s("v_hint"))
        if not self._output_path:
            self._out_disp.set(s("o_hint"))
        self._on_service_change()

    def _toggle_lang(self):
        self._lang = "pt" if self._lang == "en" else "en"
        self._apply_strings()
        cfg = load_config(); cfg["ui_lang"] = self._lang; save_config(cfg)

    # ── Service toggle ─────────────────────────────────────────────────────────
    def _on_service_change(self):
        is_deepl = self._service_var.get() == "DeepL"
        self._key_entry.configure(state="normal" if is_deepl else "disabled")
        self._key_hint.configure(
            text="" if is_deepl else self._s("key_hint")
        )
        lang_map = legendar.DEEPL_LANGUAGES if is_deepl else legendar.GOOGLE_LANGUAGES
        current = self._tgt_var.get()
        self._tgt_combo.configure(values=list(lang_map.keys()))
        if current not in lang_map:
            self._tgt_var.set("Portuguese (Brazil)")

    # ── File pickers ───────────────────────────────────────────────────────────
    def _pick_file(self):
        cfg = load_config()
        init = cfg.get("last_video_dir", os.path.expanduser("~/Movies"))
        path = filedialog.askopenfilename(
            title="Select video", initialdir=init,
            filetypes=[("Videos", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"),
                       ("All files", "*.*")],
        )
        if path:
            self._video_path = path
            self._video_disp.set(tilde_path(path))
            cfg["last_video_dir"] = os.path.dirname(path)
            save_config(cfg)

    def _pick_output(self):
        init = self._output_path or os.path.expanduser("~/Movies")
        path = filedialog.askdirectory(title="Output folder", initialdir=init)
        if path:
            self._output_path = path
            self._out_disp.set(tilde_path(path))
            cfg = load_config(); cfg["output_dir"] = path; save_config(cfg)

    def _open_output(self):
        if self._output_path:
            subprocess.run(["open", self._output_path])

    # ── Start / Stop ───────────────────────────────────────────────────────────
    def _start(self):
        video   = self._video_path
        api_key = self._key_var.get().strip()
        out_dir = self._output_path or os.path.expanduser("~/Movies/subtitled_videos")
        service = "deepl" if self._service_var.get() == "DeepL" else "google"

        if not video:
            messagebox.showwarning(self._s("warn"), self._s("no_video")); return
        if service == "deepl" and not api_key:
            messagebox.showwarning(self._s("warn"), self._s("no_key")); return

        if not self._output_path:
            self._output_path = out_dir
            self._out_disp.set(tilde_path(out_dir))

        lang_map = legendar.DEEPL_LANGUAGES if service == "deepl" else legendar.GOOGLE_LANGUAGES
        src_code = legendar.WHISPER_LANGUAGES.get(self._src_var.get())
        tgt_code = lang_map.get(self._tgt_var.get(), "PT-BR" if service == "deepl" else "pt")

        save_config({
            "api_key": api_key, "output_dir": out_dir,
            "service": self._service_var.get(),
            "src_lang": self._src_var.get(), "tgt_lang": self._tgt_var.get(),
            "ui_lang": self._lang,
            "last_video_dir": os.path.dirname(video),
            "sub_font_size":   int(self._font_size_var.get()),
            "sub_margin":      int(self._margin_var.get()),
            "sub_color":       self._sub_color_var.get(),
            "sub_font_family": self._font_family_var.get(),
            "sub_bold":        self._bold_var.get(),
            "keep_srt":        self._keep_srt_var.get(),
        })

        self._clear_log()
        self._bar.stop()
        self._bar.configure(mode="determinate", value=0)
        self._status.configure(text=self._s("starting"), foreground=C["text"])
        self._elapsed.configure(text="")
        self._start_btn.set_enabled(False)
        self._stop_btn.set_enabled(True)
        self._open_btn.configure(state="disabled")
        self._processing = True
        self._stop_event.clear()

        threading.Thread(
            target=self._worker,
            args=(video, api_key, out_dir, src_code, tgt_code, service,
                  int(self._font_size_var.get()),
                  int(self._margin_var.get()),
                  self._sub_color_var.get(),
                  self._font_family_var.get(),
                  legendar.BOLD_LEVELS.get(self._bold_var.get(), 1),
                  self._keep_srt_var.get()),
            daemon=True,
        ).start()

    def _stop(self):
        self._stop_event.set()
        self._stop_btn.set_enabled(False)
        self._status.configure(text="Stopping…", foreground=C["warn"])

    # ── Worker ─────────────────────────────────────────────────────────────────
    def _worker(self, video, api_key, out_dir, src_code, tgt_code, service,
                font_size, margin_v, sub_color, font_family, bold, keep_srt):
        def log(m):  self._q.put(("log", m))
        def prog(p, d): self._q.put(("progress", p, d))

        # Timer: shows elapsed seconds while Whisper works
        _ts = threading.Event()
        _t0 = [time.time()]

        def _timer():
            time.sleep(8)
            while not _ts.is_set():
                self._q.put(("elapsed", int(time.time() - _t0[0])))
                time.sleep(5)

        _t0[0] = time.time()
        threading.Thread(target=_timer, daemon=True).start()

        result = legendar.process_video(
            video_path=video, api_key=api_key, output_dir=out_dir,
            target_lang=tgt_code, source_lang=src_code, service=service,
            stop_event=self._stop_event,
            progress_callback=prog, log_callback=log,
            subtitle_font_size=font_size,
            subtitle_margin=margin_v,
            subtitle_color=sub_color,
            subtitle_font_family=font_family,
            subtitle_bold=bold,
            keep_srt=keep_srt,
        )
        _ts.set()
        self._q.put(("done", result))

    # ── Queue drain ────────────────────────────────────────────────────────────
    def _drain(self):
        try:
            for _ in range(40):   # cap per-cycle to keep UI responsive
                msg = self._q.get_nowait()
                try:
                    self._handle(msg)
                except Exception as e:
                    print(f"[UI] {e}")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._drain)

    def _handle(self, msg):
        k = msg[0]
        if k == "log":
            self._append(msg[1])
        elif k == "progress":
            _, pct, desc = msg
            self._status.configure(text=desc, foreground=C["text"])
            if pct < 0:
                if self._bar["mode"] != "indeterminate":
                    self._bar.configure(mode="indeterminate")
                    self._bar.start(12)
            else:
                if self._bar["mode"] == "indeterminate":
                    self._bar.stop()
                    self._bar.configure(mode="determinate")
                self._bar["value"] = pct
                self._elapsed.configure(text="")
        elif k == "elapsed":
            if self._bar["mode"] == "indeterminate":
                m, s = divmod(msg[1], 60)
                self._elapsed.configure(text=f"{m}:{s:02d}" if m else f"{s}s")
                self._status.configure(text=self._s("txing"), foreground=C["text"])
        elif k == "done":
            self._processing = False
            self._bar.stop()
            self._bar.configure(mode="determinate")
            self._start_btn.set_enabled(True)
            self._stop_btn.set_enabled(False)
            self._elapsed.configure(text="")
            if self._stop_event.is_set():
                self._bar["value"] = 0
                self._status.configure(text=self._s("stopped"), foreground=C["warn"])
            elif msg[1]:
                self._bar["value"] = 100
                self._status.configure(text=self._s("done"), foreground=C["success"])
                self._open_btn.configure(state="normal")
            else:
                self._bar["value"] = 0
                self._status.configure(text=self._s("failed"), foreground=C["error"])

    # ── Log helpers ────────────────────────────────────────────────────────────
    def _append(self, msg: str):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
