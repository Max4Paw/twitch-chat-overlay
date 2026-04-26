# -*- coding: utf-8 -*-
"""
Twitch Chat Overlay v3
----------------------
Прозрачное окно поверх всех приложений со стрим-чатом Twitch.

Возможности:
  * Анонимное чтение чата любого Twitch-канала (без OAuth-токена)
  * Поверх всех окон (always-on-top)
  * Слайдер прозрачности + режим "прозрачный фон" (chroma key, Windows)
  * Перетаскивание мышью + ресайз за края и угол
  * Сохранение истории чата
  * Иконка в системном трее и в панели задач Windows
  * Современный тёмный дизайн + красивый кастомный диалог
  * Автоматическое переподключение
  * Горячие клавиши:
        Ctrl+Alt+H  — скрыть/показать (глобально, если есть `keyboard`)
        Ctrl+Alt+Q  — выход
        Esc         — скрыть окно
        + / -       — изменить общую прозрачность

Опциональные зависимости:
    pip install keyboard pystray Pillow
"""

import os
import sys
import socket
import threading
import queue
import json
import time
import datetime
import tkinter as tk
from tkinter import ttk, font as tkfont

IS_WIN = sys.platform.startswith("win")
if IS_WIN:
    import ctypes


# ============================================================
#               Пути (учёт PyInstaller --onefile)
# ============================================================
def _resource_dir() -> str:
    """Папка, где лежат встроенные ресурсы (icon.ico/icon.png).
    В onefile-сборке PyInstaller это распакованный временный каталог."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return base
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _user_dir() -> str:
    """Папка для пользовательских файлов (config, история).
    Рядом с .exe или .py — чтобы конфиг не пропадал между запусками."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


RES_DIR  = _resource_dir()
USER_DIR = _user_dir()


# ============================================================
#                      ОБЩАЯ ПАЛИТРА
# ============================================================
PALETTE = {
    "BG":          "#0e0f1a",
    "BG_ELEV":     "#161827",
    "BG_HEADER":   "#1a1d2e",
    "BG_INPUT":    "#1e2133",
    "BORDER":      "#2a2e44",
    "TEXT":        "#e6e8ef",
    "TEXT_MUTED":  "#8b91a7",
    "TEXT_DIM":    "#5a607a",
    "ACCENT":      "#9146ff",
    "ACCENT_HOV":  "#a970ff",
    "ACCENT_DIM":  "#6e30c9",
    "DANGER":      "#ff5e7e",
    "OK":          "#5dd39e",
    "WARN":        "#ffb347",
}


# ============================================================
#                  Кастомный диалог канала
# ============================================================
class ChannelDialog(tk.Toplevel):
    """Красивый borderless-диалог для ввода имени канала Twitch."""

    def __init__(self, parent=None, initial: str = "", title: str = "Twitch"):
        super().__init__(parent)
        self.result = None
        P = PALETTE

        self.overrideredirect(True)
        self.configure(bg=P["BORDER"])
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.98)
        except Exception:
            pass

        W, H = 360, 210
        try:
            if parent and parent.winfo_viewable():
                px = parent.winfo_rootx() + parent.winfo_width() // 2
                py = parent.winfo_rooty() + parent.winfo_height() // 2
            else:
                px = self.winfo_screenwidth() // 2
                py = self.winfo_screenheight() // 2
        except Exception:
            px = self.winfo_screenwidth() // 2
            py = self.winfo_screenheight() // 2
        self.geometry(f"{W}x{H}+{px - W // 2}+{py - H // 2}")

        outer = tk.Frame(self, bg=P["BG"])
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        # ---- шапка ----
        header = tk.Frame(outer, bg=P["BG_HEADER"], height=34)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Label(
            header, text="●", bg=P["BG_HEADER"], fg=P["ACCENT"],
            font=("Segoe UI", 12, "bold"), padx=10,
        ).pack(side="left")
        title_lbl = tk.Label(
            header, text=title, bg=P["BG_HEADER"], fg=P["TEXT"],
            font=("Segoe UI Semibold", 10), anchor="w",
        )
        title_lbl.pack(side="left", fill="x", expand=True)

        close_lbl = tk.Label(
            header, text="✕", bg=P["BG_HEADER"], fg=P["TEXT_MUTED"],
            font=("Segoe UI Symbol", 11), padx=12, pady=4, cursor="hand2",
        )
        close_lbl.pack(side="right")
        close_lbl.bind("<Button-1>", lambda e: self._cancel())
        close_lbl.bind("<Enter>", lambda e: close_lbl.config(
            bg=P["BG_INPUT"], fg=P["DANGER"]))
        close_lbl.bind("<Leave>", lambda e: close_lbl.config(
            bg=P["BG_HEADER"], fg=P["TEXT_MUTED"]))

        for w in (header, title_lbl):
            w.bind("<Button-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)

        # ---- тело ----
        body = tk.Frame(outer, bg=P["BG"], padx=22, pady=18)
        body.pack(fill="both", expand=True)

        tk.Label(
            body, text="Канал Twitch",
            bg=P["BG"], fg=P["TEXT"], font=("Segoe UI Semibold", 13),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            body, text="Введите имя канала, чат которого хотите смотреть.",
            bg=P["BG"], fg=P["TEXT_MUTED"], font=("Segoe UI", 9),
            anchor="w", pady=4,
        ).pack(fill="x")

        # «скруглённое» поле через подложку
        self._input_wrap = tk.Frame(body, bg=P["BORDER"], padx=1, pady=1)
        self._input_wrap.pack(fill="x", pady=(10, 0))

        input_inner = tk.Frame(self._input_wrap, bg=P["BG_INPUT"])
        input_inner.pack(fill="x")

        tk.Label(
            input_inner, text="#", bg=P["BG_INPUT"], fg=P["ACCENT"],
            font=("Segoe UI Semibold", 13), padx=10,
        ).pack(side="left")

        self.var = tk.StringVar(value=initial)
        self.entry = tk.Entry(
            input_inner, textvariable=self.var,
            bg=P["BG_INPUT"], fg=P["TEXT"],
            insertbackground=P["ACCENT"],
            relief="flat", bd=0, font=("Segoe UI", 12),
            highlightthickness=0,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 10))
        self.entry.bind("<FocusIn>",
                        lambda e: self._input_wrap.config(bg=P["ACCENT"]))
        self.entry.bind("<FocusOut>",
                        lambda e: self._input_wrap.config(bg=P["BORDER"]))

        # ---- кнопки ----
        btns = tk.Frame(body, bg=P["BG"])
        btns.pack(fill="x", side="bottom", pady=(16, 0))

        cancel_btn = self._make_btn(
            btns, "Отмена", self._cancel,
            bg=P["BG_INPUT"], hover=P["BORDER"], fg=P["TEXT_MUTED"],
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        ok_btn = self._make_btn(
            btns, "Подключиться", self._ok,
            bg=P["ACCENT"], hover=P["ACCENT_HOV"], fg="#ffffff",
        )
        ok_btn.pack(side="right")

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<KP_Enter>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())

        self.entry.focus_set()
        self.entry.select_range(0, "end")
        try:
            self.grab_set()
        except Exception:
            pass

    def _make_btn(self, parent, text, cmd, bg, hover, fg):
        b = tk.Label(
            parent, text=text, bg=bg, fg=fg,
            font=("Segoe UI Semibold", 10),
            padx=18, pady=8, cursor="hand2",
        )
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def _start_move(self, e):
        self._mx = e.x_root - self.winfo_x()
        self._my = e.y_root - self.winfo_y()

    def _do_move(self, e):
        self.geometry(f"+{e.x_root - self._mx}+{e.y_root - self._my}")

    def _ok(self):
        val = self.var.get().strip().lstrip("#").lower()
        if not val:
            self._input_wrap.config(bg=PALETTE["DANGER"])
            self.after(700, lambda: self._input_wrap.config(bg=PALETTE["BORDER"]))
            return
        self.result = val
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _cancel(self):
        self.result = None
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


def ask_channel(parent=None, initial: str = "",
                title: str = "Twitch Chat Overlay"):
    """Показывает кастомный диалог; возвращает имя канала или None."""
    if parent is None:
        root = tk.Tk()
        root.withdraw()
        try:
            dlg = ChannelDialog(root, initial=initial, title=title)
            root.wait_window(dlg)
            return dlg.result
        finally:
            try:
                root.destroy()
            except Exception:
                pass
    else:
        dlg = ChannelDialog(parent, initial=initial, title=title)
        parent.wait_window(dlg)
        return dlg.result


# ---------------- опциональные модули ----------------
try:
    import keyboard  # type: ignore
    HAS_KEYBOARD = True
except Exception:
    HAS_KEYBOARD = False

try:
    import pystray  # type: ignore
    from PIL import Image  # type: ignore
    HAS_TRAY = True
except Exception:
    HAS_TRAY = False


# ============================================================
#                       Twitch IRC client
# ============================================================
class TwitchIRC(threading.Thread):
    HOST = "irc.chat.twitch.tv"
    PORT = 6667

    def __init__(self, channel: str, msg_queue: queue.Queue):
        super().__init__(daemon=True)
        self.channel = channel.lower().lstrip("#")
        self.queue = msg_queue
        self.sock = None
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        try:
            if self.sock:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
        except Exception:
            pass

    def _connect(self):
        nick = f"justinfan{int(time.time()) % 100000}"
        self.queue.put(("system", f"Подключаюсь к #{self.channel}..."))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(15)
        self.sock.connect((self.HOST, self.PORT))
        self.sock.sendall(b"PASS SCHMOOPIIE\r\n")
        self.sock.sendall(f"NICK {nick}\r\n".encode())
        self.sock.sendall(f"JOIN #{self.channel}\r\n".encode())
        self.sock.settimeout(None)
        self.queue.put(("status", "online"))
        self.queue.put(("system", f"✓ Подключено к #{self.channel}"))

    def run(self):
        backoff = 2
        while not self._stop.is_set():
            try:
                self._connect()
                buf = ""
                while not self._stop.is_set():
                    data = self.sock.recv(4096)
                    if not data:
                        raise ConnectionError("Соединение закрыто сервером")
                    buf += data.decode("utf-8", errors="replace")
                    while "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                        self._handle_line(line)
                backoff = 2
            except Exception as e:
                if self._stop.is_set():
                    break
                self.queue.put(("status", "offline"))
                self.queue.put(("system", f"⚠ {e}. Переподключение через {backoff} с..."))
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _handle_line(self, line: str):
        if line.startswith("PING"):
            try:
                self.sock.sendall(b"PONG :tmi.twitch.tv\r\n")
            except Exception:
                pass
            return
        if "PRIVMSG" in line:
            try:
                prefix, _, rest = line.partition(" PRIVMSG ")
                user = prefix.split("!", 1)[0].lstrip(":")
                _, _, message = rest.partition(":")
                if user and message is not None:
                    self.queue.put(("msg", (user, message)))
            except Exception:
                pass


# ============================================================
#                    Главное окно (overlay)
# ============================================================
class ChatOverlay(tk.Tk):
    APP_DIR      = USER_DIR
    CONFIG_PATH  = os.path.join(USER_DIR, "overlay_config.json")
    HISTORY_PATH = os.path.join(USER_DIR, "chat_history.txt")
    ICON_PNG     = os.path.join(RES_DIR, "icon.png")
    ICON_ICO     = os.path.join(RES_DIR, "icon.ico")

    BG          = PALETTE["BG"]
    BG_ELEV     = PALETTE["BG_ELEV"]
    BG_HEADER   = PALETTE["BG_HEADER"]
    BG_INPUT    = PALETTE["BG_INPUT"]
    BORDER      = PALETTE["BORDER"]
    TEXT        = PALETTE["TEXT"]
    TEXT_MUTED  = PALETTE["TEXT_MUTED"]
    TEXT_DIM    = PALETTE["TEXT_DIM"]
    ACCENT      = PALETTE["ACCENT"]
    ACCENT_HOV  = PALETTE["ACCENT_HOV"]
    DANGER      = PALETTE["DANGER"]
    OK          = PALETTE["OK"]
    WARN        = PALETTE["WARN"]

    NICK_COLORS = [
        "#ff7b72", "#ffa657", "#ffd93d", "#7ee787",
        "#56d4dd", "#79c0ff", "#d2a8ff", "#ff9ec1",
        "#ff8a65", "#aed581", "#80deea", "#ce93d8",
    ]

    EDGE = 6
    CHROMA = "#010102"
    APP_ID = "twitch.chat.overlay.1"

    def __init__(self, channel: str):
        super().__init__()

        self.channel = channel
        self.cfg = self._load_config()
        self.alpha = float(self.cfg.get("alpha", 0.92))
        geom = self.cfg.get("geometry", "440x560+200+150")
        self._is_topmost = True
        self._chroma_mode = bool(self.cfg.get("chroma", False))

        # ---- AppUserModelID для группировки в taskbar Windows ----
        if IS_WIN:
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    self.APP_ID
                )
            except Exception:
                pass

        # ---- настройка окна ----
        self.title(f"Twitch Chat — #{channel}")
        self.geometry(geom)
        self.configure(bg=self.BORDER)
        self.attributes("-topmost", True)
        self.attributes("-alpha", self.alpha)
        self.overrideredirect(True)
        self.minsize(280, 200)

        # иконка
        self._tk_icon = None
        try:
            if IS_WIN and os.path.exists(self.ICON_ICO):
                self.iconbitmap(default=self.ICON_ICO)
            if os.path.exists(self.ICON_PNG):
                self._tk_icon = tk.PhotoImage(file=self.ICON_PNG)
                self.iconphoto(True, self._tk_icon)
        except Exception:
            pass

        # ---- шрифты (chat-шрифт можно увеличивать) ----
        self.FONT_MIN, self.FONT_MAX = 8, 28
        self.font_size = int(self.cfg.get("font_size", 10))
        self.font_size = max(self.FONT_MIN, min(self.FONT_MAX, self.font_size))

        self.fnt        = tkfont.Font(family="Segoe UI", size=self.font_size)
        self.fnt_small  = tkfont.Font(family="Segoe UI", size=9)
        self.fnt_bold   = tkfont.Font(family="Segoe UI",
                                      size=self.font_size, weight="bold")
        self.fnt_time   = tkfont.Font(family="Segoe UI",
                                      size=max(8, self.font_size - 1))
        self.fnt_sys    = tkfont.Font(family="Segoe UI",
                                      size=max(8, self.font_size - 1),
                                      slant="italic")
        self.fnt_title  = tkfont.Font(family="Segoe UI Semibold", size=10)
        self.fnt_icon   = tkfont.Font(family="Segoe UI Symbol", size=11)

        outer = tk.Frame(self, bg=self.BG, bd=0)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        self._outer = outer

        # размеры панелей (будут показываться/скрываться по hover)
        self.HEADER_H = 36
        self.STATUS_H = 22
        self.FOOTER_H = 30

        # сначала чат — он занимает всё пространство
        self._build_chat(outer)
        # затем панели поверх него
        self._build_header(outer)
        self._build_statusbar(outer)
        self._build_footer(outer)
        self._install_edge_resizers()
        self._install_hotkeys()
        self._install_auto_hide()

        self.msg_queue = queue.Queue()
        self.irc = TwitchIRC(channel, self.msg_queue)
        self.irc.start()

        self.protocol("WM_DELETE_WINDOW", self._on_quit)
        self.after(80, self._poll_queue)

        if IS_WIN:
            self.after(60, self._force_taskbar_button)

        if self._chroma_mode:
            self.after(180, lambda: self._set_chroma(True))

        self.tray_icon = None
        self._setup_tray()

        # подсказки о недостающих модулях больше не пишутся в чат —
        # пользователь увидит их в README; в чате только сообщения от Twitch.

    # ============================================================
    #                       UI builders
    # ============================================================
    def _hover(self, widget, normal_bg, hover_bg, normal_fg=None, hover_fg=None):
        widget.bind("<Enter>", lambda e: widget.config(
            bg=hover_bg, fg=hover_fg or widget.cget("fg")))
        widget.bind("<Leave>", lambda e: widget.config(
            bg=normal_bg, fg=normal_fg or widget.cget("fg")))

    def _make_btn(self, parent, text, command, fg=None, font=None, hover_fg=None):
        fg = fg or self.TEXT_MUTED
        b = tk.Label(
            parent, text=text, bg=self.BG_HEADER, fg=fg,
            font=font or self.fnt_icon, padx=10, pady=4, cursor="hand2",
        )
        b.bind("<Button-1>", lambda e: command())
        self._hover(b, self.BG_HEADER, self.BG_INPUT, fg, hover_fg or self.TEXT)
        return b

    def _build_header(self, parent):
        self.header = tk.Frame(parent, bg=self.BG_HEADER, height=36)
        self.header.place(x=0, y=0, relwidth=1.0, height=36)
        self.header.pack_propagate(False)

        logo = tk.Label(
            self.header, text="●", bg=self.BG_HEADER, fg=self.ACCENT,
            font=("Segoe UI", 12, "bold"), padx=10,
        )
        logo.pack(side="left")

        self.title_lbl = tk.Label(
            self.header, text=f"Twitch  ·  #{self.channel}",
            bg=self.BG_HEADER, fg=self.TEXT, font=self.fnt_title, anchor="w",
        )
        self.title_lbl.pack(side="left", fill="x", expand=True)

        close_btn = self._make_btn(
            self.header, "✕", self._on_quit,
            fg=self.TEXT_MUTED, hover_fg=self.DANGER)
        close_btn.pack(side="right")

        self.pin_btn = self._make_btn(
            self.header, "📌", self._toggle_topmost,
            fg=self.ACCENT, hover_fg=self.ACCENT_HOV)
        self.pin_btn.pack(side="right")

        ch_btn = self._make_btn(
            self.header, "⟳", self._change_channel,
            fg=self.TEXT_MUTED, hover_fg=self.TEXT)
        ch_btn.pack(side="right")

        self.chroma_btn = self._make_btn(
            self.header, "◐", self._toggle_chroma,
            fg=self.TEXT_MUTED, hover_fg=self.ACCENT_HOV)
        self.chroma_btn.pack(side="right")

        # A+ / A− — размер шрифта
        font_inc = self._make_btn(
            self.header, "A+", lambda: self._change_font_size(+1),
            fg=self.TEXT_MUTED, hover_fg=self.TEXT,
            font=tkfont.Font(family="Segoe UI", size=10, weight="bold"))
        font_inc.pack(side="right")

        font_dec = self._make_btn(
            self.header, "A−", lambda: self._change_font_size(-1),
            fg=self.TEXT_MUTED, hover_fg=self.TEXT,
            font=tkfont.Font(family="Segoe UI", size=10))
        font_dec.pack(side="right")

        hide_btn = self._make_btn(
            self.header, "—", self._toggle_visible,
            fg=self.TEXT_MUTED, hover_fg=self.TEXT, font=self.fnt_bold)
        hide_btn.pack(side="right")

        for w in (self.header, self.title_lbl, logo):
            w.bind("<Button-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)
            w.bind("<Double-Button-1>", lambda e: self._toggle_topmost())

    def _build_statusbar(self, parent):
        bar = tk.Frame(parent, bg=self.BG_ELEV, height=22)
        bar.place(x=0, y=36, relwidth=1.0, height=22)
        bar.pack_propagate(False)
        self.statusbar = bar

        self.status_dot = tk.Label(
            bar, text="●", bg=self.BG_ELEV, fg=self.WARN,
            font=("Segoe UI", 10), padx=10)
        self.status_dot.pack(side="left")

        self.status_lbl = tk.Label(
            bar, text="подключение...", bg=self.BG_ELEV, fg=self.TEXT_MUTED,
            font=self.fnt_small, anchor="w")
        self.status_lbl.pack(side="left", fill="x", expand=True)

        self.count_lbl = tk.Label(
            bar, text="0 сообщений", bg=self.BG_ELEV, fg=self.TEXT_DIM,
            font=self.fnt_small, padx=10)
        self.count_lbl.pack(side="right")
        self._msg_count = 0

    def _build_chat(self, parent):
        body = tk.Frame(parent, bg=self.BG)
        body.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.body = body

        self.text = tk.Text(
            body, bg=self.BG, fg=self.TEXT,
            insertbackground=self.TEXT, font=self.fnt,
            wrap="word", bd=0, padx=12, pady=8,
            highlightthickness=0, spacing1=2, spacing3=2,
            cursor="arrow")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.config(state="disabled")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Overlay.Vertical.TScrollbar",
            background=self.BG_ELEV, troughcolor=self.BG,
            bordercolor=self.BG, arrowcolor=self.TEXT_DIM,
            lightcolor=self.BG_ELEV, darkcolor=self.BG_ELEV,
            gripcount=0, relief="flat")
        style.map("Overlay.Vertical.TScrollbar",
                  background=[("active", self.BORDER)])
        scroll = ttk.Scrollbar(
            body, command=self.text.yview,
            style="Overlay.Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        self.text.config(yscrollcommand=scroll.set)

        self.text.tag_configure("system", foreground=self.TEXT_MUTED,
                                font=self.fnt_sys,
                                spacing1=4, spacing3=4)
        self.text.tag_configure("time", foreground=self.TEXT_DIM,
                                font=self.fnt_time)
        self.text.tag_configure("colon", foreground=self.TEXT_DIM)
        self.text.tag_configure("msg", foreground=self.TEXT)
        for c in self.NICK_COLORS:
            self.text.tag_configure(f"nick_{c}", foreground=c, font=self.fnt_bold)

    def _build_footer(self, parent):
        self.footer = tk.Frame(parent, bg=self.BG_HEADER, height=30)
        self.footer.place(x=0, rely=1.0, y=-30, relwidth=1.0, height=30)
        self.footer.pack_propagate(False)

        tk.Label(
            self.footer, text="Прозрачность",
            bg=self.BG_HEADER, fg=self.TEXT_DIM,
            font=self.fnt_small, padx=10).pack(side="left")

        style = ttk.Style()
        style.configure(
            "Overlay.Horizontal.TScale",
            background=self.BG_HEADER, troughcolor=self.BG_INPUT)
        self.alpha_var = tk.DoubleVar(value=int(self.alpha * 100))
        self.alpha_scale = ttk.Scale(
            self.footer, from_=20, to=100, orient="horizontal",
            variable=self.alpha_var, command=self._on_alpha_slider,
            style="Overlay.Horizontal.TScale", length=140)
        self.alpha_scale.pack(side="left", padx=6, pady=6)

        self.alpha_lbl = tk.Label(
            self.footer, text=f"{int(self.alpha * 100)}%",
            bg=self.BG_HEADER, fg=self.TEXT_MUTED,
            font=self.fnt_small, width=5)
        self.alpha_lbl.pack(side="left")

        self.grip = tk.Label(
            self.footer, text="◢", bg=self.BG_HEADER, fg=self.TEXT_DIM,
            font=("Segoe UI", 12), cursor="size_nw_se", padx=10)
        self.grip.pack(side="right")
        self.grip.bind("<Button-1>", self._start_resize)
        self.grip.bind("<B1-Motion>", lambda e: self._do_resize(e, "se"))
        self._hover(self.grip, self.BG_HEADER, self.BG_INPUT,
                    self.TEXT_DIM, self.TEXT)

    def _install_edge_resizers(self):
        E = self.EDGE
        self.edge_r = tk.Frame(self, bg=self.BORDER, cursor="size_we", width=E)
        self.edge_r.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")
        self.edge_r.bind("<Button-1>", self._start_resize)
        self.edge_r.bind("<B1-Motion>", lambda e: self._do_resize(e, "e"))

        self.edge_b = tk.Frame(self, bg=self.BORDER, cursor="size_ns", height=E)
        self.edge_b.place(relx=0, rely=1.0, relwidth=1.0, anchor="sw")
        self.edge_b.bind("<Button-1>", self._start_resize)
        self.edge_b.bind("<B1-Motion>", lambda e: self._do_resize(e, "s"))

        self.edge_br = tk.Frame(self, bg=self.BORDER, cursor="size_nw_se",
                                width=E + 6, height=E + 6)
        self.edge_br.place(relx=1.0, rely=1.0, anchor="se")
        self.edge_br.bind("<Button-1>", self._start_resize)
        self.edge_br.bind("<B1-Motion>", lambda e: self._do_resize(e, "se"))

    def _install_hotkeys(self):
        self.bind_all("<Escape>", lambda e: self._toggle_visible())
        self.bind_all("<Control-q>", lambda e: self._on_quit())
        self.bind_all("<KeyPress>", self._on_keypress)
        # размер шрифта
        self.bind_all("<Control-equal>",
                      lambda e: self._change_font_size(+1))
        self.bind_all("<Control-plus>",
                      lambda e: self._change_font_size(+1))
        self.bind_all("<Control-KP_Add>",
                      lambda e: self._change_font_size(+1))
        self.bind_all("<Control-minus>",
                      lambda e: self._change_font_size(-1))
        self.bind_all("<Control-KP_Subtract>",
                      lambda e: self._change_font_size(-1))
        self.bind_all("<Control-0>",
                      lambda e: self._set_font_size(10))
        # Ctrl + колесо мыши
        self.bind_all("<Control-MouseWheel>", self._on_ctrl_wheel)
        # Linux версия колеса (Button-4 / Button-5)
        self.bind_all("<Control-Button-4>",
                      lambda e: self._change_font_size(+1))
        self.bind_all("<Control-Button-5>",
                      lambda e: self._change_font_size(-1))
        if HAS_KEYBOARD:
            try:
                keyboard.add_hotkey("ctrl+alt+h", self._toggle_visible_safe)
                keyboard.add_hotkey("ctrl+alt+q",
                                    lambda: self.after(0, self._on_quit))
            except Exception as e:
                self.after(500, lambda: self._log_system(
                    f"Не удалось зарегистрировать глобальные хоткеи: {e}"))

    def _on_keypress(self, e):
        # +/- меняют прозрачность только если Ctrl НЕ зажат
        if e.state & 0x4:   # Control
            return
        ch = e.char
        if ch in ("+", "="):
            self._set_alpha(self.alpha + 0.05)
        elif ch in ("-", "_"):
            self._set_alpha(self.alpha - 0.05)

    # ============================================================
    #                       размер шрифта
    # ============================================================
    def _set_font_size(self, size: int):
        size = max(self.FONT_MIN, min(self.FONT_MAX, int(size)))
        if size == self.font_size:
            return
        self.font_size = size
        # объекты Font общие у Text widget и тегов — обновятся автоматически
        try:
            self.fnt.config(size=size)
            self.fnt_bold.config(size=size)
            self.fnt_time.config(size=max(8, size - 1))
            self.fnt_sys.config(size=max(8, size - 1))
        except Exception:
            pass

    def _change_font_size(self, delta: int):
        self._set_font_size(self.font_size + delta)

    def _on_ctrl_wheel(self, e):
        delta = 1 if e.delta > 0 else -1
        self._change_font_size(delta)
        return "break"

    # ============================================================
    #          авто-скрытие шапки/статус-бара/футера
    # ============================================================
    def _install_auto_hide(self):
        self._panels_visible = True
        # bind на корневое окно
        self.bind("<Enter>", lambda e: self._set_panels_visible(True))
        self.bind("<Leave>", lambda e: self._maybe_hide_panels())
        # сразу скрываем при старте
        self.after(800, self._maybe_hide_panels)

    def _pointer_inside(self):
        try:
            x, y = self.winfo_pointerxy()
            rx, ry = self.winfo_rootx(), self.winfo_rooty()
            rw, rh = self.winfo_width(), self.winfo_height()
            return rx <= x < rx + rw and ry <= y < ry + rh
        except Exception:
            return False

    def _maybe_hide_panels(self):
        # с небольшой задержкой — чтобы не моргало при движении внутри
        def _check():
            if not self._pointer_inside():
                self._set_panels_visible(False)
        self.after(120, _check)

    def _set_panels_visible(self, visible: bool):
        if visible == self._panels_visible:
            return
        self._panels_visible = visible
        if visible:
            self.header.place(x=0, y=0, relwidth=1.0, height=self.HEADER_H)
            self.statusbar.place(x=0, y=self.HEADER_H,
                                 relwidth=1.0, height=self.STATUS_H)
            self.footer.place(x=0, rely=1.0, y=-self.FOOTER_H,
                              relwidth=1.0, height=self.FOOTER_H)
            for w in (self.header, self.statusbar, self.footer):
                try:
                    w.lift()
                except Exception:
                    pass
        else:
            for w in (self.header, self.statusbar, self.footer):
                try:
                    w.place_forget()
                except Exception:
                    pass

    def _toggle_visible_safe(self):
        self.after(0, self._toggle_visible)

    # ============================================================
    #                       config & history
    # ============================================================
    def _load_config(self):
        try:
            with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self):
        data = {
            "alpha": self.alpha,
            "geometry": self.geometry(),
            "chroma": self._chroma_mode,
            "font_size": self.font_size,
        }
        try:
            with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _save_history_line(self, line):
        try:
            with open(self.HISTORY_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    # ============================================================
    #                       move / resize
    # ============================================================
    def _start_move(self, e):
        self._mx = e.x_root - self.winfo_x()
        self._my = e.y_root - self.winfo_y()

    def _do_move(self, e):
        self.geometry(f"+{e.x_root - self._mx}+{e.y_root - self._my}")

    def _start_resize(self, e):
        self._rx, self._ry = e.x_root, e.y_root
        self._rw = self.winfo_width()
        self._rh = self.winfo_height()

    def _do_resize(self, e, mode):
        dx = e.x_root - self._rx
        dy = e.y_root - self._ry
        new_w = self._rw
        new_h = self._rh
        if "e" in mode:
            new_w = max(280, self._rw + dx)
        if "s" in mode:
            new_h = max(200, self._rh + dy)
        self.geometry(f"{new_w}x{new_h}")

    # ============================================================
    #                   прозрачность / видимость
    # ============================================================
    def _set_alpha(self, v, sync_slider=True):
        self.alpha = max(0.20, min(1.0, round(v, 2)))
        try:
            self.attributes("-alpha", self.alpha)
        except Exception:
            pass
        if sync_slider:
            try:
                self.alpha_var.set(int(self.alpha * 100))
            except Exception:
                pass
        self.alpha_lbl.config(text=f"{int(self.alpha * 100)}%")

    def _on_alpha_slider(self, val):
        try:
            self._set_alpha(float(val) / 100.0, sync_slider=False)
        except Exception:
            pass

    def _toggle_topmost(self):
        self._is_topmost = not self._is_topmost
        self.attributes("-topmost", self._is_topmost)
        self.pin_btn.config(fg=self.ACCENT if self._is_topmost else self.TEXT_DIM)
        self._log_system(f"Поверх окон: {'вкл' if self._is_topmost else 'выкл'}")

    def _toggle_visible(self):
        if self.state() == "withdrawn":
            self.deiconify()
            self.attributes("-topmost", self._is_topmost)
        else:
            self.withdraw()

    def _change_channel(self):
        new_ch = ask_channel(parent=self, initial=self.channel,
                             title="Сменить канал")
        if new_ch:
            ch = new_ch.strip().lstrip("#").lower()
            if not ch or ch == self.channel:
                return
            self.channel = ch
            self.title_lbl.config(text=f"Twitch  ·  #{ch}")
            self.title(f"Twitch Chat — #{ch}")
            try:
                self.irc.stop()
            except Exception:
                pass
            self._set_status("offline", "переподключение...")
            self.irc = TwitchIRC(ch, self.msg_queue)
            self.irc.start()
            self._update_tray_title()

    # ============================================================
    #                       вывод сообщений
    # ============================================================
    def _nick_tag(self, nick):
        idx = sum(ord(c) for c in nick) % len(self.NICK_COLORS)
        return f"nick_{self.NICK_COLORS[idx]}"

    def _append(self, segments):
        self.text.config(state="normal")
        for txt, tag in segments:
            if tag:
                self.text.insert("end", txt, tag)
            else:
                self.text.insert("end", txt)
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > 1000:
            self.text.delete("1.0", f"{line_count - 1000}.0")
        self.text.see("end")
        self.text.config(state="disabled")

    def _log_system(self, msg):
        # Системные сообщения не выводим в чат — только в файл-лог.
        # Видимая обратная связь идёт через статус-бар (_set_status).
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._save_history_line(f"[{ts}] * {msg}")

    def _log_message(self, user, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._append([
            (f" {ts}  ", "time"),
            (user, self._nick_tag(user)),
            (": ", "colon"),
            (msg.rstrip() + "\n", "msg"),
        ])
        self._save_history_line(f"[{ts}] {user}: {msg}")
        self._msg_count += 1
        self.count_lbl.config(text=f"{self._msg_count} сообщений")

    def _set_status(self, state, text=None):
        if state == "online":
            self.status_dot.config(fg=self.OK)
            self.status_lbl.config(text=text or f"подключено · #{self.channel}")
        else:
            self.status_dot.config(fg=self.DANGER)
            self.status_lbl.config(text=text or "не подключено")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "system":
                    self._log_system(payload)
                elif kind == "msg":
                    user, msg = payload
                    self._log_message(user, msg)
                elif kind == "status":
                    self._set_status(payload)
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    # ============================================================
    #              иконка в панели задач Windows
    # ============================================================
    def _get_hwnd(self):
        if not IS_WIN:
            return None
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.winfo_id())
            return hwnd or self.winfo_id()
        except Exception:
            return None

    def _force_taskbar_button(self):
        if not IS_WIN:
            return
        hwnd = self._get_hwnd()
        if not hwnd:
            return
        try:
            GWL_EXSTYLE      = -20
            WS_EX_APPWINDOW  = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            user32 = ctypes.windll.user32
            try:
                GetLong = user32.GetWindowLongPtrW
                SetLong = user32.SetWindowLongPtrW
            except AttributeError:
                GetLong = user32.GetWindowLongW
                SetLong = user32.SetWindowLongW
            ex = GetLong(hwnd, GWL_EXSTYLE)
            new_ex = (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            self.withdraw()
            SetLong(hwnd, GWL_EXSTYLE, new_ex)
            self.after(20, self._reshow)
            # после восстановления окна привяжем иконку
            self.after(60, self._set_taskbar_icon)
        except Exception:
            pass

    def _set_taskbar_icon(self):
        """Грузит icon.ico и шлёт WM_SETICON — даёт настоящую иконку
        в панели задач Windows и Alt+Tab вместо стандартной Tk-иконки."""
        if not IS_WIN or not os.path.exists(self.ICON_ICO):
            return
        hwnd = self._get_hwnd()
        if not hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            IMAGE_ICON      = 1
            LR_LOADFROMFILE = 0x00000010
            LR_DEFAULTSIZE  = 0x00000040
            WM_SETICON      = 0x0080
            ICON_SMALL      = 0
            ICON_BIG        = 1

            # сигнатуры — путь это LPCWSTR
            user32.LoadImageW.argtypes = [
                ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                ctypes.c_int, ctypes.c_int, ctypes.c_uint,
            ]
            user32.LoadImageW.restype = ctypes.c_void_p

            big = user32.LoadImageW(
                None, self.ICON_ICO, IMAGE_ICON, 32, 32, LR_LOADFROMFILE
            )
            small = user32.LoadImageW(
                None, self.ICON_ICO, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
            )
            if big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big)
            if small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small)
        except Exception:
            pass

    def _reshow(self):
        try:
            self.deiconify()
            self.attributes("-topmost", self._is_topmost)
            self.lift()
        except Exception:
            pass

    # ============================================================
    #                  режим прозрачного фона
    # ============================================================
    def _set_chroma(self, enabled):
        if not IS_WIN:
            self._log_system("Прозрачный фон поддерживается только в Windows.")
            return
        self._chroma_mode = bool(enabled)
        try:
            if enabled:
                self.attributes("-transparentcolor", self.CHROMA)
                self.configure(bg=self.CHROMA)
                self.text.config(bg=self.CHROMA)
                self.text.tag_configure("msg", foreground="#ffffff")
                self.chroma_btn.config(fg=self.ACCENT)
                self._log_system("Прозрачный фон: вкл")
            else:
                self.attributes("-transparentcolor", "")
                self.configure(bg=self.BORDER)
                self.text.config(bg=self.BG)
                self.text.tag_configure("msg", foreground=self.TEXT)
                self.chroma_btn.config(fg=self.TEXT_MUTED)
                self._log_system("Прозрачный фон: выкл")
        except Exception as e:
            self._log_system(f"Не удалось переключить прозрачный фон: {e}")

    def _toggle_chroma(self):
        self._set_chroma(not self._chroma_mode)

    # ============================================================
    #                       системный трей
    # ============================================================
    def _setup_tray(self):
        if not HAS_TRAY:
            return
        try:
            if os.path.exists(self.ICON_PNG):
                image = Image.open(self.ICON_PNG)
            else:
                image = Image.new("RGB", (64, 64), (145, 70, 255))
        except Exception:
            return

        def _ui(fn):
            return lambda *_: self.after(0, fn)

        menu = pystray.Menu(
            pystray.MenuItem("Показать / Скрыть",
                             _ui(self._toggle_visible), default=True),
            pystray.MenuItem("Поверх всех окон",
                             _ui(self._toggle_topmost),
                             checked=lambda item: self._is_topmost),
            pystray.MenuItem("Прозрачный фон",
                             _ui(self._toggle_chroma),
                             checked=lambda item: self._chroma_mode),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Сменить канал…", _ui(self._change_channel)),
            pystray.MenuItem(
                "Прозрачность",
                pystray.Menu(
                    pystray.MenuItem("100%", _ui(lambda: self._set_alpha(1.00))),
                    pystray.MenuItem("90%",  _ui(lambda: self._set_alpha(0.90))),
                    pystray.MenuItem("75%",  _ui(lambda: self._set_alpha(0.75))),
                    pystray.MenuItem("50%",  _ui(lambda: self._set_alpha(0.50))),
                    pystray.MenuItem("30%",  _ui(lambda: self._set_alpha(0.30))),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", _ui(self._on_quit)),
        )
        try:
            self.tray_icon = pystray.Icon(
                "twitch_chat_overlay", image,
                f"Twitch Chat — #{self.channel}", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            self.tray_icon = None

    def _update_tray_title(self):
        if self.tray_icon:
            try:
                self.tray_icon.title = f"Twitch Chat — #{self.channel}"
            except Exception:
                pass

    # ============================================================
    #                       выход
    # ============================================================
    def _on_quit(self):
        self._save_config()
        try:
            self.irc.stop()
        except Exception:
            pass
        if HAS_KEYBOARD:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass


# ============================================================
#                            main
# ============================================================
def main():
    if IS_WIN:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "twitch.chat.overlay.1"
            )
        except Exception:
            pass

    if len(sys.argv) > 1:
        channel = sys.argv[1].strip().lstrip("#").lower()
    else:
        channel = ask_channel(initial="")
        if not channel:
            return

    app = ChatOverlay(channel)
    app.mainloop()


if __name__ == "__main__":
    main()
