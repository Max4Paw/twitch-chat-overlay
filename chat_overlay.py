# -*- coding: utf-8 -*-
"""
Chat Overlay v4
---------------
Прозрачное окно поверх всех приложений с чатом Twitch и YouTube Live.

Возможности:
  * Twitch  — анонимное IRC (без OAuth-токена)
  * YouTube — Live-чат через pytchat (без API-ключа)
  * Поверх всех окон (always-on-top)
  * Слайдер прозрачности + режим "прозрачный фон" (chroma key, Windows)
  * Перетаскивание мышью + ресайз за края и угол
  * Подсветка упоминаний, фильтры / бан-лист
  * Открытие нескольких каналов одновременно (кнопка «+»)
  * Иконка в системном трее и в панели задач Windows
  * Автоматическое переподключение

Опциональные зависимости:
    pip install keyboard pystray Pillow pytchat
"""

import os
import re
import sys
import socket
import threading
import queue
import json
import time
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
import http.server
import socketserver
import urllib.parse
import hashlib
import webbrowser
from html import escape as html_escape
from collections import deque, Counter

IS_WIN = sys.platform.startswith("win")

APP_VERSION = "0.1.5"
APP_CHANNEL = "Stable"
GITHUB_REPO = "Max4Paw/twitch-chat-overlay"

# Известные чат-боты — скрываются галочкой «Скрывать ботов»
KNOWN_BOTS = {
    "nightbot", "streamelements", "moobot", "wizebot", "fossabot", "streamlabs",
    "soundalerts", "sery_bot", "botrixoficial", "kofistreambot", "commanderroot",
    "pokemoncommunitygame", "streamstickers", "own3d", "blerp", "lumiastream",
    "deepbot", "phantombot", "coebot", "vivbot", "ankhbot", "dixperbro",
    "tangiabot", "frostytoolsdotcom", "botisimo", "creatisbot", "wzbot",
    "stay_hydrated_bot", "streamholics", "anotherttvviewer", "pretzelrocks",
    "songlistbot", "buttsbot", "jeffbot", "mikuia", "ohbot", "revlobot",
    "scottybot", "supibot", "titlechange_bot", "markov_chain_bot", "ttdbot",
    "donationalerts_", "da_bot", "streamdps", "memealerts", "memealertsbot",
}
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
THEMES = {
    "twitch_dark": {
        "name": "Twitch Dark",
        "BG": "#0e0f1a",
        "BG_ELEV": "#161827",
        "BG_HEADER": "#1a1d2e",
        "BG_INPUT": "#1e2133",
        "BORDER": "#2a2e44",
        "TEXT": "#e6e8ef",
        "TEXT_MUTED": "#8b91a7",
        "TEXT_DIM": "#5a607a",
        "ACCENT": "#9146ff",
        "ACCENT_HOV": "#a970ff",
        "ACCENT_DIM": "#6e30c9",
        "DANGER": "#ff5e7e",
        "OK": "#5dd39e",
        "WARN": "#ffb347",
    },
    "emerald_night": {
        "name": "Emerald",
        "BG": "#0d1514",
        "BG_ELEV": "#13211f",
        "BG_HEADER": "#162825",
        "BG_INPUT": "#1a2f2b",
        "BORDER": "#27443f",
        "TEXT": "#e9f4f1",
        "TEXT_MUTED": "#9ab7b0",
        "TEXT_DIM": "#5f7f77",
        "ACCENT": "#37c996",
        "ACCENT_HOV": "#52d7a8",
        "ACCENT_DIM": "#23906d",
        "DANGER": "#ff6e7f",
        "OK": "#61d6a8",
        "WARN": "#ffc46b",
    },
    "sunset_ink": {
        "name": "Sunset Ink",
        "BG": "#151017",
        "BG_ELEV": "#211826",
        "BG_HEADER": "#2a1d31",
        "BG_INPUT": "#312239",
        "BORDER": "#4a3254",
        "TEXT": "#f4e9f7",
        "TEXT_MUTED": "#b79ec0",
        "TEXT_DIM": "#836c8b",
        "ACCENT": "#ff7a59",
        "ACCENT_HOV": "#ff946f",
        "ACCENT_DIM": "#d35e40",
        "DANGER": "#ff5d86",
        "OK": "#7be0b1",
        "WARN": "#ffca78",
    },
    "midnight": {
        "name": "Midnight",
        "BG": "#0b1020",
        "BG_ELEV": "#121a30",
        "BG_HEADER": "#16203a",
        "BG_INPUT": "#1a2644",
        "BORDER": "#2a3a60",
        "TEXT": "#e6ecff",
        "TEXT_MUTED": "#94a3c8",
        "TEXT_DIM": "#5d6a8e",
        "ACCENT": "#4f8cff",
        "ACCENT_HOV": "#76a6ff",
        "ACCENT_DIM": "#3567c9",
        "DANGER": "#ff5e7e",
        "OK": "#5dd39e",
        "WARN": "#ffb347",
    },
    "cyber_neon": {
        "name": "Cyber Neon",
        "BG": "#0a0612",
        "BG_ELEV": "#140c22",
        "BG_HEADER": "#1a0f2e",
        "BG_INPUT": "#1f1336",
        "BORDER": "#3a2163",
        "TEXT": "#f2e9ff",
        "TEXT_MUTED": "#b49ad6",
        "TEXT_DIM": "#7a6399",
        "ACCENT": "#e81cc4",
        "ACCENT_HOV": "#ff4fdb",
        "ACCENT_DIM": "#b0158f",
        "DANGER": "#ff4d6d",
        "OK": "#2bffc6",
        "WARN": "#ffd23f",
    },
    "crimson": {
        "name": "Crimson",
        "BG": "#140a0c",
        "BG_ELEV": "#1f1013",
        "BG_HEADER": "#281418",
        "BG_INPUT": "#2f181d",
        "BORDER": "#4a252c",
        "TEXT": "#f7e8ea",
        "TEXT_MUTED": "#c49aa1",
        "TEXT_DIM": "#8a6268",
        "ACCENT": "#e63950",
        "ACCENT_HOV": "#ff5c70",
        "ACCENT_DIM": "#b52a3d",
        "DANGER": "#ff7a59",
        "OK": "#6fdc9c",
        "WARN": "#ffc46b",
    },
    "ocean": {
        "name": "Deep Ocean",
        "BG": "#06141a",
        "BG_ELEV": "#0b1f27",
        "BG_HEADER": "#0e2730",
        "BG_INPUT": "#112e38",
        "BORDER": "#1d4a57",
        "TEXT": "#e3f6fa",
        "TEXT_MUTED": "#8fb9c4",
        "TEXT_DIM": "#577f8a",
        "ACCENT": "#1aa9bb",
        "ACCENT_HOV": "#2fc4d6",
        "ACCENT_DIM": "#127f8d",
        "DANGER": "#ff5e7e",
        "OK": "#5dd39e",
        "WARN": "#ffb347",
    },
    "amber": {
        "name": "Amber",
        "BG": "#14100b",
        "BG_ELEV": "#1e1810",
        "BG_HEADER": "#261e14",
        "BG_INPUT": "#2c2318",
        "BORDER": "#4a3a26",
        "TEXT": "#f5ece0",
        "TEXT_MUTED": "#c2ab8e",
        "TEXT_DIM": "#867259",
        "ACCENT": "#d98a1f",
        "ACCENT_HOV": "#eba13f",
        "ACCENT_DIM": "#a8680f",
        "DANGER": "#ff6b5e",
        "OK": "#8bd17c",
        "WARN": "#ffd36b",
    },
    "sakura": {
        "name": "Sakura",
        "BG": "#160f14",
        "BG_ELEV": "#20161d",
        "BG_HEADER": "#291b25",
        "BG_INPUT": "#2f1f2a",
        "BORDER": "#4b3043",
        "TEXT": "#fbeaf3",
        "TEXT_MUTED": "#d3a6bf",
        "TEXT_DIM": "#946b82",
        "ACCENT": "#e5568f",
        "ACCENT_HOV": "#f277a6",
        "ACCENT_DIM": "#b83c6e",
        "DANGER": "#ff5e7e",
        "OK": "#5dd39e",
        "WARN": "#ffb347",
    },
    "dracula": {
        "name": "Dracula",
        "BG": "#1e1f29",
        "BG_ELEV": "#282a36",
        "BG_HEADER": "#2d2f3d",
        "BG_INPUT": "#343746",
        "BORDER": "#44475a",
        "TEXT": "#f8f8f2",
        "TEXT_MUTED": "#bdbfd4",
        "TEXT_DIM": "#7c7f99",
        "ACCENT": "#9b6bf2",
        "ACCENT_HOV": "#b48cf7",
        "ACCENT_DIM": "#7a4ed6",
        "DANGER": "#ff5555",
        "OK": "#50fa7b",
        "WARN": "#f1fa8c",
    },
    "nord": {
        "name": "Nord",
        "BG": "#232731",
        "BG_ELEV": "#2e3440",
        "BG_HEADER": "#323846",
        "BG_INPUT": "#3b4252",
        "BORDER": "#4c566a",
        "TEXT": "#eceff4",
        "TEXT_MUTED": "#b5bdcc",
        "TEXT_DIM": "#7b8496",
        "ACCENT": "#5e81ac",
        "ACCENT_HOV": "#7096c2",
        "ACCENT_DIM": "#4a6890",
        "DANGER": "#bf616a",
        "OK": "#a3be8c",
        "WARN": "#ebcb8b",
    },
    "graphite": {
        "name": "Graphite",
        "BG": "#0f0f10",
        "BG_ELEV": "#18181a",
        "BG_HEADER": "#1d1d20",
        "BG_INPUT": "#232327",
        "BORDER": "#36363c",
        "TEXT": "#ececee",
        "TEXT_MUTED": "#a0a0a8",
        "TEXT_DIM": "#66666e",
        "ACCENT": "#6b7280",
        "ACCENT_HOV": "#868d9a",
        "ACCENT_DIM": "#4b5260",
        "DANGER": "#ff5e7e",
        "OK": "#5dd39e",
        "WARN": "#ffb347",
    },
}
PALETTE = THEMES["twitch_dark"]


# ============================================================
#                  Кастомный диалог канала
# ============================================================
class ChannelDialog(tk.Toplevel):
    """Borderless-диалог для выбора платформы (Twitch / YouTube) и канала."""

    YT_RED  = "#e62117"
    YT_HOV  = "#ff3b30"
    W, H    = 420, 344

    def __init__(self, parent=None, initial: str = "",
                 title: str = "Chat Overlay", platform: str = "twitch"):
        super().__init__(parent)
        self.result = None
        self.P = P = PALETTE
        self._title = title
        self._platform = tk.StringVar(value=platform)
        self._focused = False
        self._hover = {}

        self.overrideredirect(True)
        self.configure(bg=P["BORDER"])
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.98)
        except Exception:
            pass

        W, H = self.W, self.H
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

        # Весь диалог — один Canvas: скругления, сегменты и кнопки рисуются,
        # поверх лежит только настоящий Entry.
        self.cv = tk.Canvas(self, width=W - 2, height=H - 2, bg=P["BG"],
                            highlightthickness=0, bd=0)
        self.cv.pack(padx=1, pady=1)

        self.var = tk.StringVar(value=initial)
        self.entry = tk.Entry(
            self.cv, textvariable=self.var,
            bg=P["BG_INPUT"], fg=P["TEXT"], insertbackground=P["TEXT"],
            relief="flat", bd=0, font=("Segoe UI", 12), highlightthickness=0,
        )
        self.entry.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.var.trace_add("write", lambda *a: self._clear_error())
        self._error = ""

        self.cv.bind("<Motion>", self._on_motion)
        self.cv.bind("<Leave>", lambda e: self._on_motion(None))
        self.cv.bind("<Button-1>", self._on_click)
        self.cv.bind("<B1-Motion>", self._do_move)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<KP_Enter>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.bind("<Control-Tab>", lambda e: self._toggle_platform())

        self._draw()
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        self.after(30, self._round_corners)
        try:
            self.grab_set()
        except Exception:
            pass

    # ---------------- геометрия «кнопок» на Canvas ----------------
    def _layout(self):
        W = self.W - 2
        pad = 24
        return {
            "close":  (W - 44, 10, W - 12, 42),
            "drag":   (0, 0, W - 48, 52),
            "seg":    (pad, 74, W - pad, 114),
            "tw":     (pad + 4, 78, W // 2 - 1, 110),
            "yt":     (W // 2 + 1, 78, W - pad - 4, 110),
            "field":  (pad, 184, W - pad, 232),
            "cancel": (pad, 278, pad + 110, 320),
            "ok":     (pad + 122, 278, W - pad, 320),
        }

    @staticmethod
    def _rr(cv, x1, y1, x2, y2, r, **kw):
        r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return cv.create_polygon(pts, smooth=True, splinesteps=16, **kw)

    def _accent(self):
        return self.YT_RED if self._platform.get() == "youtube" else self.P["ACCENT"]

    def _accent_hov(self):
        return self.YT_HOV if self._platform.get() == "youtube" else self.P["ACCENT_HOV"]

    def _draw(self):
        cv, P, L = self.cv, self.P, self._layout()
        W, H = self.W - 2, self.H - 2
        is_yt = self._platform.get() == "youtube"
        acc = self._accent()
        cv.delete("all")

        # фон с лёгким цветным «свечением» сверху
        cv.create_rectangle(0, 0, W, H, fill=P["BG"], width=0)
        for i in range(10):
            a = 0.10 * (1 - i / 10)
            cv.create_oval(-60 - i * 14, -150 - i * 10, W * 0.75 + i * 14, 60 + i * 6,
                           fill=_blend_color(P["BG"], acc, a), width=0)

        # ---- шапка ----
        self._rr(cv, 20, 16, 44, 40, 7, fill=acc, outline="")
        cv.create_text(32, 28, text="▶" if is_yt else "T", fill="#ffffff",
                       font=("Segoe UI Black", 10, "bold"))
        cv.create_text(54, 28, text=self._title, anchor="w", fill=P["TEXT"],
                       font=("Segoe UI Semibold", 10))
        x1, y1, x2, y2 = L["close"]
        if self._hover.get("close"):
            self._rr(cv, x1, y1, x2, y2, 8, fill=_blend_color(P["BG"], P["DANGER"], 0.18), outline="")
        cv.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="✕",
                       fill=P["DANGER"] if self._hover.get("close") else P["TEXT_MUTED"],
                       font=("Segoe UI Symbol", 10))

        cv.create_text(24, 62, text="ПЛАТФОРМА", anchor="w", fill=P["TEXT_DIM"],
                       font=("Segoe UI Semibold", 8))

        # ---- сегмент-переключатель ----
        x1, y1, x2, y2 = L["seg"]
        self._rr(cv, x1, y1, x2, y2, 12, fill=P["BG_INPUT"], outline=P["BORDER"])
        for key, label, col in (("tw", "Twitch", P["ACCENT"]), ("yt", "YouTube", self.YT_RED)):
            sx1, sy1, sx2, sy2 = L[key]
            sel = (key == "yt") == is_yt
            if sel:
                self._rr(cv, sx1, sy1, sx2, sy2, 9, fill=col, outline="")
            elif self._hover.get(key):
                self._rr(cv, sx1, sy1, sx2, sy2, 9, fill=P["BORDER"], outline="")
            cx, cy = (sx1 + sx2) / 2, (sy1 + sy2) / 2
            tw = 7 * len(label) + 14
            # значок платформы
            ix = cx - tw / 2
            if key == "tw":
                self._rr(cv, ix - 6, cy - 6, ix + 6, cy + 6, 3,
                         fill="#ffffff" if sel else col, outline="")
                cv.create_rectangle(ix - 2, cy - 3, ix - 0.5, cy + 1,
                                    fill=col if sel else P["BG_INPUT"], width=0)
                cv.create_rectangle(ix + 1.5, cy - 3, ix + 3, cy + 1,
                                    fill=col if sel else P["BG_INPUT"], width=0)
            else:
                self._rr(cv, ix - 7, cy - 5, ix + 7, cy + 5, 3,
                         fill="#ffffff" if sel else col, outline="")
                cv.create_polygon(ix - 2, cy - 3, ix - 2, cy + 3, ix + 3, cy,
                                  fill=col if sel else P["BG_INPUT"], outline="")
            cv.create_text(ix + 14, cy, text=label, anchor="w",
                           fill="#ffffff" if sel else P["TEXT_MUTED"],
                           font=("Segoe UI Semibold", 10))

        # ---- заголовок + подсказка ----
        cv.create_text(24, 142, anchor="w", fill=P["TEXT"],
                       text="Трансляция YouTube" if is_yt else "Канал Twitch",
                       font=("Segoe UI Semibold", 15))
        cv.create_text(24, 166, anchor="w", fill=P["TEXT_MUTED"],
                       text=("Ссылка на стрим или video ID из 11 символов"
                             if is_yt else
                             "Имя канала, чат которого хотите смотреть"),
                       font=("Segoe UI", 9))

        # ---- поле ввода ----
        x1, y1, x2, y2 = L["field"]
        if self._error:
            border = P["DANGER"]
        elif self._focused:
            border = acc
        else:
            border = P["BORDER"]
        if self._focused and not self._error:
            self._rr(cv, x1 - 3, y1 - 3, x2 + 3, y2 + 3, 13,
                     fill=_blend_color(P["BG"], acc, 0.28), outline="")
        self._rr(cv, x1, y1, x2, y2, 10, fill=P["BG_INPUT"], outline=border, width=1.5)
        self._rr(cv, x1 + 8, y1 + 8, x1 + 40, y2 - 8, 7,
                 fill=_blend_color(P["BG_INPUT"], acc, 0.22), outline="")
        cv.create_text(x1 + 24, (y1 + y2) / 2, text="▶" if is_yt else "#",
                       fill=acc, font=("Segoe UI Semibold", 12))
        self.entry.config(insertbackground=acc,
                          selectbackground=_blend_color(P["BG_INPUT"], acc, 0.55),
                          selectforeground="#ffffff")
        cv.create_window(x1 + 50, (y1 + y2) / 2, window=self.entry, anchor="w",
                         width=x2 - x1 - 62, height=26)

        if self._error:
            cv.create_text(x1 + 2, y2 + 16, anchor="w", text="⚠  " + self._error,
                           fill=P["DANGER"], font=("Segoe UI", 9))
        else:
            cv.create_text(x1 + 2, y2 + 16, anchor="w", fill=P["TEXT_DIM"],
                           text="Enter — подключиться  ·  Esc — отмена  ·  Ctrl+Tab — платформа",
                           font=("Segoe UI", 8))

        # ---- кнопки ----
        x1, y1, x2, y2 = L["cancel"]
        self._rr(cv, x1, y1, x2, y2, 10,
                 fill=P["BORDER"] if self._hover.get("cancel") else P["BG_INPUT"],
                 outline=P["BORDER"])
        cv.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="Отмена",
                       fill=P["TEXT"] if self._hover.get("cancel") else P["TEXT_MUTED"],
                       font=("Segoe UI Semibold", 10))
        x1, y1, x2, y2 = L["ok"]
        self._rr(cv, x1, y1, x2, y2, 10,
                 fill=self._accent_hov() if self._hover.get("ok") else acc, outline="")
        cv.create_text((x1 + x2) / 2, (y1 + y2) / 2, text="Подключиться   →",
                       fill="#ffffff", font=("Segoe UI Semibold", 10))

    # ---------------- взаимодействие ----------------
    def _hit(self, x, y):
        L = self._layout()
        for k in ("close", "tw", "yt", "cancel", "ok"):
            x1, y1, x2, y2 = L[k]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return k
        return None

    def _on_motion(self, e):
        k = self._hit(e.x, e.y) if e is not None else None
        new = {k: True} if k else {}
        if new != self._hover:
            self._hover = new
            self.cv.config(cursor="hand2" if k else "")
            self._draw()

    def _on_click(self, e):
        k = self._hit(e.x, e.y)
        self._mx = self._my = None
        if k == "close" or k == "cancel":
            return self._cancel()
        if k == "ok":
            return self._ok()
        if k in ("tw", "yt"):
            self._platform.set("youtube" if k == "yt" else "twitch")
            self._error = ""
            self._draw()
            self.entry.focus_set()
            return
        x1, y1, x2, y2 = self._layout()["drag"]
        if y1 <= e.y <= y2:
            self._start_move(e)

    def _toggle_platform(self):
        self._platform.set("twitch" if self._platform.get() == "youtube" else "youtube")
        self._error = ""
        self._draw()
        return "break"

    def _set_focus(self, on):
        self._focused = on
        self._draw()

    def _clear_error(self):
        if self._error:
            self._error = ""
            self._draw()

    def _round_corners(self):
        """Windows 11: системные скругления углов для окна без рамки."""
        if not IS_WIN:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            pref = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass

    def _start_move(self, e):
        self._mx = e.x_root - self.winfo_x()
        self._my = e.y_root - self.winfo_y()

    def _do_move(self, e):
        if getattr(self, "_mx", None) is None:
            return
        self.geometry(f"+{e.x_root - self._mx}+{e.y_root - self._my}")

    def _ok(self):
        val = self.var.get().strip()
        plat = self._platform.get()
        if plat == "twitch":
            val = val.lstrip("#").lower()
            if "twitch.tv/" in val:
                val = val.split("twitch.tv/", 1)[1].split("/")[0].split("?")[0]
        if not val:
            self._error = ("Вставьте ссылку на стрим или video ID"
                           if plat == "youtube" else "Введите имя канала")
            self._draw()
            self.entry.focus_set()
            return
        self.result = {"channel": val, "platform": plat}
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
                title: str = "Chat Overlay",
                platform: str = "twitch"):
    """Показывает диалог выбора платформы и канала.
    Возвращает dict {"channel": str, "platform": str} или None."""
    if parent is None:
        root = tk.Tk()
        root.withdraw()
        try:
            dlg = ChannelDialog(root, initial=initial,
                                title=title, platform=platform)
            root.wait_window(dlg)
            return dlg.result
        finally:
            try:
                root.destroy()
            except Exception:
                pass
    else:
        dlg = ChannelDialog(parent, initial=initial,
                            title=title, platform=platform)
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

try:
    import pytchat  # type: ignore
    HAS_PYTCHAT = True
except Exception:
    HAS_PYTCHAT = False

# Pillow — для эмоутов Twitch (ресайз + вставка в Text)
try:
    from PIL import Image as _PILImage, ImageTk as _PILImageTk  # type: ignore
    HAS_PIL = True
except Exception:
    HAS_PIL = False


# ============================================================
#                YouTube URL / video-ID helpers
# ============================================================
_YT_URL_RE = re.compile(
    r'(?:youtube\.com/(?:watch\?v=|live/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)
_YT_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _parse_youtube_id(text: str) -> str:
    """Возвращает video ID, извлечённый из YouTube URL, или сам текст."""
    text = text.strip()
    m = _YT_URL_RE.search(text)
    if m:
        return m.group(1)
    if _YT_ID_RE.match(text):
        return text
    return text  # передаём как есть — pytchat сам разберётся


# ============================================================
#                 OBS Web overlay (local server)
# ============================================================
def _safe_int(v, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


class WebHub:
    """Простой pub/sub для SSE клиентов (без внешних зависимостей)."""

    def __init__(self, max_history: int = 250):
        self._lock = threading.Lock()
        self._clients: set[queue.Queue] = set()
        self._history = deque(maxlen=max_history)
        self._seq = 0

    def publish(self, payload: dict):
        self._seq += 1
        payload = dict(payload)
        payload["id"] = self._seq
        with self._lock:
            self._history.append(payload)
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    def broadcast(self, payload: dict):
        """Разослать событие всем клиентам, не сохраняя в историю."""
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(dict(payload))
            except Exception:
                pass

    featured = None

    def find(self, mid: str):
        with self._lock:
            for p in reversed(self._history):
                if p.get("kind") == "msg" and p.get("mid") == mid:
                    return dict(p)
        return None

    def feature(self, payload):
        """«Сообщение на экран»: payload сообщения или None — убрать."""
        self.featured = dict(payload) if payload else None
        if self.featured:
            self.featured.pop("id", None)
            self.publish({"kind": "feature", "msg": self.featured})
        else:
            self.publish({"kind": "unfeature"})

    def translate(self, mid: str, text: str):
        with self._lock:
            for p in self._history:
                if p.get("mid") == mid and p.get("kind") == "msg":
                    p["tr"] = text
        self.publish({"kind": "translate", "mid": mid, "text": text})

    def moderate(self, info: dict):
        """Удаление модерацией: чистим историю и рассылаем событие клиентам."""
        t = info.get("type")
        with self._lock:
            if t == "delete":
                mid = info.get("mid")
                keep = [p for p in self._history if p.get("mid") != mid]
            elif t == "clear_user":
                login = info.get("login")
                keep = [p for p in self._history if p.get("login") != login]
            elif t == "clear":
                keep = [p for p in self._history if p.get("kind") != "msg"]
            else:
                return
            self._history = deque(keep, maxlen=self._history.maxlen)
        f = self.featured
        if f and (t == "clear" or (t == "delete" and f.get("mid") == info.get("mid"))
                  or (t == "clear_user" and f.get("login") == info.get("login"))):
            self.feature(None)
        kind = {"delete": "delete", "clear_user": "clear_user", "clear": "clear"}[t]
        self.publish({"kind": kind, "mid": info.get("mid", ""),
                      "login": info.get("login", "")})

    def history(self) -> list[dict]:
        with self._lock:
            return list(self._history)

    def history_since(self, last_id: int) -> list[dict]:
        with self._lock:
            if not last_id:
                return list(self._history)
            return [p for p in self._history if int(p.get("id", 0)) > last_id]

    def add_client(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._clients.add(q)
        return q

    def remove_client(self, q: queue.Queue):
        with self._lock:
            self._clients.discard(q)


WEB_DIR = os.path.join(RES_DIR, "web")
OBS_STYLE_FILE = "obs_style.json"
OBS_ASSETS_DIR = "obs_assets"
_IMG_TYPES = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "image/gif": ".gif", "image/avif": ".avif",
}
_ASSET_RE = re.compile(r"^[0-9a-f]{16,40}\.(png|jpg|webp|gif|avif)$")
_MAX_UPLOAD = 15 * 1024 * 1024
_MAX_STYLE = 512 * 1024


OBS_PRESETS_FILE = "obs_presets.json"


def _json_write(path: str, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def obs_presets_load(data_dir: str) -> dict:
    try:
        with open(os.path.join(data_dir, OBS_PRESETS_FILE), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def obs_presets_save(data_dir: str, presets: dict):
    _json_write(os.path.join(data_dir, OBS_PRESETS_FILE), presets)


def obs_style_write(data_dir: str, style: dict):
    _json_write(os.path.join(data_dir, OBS_STYLE_FILE), style)


def _web_file(name: str) -> bytes:
    """Файлы веб-страниц (web/). Читаем при каждом запросе —
    правки HTML/JS видны после F5 без перезапуска программы."""
    with open(os.path.join(WEB_DIR, name), "rb") as f:
        return f.read()


_OBS_DOCK_HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Twitch Chat Overlay Dock</title>
  <style>
    :root { color-scheme: dark; }
    html, body { height: 100%; margin: 0; }
    body {
      background: #0e0f1a;
      font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
      color: #e6e8ef;
    }
    header {
      height: 44px;
      display: flex;
      align-items: center;
      padding: 0 12px;
      gap: 10px;
      background: #1a1d2e;
      border-bottom: 1px solid #2a2e44;
    }
    .dot { color: #9146ff; font-weight: 900; }
    .title { font-weight: 700; }
    .muted { color: #8b91a7; font-size: 12px; }
    #chat {
      height: calc(100% - 44px);
      padding: 10px 12px;
      box-sizing: border-box;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .line { display: flex; gap: 8px; align-items: baseline; cursor: pointer; border-radius: 6px; padding: 2px 6px; margin: 0 -6px; }
    .line:hover, .ev:hover { background: rgba(145,70,255,.12); }
    .line.featured, .ev.featured { background: rgba(145,70,255,.22); box-shadow: inset 3px 0 0 #9146ff; }
    .ev { cursor: pointer; }
    #unfeat { margin-left: auto; display: none; background: #9146ff; color: #fff; border: 0; border-radius: 6px; padding: 6px 10px; font: 600 12px "Segoe UI", sans-serif; cursor: pointer; }
    #unfeat.on { display: block; }
    #hint { color: #5a607a; font-size: 11px; padding: 6px 12px 0; }
    .t { color: #5a607a; font-size: 12px; min-width: 48px; }
    .u { font-weight: 700; }
    .c { color: #5a607a; }
    .m { color: #e6e8ef; word-break: break-word; }
    .m img.emo { height: 1.5em; vertical-align: -0.35em; margin: 0 1px; }
    .ev { color: #f5c518; font-weight: 700; font-size: 12px; padding: 4px 8px; border-left: 3px solid #f5c518; background: rgba(245,197,24,.08); border-radius: 4px; }
  </style>
</head>
<body>
  <header>
    <div class="dot">●</div>
    <div>
      <div class="title">Twitch Chat Overlay</div>
      <div class="muted" id="sub">dock</div>
    </div>
    <button id="unfeat" title="Убрать сообщение с экрана OBS">📺 Убрать с экрана</button>
  </header>
  <div id="hint">Клик по сообщению — показать его на экране (источник /obs/featured)</div>
  <div id="chat" aria-live="polite" style="height: calc(100% - 64px)"></div>
  <script>
    const chat = document.getElementById("chat");
    const sub = document.getElementById("sub");
    const MAX = 400;
    const colors = ["#ff7b72","#ffa657","#ffd93d","#7ee787","#56d4dd","#79c0ff","#d2a8ff","#ff9ec1","#ff8a65","#aed581","#80deea","#ce93d8"];
    function nickColor(nick) {
      let s = 0;
      for (let i = 0; i < nick.length; i++) s = (s + nick.charCodeAt(i)) >>> 0;
      return colors[s % colors.length];
    }
    function emoteUrl(id) {
      const enc = encodeURIComponent;
      if (id.startsWith("7tv:")) return "https://cdn.7tv.app/emote/" + enc(id.slice(4)) + "/2x.webp";
      if (id.startsWith("bttv:")) return "https://cdn.betterttv.net/emote/" + enc(id.slice(5)) + "/2x";
      if (id.startsWith("ffz:")) return "https://cdn.frankerfacez.com/emote/" + enc(id.slice(4)) + "/2";
      return "https://static-cdn.jtvnw.net/emoticons/v2/" + enc(id) + "/default/dark/2.0";
    }
    // Рендер текста с эмоутами (Twitch / 7TV / BTTV / FFZ).
    // emotes = [[start, end, id], ...], позиции в кодовых точках Unicode.
    function renderMsg(el, msg, emotes) {
      el.textContent = "";
      if (!Array.isArray(emotes) || !emotes.length) { el.textContent = msg; return; }
      const cps = Array.from(msg);
      const parts = emotes.slice().sort((x, y) => x[0] - y[0]);
      let pos = 0;
      for (const e of parts) {
        const a = Number(e[0]), b = Number(e[1]), id = String(e[2] || "");
        if (!id || a < pos || a > b || b >= cps.length) continue;
        if (a > pos) el.appendChild(document.createTextNode(cps.slice(pos, a).join("")));
        const img = document.createElement("img");
        img.className = "emo";
        img.alt = img.title = cps.slice(a, b + 1).join("");
        img.src = emoteUrl(id);
        img.onerror = () => { img.replaceWith(document.createTextNode(img.alt)); };
        el.appendChild(img);
        pos = b + 1;
      }
      if (pos < cps.length) el.appendChild(document.createTextNode(cps.slice(pos).join("")));
    }
    function addLine(p) {
      if (!p || p.kind !== "msg") return;
      const [user, msg, ts] = [p.user || "", p.msg || "", p.ts || ""];
      const line = document.createElement("div");
      line.className = "line";
      if (p.mid) line.dataset.mid = p.mid;
      line.dataset.login = (p.login || user).toLowerCase();
      if (p.event) {
        const ev = document.createElement("div");
        ev.className = "ev";
        ev.textContent = "◆ " + (p.event.text || "");
        chat.appendChild(ev);
        if (p.mid) ev.dataset.mid = p.mid;
        ev.onclick = () => feature(p.mid);
        if (!msg.trim()) { chat.scrollTop = chat.scrollHeight; return; }
      }
      const t = document.createElement("div"); t.className = "t"; t.textContent = ts ? ts : "";
      const u = document.createElement("div"); u.className = "u"; u.textContent = user; u.style.color = nickColor(user);
      const c = document.createElement("div"); c.className = "c"; c.textContent = ":";
      const m = document.createElement("div"); m.className = "m"; renderMsg(m, msg, p.emotes);
      line.append(t,u,c,m);
      if (p.tr) {
        const tr = document.createElement("div"); tr.className = "tr";
        tr.style.cssText = "flex-basis:100%;color:#8b91a7;font-style:italic;font-size:12px;padding-left:56px";
        tr.textContent = "↳ " + p.tr; line.style.flexWrap = "wrap"; line.appendChild(tr);
      }
      line.title = "Показать на экране";
      line.onclick = () => feature(p.mid);
      chat.appendChild(line);
      while (chat.children.length > MAX) chat.removeChild(chat.firstChild);
      chat.scrollTop = chat.scrollHeight;
    }
    async function loadHistory() {
      try {
        const r = await fetch("/obs/history.json", { cache: "no-store" });
        if (!r.ok) return;
        const data = await r.json();
        (data || []).forEach(addLine);
        chat.scrollTop = chat.scrollHeight;
      } catch {}
    }
    const unfeat = document.getElementById("unfeat");
    function feature(mid) {
      if (!mid) return;
      fetch("/obs/feature", { method: "POST", headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ mid }) }).catch(() => {});
    }
    unfeat.onclick = () => fetch("/obs/feature", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clear: true }) }).catch(() => {});
    function markFeatured(mid) {
      chat.querySelectorAll(".featured").forEach((n) => n.classList.remove("featured"));
      if (mid) chat.querySelectorAll("[data-mid]").forEach((n) => { if (n.dataset.mid === mid) n.classList.add("featured"); });
      unfeat.classList.toggle("on", !!mid);
    }
    fetch("/obs/featured.json").then((r) => r.json()).then((d) => markFeatured(d && d.msg && d.msg.mid)).catch(() => {});
    sub.textContent = "dock · подключение…";
    let lastId = 0;
    function trackId(p) { if (p && p.id) lastId = Math.max(lastId, Number(p.id) || 0); }
    function handlePayload(p) {
      if (!p) return;
      trackId(p);
      if (p.kind === "msg") {
        addLine(p);
      } else if (p.kind === "delete") {
        chat.querySelectorAll(".line").forEach((n) => { if (n.dataset.mid === p.mid) n.remove(); });
      } else if (p.kind === "clear_user") {
        chat.querySelectorAll(".line").forEach((n) => { if (n.dataset.login === p.login) n.remove(); });
      } else if (p.kind === "clear") {
        chat.textContent = "";
      } else if (p.kind === "translate") {
        chat.querySelectorAll(".line").forEach((n) => {
          if (n.dataset.mid === p.mid && !n.querySelector(".tr")) {
            const t = document.createElement("div"); t.className = "tr";
            t.style.cssText = "flex-basis:100%;color:#8b91a7;font-style:italic;font-size:12px;padding-left:56px";
            t.textContent = "↳ " + p.text; n.style.flexWrap = "wrap"; n.appendChild(t);
          }
        });
      } else if (p.kind === "feature") {
        markFeatured(p.msg && p.msg.mid);
      } else if (p.kind === "unfeature") {
        markFeatured(null);
      } else if (p.kind === "status") {
        const st = p.state === "online" ? "подключено" : "не подключено";
        const ch = p.channel ? (" · #" + p.channel) : "";
        sub.textContent = "dock · " + st + ch;
      }
    }
    async function poll() {
      sub.textContent = "dock · polling…";
      try {
        const r = await fetch("/obs/history.json?since=" + encodeURIComponent(String(lastId)), { cache: "no-store" });
        if (r.ok) {
          const data = await r.json();
          (data || []).forEach(handlePayload);
        }
      } catch {}
      setTimeout(poll, 1000);
    }
    function connectSseOrPoll() {
      if (typeof EventSource === "undefined") return poll();
      const es = new EventSource("/obs/events");
      let opened = false;
      es.onopen = () => { opened = true; sub.textContent = "dock · подключено"; };
      es.onmessage = (e) => { try { handlePayload(JSON.parse(e.data)); } catch {} };
      es.onerror = () => {
        try { es.close(); } catch {}
        if (!opened) return poll();
        setTimeout(connectSseOrPoll, 1500);
      };
    }
    loadHistory().then(connectSseOrPoll);
  </script>
</body>
</html>
"""


class _ObsHandler(http.server.BaseHTTPRequestHandler):
    server_version = "TwitchOverlayOBS/1.0"

    def log_message(self, format, *args):
        # не шумим в stdout
        return

    def _send(self, code: int, content_type: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------- helpers ----------
    def _json(self, code: int, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        return self._send(code, "application/json; charset=utf-8", body)

    def _data_dir(self) -> str:
        return getattr(self.server, "data_dir", USER_DIR)

    def _style_path(self) -> str:
        return os.path.join(self._data_dir(), OBS_STYLE_FILE)

    def _assets_dir(self) -> str:
        return os.path.join(self._data_dir(), OBS_ASSETS_DIR)

    def _same_origin(self) -> bool:
        """Защита от записи с чужих сайтов: POST принимаем только со страниц
        самого сервера (127.0.0.1 / localhost) или без Origin."""
        origin = self.headers.get("Origin")
        if not origin or origin == "null":
            return True
        try:
            host = urllib.parse.urlparse(origin).hostname or ""
        except Exception:
            return False
        return host in ("127.0.0.1", "localhost")

    def _read_body(self, limit: int):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if n <= 0 or n > limit:
            return None
        return self.rfile.read(n)

    def _serve_web(self, name: str, ctype: str):
        try:
            return self._send(200, ctype, _web_file(name))
        except Exception:
            return self._send(500, "text/plain; charset=utf-8",
                              f"web/{name} not found".encode("utf-8"))

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        hub: WebHub = self.server.hub  # type: ignore[attr-defined]
        if not self._same_origin():
            return self._json(403, {"error": "forbidden"})

        if path == "/obs/style":
            raw = self._read_body(_MAX_STYLE)
            if raw is None:
                return self._json(413, {"error": "bad size"})
            try:
                style = json.loads(raw.decode("utf-8"))
                if not isinstance(style, dict):
                    raise ValueError
            except Exception:
                return self._json(400, {"error": "bad json"})
            try:
                obs_style_write(self._data_dir(), style)
            except Exception as e:
                return self._json(500, {"error": str(e)})
            hub.broadcast({"kind": "style"})
            return self._json(200, {"ok": True})

        if path == "/obs/feature":
            raw = self._read_body(64 * 1024)
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                body = {}
            if body.get("clear"):
                hub.feature(None)
                return self._json(200, {"ok": True})
            if body.get("demo"):
                hub.feature({
                    "kind": "msg", "user": "ChatOverlay", "login": "chatoverlay",
                    "mid": "demo", "color": "#a970ff", "badges": ["broadcaster"],
                    "platform": "twitch", "emotes": [],
                    "msg": "Так выглядит «сообщение на экран» — кликни сообщение в Dock",
                    "ts": datetime.datetime.now().strftime("%H:%M:%S"),
                })
                return self._json(200, {"ok": True})
            p = hub.find(str(body.get("mid", "")))
            if not p:
                return self._json(404, {"error": "сообщение не найдено"})
            hub.feature(p)
            return self._json(200, {"ok": True})

        if path in ("/obs/goal", "/obs/recent"):
            raw = self._read_body(64 * 1024)
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                return self._json(400, {"error": "bad json"})
            st: StreamState = self.server.state  # type: ignore[attr-defined]
            if path == "/obs/goal":
                st.set_goal(body if isinstance(body, dict) else {})
                hub.broadcast({"kind": "goal"})
                return self._json(200, st.goal)
            if body.get("reset"):
                st.reset_recent()
            elif body.get("demo"):
                for ev, who in (({"type": "sub", "text": "DemoUser оформил подписку", "amount": 1}, "DemoUser"),
                                ({"type": "raid", "text": "Рейд! RaidFriend и 25 зрителей", "amount": 25}, "RaidFriend"),
                                ({"type": "cheer", "text": "BitsFan отправил 500 битс", "amount": 500}, "BitsFan")):
                    st.record(ev, who)
                hub.broadcast({"kind": "goal"})
            hub.broadcast({"kind": "recent"})
            return self._json(200, st.recent)

        if path == "/obs/presets":
            raw = self._read_body(_MAX_STYLE * 4)
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                return self._json(400, {"error": "bad json"})
            act = body.get("action")
            name = str(body.get("name", "")).strip()[:60]
            presets = obs_presets_load(self._data_dir())
            try:
                if act == "save" and name and isinstance(body.get("style"), dict):
                    presets[name] = body["style"]
                    obs_presets_save(self._data_dir(), presets)
                elif act == "delete" and name in presets:
                    presets.pop(name)
                    obs_presets_save(self._data_dir(), presets)
                elif act == "apply" and name in presets:
                    obs_style_write(self._data_dir(), presets[name])
                    hub.broadcast({"kind": "style"})
                else:
                    return self._json(400, {"error": "bad request"})
            except Exception as e:
                return self._json(500, {"error": str(e)})
            return self._json(200, {"ok": True, "presets": sorted(presets.keys())})

        if path == "/obs/upload":
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            ext = _IMG_TYPES.get(ctype)
            if not ext:
                return self._json(415, {"error": "Поддерживаются PNG, JPG, WEBP, GIF, AVIF"})
            raw = self._read_body(_MAX_UPLOAD)
            if raw is None:
                return self._json(413, {"error": "Файл пустой или больше 15 МБ"})
            name = hashlib.sha1(raw).hexdigest()[:20] + ext
            try:
                os.makedirs(self._assets_dir(), exist_ok=True)
                fp = os.path.join(self._assets_dir(), name)
                if not os.path.exists(fp):
                    with open(fp, "wb") as f:
                        f.write(raw)
            except Exception as e:
                return self._json(500, {"error": str(e)})
            return self._json(200, {"url": f"/obs/assets/{name}"})

        if path == "/obs/test":
            hub.publish({
                "kind": "msg", "user": "ChatOverlay", "color": "#a970ff",
                "badges": ["broadcaster"], "platform": "twitch",
                "msg": "Тестовое сообщение — так чат выглядит в OBS Kappa",
                "emotes": [[42, 46, "25"]],
                "ts": datetime.datetime.now().strftime("%H:%M:%S"),
            })
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "not found"})

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        hub: WebHub = self.server.hub  # type: ignore[attr-defined]

        if path in ("/", "/obs", "/obs/"):
            body = b"OK"
            return self._send(200, "text/plain; charset=utf-8", body)

        if path in ("/obs/browser", "/obs/browser.html"):
            return self._serve_web("browser.html", "text/html; charset=utf-8")

        if path in ("/obs/editor", "/obs/editor.html"):
            return self._serve_web("editor.html", "text/html; charset=utf-8")

        if path in ("/obs/featured", "/obs/featured.html"):
            return self._serve_web("featured.html", "text/html; charset=utf-8")

        if path == "/obs/featured.json":
            return self._json(200, {"msg": hub.featured})

        if path == "/da/callback":
            params = {k: v[0] for k, v in urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query).items()}
            da = _DA_INSTANCE
            redirect = f"http://127.0.0.1:{self.server.server_address[1]}/da/callback"
            if da is None:
                ok, text = False, "Программа не готова — попробуйте ещё раз"
            else:
                ok, text = da.handle_callback(params, redirect)
            color = "#5dd39e" if ok else "#ff5e7e"
            html = ("<!doctype html><meta charset=utf-8><title>DonationAlerts</title>"
                    "<body style='background:#0e0f1a;color:#e6e8ef;font:16px Segoe UI,sans-serif;"
                    "display:grid;place-items:center;height:100vh;margin:0'><div style='text-align:center'>"
                    f"<div style='font-size:42px;color:{color}'>{'✓' if ok else '✗'}</div>"
                    f"<h2>{html_escape(text)}</h2><p style='color:#8b91a7'>Это окно можно закрыть.</p></div>")
            return self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

        if path in ("/obs/goal", "/obs/goal.html"):
            return self._serve_web("goal.html", "text/html; charset=utf-8")

        if path in ("/obs/recent", "/obs/recent.html"):
            return self._serve_web("recent.html", "text/html; charset=utf-8")

        if path == "/obs/goal.json":
            return self._json(200, self.server.state.goal)  # type: ignore[attr-defined]

        if path == "/obs/recent.json":
            return self._json(200, self.server.state.recent)  # type: ignore[attr-defined]

        if path == "/obs/presets.json":
            return self._json(200, obs_presets_load(self._data_dir()))

        if path == "/obs/overlay.js":
            return self._serve_web("overlay.js", "application/javascript; charset=utf-8")

        if path == "/obs/style.json":
            try:
                with open(self._style_path(), "rb") as f:
                    body = f.read()
                json.loads(body.decode("utf-8"))
            except Exception:
                body = b"{}"
            return self._send(200, "application/json; charset=utf-8", body)

        if path.startswith("/obs/assets/"):
            name = path.rsplit("/", 1)[-1]
            if not _ASSET_RE.match(name):
                return self._send(404, "text/plain; charset=utf-8", b"Not found")
            try:
                with open(os.path.join(self._assets_dir(), name), "rb") as f:
                    body = f.read()
            except Exception:
                return self._send(404, "text/plain; charset=utf-8", b"Not found")
            ext = "." + name.rsplit(".", 1)[-1]
            ctype = next((k for k, v in _IMG_TYPES.items() if v == ext), "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ("/obs/dock", "/obs/dock.html"):
            return self._send(200, "text/html; charset=utf-8", _OBS_DOCK_HTML.encode("utf-8"))

        if path == "/obs/history.json":
            q = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(q)
            since = 0
            try:
                since = int((params.get("since") or ["0"])[0])
            except Exception:
                since = 0
            body = json.dumps(hub.history_since(since), ensure_ascii=False).encode("utf-8")
            return self._send(200, "application/json; charset=utf-8", body)

        if path == "/obs/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            q = hub.add_client()
            try:
                # ping сразу, чтобы OBS не считал поток "мертвым"
                self.wfile.write(b": hello\n\n")
                self.wfile.flush()
                while True:
                    try:
                        payload = q.get(timeout=15)
                        data = json.dumps(payload, ensure_ascii=False)
                        msg = f"data: {data}\n\n".encode("utf-8")
                        self.wfile.write(msg)
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except Exception:
                pass
            finally:
                hub.remove_client(q)
            return

        return self._send(404, "text/plain; charset=utf-8", b"Not found")


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


# ============================================================
#     Цель стрима и лента последних событий (для OBS)
# ============================================================
class StreamState:
    """Хранит цель стрима (obs_goal.json) и последние события
    (obs_recent.json) — переживают перезапуск программы."""

    GOAL_DEFAULT = {"title": "Цель стрима", "type": "subs", "target": 10,
                    "current": 0, "color": "#a970ff"}

    def __init__(self, data_dir: str):
        self.dir = data_dir
        self._lock = threading.Lock()
        self.goal = dict(self.GOAL_DEFAULT)
        self.goal.update(self._load("obs_goal.json"))
        self.recent = {"last": {}, "top_cheer": None, "list": []}
        self.recent.update(self._load("obs_recent.json"))

    def _load(self, name: str) -> dict:
        try:
            with open(os.path.join(self.dir, name), encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save(self):
        try:
            _json_write(os.path.join(self.dir, "obs_goal.json"), self.goal)
            _json_write(os.path.join(self.dir, "obs_recent.json"), self.recent)
        except Exception:
            pass

    def set_goal(self, data: dict):
        with self._lock:
            g = self.goal
            if "title" in data:
                g["title"] = str(data["title"])[:80]
            if data.get("type") in ("subs", "bits", "donations"):
                g["type"] = data["type"]
            for k in ("target", "current"):
                if k in data:
                    g[k] = max(0, _safe_int(data[k], g[k]))
            g["target"] = max(1, g["target"])
            if isinstance(data.get("color"), str) and re.match(r"^#[0-9a-fA-F]{6}$", data["color"]):
                g["color"] = data["color"]
            self._save()

    def reset_recent(self):
        with self._lock:
            self.recent = {"last": {}, "top_cheer": None, "top_donation": None, "list": []}
            self._save()

    def record(self, ev: dict, user: str) -> set:
        """Учесть событие. Возвращает {'goal','recent'} — что изменилось."""
        et = ev.get("type")
        amount = _safe_int(ev.get("amount", 0), 0)
        changed = set()
        with self._lock:
            g = self.goal
            if (g["type"] == "subs" and et in ("sub", "gift")) or \
               (g["type"] == "bits" and et == "cheer") or \
               (g["type"] == "donations" and et == "donation"):
                g["current"] += max(1, amount) if et in ("sub", "gift") else amount
                changed.add("goal")
            if et in ("sub", "gift", "raid", "cheer", "donation"):
                item = {"type": et, "name": user, "text": ev.get("text", ""),
                        "amount": amount,
                        "ts": datetime.datetime.now().strftime("%H:%M")}
                self.recent["last"][et] = item
                self.recent["list"] = ([item] + self.recent.get("list", []))[:10]
                if et == "cheer":
                    top = self.recent.get("top_cheer")
                    if not top or amount > top.get("amount", 0):
                        self.recent["top_cheer"] = {"name": user, "amount": amount}
                if et == "donation":
                    top = self.recent.get("top_donation")
                    if not top or amount > top.get("amount", 0):
                        self.recent["top_donation"] = {"name": user, "amount": amount,
                                                       "currency": ev.get("currency", "")}
                    item["currency"] = ev.get("currency", "")
                changed.add("recent")
            if changed:
                self._save()
        return changed


class ObsWebServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 17655,
                 data_dir: str = USER_DIR):
        self.host = host
        self.port = int(port)
        self.data_dir = data_dir
        self.hub = WebHub()
        self.state = StreamState(data_dir)
        self._httpd = None
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        httpd = _ThreadingHTTPServer((self.host, self.port), _ObsHandler)
        httpd.hub = self.hub  # type: ignore[attr-defined]
        httpd.data_dir = self.data_dir  # type: ignore[attr-defined]
        httpd.state = self.state  # type: ignore[attr-defined]
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread.start()

    def record_event(self, ev: dict, user: str):
        for kind in self.state.record(ev, user):
            self.hub.broadcast({"kind": kind})

    def stop(self):
        try:
            if self._httpd:
                self._httpd.shutdown()
                self._httpd.server_close()
        except Exception:
            pass

    def urls(self) -> dict:
        base = f"http://{self.host}:{self.port}"
        return {
            "dock": f"{base}/obs/dock",
            "browser": f"{base}/obs/browser",
            "editor": f"{base}/obs/editor",
            "featured": f"{base}/obs/featured",
            "goal": f"{base}/obs/goal",
            "recent": f"{base}/obs/recent",
        }


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
        self.sock.sendall(b"CAP REQ :twitch.tv/tags twitch.tv/commands\r\n")
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

    @staticmethod
    def _parse_emotes(tag_val: str) -> list:
        """Разбирает IRCv3-тег emotes ('id:0-4,6-10/id2:12-16')
        в отсортированный список (start, end, emote_id)."""
        out = []
        if not tag_val:
            return out
        try:
            for grp in tag_val.split("/"):
                eid, _, positions = grp.partition(":")
                if not eid or not positions:
                    continue
                for p in positions.split(","):
                    a, _, b = p.partition("-")
                    out.append((int(a), int(b), eid))
            out.sort()
        except Exception:
            return []
        return out

    @staticmethod
    def _unescape(v: str) -> str:
        """Снимает экранирование значений IRCv3-тегов."""
        out, i = [], 0
        while i < len(v):
            c = v[i]
            if c == "\\" and i + 1 < len(v):
                n = v[i + 1]
                out.append({"s": " ", ":": ";", "\\": "\\", "r": "\r", "n": "\n"}.get(n, n))
                i += 2
                continue
            out.append(c)
            i += 1
        return "".join(out)

    @staticmethod
    def _sub_tier(plan: str) -> str:
        return {"Prime": "Prime", "1000": "", "2000": " (уровень 2)",
                "3000": " (уровень 3)"}.get(plan or "", "")

    def _event_text(self, mid: str, tags: dict, name: str):
        """(тип события, текст по-русски) по msg-id USERNOTICE."""
        p = lambda k: self._unescape(tags.get(f"msg-param-{k}", ""))
        if mid == "sub":
            tier = self._sub_tier(p("sub-plan"))
            if tier == "Prime":
                return "sub", f"{name} подписался с Prime"
            return "sub", f"{name} оформил подписку{tier}"
        if mid == "resub":
            months = p("cumulative-months") or p("months")
            tier = self._sub_tier(p("sub-plan"))
            tier = " с Prime" if tier == "Prime" else tier
            return "sub", f"{name} продлил подписку{tier} — {months} мес."
        if mid in ("subgift", "anonsubgift"):
            who = name if mid == "subgift" else "Аноним"
            return "gift", f"{who} дарит подписку {p('recipient-display-name')}"
        if mid in ("submysterygift", "anonsubmysterygift"):
            who = name if mid == "submysterygift" else "Аноним"
            cnt = p("mass-gift-count") or "?"
            return "gift", f"{who} дарит чату подписки: {cnt} шт."
        if mid in ("giftpaidupgrade", "anongiftpaidupgrade", "primepaidupgrade"):
            return "sub", f"{name} продолжает подписку"
        if mid == "raid":
            who = p("displayName") or name
            return "raid", f"Рейд! {who} и {p('viewerCount') or '?'} зрителей"
        if mid == "announcement":
            return "announcement", "Объявление"
        if mid == "bitsbadgetier":
            return "cheer", f"{name} получил значок за {p('threshold')} битс"
        sysmsg = self._unescape(tags.get("system-msg", ""))
        return "other", sysmsg or mid

    def _user_extra(self, tags: dict, login: str) -> dict:
        return {
            "color": tags.get("color", ""),
            "badges": [b.split("/", 1)[0]
                       for b in tags.get("badges", "").split(",") if b],
            "id": tags.get("id", ""),
            "login": (tags.get("login") or login or "").lower(),
            "first": tags.get("first-msg") == "1",
        }

    @staticmethod
    def _display(tags: dict, login: str) -> str:
        display = TwitchIRC._unescape(tags.get("display-name", "")).strip()
        if display and display.lower() == (login or "").lower():
            return display
        return login or display

    def _handle_line(self, line: str):
        # IRCv3-теги (@key=value;...) перед основной частью строки
        tags = {}
        if line.startswith("@"):
            raw_tags, _, line = line.partition(" ")
            for part in raw_tags[1:].split(";"):
                k, _, v = part.partition("=")
                tags[k] = v
        if line.startswith("PING"):
            try:
                self.sock.sendall(b"PONG :tmi.twitch.tv\r\n")
            except Exception:
                pass
            return
        try:
            prefix, _, rest = line.partition(" ")
            cmd, _, rest = rest.partition(" ")
        except Exception:
            return

        if cmd == "PRIVMSG":
            try:
                login = prefix.split("!", 1)[0].lstrip(":")
                _, _, message = rest.partition(":")
                # /me: '\x01ACTION текст\x01' — позиции эмоутов
                # считаются по внутреннему тексту
                if message.startswith("\x01ACTION "):
                    message = message[8:].rstrip("\x01")
                emotes = self._parse_emotes(tags.get("emotes", ""))
                user = self._display(tags, login)
                extra = self._user_extra(tags, login)
                bits = tags.get("bits", "")
                if bits:
                    extra["event"] = {"type": "cheer", "amount": _safe_int(bits, 0),
                                      "text": f"{user} отправил {bits} битс"}
                if user and message is not None:
                    self.queue.put(("msg", (user, message, emotes, extra)))
            except Exception:
                pass

        elif cmd == "USERNOTICE":
            try:
                mid = tags.get("msg-id", "")
                # подарки из «массовой раздачи» приходят по одному —
                # показываем только общее событие submysterygift
                if mid in ("subgift", "anonsubgift") and tags.get(
                        "msg-param-community-gift-id"):
                    return
                login = tags.get("login", "")
                user = self._display(tags, login)
                _, _, message = rest.partition(" :")
                etype, etext = self._event_text(mid, tags, user)
                extra = self._user_extra(tags, login)
                if etype == "sub":
                    amount = 1
                elif etype == "gift":
                    amount = _safe_int(tags.get("msg-param-mass-gift-count", "1"), 1)
                elif etype == "raid":
                    amount = _safe_int(tags.get("msg-param-viewerCount", "0"), 0)
                else:
                    amount = 0
                extra["event"] = {"type": etype, "text": etext, "amount": amount}
                emotes = self._parse_emotes(tags.get("emotes", "")) if message else []
                self.queue.put(("event", (user, message or "", emotes, extra)))
            except Exception:
                pass

        elif cmd == "CLEARMSG":
            mid = tags.get("target-msg-id", "")
            if mid:
                self.queue.put(("mod", {"type": "delete", "mid": mid,
                                        "login": tags.get("login", "").lower()}))

        elif cmd == "CLEARCHAT":
            # 'CLEARCHAT #chan :login' — бан/таймаут; без ника — /clear
            _, _, target = rest.partition(" :")
            target = target.strip().lower()
            if target:
                self.queue.put(("mod", {"type": "clear_user", "login": target}))
            else:
                self.queue.put(("mod", {"type": "clear"}))

        elif cmd == "ROOMSTATE":
            rid = tags.get("room-id", "")
            if rid:
                self.queue.put(("room", rid))


# ============================================================
#        Сторонние эмоуты: 7TV, BetterTTV, FrankerFaceZ
# ============================================================
class ThirdPartyEmotes:
    """Загружает глобальные и канальные эмоуты 7TV / BTTV / FFZ
    (без авторизации) и находит их в тексте сообщений.
    Эмоут = (start, end, eid), где eid вида '7tv:ID', 'bttv:ID', 'ffz:ID'."""

    UA = {"User-Agent": "Mozilla/5.0 ChatOverlay"}

    def __init__(self):
        self._global: dict = {}           # code -> eid
        self._rooms: dict = {}            # room_id -> {code: eid}
        self._loading: set = set()
        self._lock = threading.Lock()
        self._global_loaded = False

    # ---------- загрузка ----------
    def _get_json(self, url: str):
        import urllib.request
        try:
            req = urllib.request.Request(url, headers=self.UA)
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            return None

    @staticmethod
    def _seventv(emotes) -> dict:
        out = {}
        for e in emotes or []:
            try:
                out[e["name"]] = "7tv:" + str(e["id"])
            except Exception:
                pass
        return out

    @staticmethod
    def _bttv(emotes, prefix="bttv") -> dict:
        out = {}
        for e in emotes or []:
            try:
                out[e["code"]] = f"{prefix}:{e['id']}"
            except Exception:
                pass
        return out

    def _load_global(self):
        m = {}
        # приоритет: 7TV > BTTV > FFZ (последний update выигрывает)
        d = self._get_json("https://api.betterttv.net/3/cached/frankerfacez/emotes/global")
        m.update(self._bttv(d if isinstance(d, list) else [], "ffz"))
        d = self._get_json("https://api.betterttv.net/3/cached/emotes/global")
        m.update(self._bttv(d if isinstance(d, list) else []))
        d = self._get_json("https://7tv.io/v3/emote-sets/global")
        m.update(self._seventv((d or {}).get("emotes") if isinstance(d, dict) else []))
        with self._lock:
            self._global = m
            self._global_loaded = True

    def _load_room(self, room_id: str):
        m = {}
        d = self._get_json(f"https://api.betterttv.net/3/cached/frankerfacez/users/twitch/{room_id}")
        m.update(self._bttv(d if isinstance(d, list) else [], "ffz"))
        d = self._get_json(f"https://api.betterttv.net/3/cached/users/twitch/{room_id}")
        if isinstance(d, dict):
            m.update(self._bttv(d.get("sharedEmotes")))
            m.update(self._bttv(d.get("channelEmotes")))
        d = self._get_json(f"https://7tv.io/v3/users/twitch/{room_id}")
        if isinstance(d, dict):
            m.update(self._seventv(((d.get("emote_set") or {}).get("emotes"))))
        with self._lock:
            self._rooms[room_id] = m
            self._loading.discard(room_id)

    def load_room(self, room_id: str, force: bool = False):
        """Фоновая загрузка (глобальные — один раз, канальные — на канал)."""
        if not room_id:
            return
        with self._lock:
            if room_id in self._loading or (room_id in self._rooms and not force):
                return
            self._loading.add(room_id)
            need_global = not self._global_loaded

        def _work():
            if need_global:
                self._load_global()
            self._load_room(room_id)

        threading.Thread(target=_work, daemon=True).start()

    def counts(self, room_id: str) -> tuple:
        with self._lock:
            return len(self._global), len(self._rooms.get(room_id, {}))

    # ---------- поиск в тексте ----------
    def find(self, msg: str, twitch_emotes, room_id: str = "") -> list:
        """Добавляет к Twitch-эмоутам найденные сторонние; возвращает
        отсортированный список (start, end, eid) в кодовых точках."""
        with self._lock:
            room = self._rooms.get(room_id, {}) if room_id else {}
            glob = self._global
        base = [tuple(e) for e in (twitch_emotes or [])]
        if not room and not glob:
            return base
        taken = [(a, b) for a, b, _ in base]
        out = list(base)
        for m in re.finditer(r"\S+", msg or ""):
            a, b = m.start(), m.end() - 1
            if any(not (b < x or a > y) for x, y in taken):
                continue
            eid = room.get(m.group()) or glob.get(m.group())
            if eid:
                out.append((a, b, eid))
        out.sort()
        return out


def emote_url(eid: str) -> str:
    """CDN-ссылка на эмоут (для окна и OBS)."""
    if eid.startswith("7tv:"):
        return f"https://cdn.7tv.app/emote/{eid[4:]}/2x.webp"
    if eid.startswith("bttv:"):
        return f"https://cdn.betterttv.net/emote/{eid[5:]}/2x"
    if eid.startswith("ffz:"):
        return f"https://cdn.frankerfacez.com/emote/{eid[4:]}/2"
    return f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/2.0"


# ============================================================
#           Кэш эмоутов Twitch (загрузка с CDN)
# ============================================================
class EmoteCache:
    """Скачивает эмоуты Twitch (статичный PNG) и кэширует их
    в памяти и на диске. PhotoImage создаются только в main-thread."""

    CDN = "https://static-cdn.jtvnw.net/emoticons/v2/{eid}/{fmt}/dark/2.0"

    def __init__(self, notify_q: queue.Queue):
        self._dir = os.path.join(USER_DIR, "emote_cache")
        self._mem: dict = {}        # eid -> PIL.Image (RGBA)
        self._photos: dict = {}     # (eid, h) -> ImageTk.PhotoImage
        self._failed: set = set()
        self._pending: set = set()
        self._lock = threading.Lock()
        self._dl_q: queue.Queue = queue.Queue()
        self._notify_q = notify_q   # ("emote_ready", eid) при завершении
        self._worker = None
        try:
            os.makedirs(self._dir, exist_ok=True)
        except Exception:
            pass

    @staticmethod
    def available() -> bool:
        return HAS_PIL

    def _path(self, eid: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_\-]", "_", eid)
        return os.path.join(self._dir, f"{safe}.png")

    def _load_disk(self, eid: str):
        try:
            p = self._path(eid)
            if not os.path.exists(p):
                return None
            img = _PILImage.open(p).convert("RGBA")
            with self._lock:
                self._mem[eid] = img
                if len(self._mem) > 400:
                    self._mem.pop(next(iter(self._mem)))
            return img
        except Exception:
            return None

    def get_photo(self, eid: str, height: int):
        """PhotoImage нужной высоты, если эмоут уже загружен.
        Иначе None (и загрузка стартует в фоне)."""
        if not HAS_PIL or eid in self._failed:
            return None
        key = (eid, height)
        ph = self._photos.get(key)
        if ph is not None:
            return ph
        with self._lock:
            img = self._mem.get(eid)
        if img is None:
            img = self._load_disk(eid)
        if img is None:
            self._schedule(eid)
            return None
        try:
            w = max(1, round(img.width * height / img.height))
            resample = getattr(_PILImage, "LANCZOS",
                               getattr(_PILImage, "BICUBIC", 3))
            ph = _PILImageTk.PhotoImage(img.resize((w, height), resample))
        except Exception:
            self._failed.add(eid)
            return None
        # Ссылки держим постоянно: Text-виджет не хранит свои
        # ссылки на изображения, без ссылки картинка исчезнет.
        self._photos[key] = ph
        return ph

    def _schedule(self, eid: str):
        with self._lock:
            if eid in self._pending or eid in self._failed:
                return
            self._pending.add(eid)
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._dl_loop, daemon=True)
            self._worker.start()
        self._dl_q.put(eid)

    def _dl_loop(self):
        import urllib.request
        while True:
            eid = self._dl_q.get()
            ok = False
            if eid.startswith("7tv:"):
                base = f"https://cdn.7tv.app/emote/{eid[4:]}/2x"
                urls = [base + ".png", base + ".webp", base + ".gif"]
            elif ":" in eid:
                urls = [emote_url(eid)]
            else:
                urls = [self.CDN.format(eid=urllib.parse.quote(eid), fmt=fmt)
                        for fmt in ("static", "default")]
            for url in urls:
                try:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        data = r.read()
                    tmp = self._path(eid) + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, self._path(eid))
                    ok = True
                    break
                except Exception:
                    continue
            with self._lock:
                self._pending.discard(eid)
                if not ok:
                    self._failed.add(eid)
            if ok:
                self._load_disk(eid)
            # уведомляем в любом случае — чтобы очистить плейсхолдеры
            try:
                self._notify_q.put(("emote_ready", eid))
            except Exception:
                pass


# ============================================================
#   YouTube Live Chat — прямые HTTP-запросы (без pytchat)
#   Использует те же внутренние эндпоинты, что и браузер YouTube.
# ============================================================

def _yt_walk(obj, depth: int = 0):
    """Генератор: обходит вложенный dict/list, отдаёт каждый dict."""
    if depth > 30:
        return
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _yt_walk(v, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            yield from _yt_walk(item, depth + 1)


def _yt_find_cont(obj):
    """Находит первый continuation-токен в ytInitialData / API-ответе."""
    for node in _yt_walk(obj):
        for key in ("invalidationContinuationData",
                    "timedContinuationData",
                    "reloadContinuationData",
                    "liveChatReplayContinuationData"):
            tok = node.get(key, {}).get("continuation", "")
            if len(tok) > 20:
                tms = node[key].get("timeoutMs", 2000)
                return tok, int(tms)
    return None, 2000


class _YTDirectChat:
    """
    Читает YouTube Live Chat через HTTP-запросы к внутреннему API YouTube.
    Работает без pytchat, без API-ключа, только stdlib.
    """

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    _FALLBACK_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
    _FALLBACK_VER = "2.20240417.01.00"

    def __init__(self, video_id: str):
        self.video_id = video_id
        self._cont    = None
        self._key     = self._FALLBACK_KEY
        self._ver     = self._FALLBACK_VER
        self._timeout = 2.0
        self._alive   = False

    # ------------------------------------------------------------------ #
    def _fetch(self, url: str, data: bytes = None, extra_headers: dict = None):
        import urllib.request as ur
        hdrs = {
            "User-Agent":      self._UA,
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if extra_headers:
            hdrs.update(extra_headers)
        req = ur.Request(url, data=data, headers=hdrs)
        with ur.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")

    # ------------------------------------------------------------------ #
    def init(self):
        """Загружает страницу видео и извлекает первый continuation-токен."""
        html = self._fetch(
            f"https://www.youtube.com/watch?v={self.video_id}"
        )

        # API-ключ и версия клиента из страницы
        m = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
        if m:
            self._key = m.group(1)
        m = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"', html)
        if m:
            self._ver = m.group(1)

        # Пробуем распарсить ytInitialData целиком (счётчик скобок)
        m = re.search(r"(?:var\s+)?ytInitialData\s*=\s*(\{)", html)
        if m:
            start = m.start(1)
            depth, in_str, esc, end = 0, False, False, -1
            for i, ch in enumerate(html[start:], start):
                if esc:
                    esc = False; continue
                if ch == '\\' and in_str:
                    esc = True; continue
                if ch == '"':
                    in_str = not in_str; continue
                if in_str:
                    continue
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1; break
            if end > start:
                try:
                    yd = json.loads(html[start:end])
                    tok, tms = _yt_find_cont(yd)
                    if tok:
                        self._cont    = tok
                        self._timeout = max(0.5, tms / 1000.0)
                        self._alive   = True
                        return
                except Exception:
                    pass

        # Резервный regex прямо по HTML
        for pat in (
            r'"invalidationContinuationData"\s*:\s*\{"continuation"\s*:\s*"([^"]{30,})"',
            r'"timedContinuationData"\s*:\s*\{"continuation"\s*:\s*"([^"]{30,})"',
            r'"reloadContinuationData"\s*:\s*\{"continuation"\s*:\s*"([^"]{30,})"',
        ):
            m = re.search(pat, html)
            if m:
                self._cont  = m.group(1)
                self._alive = True
                return

        # Диагностика: есть ли признаки что стрим вообще существует
        if ('"isLiveContent":true' not in html
                and '"isLive":true' not in html
                and 'liveChatRenderer' not in html):
            raise ValueError(
                "Видео не найдено или трансляция ещё не началась"
            )
        raise ValueError(
            "Не удалось получить токен чата — трансляция запланирована, "
            "попробуйте ещё раз когда она начнётся"
        )

    # ------------------------------------------------------------------ #
    def poll(self):
        """Возвращает список (author, message), обновляет continuation."""
        if not self._cont:
            return []

        payload = json.dumps({
            "context": {
                "client": {
                    "clientName":    "WEB",
                    "clientVersion": self._ver,
                    "hl": "ru",
                    "gl": "RU",
                },
            },
            "continuation": self._cont,
        }).encode("utf-8")

        raw = self._fetch(
            f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat"
            f"?key={self._key}",
            data=payload,
            extra_headers={
                "Content-Type":              "application/json",
                "X-Youtube-Client-Name":     "1",
                "X-Youtube-Client-Version":  self._ver,
                "Referer": (
                    f"https://www.youtube.com/watch?v={self.video_id}"
                ),
                "Origin":  "https://www.youtube.com",
            },
        )
        data = json.loads(raw)

        lcc = (data.get("continuationContents", {})
                   .get("liveChatContinuation", {}))

        # Сообщения
        msgs = []
        for action in lcc.get("actions", []):
            item = action.get("addChatItemAction", {}).get("item", {})
            renderer = (
                item.get("liveChatTextMessageRenderer")
                or item.get("liveChatPaidMessageRenderer")
                or item.get("liveChatMembershipItemRenderer")
            )
            if not renderer:
                continue
            author = renderer.get("authorName", {}).get("simpleText", "")
            runs = (
                renderer.get("message",            {}).get("runs", [])
                or renderer.get("headerPrimaryText", {}).get("runs", [])
                or renderer.get("headerSubtext",     {}).get("runs", [])
            )
            text = "".join(
                r.get("text", "") or r.get("emoji", {}).get("emojiId", "")
                for r in runs
            ).strip()
            if author and text:
                msgs.append((author, text))

        # Следующий continuation
        tok, tms = _yt_find_cont(lcc)
        if tok:
            self._cont    = tok
            self._timeout = max(0.5, tms / 1000.0)
            self._alive   = True
        else:
            self._alive = False  # стрим завершён

        return msgs

    def is_alive(self):  return self._alive
    def get_timeout(self): return self._timeout
    def terminate(self):   self._alive = False


# ============================================================
#                    YouTube Live Chat thread
# ============================================================
class YouTubeChat(threading.Thread):
    WAIT_RETRY = 15  # сек между попытками подключения

    def __init__(self, video_id: str, msg_queue: queue.Queue):
        super().__init__(daemon=True)
        self.video_id = _parse_youtube_id(video_id)
        self.queue    = msg_queue
        self._stop    = threading.Event()
        self._reader: _YTDirectChat | None = None

    def stop(self):
        self._stop.set()
        try:
            if self._reader:
                self._reader.terminate()
        except Exception:
            pass

    def _sleep(self, seconds: float):
        """Прерываемый sleep — реагирует на _stop."""
        end = time.time() + seconds
        while not self._stop.is_set() and time.time() < end:
            time.sleep(0.1)

    def run(self):
        self.queue.put(("system",
            f"Подключаюсь к YouTube ({self.video_id})..."))

        # ── фаза ожидания: ждём пока трансляция станет доступна ──
        while not self._stop.is_set():
            reader = _YTDirectChat(self.video_id)
            try:
                reader.init()
                self._reader = reader
                break               # успешно подключились
            except Exception as e:
                if self._stop.is_set():
                    return
                self.queue.put(("system",
                    f"⚠ {e} — повтор через {self.WAIT_RETRY} с..."))
                self._sleep(self.WAIT_RETRY)

        if self._stop.is_set():
            return

        self.queue.put(("status", "online"))
        self.queue.put(("system", f"✓ YouTube · {self.video_id}"))

        # ── фаза опроса: без внешнего реконекта ──
        err_streak = 0
        while not self._stop.is_set():
            timeout = self._reader.get_timeout()
            try:
                msgs = self._reader.poll()
                for author, text in msgs:
                    if self._stop.is_set():
                        break
                    err_streak = 0
                    self.queue.put(("msg", (author, text)))
                if not self._reader.is_alive() and not self._stop.is_set():
                    self.queue.put(("status", "offline"))
                    self.queue.put(("system", "Стрим завершён"))
                    return
            except Exception as e:
                if self._stop.is_set():
                    break
                err_streak += 1
                self.queue.put(("system", f"⚠ {e}"))
                if err_streak >= 5:
                    self.queue.put(("status", "offline"))
                    self.queue.put(("system", "Соединение потеряно"))
                    return
                timeout = 5.0

            self._sleep(timeout)


# ============================================================
#           Вспомогательные функции цвета
# ============================================================
def _blend_color(bg: str, fg: str, alpha: float) -> str:
    """Смешивает fg над bg при заданной непрозрачности (0–1)."""
    def _p(h):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    br, bg_, bb = _p(bg)
    fr, fg_, fb = _p(fg)
    r = max(0, min(255, int(br + (fr - br) * alpha)))
    g = max(0, min(255, int(bg_ + (fg_ - bg_) * alpha)))
    b = max(0, min(255, int(bb + (fb - bb) * alpha)))
    return f"#{r:02x}{g:02x}{b:02x}"


# Стили подложки сообщений (key → отображаемое имя)
MSG_STYLES: dict[str, str] = {
    "none":   "Без подложки",
    "card":   "Карточки",
    "stripe": "Полосы",
    "glow":   "Свечение",
    "pill":   "Пилюли",
}


# ============================================================
#   _TaggedQueue — обёртка над queue.Queue.
#   Позволяет нескольким читателям слать в одну очередь,
#   автоматически добавляя к каждому сообщению тег источника.
# ============================================================
class _TaggedQueue:
    def __init__(self, real_q: queue.Queue, tag: str):
        self._q   = real_q
        self._tag = tag

    def put(self, item):
        kind, val = item
        if kind in ("msg", "status", "system", "event", "mod", "room"):
            self._q.put((kind, (self._tag, val)))
        else:
            self._q.put(item)


# ============================================================
#                 DonationAlerts (официальный API)
# ============================================================
class DonationAlerts:
    """Интеграция с DonationAlerts через официальный OAuth API.
    Пользователь создаёт своё приложение на donationalerts.com
    (Client ID + Client secret), программа авторизуется через браузер
    (redirect на локальный сервер) и раз в несколько секунд опрашивает
    список донатов. Новые донаты → очередь UI: ("donation", dict)."""

    AUTH = "https://www.donationalerts.com/oauth/authorize"
    TOKEN = "https://www.donationalerts.com/oauth/token"
    API = "https://www.donationalerts.com/api/v1"
    SCOPE = "oauth-user-show oauth-donation-index"
    POLL = 6.0
    FILE = "donationalerts.json"

    def __init__(self, data_dir: str, notify_q: queue.Queue):
        self.path = os.path.join(data_dir, self.FILE)
        self._notify = notify_q
        self._lock = threading.Lock()
        self.cfg = {"client_id": "", "client_secret": "", "access_token": "",
                    "refresh_token": "", "expires_at": 0, "user": ""}
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.cfg.update(d)
        except Exception:
            pass
        self._state = ""
        self._seen: set = set()
        self._primed = False
        self._thread = None
        self._stop = threading.Event()
        self.status = "off"          # off | on | error
        self.status_text = "не подключено"

    # ---------- хранение ----------
    def _save(self):
        with self._lock:
            try:
                _json_write(self.path, self.cfg)
            except Exception:
                pass

    @property
    def connected(self) -> bool:
        return bool(self.cfg.get("access_token"))

    def set_app(self, client_id: str, client_secret: str):
        client_id, client_secret = client_id.strip(), client_secret.strip()
        if (client_id, client_secret) != (self.cfg.get("client_id"), self.cfg.get("client_secret")):
            self.cfg.update({"client_id": client_id, "client_secret": client_secret})
            self._save()

    # ---------- HTTP ----------
    @staticmethod
    def _request(url: str, data: dict = None, token: str = ""):
        import urllib.request
        headers = {"User-Agent": "ChatOverlay", "Accept": "application/json"}
        body = None
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def _set_status(self, status: str, text: str):
        if (status, text) != (self.status, self.status_text):
            self.status, self.status_text = status, text
            self._notify.put(("da_status", (status, text)))

    # ---------- OAuth ----------
    def auth_url(self, redirect_uri: str) -> str:
        import secrets
        self._state = secrets.token_urlsafe(16)
        q = urllib.parse.urlencode({
            "client_id": self.cfg["client_id"], "redirect_uri": redirect_uri,
            "response_type": "code", "scope": self.SCOPE, "state": self._state})
        return f"{self.AUTH}?{q}"

    def _store_tokens(self, tok: dict):
        self.cfg["access_token"] = tok.get("access_token", "")
        if tok.get("refresh_token"):
            self.cfg["refresh_token"] = tok["refresh_token"]
        self.cfg["expires_at"] = time.time() + _safe_int(tok.get("expires_in", 0), 0) - 60
        self._save()

    def handle_callback(self, params: dict, redirect_uri: str):
        """Вызывается HTTP-сервером на /da/callback. → (ok, текст)."""
        if params.get("error"):
            return False, f"DonationAlerts вернул ошибку: {params.get('error')}"
        if not self._state or params.get("state") != self._state:
            return False, "Неверный state — начните подключение заново из программы"
        try:
            tok = self._request(self.TOKEN, {
                "grant_type": "authorization_code",
                "client_id": self.cfg["client_id"],
                "client_secret": self.cfg["client_secret"],
                "redirect_uri": redirect_uri, "code": params.get("code", "")})
            if not tok.get("access_token"):
                raise RuntimeError(str(tok)[:200])
            self._store_tokens(tok)
            self._state = ""
            self._load_user()
            self.start()
            return True, f"Подключено: {self.cfg.get('user') or 'аккаунт DonationAlerts'}"
        except Exception as e:
            self._set_status("error", f"ошибка авторизации: {e}")
            return False, f"Не удалось получить токен: {e}"

    def _refresh(self) -> bool:
        if not self.cfg.get("refresh_token"):
            return False
        try:
            tok = self._request(self.TOKEN, {
                "grant_type": "refresh_token", "refresh_token": self.cfg["refresh_token"],
                "client_id": self.cfg["client_id"], "client_secret": self.cfg["client_secret"],
                "scope": self.SCOPE})
            if tok.get("access_token"):
                self._store_tokens(tok)
                return True
        except Exception:
            pass
        return False

    def _load_user(self):
        try:
            d = self._request(f"{self.API}/user/oauth", token=self.cfg["access_token"])
            self.cfg["user"] = ((d or {}).get("data") or {}).get("name", "") or self.cfg.get("user", "")
            self._save()
        except Exception:
            pass

    def disconnect(self):
        self.stop()
        self.cfg.update({"access_token": "", "refresh_token": "", "expires_at": 0, "user": ""})
        self._save()
        self._set_status("off", "не подключено")

    # ---------- опрос донатов ----------
    def start(self):
        if not self.connected:
            self._set_status("off", "не подключено")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._primed = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _fetch(self):
        import urllib.error
        if self.cfg.get("expires_at") and time.time() > self.cfg["expires_at"]:
            self._refresh()
        try:
            return self._request(f"{self.API}/alerts/donations", token=self.cfg["access_token"])
        except urllib.error.HTTPError as e:
            if e.code == 401 and self._refresh():
                return self._request(f"{self.API}/alerts/donations", token=self.cfg["access_token"])
            raise

    def _loop(self):
        while not self._stop.is_set():
            try:
                d = self._fetch()
                items = (d or {}).get("data") or []
                fresh = []
                for it in items:
                    did = it.get("id")
                    if did is None or did in self._seen:
                        continue
                    self._seen.add(did)
                    if self._primed:
                        fresh.append(it)
                self._primed = True
                for it in reversed(fresh):          # от старых к новым
                    self._notify.put(("donation", it))
                user = self.cfg.get("user") or "аккаунт"
                self._set_status("on", f"подключено: {user}")
            except Exception as e:
                self._set_status("error", f"ошибка: {e}"[:120])
            self._stop.wait(self.POLL)


_DA_INSTANCE = None     # для HTTP-обработчика /da/callback


# ============================================================
#        Перевод сообщений и проверка обновлений
# ============================================================
class Translator:
    """Перевод сообщений без ключа: Google Translate (основной),
    MyMemory (запасной). Работает в фоне, результат — в очередь UI:
    ("translated", (mid, text, lang)); ошибки — ("translate_error", msg)."""

    GOOGLE = ("https://translate.googleapis.com/translate_a/single"
              "?client=gtx&sl=auto&tl={tl}&dt=t&q={q}")
    GOOGLE2 = ("https://clients5.google.com/translate_a/t"
               "?client=dict-chrome-ex&sl=auto&tl={tl}&q={q}")
    MYMEMORY = "https://api.mymemory.translated.net/get?q={q}&langpair={sl}|{tl}&mt=1"

    def __init__(self, notify_q: queue.Queue):
        self._q: queue.Queue = queue.Queue(maxsize=30)
        self._notify = notify_q
        self._cache: dict = {}
        self._worker = None
        self.last_error = ""
        self._err_reported = 0.0
        self._log_path = os.path.join(USER_DIR, "translate_debug.log")
        self._cooldown: dict = {}          # провайдер -> time до которого не трогаем (429)

    def log(self, text: str):
        """Подробный журнал переводчика (translate_debug.log рядом с программой)."""
        try:
            if os.path.exists(self._log_path) and os.path.getsize(self._log_path) > 300_000:
                os.replace(self._log_path, self._log_path + ".old")
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(datetime.datetime.now().strftime("[%H:%M:%S] ") + text + "\n")
        except Exception:
            pass

    # ---------- провайдеры ----------
    @staticmethod
    def _get(url: str):
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json,text/plain,*/*"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    def _google(self, text: str, target: str):
        url = self.GOOGLE.format(tl=target, q=urllib.parse.quote(text))
        data = self._get(url)
        self.log(f"Google raw: {json.dumps(data, ensure_ascii=False)[:300]}")
        tr = "".join(seg[0] for seg in (data[0] or []) if seg and seg[0])
        lang = data[2] if len(data) > 2 and isinstance(data[2], str) else ""
        return tr.strip(), lang

    def _google2(self, text: str, target: str):
        """Второй эндпоинт Google (другой лимит запросов)."""
        data = self._get(self.GOOGLE2.format(tl=target, q=urllib.parse.quote(text)))
        self.log(f"Google2 raw: {json.dumps(data, ensure_ascii=False)[:300]}")
        lang = ""
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, list):          # [["перевод", "en"]]
                tr = str(first[0]) if first else ""
                lang = str(first[1]) if len(first) > 1 else ""
            else:                                  # ["перевод"]
                tr = str(first)
        elif isinstance(data, dict):               # {"sentences":[{"trans":..}],"src":"en"}
            tr = "".join(x.get("trans", "") for x in data.get("sentences", []))
            lang = data.get("src", "")
        else:
            tr = ""
        return tr.strip(), lang

    def _mymemory(self, text: str, target: str):
        src = "ru" if _CYR_RE.search(text) else "en"
        if src == target:
            return "", src
        data = self._get(self.MYMEMORY.format(
            q=urllib.parse.quote(text), sl=src, tl=target))
        self.log(f"MyMemory raw: {json.dumps(data, ensure_ascii=False)[:300]}")
        tr = ((data or {}).get("responseData") or {}).get("translatedText") or ""
        if "MYMEMORY WARNING" in tr.upper():
            raise RuntimeError("MyMemory: превышен дневной лимит")
        if tr.strip().lower() == text.strip().lower():
            # в «памяти переводов» иногда лежит непереведённый вариант —
            # берём лучший из остальных совпадений, где текст реально переведён
            want_cyr = target in ("ru", "uk")
            for m in sorted((data or {}).get("matches") or [],
                            key=lambda m: float(m.get("match") or 0), reverse=True):
                cand = str(m.get("translation") or "").strip()
                if not cand or cand.lower() == text.strip().lower():
                    continue
                if want_cyr and not _CYR_RE.search(cand):
                    continue
                tr = cand
                break
        return tr.strip(), src

    def translate_now(self, text: str, target: str):
        """Синхронный перевод (для кнопки «Проверить»). (tr, lang, provider)."""
        errors = []
        for name, fn in (("Google", self._google), ("Google2", self._google2),
                         ("MyMemory", self._mymemory)):
            if self._cooldown.get(name, 0) > time.time():
                errors.append(f"{name}: пауза после 429")
                continue
            t0 = time.time()
            try:
                tr, lang = fn(text, target)
                self.log(f"{name} {time.time() - t0:.1f}s lang={lang!r} -> {tr!r}")
                if tr and tr.strip().lower() != text.strip().lower():
                    return tr, lang, name
                if tr and lang == target:
                    return tr, lang, name          # текст уже на нужном языке
                errors.append(f"{name}: вернул текст без перевода")
            except Exception as e:
                self.log(f"{name} {time.time() - t0:.1f}s ОШИБКА {type(e).__name__}: {e}")
                errors.append(f"{name}: {e}")
                if "429" in str(e):
                    self._cooldown[name] = time.time() + 600   # 10 минут не дёргаем
        raise RuntimeError("; ".join(errors))

    # ---------- очередь ----------
    def request(self, mid: str, text: str, target: str):
        self.log(f"запрос [{target}] {text!r}")
        key = (text, target)
        if key in self._cache:
            res = self._cache[key]
            if res:
                self._notify.put(("translated", (mid, res[0], res[1])))
            return
        try:
            self._q.put_nowait((mid, text, target))
        except queue.Full:
            return
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._loop, daemon=True)
            self._worker.start()

    def _loop(self):
        while True:
            try:
                mid, text, target = self._q.get(timeout=30)
            except queue.Empty:
                return
            res = None
            try:
                tr, lang, _prov = self.translate_now(text, target)
                self.last_error = ""
                same = tr.strip().lower() == text.strip().lower()
                if tr and lang != target and not same:
                    res = (tr, lang)
                else:
                    self._notify.put(("translate_skip", (text, lang)))
                if len(self._cache) > 500:
                    self._cache.clear()
                self._cache[(text, target)] = res      # кэшируем только успешные запросы
            except Exception as e:
                self.last_error = str(e)
                now = time.time()
                if now - self._err_reported > 60:    # не чаще раза в минуту
                    self._err_reported = now
                    self._notify.put(("translate_error", self.last_error))
            if res:
                self._notify.put(("translated", (mid, res[0], res[1])))
            time.sleep(0.25)


_CYR_RE = re.compile(r"[А-Яа-яЁёІіЇїЄєҐґ]")
_LETTERS_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def needs_translation(text: str, target: str) -> bool:
    """Переводим всё, где есть буквы, кроме команд «!…» и сообщений,
    уже написанных на целевом языке (кириллица при переводе на ru/uk)."""
    t = (text or "").strip()
    if not _LETTERS_RE.search(t) or t.startswith("!"):
        return False
    if target in ("ru", "uk") and _CYR_RE.search(t):
        return False
    return True


def _ver_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def check_github_update(notify_q: queue.Queue, manual: bool = False):
    """Фоновая проверка последнего релиза на GitHub."""
    def _work():
        import urllib.request
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"User-Agent": "ChatOverlay", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            tag = str(data.get("tag_name", ""))
            url = str(data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"))
            if _ver_tuple(tag) > _ver_tuple(APP_VERSION):
                notify_q.put(("update", (tag, url, manual)))
            else:
                notify_q.put(("update", ("", url, manual)))
        except Exception as e:
            notify_q.put(("update", (None, str(e), manual)))
    threading.Thread(target=_work, daemon=True).start()


# ============================================================
#                Звуковые уведомления
# ============================================================
class SoundPlayer:
    """Короткие звуки уведомлений. Встроенные звуки синтезируются в WAV
    (кэш в папке sounds/), свой файл — любой WAV. Громкость применяется
    к PCM-данным, поэтому работает и через winsound."""

    BUILTIN = {
        "ding":  ("Динь",        [(1320, 0.0, 0.35), (1760, 0.0, 0.25)], 0.45),
        "pop":   ("Пузырь",      [(660, 0.0, 0.10), (990, 0.05, 0.10)], 0.18),
        "chime": ("Колокольчик", [(1046, 0.0, 0.5), (1318, 0.12, 0.5), (1568, 0.24, 0.5)], 0.8),
        "soft":  ("Мягкий",      [(523, 0.0, 0.4), (784, 0.0, 0.3)], 0.5),
    }
    RATE = 22050

    def __init__(self, folder: str):
        self.dir = os.path.join(folder, "sounds")

    def _synth(self, key: str, volume: float) -> str:
        import math
        import wave
        import array
        name, tones, length = self.BUILTIN[key]
        path = os.path.join(self.dir, f"{key}_{int(volume * 100)}.wav")
        if os.path.exists(path):
            return path
        os.makedirs(self.dir, exist_ok=True)
        n = int(self.RATE * length)
        buf = [0.0] * n
        for freq, start, dur in tones:
            s0 = int(start * self.RATE)
            for i in range(int(dur * self.RATE)):
                j = s0 + i
                if j >= n:
                    break
                t = i / self.RATE
                env = min(1.0, t / 0.005) * math.exp(-t * 7.0 / dur)
                buf[j] += math.sin(2 * math.pi * freq * t) * env
        peak = max(1e-6, max(abs(x) for x in buf))
        amp = 0.85 * 32767 * max(0.0, min(1.0, volume)) / peak
        data = array.array("h", (int(x * amp) for x in buf))
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.RATE)
            w.writeframes(data.tobytes())
        return path

    def _scaled_file(self, src: str, volume: float) -> str:
        """Копия своего WAV с нужной громкостью (только 16-bit PCM)."""
        import wave
        import array
        if volume >= 0.99:
            return src
        try:
            st = os.stat(src)
            key = hashlib.sha1(f"{src}|{st.st_mtime}|{st.st_size}".encode()).hexdigest()[:12]
            path = os.path.join(self.dir, f"custom_{key}_{int(volume * 100)}.wav")
            if os.path.exists(path):
                return path
            with wave.open(src, "rb") as r:
                params = r.getparams()
                if params.sampwidth != 2:
                    return src
                frames = r.readframes(params.nframes)
            a = array.array("h")
            a.frombytes(frames)
            if sys.byteorder == "big":
                a.byteswap()
            a = array.array("h", (int(x * volume) for x in a))
            if sys.byteorder == "big":
                a.byteswap()
            os.makedirs(self.dir, exist_ok=True)
            with wave.open(path, "wb") as w:
                w.setparams(params)
                w.writeframes(a.tobytes())
            return path
        except Exception:
            return src

    def play(self, sound: str = "ding", volume: float = 0.7, custom: str = ""):
        try:
            if sound == "custom" and custom and os.path.exists(custom):
                path = self._scaled_file(custom, volume)
            else:
                path = self._synth(sound if sound in self.BUILTIN else "ding", volume)
        except Exception:
            return
        if IS_WIN:
            try:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC
                                   | winsound.SND_NODEFAULT)
            except Exception:
                pass
        else:
            import subprocess
            for cmd in (["paplay", path], ["aplay", "-q", path]):
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    break
                except Exception:
                    continue


# ============================================================
#                    Главное окно (overlay)
# ============================================================
class ChatOverlay(tk.Tk):
    APP_DIR      = USER_DIR
    CONFIG_PATH  = os.path.join(USER_DIR, "overlay_config.json")
    HISTORY_PATH = os.path.join(USER_DIR, "chat_history.txt")
    ICON_PNG     = os.path.join(RES_DIR, "assets/icon.png")
    ICON_ICO     = os.path.join(RES_DIR, "assets/icon.ico")

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

    # Цвет тега-источника для каждого канала в мульти-чате
    CHANNEL_TAG_COLORS = [
        "#a970ff",  # фиолетовый
        "#4fc3f7",  # голубой
        "#81c784",  # зелёный
        "#ffb74d",  # оранжевый
        "#f06292",  # розовый
        "#4dd0e1",  # циан
    ]

    EDGE = 6
    CHROMA = "#010102"
    APP_ID = "twitch.chat.overlay.1"

    def __init__(self, channel: str, platform: str = "twitch"):
        super().__init__()

        # ── мульти-чат ──────────────────────────────────────────────
        # backward-compat: self.channel / self.platform = первый канал
        self.channel  = channel
        self.platform = platform
        self._ch_list: list[dict] = []   # {"channel","platform","tag","idx"}
        self._readers: dict       = {}   # tag → thread
        self._statuses: dict      = {}   # tag → "online"|"offline"
        # ────────────────────────────────────────────────────────────
        self.cfg = self._load_config()
        self.theme_name = str(self.cfg.get("theme", "twitch_dark"))
        if self.theme_name not in THEMES:
            self.theme_name = "twitch_dark"
        global PALETTE
        PALETTE = THEMES[self.theme_name]
        self._apply_theme_values(THEMES[self.theme_name])
        self.alpha = float(self.cfg.get("alpha", 0.92))
        geom = self.cfg.get("geometry", "440x560+200+150")
        self.highlight_words = list(self.cfg.get("highlight_words", []))
        self.banned_users    = [u.lower() for u in self.cfg.get("banned_users", [])]
        self.banned_words    = [w.lower() for w in self.cfg.get("banned_words", [])]
        self.msg_style  = str(self.cfg.get("msg_style", "card"))
        if self.msg_style not in MSG_STYLES:
            self.msg_style = "card"
        self._row_counter = 0
        self._is_topmost = True
        self._chroma_mode = bool(self.cfg.get("chroma", False))
        self._obs_enabled = bool(self.cfg.get("obs_web_enabled", True))
        self._obs_port = _safe_int(self.cfg.get("obs_web_port", 17655), 17655)
        self._obs_server = None
        self._settings_win = None
        self._taskbar_icon_retry = 0

        # ---- AppUserModelID для группировки в taskbar Windows ----
        if IS_WIN:
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    self.APP_ID
                )
            except Exception:
                pass

        # ---- настройка окна ----
        self.title("Chat Overlay")
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

        # ---- эмоуты Twitch ----
        self.show_emotes = bool(self.cfg.get("show_emotes", True))
        # ---- 7TV / BTTV / FFZ, события, синхронизация с модерацией ----
        self.third_party_emotes = bool(self.cfg.get("third_party_emotes", True))
        self.show_events = bool(self.cfg.get("show_events", True))
        self.mod_sync = bool(self.cfg.get("mod_sync", True))
        self.hide_bots = bool(self.cfg.get("hide_bots", False))
        self.hide_commands = bool(self.cfg.get("hide_commands", False))
        self.show_first = bool(self.cfg.get("show_first", True))
        self.translate_on = bool(self.cfg.get("translate_enabled", False))
        self.translate_to = str(self.cfg.get("translate_to", "ru"))
        self.check_updates = bool(self.cfg.get("check_updates", True))
        self._update_info = None
        self._stats_reset()
        self._tpe = ThirdPartyEmotes()
        # ---- звуки ----
        self.sound = {
            "enabled": bool(self.cfg.get("sound_enabled", True)),
            "hl":      bool(self.cfg.get("sound_hl", True)),
            "events":  bool(self.cfg.get("sound_events", True)),
            "all":     bool(self.cfg.get("sound_all", False)),
            "name":    str(self.cfg.get("sound_name", "ding")),
            "file":    str(self.cfg.get("sound_file", "")),
            "volume":  max(0, min(100, _safe_int(self.cfg.get("sound_volume", 70), 70))),
            "mention": bool(self.cfg.get("sound_mention", True)),
            "mention_name": str(self.cfg.get("sound_mention_name", "chime")),
            "mention_file": str(self.cfg.get("sound_mention_file", "")),
            "my_nick": str(self.cfg.get("my_nick", "")).strip().lstrip("@").lower(),
        }
        self._sound = SoundPlayer(USER_DIR)
        self._sound_last = 0.0
        self._room_ids: dict = {}         # tag -> twitch room-id
        self._emotes = EmoteCache(self.msg_queue)
        self._translator = Translator(self.msg_queue)
        global _DA_INSTANCE
        self.show_donations = bool(self.cfg.get("show_donations", True))
        self._da = DonationAlerts(USER_DIR, self.msg_queue)
        _DA_INSTANCE = self._da
        self._da_status_cb = None
        if self._da.connected:
            self.after(2500, self._da.start)
        if self.check_updates:
            self.after(4000, lambda: check_github_update(self.msg_queue))
        self._emote_pending: dict = {}   # eid -> [(placeholder_tag, height)]
        self._emote_seq = 0

        self._add_channel(channel, platform)

        if self._obs_enabled:
            try:
                self._obs_server = ObsWebServer(port=self._obs_port)
                self._obs_server.start()
                try:
                    self._obs_server.hub.publish({
                        "kind": "status",
                        "state": "offline",
                        "channel": self.channel,
                    })
                except Exception:
                    pass
            except Exception:
                self._obs_server = None

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

    def _apply_theme_values(self, p):
        self.BG = p["BG"]
        self.BG_ELEV = p["BG_ELEV"]
        self.BG_HEADER = p["BG_HEADER"]
        self.BG_INPUT = p["BG_INPUT"]
        self.BORDER = p["BORDER"]
        self.TEXT = p["TEXT"]
        self.TEXT_MUTED = p["TEXT_MUTED"]
        self.TEXT_DIM = p["TEXT_DIM"]
        self.ACCENT = p["ACCENT"]
        self.ACCENT_HOV = p["ACCENT_HOV"]
        self.DANGER = p["DANGER"]
        self.OK = p["OK"]
        self.WARN = p["WARN"]

    def _apply_theme_runtime(self):
        self.configure(bg=self.BORDER)
        self._outer.config(bg=self.BG)
        self.header.config(bg=self.BG_HEADER)
        self.statusbar.config(bg=self.BG_ELEV)
        self.footer.config(bg=self.BG_HEADER)
        self.body.config(bg=self.BG)
        self.text.config(bg=self.BG, fg=self.TEXT, insertbackground=self.TEXT)

        self.logo_dot.config(bg=self.BG_HEADER, fg=self._platform_dot_color())
        self.title_lbl.config(bg=self.BG_HEADER, fg=self.TEXT)
        self.status_dot.config(bg=self.BG_ELEV)
        self.status_lbl.config(bg=self.BG_ELEV, fg=self.TEXT_MUTED)
        self.count_lbl.config(bg=self.BG_ELEV, fg=self.TEXT_DIM)
        self.alpha_lbl.config(bg=self.BG_HEADER, fg=self.TEXT_MUTED)
        self.grip.config(bg=self.BG_HEADER, fg=self.TEXT_DIM)

        self.pin_btn.config(bg=self.BG_HEADER,
                            fg=self.ACCENT if self._is_topmost else self.TEXT_DIM)
        self.chroma_btn.config(bg=self.BG_HEADER,
                               fg=self.ACCENT if self._chroma_mode else self.TEXT_MUTED)
        self.settings_btn.config(bg=self.BG_HEADER, fg=self.TEXT_MUTED)
        self.close_btn.config(bg=self.BG_HEADER, fg=self.TEXT_MUTED)
        self.ch_btn.config(bg=self.BG_HEADER, fg=self.TEXT_MUTED)
        self.font_inc_btn.config(bg=self.BG_HEADER, fg=self.TEXT_MUTED)
        self.font_dec_btn.config(bg=self.BG_HEADER, fg=self.TEXT_MUTED)
        self.hide_btn.config(bg=self.BG_HEADER, fg=self.TEXT_MUTED)

        for edge in (self.edge_r, self.edge_b, self.edge_br):
            edge.config(bg=self.BORDER)

        self.text.tag_configure("system",         foreground=self.TEXT_MUTED, font=self.fnt_sys)
        self.text.tag_configure("time",           foreground=self.TEXT_DIM,   font=self.fnt_time)
        self.text.tag_configure("colon",          foreground=self.TEXT_DIM)
        self.text.tag_configure("msg",            foreground=self.TEXT)
        self.text.tag_configure("highlight_mark", foreground=self.WARN,       font=self.fnt_bold)
        self.text.tag_configure("highlight_msg",  foreground="#ffffff")
        self._configure_row_tags()

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

        self.logo_dot = tk.Label(
            self.header, text="●", bg=self.BG_HEADER,
            fg=self._platform_dot_color(),
            font=("Segoe UI", 12, "bold"), padx=10,
        )
        self.logo_dot.pack(side="left")

        self.title_lbl = tk.Label(
            self.header, text=self._header_title(),
            bg=self.BG_HEADER, fg=self.TEXT, font=self.fnt_title, anchor="w",
        )
        self.title_lbl.pack(side="left", fill="x", expand=True)

        self.close_btn = self._make_btn(
            self.header, "✕", self._on_quit,
            fg=self.TEXT_MUTED, hover_fg=self.DANGER)
        self.close_btn.pack(side="right")

        self.settings_btn = self._make_btn(
            self.header, "⚙", self._open_settings,
            fg=self.TEXT_MUTED, hover_fg=self.TEXT)
        self.settings_btn.pack(side="right")

        self.pin_btn = self._make_btn(
            self.header, "📌", self._toggle_topmost,
            fg=self.ACCENT, hover_fg=self.ACCENT_HOV)
        self.pin_btn.pack(side="right")

        self.ch_btn = self._make_btn(
            self.header, "⟳", self._change_channel,
            fg=self.TEXT_MUTED, hover_fg=self.TEXT)
        self.ch_btn.pack(side="right")

        self.chroma_btn = self._make_btn(
            self.header, "◐", self._toggle_chroma,
            fg=self.TEXT_MUTED, hover_fg=self.ACCENT_HOV)
        self.chroma_btn.pack(side="right")

        # A+ / A− — размер шрифта
        self.font_inc_btn = self._make_btn(
            self.header, "A+", lambda: self._change_font_size(+1),
            fg=self.TEXT_MUTED, hover_fg=self.TEXT,
            font=tkfont.Font(family="Segoe UI", size=10, weight="bold"))
        self.font_inc_btn.pack(side="right")

        self.font_dec_btn = self._make_btn(
            self.header, "A−", lambda: self._change_font_size(-1),
            fg=self.TEXT_MUTED, hover_fg=self.TEXT,
            font=tkfont.Font(family="Segoe UI", size=10))
        self.font_dec_btn.pack(side="right")

        self.hide_btn = self._make_btn(
            self.header, "—", self._toggle_visible,
            fg=self.TEXT_MUTED, hover_fg=self.TEXT, font=self.fnt_bold)
        self.hide_btn.pack(side="right")

        self.new_ch_btn = self._make_btn(
            self.header, "+", self._open_new_channel,
            fg=self.TEXT_MUTED, hover_fg=self.OK,
            font=tkfont.Font(family="Segoe UI", size=13, weight="bold"))
        self.new_ch_btn.pack(side="right")

        for w in (self.header, self.title_lbl, self.logo_dot):
            w.bind("<Button-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)
            w.bind("<Double-Button-1>", lambda e: self._toggle_topmost())

    # ============================================================
    #                       settings window
    # ============================================================
    def _obs_urls(self):
        if self._obs_server:
            try:
                return self._obs_server.urls()
            except Exception:
                pass
        base = f"http://127.0.0.1:{int(self._obs_port)}"
        return {"dock": f"{base}/obs/dock", "browser": f"{base}/obs/browser",
                "editor": f"{base}/obs/editor", "featured": f"{base}/obs/featured"}

    def _copy_to_clipboard(self, text: str):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except Exception:
            pass

    def _apply_obs_settings(self, enabled: bool, port: int):
        enabled = bool(enabled)
        port = int(port)
        port = max(1, min(65535, port))

        changed = (enabled != self._obs_enabled) or (port != self._obs_port)
        self._obs_enabled = enabled
        self._obs_port = port
        if not changed:
            return

        # перезапуск сервера (или выключение)
        try:
            if self._obs_server:
                self._obs_server.stop()
        except Exception:
            pass
        self._obs_server = None

        if self._obs_enabled:
            try:
                self._obs_server = ObsWebServer(port=self._obs_port)
                self._obs_server.start()
                try:
                    self._obs_server.hub.publish({
                        "kind": "status",
                        "state": "offline",
                        "channel": self.channel,
                    })
                except Exception:
                    pass
            except Exception:
                self._obs_server = None

    def _open_settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            try:
                self._settings_win.lift()
                self._settings_win.focus_force()
            except Exception:
                pass
            return

        win = tk.Toplevel(self)
        self._settings_win = win
        win.title("Настройки")
        win.configure(bg=self.BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        try:
            if IS_WIN and os.path.exists(self.ICON_ICO):
                win.iconbitmap(default=self.ICON_ICO)
            if self._tk_icon is not None:
                win.iconphoto(True, self._tk_icon)
            elif os.path.exists(self.ICON_PNG):
                settings_icon = tk.PhotoImage(file=self.ICON_PNG)
                win._settings_icon = settings_icon
                win.iconphoto(True, settings_icon)
        except Exception:
            pass

        try:
            w, h = 500, 760
            px = self.winfo_rootx() + self.winfo_width() // 2
            py = self.winfo_rooty() + self.winfo_height() // 2
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(0, min(sw - w, px - w // 2))
            y = max(0, min(sh - h - 40, py - h // 2))
            win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

        outer = tk.Frame(win, bg=self.BG, padx=14, pady=10)
        outer.pack(fill="both", expand=True)

        # ---- заголовок ----
        title_row = tk.Frame(outer, bg=self.BG)
        title_row.pack(fill="x", pady=(0, 8))
        tk.Label(title_row, text="⚙", bg=self.BG, fg=self.ACCENT,
                 font=("Segoe UI Symbol", 14)).pack(side="left")
        tk.Label(title_row, text="Настройки", bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI Semibold", 12), padx=8).pack(side="left")

        # ---- notebook ----
        nb_style = ttk.Style()
        # плоские вкладки без светлых рамок темы clam
        nb_style.configure("Settings.TNotebook",
                            background=self.BG, borderwidth=0,
                            bordercolor=self.BORDER, lightcolor=self.BG_ELEV,
                            darkcolor=self.BG_ELEV, tabmargins=(0, 0, 0, 0))
        nb_style.configure("Settings.TNotebook.Tab",
                            background=self.BG, foreground=self.TEXT_MUTED,
                            bordercolor=self.BG, lightcolor=self.BG,
                            darkcolor=self.BG, borderwidth=0,
                            padding=(11, 7), font=("Segoe UI Semibold", 9),
                            focuscolor=self.BG)
        nb_style.map("Settings.TNotebook.Tab",
                     background=[("selected", self.BG_ELEV), ("active", self.BG_INPUT)],
                     foreground=[("selected", self.TEXT), ("active", self.TEXT)],
                     bordercolor=[("selected", self.BORDER)],
                     lightcolor=[("selected", self.BG_ELEV)],
                     darkcolor=[("selected", self.BG_ELEV)],
                     expand=[("selected", (0, 0, 0, 0))])

        nb = ttk.Notebook(outer, style="Settings.TNotebook")
        nb.pack(fill="both", expand=True)

        # ========== Вкладка 1: OBS ==========
        obs_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=16, pady=12)
        nb.add(obs_tab, text="OBS")

        enabled_var = tk.BooleanVar(value=self._obs_enabled)
        port_var = tk.StringVar(value=str(self._obs_port))

        # ---- сервер: переключатель + статус + порт ----
        self._ui_section(obs_tab, "ВЕБ-СТРАНИЦА ДЛЯ OBS")
        srv_card = self._ui_card(obs_tab)

        status_row = tk.Frame(srv_card, bg=self.BG_INPUT)
        status_row.pack(fill="x", pady=(0, 10))
        status_pill = tk.Label(status_row, text="", padx=10, pady=2,
                               font=("Segoe UI Semibold", 8))
        status_pill.pack(side="left")

        def _refresh_status():
            running = self._obs_server is not None
            want = bool(enabled_var.get())
            if running and want:
                txt, col = f"●  Работает · порт {self._obs_port}", self.OK
            elif want:
                txt, col = "●  Запустится после «Применить»", self.WARN
            else:
                txt, col = "●  Выключена", self.TEXT_DIM
            status_pill.config(text=txt, fg=col,
                               bg=_blend_color(self.BG_INPUT, col, 0.16))

        self._ui_toggle(
            srv_card, "Включить веб-страницу",
            "Ссылки работают, пока запущена программа",
            self._obs_enabled,
            lambda on: (enabled_var.set(on), _refresh_status()),
        )

        port_row = tk.Frame(srv_card, bg=self.BG_INPUT)
        port_row.pack(fill="x", pady=(12, 0))
        port_txt = tk.Frame(port_row, bg=self.BG_INPUT)
        port_txt.pack(side="left", fill="x", expand=True)
        tk.Label(port_txt, text="Порт", bg=self.BG_INPUT, fg=self.TEXT,
                 anchor="w", font=("Segoe UI", 10)).pack(fill="x")
        tk.Label(port_txt, text="Меняй, если 17655 занят",
                 bg=self.BG_INPUT, fg=self.TEXT_DIM, anchor="w",
                 font=("Segoe UI", 8)).pack(fill="x")
        port_wrap = tk.Frame(port_row, bg=self.BORDER, padx=1, pady=1)
        port_wrap.pack(side="right")
        port_in = tk.Frame(port_wrap, bg=self.BG_ELEV)
        port_in.pack()
        port_entry = tk.Entry(
            port_in, textvariable=port_var, width=7, justify="center",
            bg=self.BG_ELEV, fg=self.TEXT, insertbackground=self.ACCENT,
            relief="flat", bd=0, highlightthickness=0,
            font=("Consolas", 11),
        )
        port_entry.pack(ipady=5, padx=8)
        port_entry.bind("<FocusIn>", lambda e: port_wrap.config(bg=self.ACCENT))
        port_entry.bind("<FocusOut>", lambda e: port_wrap.config(bg=self.BORDER))

        # ---- ссылки ----
        self._ui_section(obs_tab, "ССЫЛКИ", "Вставь в OBS → Источник → Браузер",
                         pady=(14, 0))
        links_card = self._ui_card(obs_tab)

        def _base_url():
            p = port_var.get().strip()
            port = int(p) if p.isdigit() and 1 <= int(p) <= 65535 else self._obs_port
            return f"http://127.0.0.1:{port}"

        url_labels = []

        def _link_row(icon, color, title, path, first=False):
            row = tk.Frame(links_card, bg=self.BG_INPUT)
            row.pack(fill="x", pady=(0 if first else 6, 0))
            ic = tk.Canvas(row, width=26, height=26, bg=self.BG_INPUT,
                           highlightthickness=0, bd=0)
            ic.pack(side="left")
            self._ui_round_rect(ic, 0, 0, 26, 26, 7,
                                fill=_blend_color(self.BG_INPUT, color, 0.22), outline="")
            ic.create_text(13, 13, text=icon, fill=color,
                           font=("Segoe UI Symbol", 10, "bold"))
            btn = tk.Label(row, text="Копировать", bg=self.BG_ELEV, fg=self.TEXT,
                           width=12, pady=3, cursor="hand2",
                           font=("Segoe UI Semibold", 9),
                           highlightthickness=1, highlightbackground=self.BORDER)
            btn.pack(side="right")
            txt = tk.Frame(row, bg=self.BG_INPUT)
            txt.pack(side="left", fill="x", expand=True, padx=(8, 8))
            tk.Label(txt, text=title, bg=self.BG_INPUT, fg=self.TEXT, anchor="w",
                     font=("Segoe UI Semibold", 9)).pack(side="left")
            url_lbl = tk.Label(txt, text="", bg=self.BG_INPUT, fg=self.TEXT_DIM,
                               anchor="w", font=("Consolas", 8))
            url_lbl.pack(side="left", padx=(6, 0))
            url_labels.append((url_lbl, path))

            st = {"done": False}

            def _copy(e=None):
                self._copy_to_clipboard(_base_url() + path)
                st["done"] = True
                btn.config(text="✓ Скопировано", fg=self.OK,
                           bg=_blend_color(self.BG_INPUT, self.OK, 0.15))

                def _reset():
                    st["done"] = False
                    btn.config(text="Копировать", fg=self.TEXT, bg=self.BG_ELEV)
                btn.after(1600, _reset)

            btn.bind("<Button-1>", _copy)
            btn.bind("<Enter>", lambda e: None if st["done"] else btn.config(bg=self.BORDER))
            btn.bind("<Leave>", lambda e: None if st["done"] else btn.config(bg=self.BG_ELEV))

        _link_row("▣", self.ACCENT, "Browser Source", "/obs/browser", first=True)
        _link_row("▤", "#4fc3f7", "Dock-панель", "/obs/dock")
        _link_row("◉", "#ffb347", "Сообщение на экран", "/obs/featured")
        _link_row("◎", "#3ddc84", "Цель стрима", "/obs/goal")
        _link_row("◷", "#ff6bcb", "Последние события", "/obs/recent")

        def _refresh_urls(*_):
            for lbl, path in url_labels:
                lbl.config(text=path)

        port_var.trace_add("write", _refresh_urls)
        _refresh_urls()
        _refresh_status()

        # ---- редактор оформления ----
        self._ui_section(obs_tab, "ОФОРМЛЕНИЕ BROWSER SOURCE", pady=(14, 0))
        ed_card = self._ui_card(obs_tab)
        ed_row = tk.Frame(ed_card, bg=self.BG_INPUT)
        ed_row.pack(fill="x")
        ed_ic = tk.Canvas(ed_row, width=32, height=32, bg=self.BG_INPUT,
                          highlightthickness=0, bd=0)
        ed_ic.pack(side="left")
        self._ui_round_rect(ed_ic, 0, 0, 32, 32, 8, fill=self.ACCENT, outline="")
        ed_ic.create_text(16, 16, text="✦", fill="#ffffff",
                          font=("Segoe UI Symbol", 12, "bold"))
        editor_btn = tk.Label(
            ed_row, text="Открыть  ›", bg=self.ACCENT, fg="#ffffff",
            padx=14, pady=7, cursor="hand2", font=("Segoe UI Semibold", 9),
        )
        editor_btn.pack(side="right")
        ed_txt = tk.Frame(ed_row, bg=self.BG_INPUT)
        ed_txt.pack(side="left", fill="x", expand=True, padx=(10, 8))
        tk.Label(ed_txt, text="Плашки, шрифты, анимации", bg=self.BG_INPUT,
                 fg=self.TEXT, anchor="w",
                 font=("Segoe UI Semibold", 10)).pack(fill="x")
        tk.Label(ed_txt, text="Редактор в браузере с живым превью",
                 bg=self.BG_INPUT, fg=self.TEXT_MUTED, anchor="w",
                 font=("Segoe UI", 9)).pack(fill="x")

        def _open_editor():
            if not self._obs_server:
                messagebox.showwarning(
                    "Редактор оформления",
                    "Сначала включите веб-страницу и нажмите «Применить».",
                    parent=win)
                return
            try:
                webbrowser.open(self._obs_urls()["editor"])
            except Exception:
                pass

        editor_btn.bind("<Button-1>", lambda e: _open_editor())
        self._hover(editor_btn, self.ACCENT, self.ACCENT_HOV, "#ffffff", "#ffffff")

        # ---- быстрые пресеты оформления ----
        pr_row = tk.Frame(ed_card, bg=self.BG_INPUT)
        pr_row.pack(fill="x", pady=(10, 0))
        tk.Label(pr_row, text="Пресеты:", bg=self.BG_INPUT, fg=self.TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        presets = obs_presets_load(USER_DIR)
        if not presets:
            tk.Label(pr_row, text="сохраняются в редакторе → «Мои пресеты»",
                     bg=self.BG_INPUT, fg=self.TEXT_DIM,
                     font=("Segoe UI", 9)).pack(side="left")
        pr_btns = []

        def _apply_preset(name, btn):
            try:
                obs_style_write(USER_DIR, obs_presets_load(USER_DIR)[name])
                if self._obs_server:
                    self._obs_server.hub.broadcast({"kind": "style"})
            except Exception:
                return
            for b in pr_btns:
                b.config(bg=self.BG_ELEV, fg=self.TEXT)
            btn.config(bg=self.ACCENT, fg="#ffffff")

        for name in sorted(presets.keys())[:6]:
            b = tk.Label(pr_row, text=name, bg=self.BG_ELEV, fg=self.TEXT,
                         padx=10, pady=3, cursor="hand2",
                         font=("Segoe UI Semibold", 9),
                         highlightthickness=1, highlightbackground=self.BORDER)
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, n=name, bb=b: _apply_preset(n, bb))
            pr_btns.append(b)

        # ========== Вкладка 2: Оформление ==========
        theme_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=16, pady=12)
        nb.add(theme_tab, text="Тема")

        # исходные значения — если закрыть без «Применить», откатываем превью
        orig_look = {
            "theme": self.theme_name, "alpha": self.alpha,
            "font": self.font_size, "chroma": self._chroma_mode,
        }
        theme_sel = {"key": self.theme_name}

        # ---- тема: карточки с мини-превью окна ----
        self._ui_section(theme_tab, "ТЕМА ИНТЕРФЕЙСА",
                         "Нажми на карточку — оверлей сразу перекрасится")
        cards_row = tk.Frame(theme_tab, bg=self.BG_ELEV)
        cards_row.pack(fill="x", pady=(8, 4))
        theme_cards = {}

        def _pick_theme(key):
            theme_sel["key"] = key
            for k, redraw in theme_cards.items():
                redraw()
            self._set_theme(key)

        THEME_COLS = 4
        for i, key in enumerate(THEMES.keys()):
            redraw = self._ui_theme_card(
                cards_row, key, i // THEME_COLS, i % THEME_COLS,
                is_selected=lambda k=key: theme_sel["key"] == k,
                on_click=lambda k=key: _pick_theme(k),
            )
            theme_cards[key] = redraw
        for c in range(THEME_COLS):
            cards_row.grid_columnconfigure(c, weight=1, uniform="tc")

        # ---- окно ----
        self._ui_section(theme_tab, "ОКНО ОВЕРЛЕЯ", pady=(12, 0))
        win_card = self._ui_card(theme_tab)

        self._ui_slider(
            win_card, "Непрозрачность", 20, 100, int(round(self.alpha * 100)),
            lambda v: self._set_alpha(v / 100.0), fmt=lambda v: f"{v}%",
        )
        self._ui_slider(
            win_card, "Размер шрифта чата", self.FONT_MIN, self.FONT_MAX,
            self.font_size, lambda v: self._set_font_size(v),
            fmt=lambda v: f"{v} pt", pady=(10, 0),
        )
        self._ui_toggle(
            win_card, "Прозрачный фон",
            "Остаётся только текст, клики проходят насквозь"
            if IS_WIN else "Доступно только в Windows",
            self._chroma_mode,
            lambda on: self._set_chroma(on),
            enabled=IS_WIN, pady=(12, 0),
        )

        # ========== Вкладка 3: Фильтры ==========
        filter_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=16, pady=12)
        nb.add(filter_tab, text="Фильтры")

        self._ui_section(filter_tab, "ФИЛЬТРЫ ЧАТА",
                         "Enter — добавить, × — удалить")

        def _norm_word(w):
            return w.strip().lower()

        def _norm_user(w):
            return w.strip().lstrip("@").lower()

        filt = {"bots": self.hide_bots, "cmds": self.hide_commands}
        bot_card = self._ui_card(filter_tab)
        self._ui_toggle(bot_card, "Скрывать ботов",
                        "Nightbot, StreamElements, Moobot и ещё ~40",
                        self.hide_bots, lambda on: filt.__setitem__("bots", on))
        self._ui_toggle(bot_card, "Скрывать команды",
                        "Сообщения, начинающиеся с «!»",
                        self.hide_commands, lambda on: filt.__setitem__("cmds", on),
                        pady=(8, 0))

        hl_items = self._ui_chip_list(
            filter_tab, "Подсветка", "★", self.WARN,
            "Сообщения с этими словами или ником выделяются",
            "слово или ник…", self.highlight_words, _norm_user,
        )
        bu_items = self._ui_chip_list(
            filter_tab, "Скрытые пользователи", "⊘", self.DANGER,
            "Их сообщения не показываются ни в окне, ни в OBS",
            "никнейм…", self.banned_users, _norm_user,
        )
        bw_items = self._ui_chip_list(
            filter_tab, "Запрещённые слова", "✕", "#4fc3f7",
            "Сообщение со словом целиком скрывается",
            "слово или фраза…", self.banned_words, _norm_word,
        )

        # ========== Вкладка 4: Сообщения ==========
        msg_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=16, pady=12)
        nb.add(msg_tab, text="Чат")

        orig_look["msg_style"] = self.msg_style
        orig_look["emotes"] = self.show_emotes
        style_sel = {"key": self.msg_style}

        self._ui_section(msg_tab, "ПОДЛОЖКА СООБЩЕНИЙ",
                         "Применяется к окну сразу")
        style_grid = tk.Frame(msg_tab, bg=self.BG_ELEV)
        style_grid.pack(fill="x", pady=(8, 0))
        style_cards = []

        def _pick_style(key):
            style_sel["key"] = key
            for redraw in style_cards:
                redraw()
            if key != self.msg_style:
                self.msg_style = key
                self._configure_row_tags()

        for i, sk in enumerate(MSG_STYLES.keys()):
            style_cards.append(self._ui_style_card(
                style_grid, sk, i // 3, i % 3,
                is_selected=lambda k=sk: style_sel["key"] == k,
                on_click=lambda k=sk: _pick_style(k),
            ))
        for c in range(3):
            style_grid.grid_columnconfigure(c, weight=1, uniform="sc")

        # ---- эмоуты ----
        self._ui_section(msg_tab, "СОДЕРЖИМОЕ", pady=(14, 0))
        emo_card = self._ui_card(msg_tab)
        emotes_var = tk.IntVar(value=1 if self.show_emotes else 0)

        def _set_emotes(on):
            emotes_var.set(1 if on else 0)
            self.show_emotes = bool(on)

        self._ui_toggle(
            emo_card, "Эмоуты Twitch картинками",
            "Картинки вместо текста в окне программы"
            if HAS_PIL else "Нужен Pillow: pip install Pillow",
            self.show_emotes, _set_emotes, enabled=HAS_PIL,
        )
        chat_opts = {"tpe": self.third_party_emotes, "events": self.show_events,
                     "mod": self.mod_sync}
        self._ui_toggle(
            emo_card, "Эмоуты 7TV, BTTV и FFZ",
            "Глобальные и канала — в окне и в OBS",
            self.third_party_emotes,
            lambda on: chat_opts.__setitem__("tpe", on), pady=(12, 0),
        )
        self._ui_toggle(
            emo_card, "События канала",
            "Подписки, подарки, рейды, битсы и объявления",
            self.show_events,
            lambda on: chat_opts.__setitem__("events", on), pady=(12, 0),
        )
        chat_opts["first"] = self.show_first
        self._ui_toggle(
            emo_card, "Новые зрители",
            "Первое сообщение зрителя на канале — 👋 и зелёный фон",
            self.show_first,
            lambda on: chat_opts.__setitem__("first", on), pady=(12, 0),
        )
        self._ui_toggle(
            emo_card, "Синхронизация с модерацией",
            "Удалённое модераторами исчезает из чата и OBS",
            self.mod_sync,
            lambda on: chat_opts.__setitem__("mod", on), pady=(12, 0),
        )

        # ========== Вкладка 5: Звук ==========
        snd_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=16, pady=10)
        nb.add(snd_tab, text="Звук")
        snd = dict(self.sound)          # правки применяются по «Применить»

        self._ui_section(snd_tab, "КОГДА ИГРАТЬ ЗВУК")
        when_card = self._ui_card(snd_tab)
        self._ui_toggle(when_card, "Звуковые уведомления",
                        "Общий выключатель", snd["enabled"],
                        lambda on: snd.__setitem__("enabled", on))
        self._ui_toggle(when_card, "Упоминания через @",
                        "@канал или @ник ниже — свой звук", snd["mention"],
                        lambda on: snd.__setitem__("mention", on), pady=(10, 0))
        self._ui_toggle(when_card, "Подсветка из «Фильтров»",
                        None, snd["hl"],
                        lambda on: snd.__setitem__("hl", on), pady=(10, 0))
        self._ui_toggle(when_card, "События и новые зрители",
                        None, snd["events"],
                        lambda on: snd.__setitem__("events", on), pady=(10, 0))
        self._ui_toggle(when_card, "Каждое сообщение",
                        "Не чаще раза в 1,2 с", snd["all"],
                        lambda on: snd.__setitem__("all", on), pady=(10, 0))

        nick_row = tk.Frame(when_card, bg=self.BG_INPUT)
        nick_row.pack(fill="x", pady=(10, 0))
        tk.Label(nick_row, text="Твой ник для @", bg=self.BG_INPUT, fg=self.TEXT,
                 font=("Segoe UI", 10)).pack(side="left")
        nick_wrap = tk.Frame(nick_row, bg=self.BORDER, padx=1, pady=1)
        nick_wrap.pack(side="right")
        nick_var = tk.StringVar(value=snd.get("my_nick", ""))
        nick_ent = tk.Entry(nick_wrap, textvariable=nick_var, width=18,
                            bg=self.BG_ELEV, fg=self.TEXT, insertbackground=self.ACCENT,
                            relief="flat", bd=0, highlightthickness=0,
                            font=("Segoe UI", 10))
        nick_ent.pack(ipady=4, padx=8)
        nick_ent.bind("<FocusIn>", lambda e: nick_wrap.config(bg=self.ACCENT))
        nick_ent.bind("<FocusOut>", lambda e: nick_wrap.config(bg=self.BORDER))
        nick_var.trace_add("write", lambda *a: snd.__setitem__(
            "my_nick", nick_var.get().strip().lstrip("@").lower()))

        self._ui_section(snd_tab, "ЗВУКИ", "свой WAV — кнопка «Свой WAV»", pady=(12, 0))
        what_card = self._ui_card(snd_tab)
        options = [(k, v[0]) for k, v in SoundPlayer.BUILTIN.items()] + [("custom", "Свой WAV")]

        def _test(kind):
            old = self.sound
            self.sound = snd
            try:
                self._maybe_sound(False, False, force=True, mention=(kind == "mention"))
            finally:
                self.sound = old

        def _chip_row(title, name_key, file_key, kind, first=False):
            tk.Label(what_card, text=title, bg=self.BG_INPUT, fg=self.TEXT_MUTED,
                     anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(0 if first else 10, 4))
            row = tk.Frame(what_card, bg=self.BG_INPUT)
            row.pack(fill="x")
            btns = {}

            def paint():
                for k, b in btns.items():
                    on = snd[name_key] == k
                    b.config(bg=self.ACCENT if on else self.BG_ELEV,
                             fg="#ffffff" if on else self.TEXT)
                f = snd.get(file_key) or ""
                btns["custom"].config(text=("♪ " + os.path.basename(f)[:12]) if f else "Свой WAV")

            def pick(k):
                if k == "custom":
                    from tkinter import filedialog
                    path = filedialog.askopenfilename(
                        parent=win, title="Выберите звук (.wav)",
                        filetypes=[("WAV", "*.wav"), ("Все файлы", "*.*")])
                    if not path:
                        return
                    snd[file_key] = path
                snd[name_key] = k
                paint()
                _test(kind)

            for k, label in options:
                b = tk.Label(row, text=label, padx=8, pady=4, cursor="hand2",
                             font=("Segoe UI Semibold", 9),
                             highlightthickness=1, highlightbackground=self.BORDER)
                b.pack(side="left", padx=(0, 5))
                b.bind("<Button-1>", lambda e, kk=k: pick(kk))
                btns[k] = b
            paint()

        _chip_row("Упоминание через @", "mention_name", "mention_file", "mention", first=True)
        _chip_row("Подсветка, события, сообщения", "name", "file", "other")

        def _set_vol(v):
            snd["volume"] = int(v)

        self._ui_slider(what_card, "Громкость", 0, 100, snd["volume"], _set_vol,
                        fmt=lambda v: f"{v}%", pady=(12, 0))

        tb_row = tk.Frame(what_card, bg=self.BG_INPUT)
        tb_row.pack(fill="x", pady=(10, 0))
        for label, kind in (("▶  Упоминание", "mention"), ("▶  Остальное", "other")):
            tb = tk.Label(tb_row, text=label, bg=self.ACCENT, fg="#ffffff",
                          padx=12, pady=5, cursor="hand2", font=("Segoe UI Semibold", 9))
            tb.pack(side="left", padx=(0, 8))
            tb.bind("<Button-1>", lambda e, k=kind: _test(k))
            self._hover(tb, self.ACCENT, self.ACCENT_HOV, "#ffffff", "#ffffff")

        # ========== Вкладка 6: Ещё ==========
        more_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=16, pady=10)
        nb.add(more_tab, text="Ещё")
        more = {"tr": self.translate_on, "to": self.translate_to,
                "upd": self.check_updates}

        # ---- перевод ----
        self._ui_section(more_tab, "ПЕРЕВОД СООБЩЕНИЙ")
        tr_card = self._ui_card(more_tab)
        self._ui_toggle(tr_card, "Переводить иностранные сообщения",
                        "Google Translate, запасной — MyMemory; нужен интернет",
                        more["tr"], lambda on: more.__setitem__("tr", on))
        lang_row = tk.Frame(tr_card, bg=self.BG_INPUT)
        lang_row.pack(fill="x", pady=(10, 0))
        tk.Label(lang_row, text="На язык:", bg=self.BG_INPUT, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
        lang_btns = {}

        def _paint_lang():
            for k, b in lang_btns.items():
                on = more["to"] == k
                b.config(bg=self.ACCENT if on else self.BG_ELEV,
                         fg="#ffffff" if on else self.TEXT)

        for code, name in (("ru", "Русский"), ("en", "English"), ("uk", "Українська")):
            b = tk.Label(lang_row, text=name, padx=10, pady=3, cursor="hand2",
                         font=("Segoe UI Semibold", 9),
                         highlightthickness=1, highlightbackground=self.BORDER)
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, c=code: (more.__setitem__("to", c), _paint_lang()))
            lang_btns[code] = b
        _paint_lang()

        trt_row = tk.Frame(tr_card, bg=self.BG_INPUT)
        trt_row.pack(fill="x", pady=(10, 0))
        trt_lbl = tk.Label(trt_row, text="", bg=self.BG_INPUT, fg=self.TEXT_MUTED,
                           anchor="w", justify="left", wraplength=300,
                           font=("Segoe UI", 9))
        trt_lbl.pack(side="left", fill="x", expand=True)

        def _test_tr():
            trt_lbl.config(text="Проверяю…", fg=self.TEXT_MUTED)
            target = more["to"]
            sample = "Hello! How are you?" if target != "en" else "Привет! Как дела?"

            def work():
                try:
                    tr, lang, prov = self._translator.translate_now(sample, target)
                    msg, col = f"✓ {prov}: «{tr}»", self.OK
                except Exception as e:
                    msg, col = f"✗ {e}"[:220], self.DANGER
                try:
                    self.after(0, lambda: trt_lbl.winfo_exists() and trt_lbl.config(text=msg, fg=col))
                except Exception:
                    pass
            threading.Thread(target=work, daemon=True).start()

        trt_btn = tk.Label(trt_row, text="Проверить перевод", bg=self.BG_ELEV, fg=self.TEXT,
                           padx=10, pady=4, cursor="hand2", font=("Segoe UI Semibold", 9),
                           highlightthickness=1, highlightbackground=self.BORDER)
        trt_btn.pack(side="right")
        trt_btn.bind("<Button-1>", lambda e: _test_tr())
        if self._translator.last_error:
            trt_lbl.config(text=f"✗ {self._translator.last_error}"[:220], fg=self.DANGER)

        # ---- статистика ----
        self._ui_section(more_tab, "СТАТИСТИКА", pady=(14, 0))
        st_card = self._ui_card(more_tab)
        st_row = tk.Frame(st_card, bg=self.BG_INPUT)
        st_row.pack(fill="x")
        st_lbl = tk.Label(st_row, bg=self.BG_INPUT, fg=self.TEXT, anchor="w",
                          justify="left", font=("Segoe UI", 10))
        st_lbl.pack(side="left", fill="x", expand=True)
        st_btn = tk.Label(st_row, text="Открыть  ›", bg=self.ACCENT, fg="#ffffff",
                          padx=12, pady=5, cursor="hand2", font=("Segoe UI Semibold", 9))
        st_btn.pack(side="right")
        st_btn.bind("<Button-1>", lambda e: self._open_stats())
        self._hover(st_btn, self.ACCENT, self.ACCENT_HOV, "#ffffff", "#ffffff")

        def _st_refresh():
            if not st_lbl.winfo_exists():
                return
            st = self._stats
            st_lbl.config(text=f"{st['msgs']} сообщений · {self._stats_rate()}/мин\n"
                               f"{len(st['chatters'])} пишут · {len(st['first'])} новичков")
            st_lbl.after(3000, _st_refresh)
        _st_refresh()
        tk.Label(st_card, text="Тоже открывается кликом по счётчику в строке статуса",
                 bg=self.BG_INPUT, fg=self.TEXT_DIM, font=("Segoe UI", 8),
                 anchor="w").pack(fill="x", pady=(6, 0))

        # ---- о программе / обновления ----
        self._ui_section(more_tab, "О ПРОГРАММЕ", pady=(14, 0))
        ab_card = self._ui_card(more_tab)
        ab_row = tk.Frame(ab_card, bg=self.BG_INPUT)
        ab_row.pack(fill="x")
        tk.Label(ab_row, text=f"Chat Overlay  v{APP_VERSION} - {APP_CHANNEL}", bg=self.BG_INPUT,
                 fg=self.TEXT, font=("Segoe UI Semibold", 11)).pack(side="left")
        gh = tk.Label(ab_row, text="GitHub ↗", bg=self.BG_INPUT, fg=self.ACCENT,
                      cursor="hand2", font=("Segoe UI Semibold", 9))
        gh.pack(side="right")
        gh.bind("<Button-1>", lambda e: webbrowser.open(f"https://github.com/{GITHUB_REPO}"))
        self._ui_toggle(ab_card, "Проверять обновления при запуске",
                        "Сравнивает с последним релизом на GitHub",
                        more["upd"], lambda on: more.__setitem__("upd", on), pady=(10, 0))
        upd_row = tk.Frame(ab_card, bg=self.BG_INPUT)
        upd_row.pack(fill="x", pady=(10, 0))
        upd_lbl = tk.Label(upd_row, text="", bg=self.BG_INPUT, fg=self.TEXT_MUTED,
                           anchor="w", font=("Segoe UI", 9), cursor="hand2")
        upd_lbl.pack(side="left", fill="x", expand=True)

        def _show_update(tag, url):
            if not upd_lbl.winfo_exists():
                return
            if tag:
                upd_lbl.config(text=f"⬆ Доступна версия {tag} — открыть", fg=self.OK)
                upd_lbl.bind("<Button-1>", lambda e: webbrowser.open(url))
            elif tag == "":
                upd_lbl.config(text="✓ Установлена последняя версия", fg=self.TEXT_MUTED)
            else:
                upd_lbl.config(text="Нет релизов или сети",
                               fg=self.TEXT_DIM)

        self._update_cb = _show_update
        if self._update_info:
            _show_update(*self._update_info)

        def _check_now():
            upd_lbl.config(text="Проверяю…", fg=self.TEXT_MUTED)
            check_github_update(self.msg_queue, manual=True)

        ub = tk.Label(upd_row, text="Проверить сейчас", bg=self.BG_ELEV, fg=self.TEXT,
                      padx=10, pady=4, cursor="hand2", font=("Segoe UI Semibold", 9),
                      highlightthickness=1, highlightbackground=self.BORDER)
        ub.pack(side="right")
        ub.bind("<Button-1>", lambda e: _check_now())

        # ========== Вкладка 7: Донаты (DonationAlerts) ==========
        da_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=16, pady=10)
        nb.add(da_tab, text="Донаты")
        da = self._da
        da_opts = {"show": self.show_donations}

        self._ui_section(da_tab, "DONATIONALERTS")
        da_card = self._ui_card(da_tab)
        st_row = tk.Frame(da_card, bg=self.BG_INPUT)
        st_row.pack(fill="x")
        da_pill = tk.Label(st_row, text="", padx=10, pady=2, font=("Segoe UI Semibold", 8))
        da_pill.pack(side="left")

        def _paint_status(status=None, text=None):
            if not da_pill.winfo_exists():
                return
            status = status or da.status
            text = text or da.status_text
            col = {"on": self.OK, "error": self.DANGER}.get(status, self.TEXT_DIM)
            da_pill.config(text=f"●  {text}", fg=col, bg=_blend_color(self.BG_INPUT, col, 0.16))
            conn_btn.config(text="Отключить" if da.connected else "Подключить")

        def _entry_row(label, value, show=None):
            row = tk.Frame(da_card, bg=self.BG_INPUT)
            row.pack(fill="x", pady=(10, 0))
            tk.Label(row, text=label, bg=self.BG_INPUT, fg=self.TEXT, width=13, anchor="w",
                     font=("Segoe UI", 10)).pack(side="left")
            wrap = tk.Frame(row, bg=self.BORDER, padx=1, pady=1)
            wrap.pack(side="left", fill="x", expand=True)
            var = tk.StringVar(value=value)
            ent = tk.Entry(wrap, textvariable=var, bg=self.BG_ELEV, fg=self.TEXT, show=show or "",
                           insertbackground=self.ACCENT, relief="flat", bd=0,
                           highlightthickness=0, font=("Consolas", 10))
            ent.pack(fill="x", ipady=4, padx=8)
            ent.bind("<FocusIn>", lambda e: wrap.config(bg=self.ACCENT))
            ent.bind("<FocusOut>", lambda e: wrap.config(bg=self.BORDER))
            return var

        id_var = _entry_row("Client ID", da.cfg.get("client_id", ""))
        sec_var = _entry_row("Client secret", da.cfg.get("client_secret", ""), show="•")

        btn_row = tk.Frame(da_card, bg=self.BG_INPUT)
        btn_row.pack(fill="x", pady=(12, 0))
        da_err = tk.Label(btn_row, text="", bg=self.BG_INPUT, fg=self.DANGER,
                          font=("Segoe UI", 9), anchor="w")

        def _connect():
            if da.connected:
                da.disconnect()
                _paint_status()
                return
            cid, sec = id_var.get().strip(), sec_var.get().strip()
            if not cid.isdigit() or not sec:
                da_err.config(text="Впиши Client ID (число) и Client secret")
                return
            if not self._obs_server:
                da_err.config(text="Включи веб-страницу на вкладке OBS и нажми «Применить»")
                return
            da_err.config(text="")
            da.set_app(cid, sec)
            webbrowser.open(da.auth_url(self._da_redirect()))
            da._set_status("off", "ожидаю вход в браузере…")
            _paint_status()

        conn_btn = tk.Label(btn_row, text="Подключить", bg=self.ACCENT, fg="#ffffff",
                            padx=14, pady=6, cursor="hand2", font=("Segoe UI Semibold", 9))
        conn_btn.pack(side="left")
        conn_btn.bind("<Button-1>", lambda e: _connect())
        self._hover(conn_btn, self.ACCENT, self.ACCENT_HOV, "#ffffff", "#ffffff")

        def _test_don():
            self.msg_queue.put(("donation", {
                "id": f"test{int(time.time() * 1000)}", "username": "Тестовый донатер",
                "message": "Это тестовый донат — проверка оформления!", "amount": 150,
                "currency": "RUB", "message_type": "text"}))

        test_btn = tk.Label(btn_row, text="Тестовый донат", bg=self.BG_ELEV, fg=self.TEXT,
                            padx=10, pady=6, cursor="hand2", font=("Segoe UI Semibold", 9),
                            highlightthickness=1, highlightbackground=self.BORDER)
        test_btn.pack(side="left", padx=(8, 0))
        test_btn.bind("<Button-1>", lambda e: _test_don())
        da_err.pack(side="left", padx=(10, 0))

        self._ui_toggle(da_card, "Показывать донаты в чате и OBS",
                        "Цель и лента событий считают донаты всегда",
                        self.show_donations, lambda on: da_opts.__setitem__("show", on),
                        pady=(12, 0))

        # ---- как подключить ----
        self._ui_section(da_tab, "КАК ПОДКЛЮЧИТЬ (ОДИН РАЗ)", pady=(14, 0))
        how = self._ui_card(da_tab)
        steps = ("1. Открой donationalerts.com → Приложения и нажми «Создать»",
                 "2. В «URL перенаправления» вставь адрес ниже",
                 "3. Вставь сюда ID и Ключ API → «Подключить» → «Разрешить»")
        for t_ in steps:
            tk.Label(how, text=t_, bg=self.BG_INPUT, fg=self.TEXT_MUTED, anchor="w",
                     justify="left", font=("Segoe UI", 9)).pack(fill="x", pady=1)
        red_row = tk.Frame(how, bg=self.BG_INPUT)
        red_row.pack(fill="x", pady=(8, 0))
        red_lbl = tk.Label(red_row, text=self._da_redirect(), bg=self.BG_INPUT, fg=self.TEXT,
                           anchor="w", font=("Consolas", 9))
        red_lbl.pack(side="left", fill="x", expand=True)

        def _copy_red(e=None):
            self._copy_to_clipboard(self._da_redirect())
            cp.config(text="✓ Скопировано", fg=self.OK)
            cp.after(1500, lambda: cp.config(text="Копировать", fg=self.TEXT))

        cp = tk.Label(red_row, text="Копировать", bg=self.BG_ELEV, fg=self.TEXT, padx=10, pady=3,
                      cursor="hand2", font=("Segoe UI Semibold", 9),
                      highlightthickness=1, highlightbackground=self.BORDER)
        cp.pack(side="right")
        cp.bind("<Button-1>", _copy_red)
        op = tk.Label(how, text="Открыть страницу приложений DonationAlerts ↗", bg=self.BG_INPUT,
                      fg=self.ACCENT, cursor="hand2", anchor="w", font=("Segoe UI Semibold", 9))
        op.pack(fill="x", pady=(8, 0))
        op.bind("<Button-1>", lambda e: webbrowser.open(
            "https://www.donationalerts.com/application/clients"))

        self._da_status_cb = _paint_status
        _paint_status()

        # ========== Нижние кнопки ==========
        btns = tk.Frame(outer, bg=self.BG)
        btns.pack(fill="x", pady=(10, 0))

        err_lbl = tk.Label(btns, text="", bg=self.BG, fg=self.DANGER,
                           font=("Segoe UI", 9))
        err_lbl.pack(side="left")

        committed = {"ok": False}

        def _close():
            # закрыли без «Применить» — откатываем живое превью оформления
            if not committed["ok"]:
                try:
                    self._set_theme(orig_look["theme"])
                    self._set_alpha(orig_look["alpha"])
                    self._set_font_size(orig_look["font"])
                    if self._chroma_mode != orig_look["chroma"]:
                        self._set_chroma(orig_look["chroma"])
                    self.show_emotes = orig_look["emotes"]
                    if self.msg_style != orig_look["msg_style"]:
                        self.msg_style = orig_look["msg_style"]
                        self._configure_row_tags()
                except Exception:
                    pass
            try:
                win.destroy()
            except Exception:
                pass

        def _apply():
            err_lbl.config(text="")
            # валидация порта
            p = port_var.get().strip()
            if not p.isdigit():
                nb.select(0)
                err_lbl.config(text="Порт должен быть числом (1–65535).")
                return
            port = int(p)
            if not (1 <= port <= 65535):
                nb.select(0)
                err_lbl.config(text="Порт должен быть в диапазоне 1–65535.")
                return
            # тема / окно уже применены вживую на вкладке «Оформление»
            self._set_theme(theme_sel["key"])
            committed["ok"] = True
            # OBS
            self._apply_obs_settings(bool(enabled_var.get()), port)
            # фильтры
            self.highlight_words = list(hl_items)
            self.banned_users    = list(bu_items)
            self.banned_words    = list(bw_items)
            # стиль сообщений (уже применён вживую на вкладке «Сообщения»)
            if style_sel["key"] != self.msg_style:
                self.msg_style = style_sel["key"]
                self._configure_row_tags()
            # эмоуты
            self.show_emotes = bool(emotes_var.get())
            self.show_events = bool(chat_opts["events"])
            self.mod_sync = bool(chat_opts["mod"])
            self.show_first = bool(chat_opts["first"])
            self.hide_bots = bool(filt["bots"])
            self.hide_commands = bool(filt["cmds"])
            if chat_opts["tpe"] and not self.third_party_emotes:
                for rid in self._room_ids.values():
                    self._tpe.load_room(rid)
            self.third_party_emotes = bool(chat_opts["tpe"])
            # звук
            self.sound = dict(snd)
            # ещё
            self.translate_on = bool(more["tr"])
            self.translate_to = more["to"]
            self.check_updates = bool(more["upd"])
            self.show_donations = bool(da_opts["show"])
            if id_var.get().strip() or sec_var.get().strip():
                self._da.set_app(id_var.get(), sec_var.get())

            self._save_config()
            _close()

        cancel_btn = tk.Label(
            btns, text="Закрыть",
            bg=self.BG_INPUT, fg=self.TEXT_MUTED, padx=14, pady=8,
            cursor="hand2", font=("Segoe UI Semibold", 9),
        )
        cancel_btn.pack(side="right", padx=(10, 0))
        cancel_btn.bind("<Button-1>", lambda e: _close())
        self._hover(cancel_btn, self.BG_INPUT, self.BORDER, self.TEXT_MUTED, self.TEXT)

        apply_btn = tk.Label(
            btns, text="Применить",
            bg=self.ACCENT, fg="#ffffff", padx=14, pady=8,
            cursor="hand2", font=("Segoe UI Semibold", 9),
        )
        apply_btn.pack(side="right")
        apply_btn.bind("<Button-1>", lambda e: _apply())
        self._hover(apply_btn, self.ACCENT, self.ACCENT_HOV, "#ffffff", "#ffffff")

        win.bind("<Escape>", lambda e: _close())
        win.bind("<Return>", lambda e: _apply())
        win.protocol("WM_DELETE_WINDOW", _close)
        try:
            win.focus_force()
        except Exception:
            pass

    # ============================================================
    #          современные виджеты для окна настроек
    # ============================================================
    @staticmethod
    def _ui_round_rect(cv, x1, y1, x2, y2, r, **kw):
        """Скруглённый прямоугольник на Canvas (полигон со сглаживанием)."""
        r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return cv.create_polygon(pts, smooth=True, splinesteps=16, **kw)

    def _ui_section(self, parent, title, hint=None, pady=(0, 0)):
        row = tk.Frame(parent, bg=self.BG_ELEV)
        row.pack(fill="x", pady=pady)
        tk.Label(row, text=title, bg=self.BG_ELEV, fg=self.TEXT_DIM,
                 font=("Segoe UI Semibold", 8)).pack(side="left")
        if hint:
            tk.Label(row, text=hint, bg=self.BG_ELEV, fg=self.TEXT_DIM,
                     font=("Segoe UI", 8)).pack(side="right")
        return row

    def _ui_card(self, parent):
        """Карточка-группа: фон BG_INPUT с тонкой рамкой."""
        border = tk.Frame(parent, bg=self.BORDER, padx=1, pady=1)
        border.pack(fill="x", pady=(8, 0))
        inner = tk.Frame(border, bg=self.BG_INPUT, padx=14, pady=12)
        inner.pack(fill="x")
        return inner

    def _ui_theme_card(self, parent, key, row, col, is_selected, on_click):
        """Карточка темы с миниатюрой окна чата. Возвращает функцию redraw()."""
        t = THEMES[key]
        W, H = 104, 86
        cv = tk.Canvas(parent, width=W, height=H, bg=self.BG_ELEV,
                       highlightthickness=0, bd=0, cursor="hand2")
        cv.grid(row=row, column=col, padx=3, pady=3)
        state = {"hover": False}
        nick_cols = ("#ff7b72", "#7ee787", "#79c0ff")

        def redraw():
            cv.delete("all")
            sel = is_selected()
            outline = self.ACCENT if sel else (self.TEXT_DIM if state["hover"] else self.BORDER)
            self._ui_round_rect(cv, 1, 1, W - 1, H - 1, 10, fill=self.BG_INPUT,
                                outline=outline, width=2 if sel else 1)
            # мини-окно
            x1, y1, x2, y2 = 7, 7, W - 7, 60
            self._ui_round_rect(cv, x1, y1, x2, y2, 6, fill=t["BG"], outline=t["BORDER"])
            cv.create_rectangle(x1 + 1, y1 + 5, x2 - 1, y1 + 12, fill=t["BG_HEADER"], width=0)
            self._ui_round_rect(cv, x1 + 1, y1 + 1, x2 - 1, y1 + 12, 5, fill=t["BG_HEADER"], outline="")
            cv.create_oval(x1 + 5, y1 + 4, x1 + 10, y1 + 9, fill=t["ACCENT"], width=0)
            cv.create_rectangle(x1 + 14, y1 + 6, x1 + 38, y1 + 7, fill=t["TEXT_MUTED"], width=0)
            self._ui_round_rect(cv, x2 - 19, y1 + 3, x2 - 5, y1 + 10, 3, fill=t["ACCENT"], outline="")
            # строки чата
            for j, (nw, tw) in enumerate(((14, 40), (19, 28), (11, 46))):
                yy = y1 + 18 + j * 11
                self._ui_round_rect(cv, x1 + 4, yy - 3, x2 - 4, yy + 6, 3,
                                    fill=t["BG_ELEV"], outline="")
                cv.create_rectangle(x1 + 7, yy, x1 + 7 + nw, yy + 3,
                                    fill=nick_cols[j], width=0)
                cv.create_rectangle(x1 + 10 + nw, yy, min(x2 - 7, x1 + 10 + nw + tw), yy + 3,
                                    fill=t["TEXT_MUTED"], width=0)
            # подпись
            cv.create_text(9, 73, text=t["name"], anchor="w", fill=self.TEXT,
                           font=("Segoe UI Semibold", 8))
            if sel:
                cv.create_oval(W - 22, 65, W - 7, 80, fill=self.ACCENT, width=0)
                cv.create_text(W - 14.5, 72.5, text="✓", fill="#ffffff",
                               font=("Segoe UI Symbol", 8, "bold"))
            else:
                cv.create_oval(W - 18, 69, W - 10, 77, fill=t["ACCENT"], width=0)

        def _enter(e):
            state["hover"] = True
            redraw()

        def _leave(e):
            state["hover"] = False
            redraw()

        cv.bind("<Enter>", _enter)
        cv.bind("<Leave>", _leave)
        cv.bind("<Button-1>", lambda e: on_click())
        redraw()
        return redraw

    def _ui_slider(self, parent, label, lo, hi, value, on_change,
                   fmt=str, pady=(0, 0)):
        """Плоский слайдер: заполненная дорожка + круглый ползунок."""
        box = tk.Frame(parent, bg=self.BG_INPUT)
        box.pack(fill="x", pady=pady)
        head = tk.Frame(box, bg=self.BG_INPUT)
        head.pack(fill="x")
        tk.Label(head, text=label, bg=self.BG_INPUT, fg=self.TEXT,
                 font=("Segoe UI", 10)).pack(side="left")
        val_lbl = tk.Label(head, text=fmt(value), bg=self.BG_INPUT, fg=self.ACCENT,
                           font=("Segoe UI Semibold", 10))
        val_lbl.pack(side="right")

        H, R, PAD = 22, 7, 8
        cv = tk.Canvas(box, height=H, bg=self.BG_INPUT, highlightthickness=0,
                       bd=0, cursor="hand2")
        cv.pack(fill="x", pady=(4, 0))
        st = {"v": int(value), "drag": False}

        def _x_for(v):
            w = max(cv.winfo_width(), 2 * PAD + 1)
            return PAD + (w - 2 * PAD) * (v - lo) / max(1, hi - lo)

        def redraw(*_):
            cv.delete("all")
            w = max(cv.winfo_width(), 2 * PAD + 1)
            cy = H / 2
            self._ui_round_rect(cv, PAD, cy - 2, w - PAD, cy + 2, 2,
                                fill=self.BORDER, outline="")
            x = _x_for(st["v"])
            self._ui_round_rect(cv, PAD, cy - 2, max(PAD + 4, x), cy + 2, 2,
                                fill=self.ACCENT, outline="")
            r = R + (1 if st["drag"] else 0)
            cv.create_oval(x - r - 3, cy - r - 3, x + r + 3, cy + r + 3,
                           fill=_blend_color(self.BG_INPUT, self.ACCENT, 0.25), width=0)
            cv.create_oval(x - r, cy - r, x + r, cy + r, fill="#ffffff",
                           outline=self.ACCENT, width=2)

        def _set_from_x(x):
            w = max(cv.winfo_width(), 2 * PAD + 1)
            frac = (x - PAD) / max(1, w - 2 * PAD)
            v = int(round(lo + max(0.0, min(1.0, frac)) * (hi - lo)))
            if v != st["v"]:
                st["v"] = v
                val_lbl.config(text=fmt(v))
                try:
                    on_change(v)
                except Exception:
                    pass
            redraw()

        def _down(e):
            st["drag"] = True
            _set_from_x(e.x)

        def _up(e):
            st["drag"] = False
            redraw()

        def _wheel(e):
            step = 1 if getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4 else -1
            _set_from_x(_x_for(max(lo, min(hi, st["v"] + step))))

        cv.bind("<Configure>", redraw)
        cv.bind("<Button-1>", _down)
        cv.bind("<B1-Motion>", lambda e: _set_from_x(e.x))
        cv.bind("<ButtonRelease-1>", _up)
        cv.bind("<MouseWheel>", _wheel)
        cv.bind("<Button-4>", _wheel)
        cv.bind("<Button-5>", _wheel)
        return box

    def _ui_toggle(self, parent, label, hint, value, on_change,
                   enabled=True, pady=(0, 0)):
        """Переключатель-«таблетка» с подписью и подсказкой."""
        row = tk.Frame(parent, bg=self.BG_INPUT)
        row.pack(fill="x", pady=pady)
        W, H = 40, 22
        cv = tk.Canvas(row, width=W, height=H, bg=self.BG_INPUT,
                       highlightthickness=0, bd=0,
                       cursor="hand2" if enabled else "arrow")
        cv.pack(side="right", padx=(10, 0))
        txt = tk.Frame(row, bg=self.BG_INPUT)
        txt.pack(side="left", fill="x", expand=True)
        tk.Label(txt, text=label, bg=self.BG_INPUT,
                 fg=self.TEXT if enabled else self.TEXT_DIM, anchor="w",
                 font=("Segoe UI", 10)).pack(fill="x")
        if hint:
            tk.Label(txt, text=hint, bg=self.BG_INPUT, fg=self.TEXT_DIM,
                     anchor="w", font=("Segoe UI", 8)).pack(fill="x")

        st = {"on": bool(value)}

        def redraw():
            cv.delete("all")
            on = st["on"] and enabled
            fill = self.ACCENT if on else self.BG_ELEV
            self._ui_round_rect(cv, 1, 1, W - 1, H - 1, H / 2, fill=fill,
                                outline=self.ACCENT if on else self.BORDER)
            k = 8
            cx = W - 1 - H / 2 if on else 1 + H / 2
            cv.create_oval(cx - k, H / 2 - k, cx + k, H / 2 + k,
                           fill="#ffffff" if on else self.TEXT_DIM, width=0)

        def _click(e):
            if not enabled:
                return
            st["on"] = not st["on"]
            redraw()
            try:
                on_change(st["on"])
            except Exception:
                pass

        cv.bind("<Button-1>", _click)
        redraw()
        return row

    def _ui_chip_list(self, parent, title, icon, color, hint, placeholder,
                      initial, normalize):
        """Карточка со списком-«чипсами»: поле ввода + теги с крестиком.
        Возвращает живой list, который меняется по мере редактирования."""
        items: list[str] = []
        for w in initial:
            w = normalize(str(w))
            if w and w not in items:
                items.append(w)

        border = tk.Frame(parent, bg=self.BORDER, padx=1, pady=1)
        border.pack(fill="x", pady=(10, 0))
        card = tk.Frame(border, bg=self.BG_INPUT, padx=12, pady=8)
        card.pack(fill="x")

        # ---- шапка: иконка, заголовок, счётчик ----
        head = tk.Frame(card, bg=self.BG_INPUT)
        head.pack(fill="x")
        ic = tk.Canvas(head, width=26, height=26, bg=self.BG_INPUT,
                       highlightthickness=0, bd=0)
        ic.pack(side="left")
        self._ui_round_rect(ic, 0, 0, 26, 26, 7,
                            fill=_blend_color(self.BG_INPUT, color, 0.22), outline="")
        ic.create_text(13, 13, text=icon, fill=color,
                       font=("Segoe UI Symbol", 11, "bold"))
        count = tk.Label(head, text="", bg=_blend_color(self.BG_INPUT, color, 0.18),
                         fg=color, padx=8, pady=1, font=("Segoe UI Semibold", 8))
        count.pack(side="right", anchor="n")
        ttl = tk.Frame(head, bg=self.BG_INPUT)
        ttl.pack(side="left", fill="x", expand=True, padx=(10, 0))
        tk.Label(ttl, text=title, bg=self.BG_INPUT, fg=self.TEXT, anchor="w",
                 font=("Segoe UI Semibold", 10)).pack(fill="x")
        tk.Label(ttl, text=hint, bg=self.BG_INPUT, fg=self.TEXT_DIM, anchor="w",
                 font=("Segoe UI", 8)).pack(fill="x")

        # ---- поле ввода + кнопка ----
        row = tk.Frame(card, bg=self.BG_INPUT)
        row.pack(fill="x", pady=(8, 0))
        ent_wrap = tk.Frame(row, bg=self.BORDER, padx=1, pady=1)
        ent_wrap.pack(side="left", fill="x", expand=True)
        ent_in = tk.Frame(ent_wrap, bg=self.BG_ELEV)
        ent_in.pack(fill="x")
        ent = tk.Entry(ent_in, bg=self.BG_ELEV, fg=self.TEXT_DIM,
                       insertbackground=color, relief="flat", bd=0,
                       highlightthickness=0, font=("Segoe UI", 10))
        ent.pack(fill="x", ipady=4, padx=9)
        ent.insert(0, placeholder)
        ph = {"on": True}

        def _focus_in(e):
            ent_wrap.config(bg=color)
            if ph["on"]:
                ent.delete(0, "end")
                ent.config(fg=self.TEXT)
                ph["on"] = False

        def _focus_out(e):
            ent_wrap.config(bg=self.BORDER)
            if not ent.get().strip():
                ent.delete(0, "end")
                ent.insert(0, placeholder)
                ent.config(fg=self.TEXT_DIM)
                ph["on"] = True

        ent.bind("<FocusIn>", _focus_in)
        ent.bind("<FocusOut>", _focus_out)

        add_btn = tk.Label(row, text="＋", bg=color, fg="#ffffff" if color != self.WARN else "#1a1300",
                           width=3, pady=4, cursor="hand2",
                           font=("Segoe UI Semibold", 11))
        add_btn.pack(side="left", padx=(8, 0))
        add_hov = _blend_color(color, "#ffffff", 0.18)
        add_btn.bind("<Enter>", lambda e: add_btn.config(bg=add_hov))
        add_btn.bind("<Leave>", lambda e: add_btn.config(bg=color))

        # ---- чипсы: Text-виджет сам переносит встроенные окна по строкам ----
        holder = tk.Frame(card, bg=self.BG_INPUT, height=30)
        holder.pack(fill="x", pady=(8, 0))
        holder.pack_propagate(False)
        chips = tk.Text(holder, height=1, bg=self.BG_INPUT, relief="flat", bd=0,
                        wrap="char", cursor="arrow", padx=0, pady=2,
                        spacing1=3, spacing3=3, highlightthickness=0,
                        font=("Segoe UI", 9), fg=self.TEXT_DIM,
                        selectbackground=self.BG_INPUT, takefocus=0)
        chips.pack(fill="both", expand=True)
        chip_bg = _blend_color(self.BG_INPUT, color, 0.16)
        chip_hov = _blend_color(self.BG_INPUT, color, 0.30)

        def _remove(word):
            if word in items:
                items.remove(word)
                render()

        def _make_chip(word):
            chip = tk.Frame(chips, bg=chip_bg, padx=8, pady=2, cursor="arrow")
            tk.Label(chip, text=word, bg=chip_bg, fg=self.TEXT,
                     font=("Segoe UI", 9)).pack(side="left")
            x = tk.Label(chip, text="×", bg=chip_bg, fg=self.TEXT_MUTED,
                         cursor="hand2", padx=0, font=("Segoe UI", 10, "bold"))
            x.pack(side="left", padx=(6, 0))
            x.bind("<Button-1>", lambda e, w=word: _remove(w))

            def _hover(on):
                c = chip_hov if on else chip_bg
                chip.config(bg=c)
                for ch in chip.winfo_children():
                    ch.config(bg=c)
                x.config(fg=color if on else self.TEXT_MUTED)

            for wdg in (chip, *chip.winfo_children()):
                wdg.bind("<Enter>", lambda e: _hover(True), add="+")
                wdg.bind("<Leave>", lambda e: _hover(False), add="+")
            return chip

        def render():
            chips.config(state="normal")
            for w in chips.window_names():
                try:
                    chips.nametowidget(w).destroy()
                except Exception:
                    pass
            chips.delete("1.0", "end")
            if not items:
                chips.insert("end", "Список пуст")
            for w in items:
                chips.window_create("end", window=_make_chip(w), padx=3, pady=1)
            chips.config(state="disabled")
            count.config(text=str(len(items)))
            fit_height()
            # встроенные окна получают размер после отрисовки — пересчитаем ещё раз
            chips.after(60, fit_height)
            chips.after(250, fit_height)

        def fit_height(e=None):
            # высота по содержимому: до двух рядов чипсов, дальше — колёсико
            try:
                chips.update_idletasks()
                px = chips.count("1.0", "end", "ypixels")[0] or 26
            except Exception:
                px = 26
            h = max(26, min(60, int(px) + 2))
            if int(holder.cget("height")) != h:
                holder.config(height=h)

        def scroll_to_last():
            try:
                n = chips.count("1.0", "end", "displaylines")[0] or 1
                chips.yview_moveto(0)
                if n > 2:
                    chips.yview_scroll(n - 2, "units")
            except Exception:
                pass

        def _add(e=None):
            if ph["on"]:
                return "break"
            raw = ent.get()
            changed = False
            for part in re.split(r"[,\n;]+", raw):
                w = normalize(part)
                if w and w not in items:
                    items.append(w)
                    changed = True
            ent.delete(0, "end")
            if changed:
                render()
                # прокрутка к последнему ряду с выравниванием по началу строки
                chips.after(300, scroll_to_last)
            return "break"   # не даём Enter закрыть окно настроек

        ent.bind("<Return>", _add)
        ent.bind("<KP_Enter>", _add)
        add_btn.bind("<Button-1>", lambda e: (ent.focus_set(), _add()))

        def _wheel(e):
            chips.yview_scroll(-1 if getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4 else 1, "units")
            return "break"

        chips.bind("<Configure>", lambda e: chips.after_idle(fit_height), add="+")
        chips.bind("<MouseWheel>", _wheel)
        chips.bind("<Button-4>", _wheel)
        chips.bind("<Button-5>", _wheel)
        render()
        return items

    _STYLE_HINTS = {
        "none":   "Только текст",
        "card":   "На карточке",
        "stripe": "Полосы через одну",
        "glow":   "Фон цветом акцента",
        "pill":   "Плашка с отступом",
    }

    def _ui_style_card(self, parent, key, row, col, is_selected, on_click):
        """Карточка стиля подложки с мини-чатом в этом стиле."""
        W, H = 134, 100
        cv = tk.Canvas(parent, width=W, height=H, bg=self.BG_ELEV,
                       highlightthickness=0, bd=0, cursor="hand2")
        cv.grid(row=row, column=col, padx=3, pady=3, sticky="w")
        state = {"hover": False}
        nick_cols = ("#ff7b72", "#7ee787", "#79c0ff")
        rows = ((16, 44), (22, 30), (13, 52))

        def redraw():
            cv.delete("all")
            sel = is_selected()
            outline = self.ACCENT if sel else (self.TEXT_DIM if state["hover"] else self.BORDER)
            self._ui_round_rect(cv, 1, 1, W - 1, H - 1, 10, fill=self.BG_INPUT,
                                outline=outline, width=2 if sel else 1)
            # область чата в цветах текущей темы
            x1, y1, x2, y2 = 7, 7, W - 7, 60
            self._ui_round_rect(cv, x1, y1, x2, y2, 6, fill=self.BG, outline=self.BORDER)
            n = len(rows)
            rh = (y2 - y1 - 8) / n
            for j, (nw, tw) in enumerate(rows):
                top = y1 + 4 + j * rh
                bot = top + rh - 2
                lx = x1 + 6
                if key == "card":
                    self._ui_round_rect(cv, x1 + 4, top + 1, x2 - 4, bot, 3,
                                        fill=self.BG_ELEV, outline="")
                    lx = x1 + 10
                elif key == "stripe":
                    cv.create_rectangle(x1 + 1, top, x2 - 1, bot + 1,
                                        fill=self.BG_ELEV if j % 2 == 0 else self.BG, width=0)
                elif key == "glow":
                    a = 0.18 if j % 2 == 0 else 0.09
                    self._ui_round_rect(cv, x1 + 3, top + 1, x2 - 3, bot, 3,
                                        fill=_blend_color(self.BG, self.ACCENT, a), outline="")
                    lx = x1 + 9
                elif key == "pill":
                    self._ui_round_rect(cv, x1 + 14, top + 1, x2 - 4, bot, (bot - top) / 2,
                                        fill=_blend_color(self.BG_ELEV, self.ACCENT, 0.24), outline="")
                    lx = x1 + 22
                cy = (top + bot) / 2
                cv.create_rectangle(lx, cy - 1, lx + 10, cy + 1, fill=self.TEXT_DIM, width=0)
                cv.create_rectangle(lx + 14, cy - 2, lx + 14 + nw, cy + 2,
                                    fill=nick_cols[j], width=0)
                cv.create_rectangle(lx + 18 + nw, cy - 1.5,
                                    min(x2 - 10, lx + 18 + nw + tw), cy + 1.5,
                                    fill=self.TEXT_MUTED, width=0)
            # подписи
            cv.create_text(10, 73, text=MSG_STYLES.get(key, key), anchor="w",
                           fill=self.TEXT, font=("Segoe UI Semibold", 9))
            cv.create_text(10, 88, text=self._STYLE_HINTS.get(key, ""), anchor="w",
                           fill=self.TEXT_DIM, font=("Segoe UI", 8))
            if sel:
                cv.create_oval(W - 23, 65, W - 8, 80, fill=self.ACCENT, width=0)
                cv.create_text(W - 15.5, 72.5, text="✓", fill="#ffffff",
                               font=("Segoe UI Symbol", 8, "bold"))

        def _hover(on):
            state["hover"] = on
            redraw()

        cv.bind("<Enter>", lambda e: _hover(True))
        cv.bind("<Leave>", lambda e: _hover(False))
        cv.bind("<Button-1>", lambda e: on_click())
        redraw()
        return redraw

    def _set_theme(self, key: str):
        """Применить тему к окну оверлея сразу (используется для превью)."""
        global PALETTE
        if key not in THEMES or key == self.theme_name:
            return
        self.theme_name = key
        PALETTE = THEMES[key]
        self._apply_theme_values(THEMES[key])
        self._apply_theme_runtime()
        # тема сбрасывает фон текста — восстанавливаем chroma-режим
        if self._chroma_mode and IS_WIN:
            try:
                self.configure(bg=self.CHROMA)
                self.text.config(bg=self.CHROMA)
                self.text.tag_configure("msg", foreground="#ffffff")
                self.chroma_btn.config(fg=self.ACCENT)
            except Exception:
                pass

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
        self.count_lbl.config(cursor="hand2")
        self.update_lbl = tk.Label(bar, text="", bg=self.BG_ELEV, fg=self.ACCENT,
                                   font=("Segoe UI Semibold", 8), cursor="hand2", padx=6)
        self.update_lbl.bind("<Button-1>", lambda e: webbrowser.open(
            (self._update_info or ("", f"https://github.com/{GITHUB_REPO}/releases"))[1]))
        self.count_lbl.bind("<Button-1>", lambda e: self._open_stats())
        self._msg_count = 0
        self.after(5000, self._tick_count_lbl)

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
        # ПКМ по сообщению: на экран OBS / копировать / скрыть пользователя
        self.text.bind("<Button-3>", self._on_chat_menu)

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

        self.text.tag_configure("system",         foreground=self.TEXT_MUTED,
                                font=self.fnt_sys, spacing1=4, spacing3=4)
        self.text.tag_configure("time",           foreground=self.TEXT_DIM,
                                font=self.fnt_time)
        self.text.tag_configure("colon",          foreground=self.TEXT_DIM)
        self.text.tag_configure("msg",            foreground=self.TEXT)
        self.text.tag_configure("highlight_mark", foreground=self.WARN,
                                font=self.fnt_bold)
        self.text.tag_configure("highlight_msg",  foreground="#ffffff")
        for c in self.NICK_COLORS:
            self.text.tag_configure(f"nick_{c}", foreground=c, font=self.fnt_bold)
        # подложки строк (будут перенастроены после __init__)
        self._configure_row_tags()

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
                err = str(e)
                self.after(500, lambda: self._log_system(
                    f"Не удалось зарегистрировать глобальные хоткеи: {err}"))

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
        saved_channels = [
            {"channel": c["channel"], "platform": c["platform"]}
            for c in self._ch_list
        ]
        data = {
            "alpha": self.alpha,
            "geometry": self.geometry(),
            "chroma": self._chroma_mode,
            "font_size": self.font_size,
            "theme": self.theme_name,
            "obs_web_enabled": self._obs_enabled,
            "obs_web_port": self._obs_port,
            # backward compat
            "last_channel":  self.channel,
            "last_platform": self.platform,
            # новый формат
            "channels": saved_channels,
            "msg_style": self.msg_style,
            "show_emotes": self.show_emotes,
            "third_party_emotes": self.third_party_emotes,
            "show_events": self.show_events,
            "mod_sync": self.mod_sync,
            "hide_bots": self.hide_bots,
            "hide_commands": self.hide_commands,
            "show_first": self.show_first,
            "translate_enabled": self.translate_on,
            "translate_to": self.translate_to,
            "check_updates": self.check_updates,
            "show_donations": self.show_donations,
            "sound_enabled": self.sound["enabled"],
            "sound_hl": self.sound["hl"],
            "sound_events": self.sound["events"],
            "sound_all": self.sound["all"],
            "sound_name": self.sound["name"],
            "sound_file": self.sound["file"],
            "sound_volume": self.sound["volume"],
            "sound_mention": self.sound["mention"],
            "sound_mention_name": self.sound["mention_name"],
            "sound_mention_file": self.sound["mention_file"],
            "my_nick": self.sound["my_nick"],
            "highlight_words": self.highlight_words,
            "banned_users": self.banned_users,
            "banned_words": self.banned_words,
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

    # ============================================================
    #              вспомогательные методы платформы
    # ============================================================
    YT_RED = "#ff0000"

    def _platform_dot_color(self) -> str:
        plat = self._ch_list[0]["platform"] if self._ch_list else self.platform
        return self.YT_RED if plat == "youtube" else self.ACCENT

    def _header_title(self) -> str:
        n = len(self._ch_list)
        if n == 0:
            return "Chat Overlay"
        if n == 1:
            c = self._ch_list[0]
            if c["platform"] == "youtube":
                return f"YouTube  ·  {c['channel']}"
            return f"Twitch  ·  #{c['channel']}"
        # 2+ каналов: перечисляем первые три
        parts = []
        for c in self._ch_list[:3]:
            if c["platform"] == "youtube":
                parts.append("YT")
            else:
                parts.append(f"#{c['channel'][:8]}")
        title = " · ".join(parts)
        if n > 3:
            title += f" +{n - 3}"
        return title

    def _win_title(self) -> str:
        n = len(self._ch_list)
        if n == 0:
            return "Chat Overlay"
        if n == 1:
            c = self._ch_list[0]
            if c["platform"] == "youtube":
                return f"YouTube Chat — {c['channel']}"
            return f"Twitch Chat — #{c['channel']}"
        return f"Chat Overlay — {n} каналов"

    def _make_reader(self, channel: str, platform: str, msg_q=None):
        q = msg_q if msg_q is not None else self.msg_queue
        if platform == "youtube":
            return YouTubeChat(channel, q)
        return TwitchIRC(channel, q)

    # ============================================================
    #                       мульти-чат
    # ============================================================

    def _ch_idx(self, tag: str) -> int:
        for i, c in enumerate(self._ch_list):
            if c["tag"] == tag:
                return i
        return 0

    def _tag_label(self, tag: str) -> str:
        """Короткое отображаемое имя канала для бейджа источника."""
        platform, _, channel = tag.partition(":")
        if platform == "youtube":
            return "YT"
        return channel[:9]

    def _ch_color(self, idx: int) -> str:
        return self.CHANNEL_TAG_COLORS[idx % len(self.CHANNEL_TAG_COLORS)]

    def _src_tk_tag(self, tag: str) -> str:
        return f"src_{self._ch_idx(tag)}"

    def _register_channel_tags(self, idx: int):
        """Регистрирует tk-теги цвета источника для канала с индексом idx."""
        color = self._ch_color(idx)
        try:
            self.text.tag_configure(
                f"src_{idx}",
                foreground=color,
                font=tkfont.Font(
                    family="Segoe UI", size=max(8, self.font_size - 1)
                ),
            )
        except Exception:
            pass

    def _add_channel(self, channel: str, platform: str):
        """Добавляет канал в объединённый поток."""
        tag = f"{platform}:{channel}"
        if tag in self._readers:
            self._log_system(f"Канал уже подключён: {channel}")
            return
        idx = len(self._ch_list)
        self._ch_list.append({
            "channel":  channel,
            "platform": platform,
            "tag":      tag,
            "idx":      idx,
        })
        self._statuses[tag] = "offline"

        # обновляем primary-атрибуты при первом канале
        if idx == 0:
            self.channel  = channel
            self.platform = platform

        self._register_channel_tags(idx)
        # Перенастраиваем фоны: стиль "glow" использует per-канальные
        # теги row_ch_{i}_{sfx}, которые создаются именно здесь.
        # Без этого после добавления 2-го канала в мульти-чате
        # подложки в режиме "glow" не накладываются.
        self._configure_row_tags()
        self._update_header_title()

        tagged_q = _TaggedQueue(self.msg_queue, tag)
        reader = self._make_reader(channel, platform, tagged_q)
        self._readers[tag] = reader
        reader.start()

        if idx > 0:
            # системное сообщение о добавлении (для второго+ канала)
            plat_str = "YouTube" if platform == "youtube" else "Twitch"
            self._log_system(f"+ {plat_str} · {channel}")
        self._save_config()

    def _remove_channel(self, tag: str):
        """Отключает и удаляет канал из потока."""
        reader = self._readers.pop(tag, None)
        if reader:
            try:
                reader.stop()
            except Exception:
                pass
        self._statuses.pop(tag, None)
        self._ch_list = [c for c in self._ch_list if c["tag"] != tag]
        # переиндексируем idx
        for i, c in enumerate(self._ch_list):
            c["idx"] = i
        # обновляем primary
        if self._ch_list:
            self.channel  = self._ch_list[0]["channel"]
            self.platform = self._ch_list[0]["platform"]
        # Перенастраиваем фоны: per-канальные glow-теги зависят от
        # текущего состава _ch_list. После удаления канала нужно
        # пересоздать row_ch_{i}_{sfx} под новые индексы.
        self._configure_row_tags()
        self._update_header_title()
        self._update_status_bar()
        self._save_config()

    def _update_header_title(self):
        try:
            self.title_lbl.config(text=self._header_title())
            self.logo_dot.config(fg=self._platform_dot_color())
            self.title(self._win_title())
        except Exception:
            pass

    def _update_status_bar(self):
        """Обновляет статус-бар на основе статусов всех каналов."""
        if not self._statuses:
            self._set_status_raw("offline", "нет каналов")
            return
        vals       = list(self._statuses.values())
        online_cnt = vals.count("online")
        total      = len(vals)
        if online_cnt == total:
            ch_names = " · ".join(
                ("YT" if c["platform"] == "youtube"
                 else f"#{c['channel']}")
                for c in self._ch_list
            )
            self._set_status_raw("online", f"подключено · {ch_names}")
        elif online_cnt > 0:
            self._set_status_raw("warn",
                                 f"подключено {online_cnt}/{total}")
        else:
            self._set_status_raw("offline", "не подключено")

    def _set_status_raw(self, state: str, text: str):
        color_map = {"online": self.OK, "warn": self.WARN}
        self.status_dot.config(
            fg=color_map.get(state, self.DANGER)
        )
        self.status_lbl.config(text=text)

    def _set_channel_status(self, tag: str, state: str):
        if tag in self._statuses:
            self._statuses[tag] = state
        self._update_status_bar()

    def _manage_channels(self):
        """Диалог управления каналами мульти-чата (добавить / удалить)."""
        win = tk.Toplevel(self)
        win.title("Каналы")
        win.configure(bg=self.BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        try:
            if IS_WIN and os.path.exists(self.ICON_ICO):
                win.iconbitmap(default=self.ICON_ICO)
            if self._tk_icon is not None:
                win.iconphoto(True, self._tk_icon)
        except Exception:
            pass
        try:
            w, h = 390, 310
            px = self.winfo_rootx() + self.winfo_width() // 2
            py = self.winfo_rooty() + self.winfo_height() // 2
            win.geometry(f"{w}x{h}+{px - w // 2}+{py - h // 2}")
        except Exception:
            pass

        outer = tk.Frame(win, bg=self.BG, padx=14, pady=12)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="Подключённые каналы",
                 bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w",
                                                       pady=(0, 10))

        list_frame = tk.Frame(outer, bg=self.BG_ELEV, padx=6, pady=6)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))

        row_widgets: list = []

        def _refresh():
            for w in row_widgets:
                try:
                    w.destroy()
                except Exception:
                    pass
            row_widgets.clear()

            if not self._ch_list:
                lbl = tk.Label(
                    list_frame,
                    text="Нет каналов. Нажмите «+ Добавить».",
                    bg=self.BG_ELEV, fg=self.TEXT_MUTED,
                    font=("Segoe UI", 9))
                lbl.pack(padx=8, pady=10)
                row_widgets.append(lbl)
                return

            for ch_info in list(self._ch_list):
                tag_  = ch_info["tag"]
                idx   = ch_info["idx"]
                plat  = ch_info["platform"]
                name  = ch_info["channel"]
                color = self._ch_color(idx)
                state = self._statuses.get(tag_, "offline")

                row = tk.Frame(list_frame, bg=self.BG_ELEV)
                row.pack(fill="x", pady=3)
                row_widgets.append(row)

                tk.Label(row, text="●", bg=self.BG_ELEV, fg=color,
                         font=("Segoe UI", 11)).pack(side="left",
                                                      padx=(2, 6))

                plat_lbl = "YT" if plat == "youtube" else "T"
                disp_name = name if len(name) <= 30 else name[:27] + "..."
                tk.Label(row,
                         text=f"[{plat_lbl}]  {disp_name}",
                         bg=self.BG_ELEV, fg=self.TEXT,
                         font=("Segoe UI", 10),
                         anchor="w").pack(side="left",
                                          fill="x", expand=True)

                dot_color = self.OK if state == "online" else self.DANGER
                tk.Label(row, text=state,
                         bg=self.BG_ELEV, fg=dot_color,
                         font=("Segoe UI", 8)).pack(side="left", padx=8)

                def _make_remove(t=tag_):
                    def _do():
                        self._remove_channel(t)
                        _refresh()
                    return _do

                rm = tk.Label(row, text="✕",
                              bg=self.BG_ELEV, fg=self.TEXT_DIM,
                              font=("Segoe UI Symbol", 10),
                              cursor="hand2", padx=8)
                rm.pack(side="right")
                rm.bind("<Button-1>", lambda e, fn=_make_remove(): fn())
                self._hover(rm, self.BG_ELEV, self.BG_INPUT,
                            self.TEXT_DIM, self.DANGER)

        _refresh()

        # ── кнопки ──
        btns = tk.Frame(outer, bg=self.BG)
        btns.pack(fill="x")

        def _add_new():
            res = ask_channel(parent=win, title="Добавить канал",
                              platform=self.platform)
            if not res:
                return
            self._add_channel(res["channel"], res["platform"])
            _refresh()

        add_btn = tk.Label(
            btns, text="+ Добавить",
            bg=self.ACCENT, fg="#ffffff",
            padx=14, pady=7,
            cursor="hand2", font=("Segoe UI Semibold", 9))
        add_btn.pack(side="left")
        add_btn.bind("<Button-1>", lambda e: _add_new())
        self._hover(add_btn, self.ACCENT, self.ACCENT_HOV, "#ffffff", "#ffffff")

        close_btn = tk.Label(
            btns, text="Закрыть",
            bg=self.BG_INPUT, fg=self.TEXT_MUTED,
            padx=14, pady=7,
            cursor="hand2", font=("Segoe UI Semibold", 9))
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: win.destroy())
        self._hover(close_btn, self.BG_INPUT, self.BORDER,
                    self.TEXT_MUTED, self.TEXT)

        win.bind("<Escape>", lambda e: win.destroy())

    # ============================================================
    #                   стиль подложки сообщений
    # ============================================================

    def _configure_row_tags(self):
        """Настраивает tk-теги фоновых подложек по текущему msg_style."""
        style  = self.msg_style
        BG     = self.BG
        BG_E   = self.BG_ELEV

        if style == "none":
            for tn in ("row_even", "row_odd"):
                self.text.tag_configure(
                    tn, background="",
                    spacing1=2, spacing3=2,
                    lmargin1=0, lmargin2=0)

        elif style == "card":
            for tn in ("row_even", "row_odd"):
                self.text.tag_configure(
                    tn, background=BG_E,
                    spacing1=7, spacing3=7,
                    lmargin1=10, lmargin2=10)

        elif style == "stripe":
            self.text.tag_configure(
                "row_even", background=BG_E,
                spacing1=5, spacing3=5,
                lmargin1=0, lmargin2=0)
            self.text.tag_configure(
                "row_odd",  background=BG,
                spacing1=5, spacing3=5,
                lmargin1=0, lmargin2=0)

        elif style == "glow":
            g1 = _blend_color(BG, self.ACCENT, 0.14)
            g2 = _blend_color(BG, self.ACCENT, 0.07)
            self.text.tag_configure(
                "row_even", background=g1,
                spacing1=6, spacing3=6,
                lmargin1=8, lmargin2=8)
            self.text.tag_configure(
                "row_odd",  background=g2,
                spacing1=6, spacing3=6,
                lmargin1=8, lmargin2=8)
            # multi-chat: per-channel glow tags
            for i, ch in enumerate(self._ch_list):
                col = self._ch_color(i)
                for sfx, a in (("even", 0.14), ("odd", 0.07)):
                    self.text.tag_configure(
                        f"row_ch_{i}_{sfx}",
                        background=_blend_color(BG, col, a),
                        spacing1=6, spacing3=6,
                        lmargin1=8, lmargin2=8)

        elif style == "pill":
            pill = _blend_color(BG_E, self.ACCENT, 0.20)
            for tn in ("row_even", "row_odd"):
                self.text.tag_configure(
                    tn, background=pill,
                    spacing1=8, spacing3=8,
                    lmargin1=20, lmargin2=20)

        # события канала — под текущую тему/стиль
        try:
            self._ensure_event_tags()
        except Exception:
            pass

        # подсвеченные сообщения — тёплый фон цветом WARN поверх стиля
        try:
            self.text.tag_configure(
                "row_hl",
                background=_blend_color(BG, self.WARN, 0.22),
                **{k: self.text.tag_cget("row_even", k) or 0 for k in
                   ("spacing1", "spacing3", "lmargin1", "lmargin2")})
        except Exception:
            pass

        try:
            self.text.tag_configure(
                "row_first",
                background=_blend_color(BG, self.OK, 0.18),
                **{k: self.text.tag_cget("row_even", k) or 0 for k in
                   ("spacing1", "spacing3", "lmargin1", "lmargin2")})
            self.text.tag_configure("first_mark", foreground=self.OK,
                                    font=self.fnt_time)
        except Exception:
            pass

        # per-канальные теги (из стиля «glow») приводим к текущему стилю
        if style != "glow":
            for i in range(len(self._ch_list)):
                for sfx in ("even", "odd"):
                    try:
                        src = f"row_{sfx}"
                        self.text.tag_configure(
                            f"row_ch_{i}_{sfx}",
                            **{k: self.text.tag_cget(src, k) for k in
                               ("background", "spacing1", "spacing3",
                                "lmargin1", "lmargin2")})
                    except Exception:
                        pass

    def _get_row_tag(self, channel_tag: str) -> str | None:
        """Возвращает имя tk-тега подложки для данного сообщения."""
        style = self.msg_style
        # тег ставим и в стиле «none» (там он без фона) — тогда смена
        # стиля в настройках сразу перекрашивает уже показанные сообщения
        sfx = "even" if self._row_counter % 2 == 0 else "odd"
        if style == "glow" and len(self._ch_list) > 1:
            idx = self._ch_idx(channel_tag)
            return f"row_ch_{idx}_{sfx}"
        return f"row_{sfx}"

    def _connect_channel(self, channel: str, platform: str):
        """Заменяет ВСЕ каналы одним (полная смена — для compat)."""
        for reader in list(self._readers.values()):
            try:
                reader.stop()
            except Exception:
                pass
        self._readers.clear()
        self._statuses.clear()
        self._ch_list.clear()
        while not self.msg_queue.empty():
            try:
                self.msg_queue.get_nowait()
            except queue.Empty:
                break
        self.channel  = channel
        self.platform = platform
        self._add_channel(channel, platform)
        self._update_tray_title()

    def _open_new_channel(self):
        """Добавляет ещё один канал в объединённый поток."""
        res = ask_channel(parent=self, title="Добавить канал",
                          platform=self.platform)
        if not res:
            return
        self._add_channel(res["channel"], res["platform"])

    def _change_channel(self):
        """Открывает диалог управления каналами мульти-чата."""
        self._manage_channels()

    # ============================================================
    #                       вывод сообщений
    # ============================================================
    def _nick_tag(self, nick):
        idx = sum(ord(c) for c in nick) % len(self.NICK_COLORS)
        return f"nick_{self.NICK_COLORS[idx]}"

    # ============================================================
    #                       эмоуты Twitch
    # ============================================================
    def _emote_px(self) -> int:
        """Высота эмоута в пикселях под текущий размер шрифта."""
        try:
            return max(16, int(self.fnt.metrics("linespace")))
        except Exception:
            return max(16, int(self.font_size * 1.8))

    def _msg_segments(self, msg: str, emotes, content_tag: str) -> list:
        """Разбивает текст сообщения на сегменты текст/эмоут.
        Возвращает список (txt, tag), где для эмоутов
        tag = ("emote", emote_id, content_tag)."""
        msg = msg.rstrip()
        if not (emotes and self.show_emotes and self._emotes.available()):
            return [(msg + "\n", content_tag)]
        segs = []
        pos, n = 0, len(msg)
        for a, b, eid in emotes:
            if a < pos or a > b or b >= n:
                continue
            if a > pos:
                segs.append((msg[pos:a], content_tag))
            segs.append((msg[a:b + 1], ("emote", eid, content_tag)))
            pos = b + 1
        if pos < n:
            segs.append((msg[pos:], content_tag))
        segs.append(("\n", content_tag))
        return segs

    def _on_emote_ready(self, eid: str):
        """Эмоут скачан (или не удался) — заменяем плейсхолдеры."""
        entries = self._emote_pending.pop(eid, None)
        if not entries:
            return
        try:
            self.text.config(state="normal")
            for ptag, h in entries:
                ph = self._emotes.get_photo(eid, h)
                if ph is None:
                    self.text.tag_delete(ptag)   # остаётся текст
                    continue
                rngs = self.text.tag_ranges(ptag)
                # заменяем с конца, чтобы индексы не съехали
                for i in range(len(rngs) - 2, -1, -2):
                    start, end = rngs[i], rngs[i + 1]
                    self.text.delete(start, end)
                    self.text.image_create(start, image=ph, padx=1)
                self.text.tag_delete(ptag)
        except Exception:
            pass
        finally:
            try:
                self.text.config(state="disabled")
            except Exception:
                pass

    def _append(self, segments, row_tag: str | None = None):
        self.text.config(state="normal")
        # ВАЖНО: используем "end-1c", а не "end".
        # У Tk Text всегда есть неявный завершающий "\n", а index("end")
        # указывает ПОСЛЕ него. insert("end", ...) при этом вставляет
        # ПЕРЕД этим неявным "\n", поэтому позиции, снятые через "end",
        # после вставки указывали бы на пустую строку ПОСЛЕ сообщения —
        # из-за этого подложка съезжала на строку вниз и копилась после
        # последнего сообщения вместо того, чтобы быть под каждым.
        pos_start = self.text.index("end-1c")
        for txt, tag in segments:
            # спец-сегмент эмоута: tag = ("emote", emote_id, базовый_тег)
            if isinstance(tag, tuple) and tag and tag[0] == "emote":
                _, eid, base_tag = tag
                h = self._emote_px()
                ph = self._emotes.get_photo(eid, h)
                if ph is not None:
                    self.text.image_create("end", image=ph, padx=1)
                else:
                    # ещё не скачан — текст-плейсхолдер, заменим позже
                    self._emote_seq += 1
                    ptag = f"emo_{self._emote_seq}"
                    self._emote_pending.setdefault(eid, []).append((ptag, h))
                    tags = (base_tag, ptag) if base_tag else (ptag,)
                    self.text.insert("end", txt, tags)
                continue
            if tag:
                self.text.insert("end", txt, tag)
            else:
                self.text.insert("end", txt)
        if row_tag:
            pos_end = self.text.index("end-1c")
            self.text.tag_add(row_tag, pos_start, pos_end)
            # row-теги под content-тегами по приоритету
            self.text.tag_lower(row_tag, "msg")
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > 1200:
            self.text.delete("1.0", f"{line_count - 1200}.0")
        self.text.see("end")
        self.text.config(state="disabled")

    # ============================================================
    #               фильтрация и подсветка сообщений
    # ============================================================
    def _is_banned(self, user: str, msg: str) -> bool:
        if user.lower() in self.banned_users:
            return True
        ml = msg.lower()
        return any(w and w in ml for w in self.banned_words)

    def _is_highlight(self, user: str, msg: str) -> bool:
        """Подсветка: сообщение ОТ ника из списка или со словом/ником в тексте."""
        ul = (user or "").lower().lstrip("@")
        ml = (msg or "").lower()
        for w in self.highlight_words:
            w = (w or "").strip().lower().lstrip("@")
            if w and (w == ul or w in ml):
                return True
        return False

    def _log_system(self, msg):
        # Системные сообщения не выводим в чат — только в файл-лог.
        # Видимая обратная связь идёт через статус-бар (_set_status).
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._save_history_line(f"[{ts}] * {msg}")

    def _log_message(self, tag, user, msg, emotes=None, extra=None, is_hl=None):
        extra = extra or {}
        if self._is_banned(user, msg):
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        msg_start = self.text.index("end-1c")

        # бейдж источника — только при 2+ каналах
        src_segs: list = []
        if len(self._ch_list) > 1:
            label   = f"[{self._tag_label(tag):<9}]"
            src_tag = self._src_tk_tag(tag)
            src_segs = [(f"{label} ", src_tag)]

        # разделитель перед карточкой (card / pill)
        if self.msg_style in ("card", "pill") and self._row_counter > 0:
            try:
                self.text.config(state="normal")
                self.text.insert("end", "\n", "row_sep")
                self.text.config(state="disabled")
            except Exception:
                pass

        row_tag = self._get_row_tag(tag)
        if is_hl is None:
            is_hl = self._is_highlight(user, msg)
        if is_hl:
            row_tag = "row_hl"
        ev = extra.get("event")
        first = bool(extra.get("first")) and not ev
        if first and not is_hl:
            row_tag = "row_first"

        if ev:
            et = ev.get("type", "other")
            if et not in self.EVENT_COLORS:
                et = "other"
            self._ensure_event_tags()
            row_tag = f"row_ev_{et}"
            segs = (
                [(f" {self.EVENT_ICONS[et]}  ", f"ev_icon_{et}"),
                 (ev.get("text", ""), f"ev_title_{et}")]
                + src_segs
            )
            if msg.strip():
                segs += [("\n", "msg"), (user, self._nick_tag(user)), (": ", "colon")]
                segs += self._msg_segments(msg, emotes, "msg")
            else:
                segs.append(("\n", "msg"))
        elif first:
            segs = (
                [("👋 новый зритель  ", "first_mark"), (f"{ts}  ", "time")]
                + src_segs
                + [(user, self._nick_tag(user)),
                   (": ", "colon")]
                + self._msg_segments(msg, emotes, "msg")
            )
        elif is_hl:
            segs = (
                [("★ ", "highlight_mark"), (f"{ts}  ", "time")]
                + src_segs
                + [(user, self._nick_tag(user)),
                   (": ", "colon")]
                + self._msg_segments(msg, emotes, "highlight_msg")
            )
        else:
            segs = (
                [(f" {ts}  ", "time")]
                + src_segs
                + [(user, self._nick_tag(user)),
                   (": ", "colon")]
                + self._msg_segments(msg, emotes, "msg")
            )

        self._append(segs, row_tag=row_tag)
        # метки для удаления модерацией (CLEARMSG / CLEARCHAT)
        try:
            msg_end = self.text.index("end-1c")
            if extra.get("id"):
                self.text.tag_add(f"mid_{extra['id']}", msg_start, msg_end)
            login = (extra.get("login") or "").lower()
            if login:
                self.text.tag_add(f"usr_{login}", msg_start, msg_end)
        except Exception:
            pass
        self._row_counter += 1
        if ev:
            self._save_history_line(f"[{ts}] [{tag}] * {ev.get('text', '')} {msg}")
        else:
            self._save_history_line(f"[{ts}] [{tag}] {user}: {msg}")
        self._msg_count += 1
        self._update_count_lbl()

    def _set_status(self, state, text=None):
        """Прямая установка статуса (backward compat)."""
        if state == "online":
            self._set_status_raw("online",
                                 text or f"подключено · {self.channel}")
        elif state == "warn":
            self._set_status_raw("warn", text or "ожидание...")
        else:
            self._set_status_raw("offline", text or "не подключено")

    # ============================================================
    #        сообщения / события / модерация (общая точка)
    # ============================================================
    EVENT_COLORS = {
        "sub": "#a970ff", "gift": "#ff6bcb", "raid": "#ff9f1c",
        "cheer": "#f5c518", "announcement": "#4fc3f7", "donation": "#f57d07",
        "other": "#8b91a7",
    }
    EVENT_ICONS = {
        "sub": "★", "gift": "🎁", "raid": "⚑", "cheer": "◆",
        "announcement": "📣", "donation": "💰", "other": "•",
    }

    def _handle_chat(self, tag, user, msg, emotes, extra):
        ev = extra.get("event")
        # цель стрима и лента событий считаются всегда, даже если
        # показ событий в чате выключен
        if ev and self._obs_server:
            try:
                self._obs_server.record_event(ev, user)
            except Exception:
                pass
        if ev and not self.show_events:
            # события выключены: сообщение-объявление/читер показываем как обычное
            if not (msg or "").strip():
                return
            extra.pop("event", None)
            ev = None
        if self._is_banned(user, msg or ""):
            return
        login = (extra.get("login") or user or "").lower()
        if self.hide_bots and login in KNOWN_BOTS:
            return
        if self.hide_commands and not ev and (msg or "").lstrip().startswith("!"):
            return
        if not self.show_first:
            extra["first"] = False
        self._stats_add(user, ev, bool(extra.get("first")), key=login)
        if not extra.get("id"):
            # локальный id — для «сообщения на экран» и удаления (YouTube и т.п.)
            self._mid_seq = getattr(self, "_mid_seq", 0) + 1
            extra["id"] = f"loc{self._mid_seq}"
        if self.third_party_emotes and msg:
            try:
                emotes = self._tpe.find(msg, emotes, self._room_ids.get(tag, ""))
            except Exception:
                pass
        is_mention = self._is_mention(user, msg or "", extra.get("login", ""))
        is_hl = is_mention or self._is_highlight(user, msg or "")
        self._log_message(tag, user, msg or "", emotes, extra=extra, is_hl=is_hl)
        self._maybe_sound(bool(ev) or bool(extra.get("first")), is_hl, mention=is_mention)
        if self.translate_on and msg and not ev:
            plain = msg
            for a, b, _e in sorted(emotes or [], reverse=True):
                plain = plain[:a] + " " + plain[b + 1:]
            if needs_translation(plain, self.translate_to):
                self._translator.request(extra["id"], plain.strip(), self.translate_to)
            else:
                self._translator.log(f"пропуск (не нужен перевод): {plain!r}")
        if self._obs_server:
            try:
                payload = {
                    "kind": "msg",
                    "user": user,
                    "login": extra.get("login") or user.lower(),
                    "mid": extra.get("id", ""),
                    "msg":  (msg or "").rstrip(),
                    "emotes": [[a, b, e] for a, b, e in (emotes or [])],
                    "color": extra.get("color", ""),
                    "badges": extra.get("badges", []),
                    "platform": tag.partition(":")[0] or "twitch",
                    "hl": is_hl,
                    "ts":   datetime.datetime.now().strftime("%H:%M:%S"),
                }
                if ev:
                    payload["event"] = ev
                if extra.get("first") and not ev:
                    payload["first"] = True
                self._obs_server.hub.publish(payload)
            except Exception:
                pass

    # ---------------- статистика ----------------
    def _stats_reset(self):
        self._stats = {
            "start": time.time(), "msgs": 0, "chatters": Counter(),
            "names": {}, "first": [], "times": deque(maxlen=5000),
            "subs": 0, "gifts": 0, "raids": 0, "bits": 0, "donations": 0,
        }

    def _stats_add(self, who: str, ev, first: bool, key: str = ""):
        st = self._stats
        now = time.time()
        if ev:
            et = ev.get("type")
            if et == "sub":
                st["subs"] += 1
            elif et == "gift":
                st["gifts"] += max(1, _safe_int(ev.get("amount", 1), 1))
            elif et == "raid":
                st["raids"] += 1
            elif et == "cheer":
                st["bits"] += _safe_int(ev.get("amount", 0), 0)
            elif et == "donation":
                st["donations"] += _safe_int(ev.get("amount", 0), 0)
            return
        st["msgs"] += 1
        st["times"].append(now)
        key = (key or who or "").lower()
        st["chatters"][key] += 1
        st["names"][key] = who
        if first:
            st["first"].append(who)

    def _stats_rate(self) -> int:
        cut = time.time() - 60
        return sum(1 for t in self._stats["times"] if t >= cut)

    def _on_translated(self, mid: str, text: str, lang: str):
        self._log_system(f"Перевод ({lang or '?'}): {text}")
        tk_tag = f"mid_{mid}"
        rngs = self.text.tag_ranges(tk_tag)
        if rngs:
            end = rngs[-1]
            pos = self.text.index(f"{end} -1c")      # перед завершающим \n
            tags = [t for t in self.text.tag_names(f"{end} -2c")
                    if t.startswith(("row_", "mid_", "usr_"))]
            self.text.config(state="normal")
            try:
                self.text.tag_configure("tr", foreground=self.TEXT_MUTED,
                                        font=self.fnt_sys, lmargin1=24, lmargin2=24)
                label = f"\n↳ {text}" + (f"  ({lang})" if lang else "")
                self.text.insert(pos, label, tuple(["tr"] + tags))
                for t in tags:
                    if t.startswith("row_"):
                        self.text.tag_lower(t, "msg")
            finally:
                self.text.config(state="disabled")
            self.text.see("end")
        if self._obs_server:
            self._obs_server.hub.translate(mid, text)

    def _on_update_info(self, tag, url, manual):
        self._update_info = (tag, url)
        if tag:
            try:
                self.update_lbl.config(text=f"⬆ {tag}")
                self.update_lbl.pack(side="right", before=self.count_lbl)
            except Exception:
                pass
        cb = getattr(self, "_update_cb", None)
        if cb:
            try:
                cb(tag, url)
            except Exception:
                pass

    def _da_redirect(self) -> str:
        return f"http://127.0.0.1:{int(self._obs_port)}/da/callback"

    def _on_donation(self, it: dict):
        name = (it.get("username") or "").strip() or "Аноним"
        try:
            amount = float(it.get("amount") or 0)
        except Exception:
            amount = 0.0
        amt = int(amount) if amount == int(amount) else round(amount, 2)
        cur = str(it.get("currency") or "RUB")
        sym = {"RUB": "₽", "USD": "$", "EUR": "€", "UAH": "₴", "KZT": "₸", "BYN": "Br"}.get(cur, cur)
        msg = it.get("message") or ""
        if it.get("message_type") == "audio":
            msg = "🎤 голосовое сообщение"
        ev = {"type": "donation", "text": f"{name} — {amt} {sym}",
              "amount": int(round(amount)), "currency": sym}
        extra = {"event": ev, "login": "da_" + name.lower(), "id": f"da{it.get('id', '')}"}
        if not self.show_donations:
            if self._obs_server:
                self._obs_server.record_event(ev, name)
            self._stats_add(name, ev, False)
            return
        self._handle_chat("donationalerts:da", name, msg, [], extra)

    def _update_count_lbl(self):
        try:
            self.count_lbl.config(
                text=f"{self._msg_count} сообщ · {self._stats_rate()}/мин  📊")
        except Exception:
            pass

    def _tick_count_lbl(self):
        self._update_count_lbl()
        self.after(5000, self._tick_count_lbl)

    def _open_stats(self):
        """Окно статистики чата (обновляется каждые 2 с)."""
        if getattr(self, "_stats_win", None) and self._stats_win.winfo_exists():
            self._stats_win.lift()
            return
        win = tk.Toplevel(self)
        self._stats_win = win
        win.title("Статистика чата")
        win.configure(bg=self.BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        try:
            x = self.winfo_rootx() + 30
            y = self.winfo_rooty() + 30
            win.geometry(f"420x560+{x}+{y}")
        except Exception:
            pass
        outer = tk.Frame(win, bg=self.BG, padx=16, pady=12)
        outer.pack(fill="both", expand=True)
        head = tk.Frame(outer, bg=self.BG)
        head.pack(fill="x")
        tk.Label(head, text="📊  Статистика чата", bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI Semibold", 12)).pack(side="left")
        dur_lbl = tk.Label(head, bg=self.BG, fg=self.TEXT_DIM, font=("Segoe UI", 9))
        dur_lbl.pack(side="right")

        grid = tk.Frame(outer, bg=self.BG)
        grid.pack(fill="x", pady=(10, 0))
        tiles = {}
        spec = [("msgs", "сообщений", self.TEXT), ("rate", "в минуту", self.ACCENT),
                ("chatters", "пишут", self.TEXT), ("first", "новичков", self.OK),
                ("subs", "подписок", "#a970ff"), ("gifts", "подарено", "#ff6bcb"),
                ("raids", "рейдов", "#ff9f1c"), ("bits", "битсов", "#f5c518"),
                ("donations", "донатов, ₽", "#f57d07")]
        for i, (key, label, col) in enumerate(spec):
            t = tk.Frame(grid, bg=self.BG_ELEV, padx=10, pady=8,
                         highlightthickness=1, highlightbackground=self.BORDER)
            t.grid(row=i // 4, column=i % 4, padx=3, pady=3, sticky="nsew")
            v = tk.Label(t, text="0", bg=self.BG_ELEV, fg=col,
                         font=("Segoe UI Semibold", 15))
            v.pack(anchor="w")
            tk.Label(t, text=label, bg=self.BG_ELEV, fg=self.TEXT_DIM,
                     font=("Segoe UI", 8)).pack(anchor="w")
            tiles[key] = v
        for c in range(4):
            grid.grid_columnconfigure(c, weight=1, uniform="st")

        tk.Label(outer, text="САМЫЕ АКТИВНЫЕ", bg=self.BG, fg=self.TEXT_DIM,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(14, 4))
        top = tk.Canvas(outer, height=250, bg=self.BG, highlightthickness=0, bd=0)
        top.pack(fill="x")

        tk.Label(outer, text="НОВЫЕ ЗРИТЕЛИ", bg=self.BG, fg=self.TEXT_DIM,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(8, 2))
        first_lbl = tk.Label(outer, bg=self.BG, fg=self.OK, anchor="w", justify="left",
                             wraplength=380, font=("Segoe UI", 9))
        first_lbl.pack(fill="x")

        def _reset():
            self._stats_reset()
            refresh(reschedule=False)

        rb = tk.Label(outer, text="Сбросить", bg=self.BG_INPUT, fg=self.TEXT_MUTED,
                      padx=12, pady=5, cursor="hand2", font=("Segoe UI Semibold", 9))
        rb.pack(side="bottom", anchor="e", pady=(8, 0))
        rb.bind("<Button-1>", lambda e: _reset())
        self._hover(rb, self.BG_INPUT, self.BORDER, self.TEXT_MUTED, self.TEXT)

        def refresh(reschedule=True):
            if not win.winfo_exists():
                return
            st = self._stats
            mins = int((time.time() - st["start"]) // 60)
            dur_lbl.config(text=f"за {mins // 60} ч {mins % 60} мин" if mins >= 60
                           else f"за {mins} мин")
            vals = {"msgs": st["msgs"], "rate": self._stats_rate(),
                    "chatters": len(st["chatters"]), "first": len(st["first"]),
                    "subs": st["subs"], "gifts": st["gifts"],
                    "raids": st["raids"], "bits": st["bits"],
                    "donations": st.get("donations", 0)}
            for k, v in vals.items():
                tiles[k].config(text=str(v))
            top.delete("all")
            items = st["chatters"].most_common(10)
            w = max(top.winfo_width(), 380)
            mx = items[0][1] if items else 1
            for i, (k, n) in enumerate(items):
                y = i * 25
                bw = max(4, int((w - 150) * n / mx))
                self._ui_round_rect(top, 110, y + 4, 110 + bw, y + 20, 4,
                                    fill=_blend_color(self.BG, self.ACCENT, 0.55), outline="")
                top.create_text(0, y + 12, anchor="w", fill=self.TEXT,
                                text=st["names"].get(k, k)[:16], font=("Segoe UI", 9))
                top.create_text(116 + bw, y + 12, anchor="w", fill=self.TEXT_MUTED,
                                text=str(n), font=("Segoe UI Semibold", 9))
            if not items:
                top.create_text(0, 12, anchor="w", fill=self.TEXT_DIM,
                                text="пока никто не писал", font=("Segoe UI", 9))
            fl = st["first"][-12:]
            first_lbl.config(text=", ".join(fl) if fl else "—")
            if reschedule:
                win.after(2000, refresh)

        refresh()
        win.bind("<Escape>", lambda e: win.destroy())

    _MENTION_RE = re.compile(r"@([\w]+)", re.UNICODE)

    def _is_mention(self, user: str, msg: str, login: str = "") -> bool:
        """@канал (любой подключённый Twitch-канал) или @мой_ник в тексте."""
        if "@" not in (msg or ""):
            return False
        targets = {c["channel"].lower() for c in self._ch_list
                   if c.get("platform") == "twitch"}
        my = (self.sound.get("my_nick") or "").lower()
        if my:
            targets.add(my)
        author = (login or user or "").lower()
        targets.discard(author)          # сам себя не упоминает
        return any(m.lower() in targets for m in self._MENTION_RE.findall(msg))

    def _maybe_sound(self, is_event: bool, is_hl: bool, force: bool = False,
                     mention: bool = False):
        snd = self.sound
        use_mention = mention and snd.get("mention", True)
        if not force:
            if not snd["enabled"]:
                return
            if not (use_mention or (is_event and snd["events"])
                    or (is_hl and snd["hl"]) or snd["all"]):
                return
            now = time.monotonic()
            # упоминания важнее: у них короткая пауза
            if now - self._sound_last < (0.4 if use_mention else 1.2):
                return
            self._sound_last = now
        vol = snd["volume"] / 100.0
        if use_mention or (force and mention):
            args = (snd.get("mention_name", "chime"), vol, snd.get("mention_file", ""))
        else:
            args = (snd["name"], vol, snd["file"])
        threading.Thread(target=self._sound.play, args=args, daemon=True).start()

    # ---------------- «сообщение на экран» ----------------
    def _mid_at(self, index) -> str:
        for tn in self.text.tag_names(index):
            if tn.startswith("mid_"):
                return tn[4:]
        return ""

    def _feature_mid(self, mid: str):
        if not self._obs_server or not mid:
            return
        p = self._obs_server.hub.find(mid)
        if p:
            self._obs_server.hub.feature(p)
            self._set_status_raw("online", "📺 сообщение показано на экране OBS")

    def _unfeature(self):
        if self._obs_server:
            self._obs_server.hub.feature(None)

    def _on_chat_menu(self, e):
        idx = self.text.index(f"@{e.x},{e.y}")
        mid = self._mid_at(idx)
        login = ""
        for tn in self.text.tag_names(idx):
            if tn.startswith("usr_"):
                login = tn[4:]
        m = tk.Menu(self, tearoff=0, bg=self.BG_ELEV, fg=self.TEXT,
                    activebackground=self.ACCENT, activeforeground="#ffffff",
                    bd=0, relief="flat", font=("Segoe UI", 10))
        has_srv = self._obs_server is not None
        m.add_command(label="📺  Показать на экране OBS",
                      state="normal" if (mid and has_srv) else "disabled",
                      command=lambda: self._feature_mid(mid))
        featured = has_srv and self._obs_server.hub.featured
        m.add_command(label="✖  Убрать с экрана",
                      state="normal" if featured else "disabled",
                      command=self._unfeature)
        m.add_separator()

        def _copy():
            try:
                rngs = self.text.tag_ranges(f"mid_{mid}")
                if rngs:
                    self._copy_to_clipboard(self.text.get(rngs[0], rngs[-1]).strip())
            except Exception:
                pass

        m.add_command(label="⧉  Копировать сообщение",
                      state="normal" if mid else "disabled", command=_copy)

        def _hide_user():
            if login and login not in self.banned_users:
                self.banned_users.append(login)
                self._save_config()
                self._apply_moderation({"type": "clear_user", "login": login})

        m.add_command(label=f"⊘  Скрыть {login}" if login else "⊘  Скрыть пользователя",
                      state="normal" if login else "disabled", command=_hide_user)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _apply_moderation(self, info: dict):
        t = info.get("type")
        try:
            self.text.config(state="normal")
            if t == "delete" and info.get("mid"):
                self._delete_tagged(f"mid_{info['mid']}")
            elif t == "clear_user" and info.get("login"):
                self._delete_tagged(f"usr_{info['login']}")
            elif t == "clear":
                self.text.delete("1.0", "end")
                self._row_counter = 0
        except Exception:
            pass
        finally:
            try:
                self.text.config(state="disabled")
            except Exception:
                pass
        if self._obs_server:
            try:
                self._obs_server.hub.moderate(info)
            except Exception:
                pass

    def _ensure_event_tags(self):
        """tk-теги оформления событий (под текущую тему и стиль)."""
        try:
            sp = {k: self.text.tag_cget("row_even", k) or 0
                  for k in ("lmargin1", "lmargin2")}
        except Exception:
            sp = {}
        for et, col in self.EVENT_COLORS.items():
            try:
                self.text.tag_configure(
                    f"row_ev_{et}", background=_blend_color(self.BG, col, 0.20),
                    spacing1=6, spacing3=6, **sp)
                self.text.tag_configure(f"ev_icon_{et}", foreground=col,
                                        font=self.fnt_bold)
                self.text.tag_configure(f"ev_title_{et}", foreground=col,
                                        font=self.fnt_bold)
                self.text.tag_lower(f"row_ev_{et}", "msg")
            except Exception:
                pass

    def _delete_tagged(self, tk_tag: str):
        rngs = self.text.tag_ranges(tk_tag)
        for i in range(len(rngs) - 2, -1, -2):
            self.text.delete(rngs[i], rngs[i + 1])
        try:
            self.text.tag_delete(tk_tag)
        except Exception:
            pass

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()

                if kind == "system":
                    # payload = (tag, text)
                    _, text = payload if isinstance(payload, tuple) else ("", payload)
                    self._log_system(text)

                elif kind == "emote_ready":
                    # payload = emote_id (от EmoteCache, без _TaggedQueue)
                    try:
                        self._on_emote_ready(payload)
                    except Exception:
                        pass

                elif kind in ("msg", "event"):
                    # payload = (tag, (user, msg[, emotes[, extra]]))  — от _TaggedQueue
                    if isinstance(payload, tuple) and len(payload) == 2:
                        tag, inner = payload
                        extra = {}
                        if isinstance(inner, tuple) and len(inner) == 4:
                            user, msg, emotes, extra = inner
                        elif isinstance(inner, tuple) and len(inner) == 3:
                            user, msg, emotes = inner
                        elif isinstance(inner, tuple) and len(inner) == 2:
                            user, msg = inner
                            emotes = []
                        else:
                            # неожиданный формат — пропускаем
                            continue
                    else:
                        continue
                    self._handle_chat(tag, user, msg, emotes, dict(extra or {}))

                elif kind == "mod":
                    if isinstance(payload, tuple):
                        _, info = payload
                    else:
                        info = payload
                    if self.mod_sync and isinstance(info, dict):
                        self._apply_moderation(info)

                elif kind == "translated":
                    try:
                        self._on_translated(*payload)
                    except Exception as e:
                        self._translator.log(f"ошибка вставки перевода: {e!r}")

                elif kind == "donation":
                    try:
                        self._on_donation(payload)
                    except Exception as e:
                        self._log_system(f"DonationAlerts: {e}")

                elif kind == "da_status":
                    st, txt = payload
                    self._log_system(f"DonationAlerts: {txt}")
                    cb = self._da_status_cb
                    if cb:
                        try:
                            cb(st, txt)
                        except Exception:
                            self._da_status_cb = None

                elif kind == "translate_skip":
                    self._log_system(f"Перевод не нужен ({payload[1] or '?'}): {payload[0]}")

                elif kind == "translate_error":
                    self._log_system(f"Перевод: ошибка — {payload}")
                    self._set_status_raw("warn", "⚠ перевод не работает — см. Настройки → Ещё")

                elif kind == "update":
                    try:
                        self._on_update_info(*payload)
                    except Exception:
                        pass

                elif kind == "room":
                    tag, rid = payload if isinstance(payload, tuple) else ("", payload)
                    self._room_ids[tag] = rid
                    if self.third_party_emotes:
                        self._tpe.load_room(rid)

                elif kind == "status":
                    # payload = (tag, state)
                    if isinstance(payload, tuple):
                        tag, state = payload
                    else:
                        tag, state = "", payload
                    self._set_channel_status(tag, state)
                    if self._obs_server:
                        try:
                            self._obs_server.hub.publish({
                                "kind":    "status",
                                "state":   state,
                                "channel": self.channel,
                            })
                        except Exception:
                            pass

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
            self.update_idletasks()

            # Иногда GetParent(self.winfo_id()) возвращает не тот HWND,
            # поэтому попробуем применить стиль сразу к обоим вариантам.
            candidates = []
            try:
                parent_hwnd = user32.GetParent(self.winfo_id())
                if parent_hwnd:
                    candidates.append(parent_hwnd)
            except Exception:
                pass
            self_hwnd = self.winfo_id()
            if self_hwnd:
                candidates.append(self_hwnd)

            for hwnd in candidates:
                try:
                    ex = GetLong(hwnd, GWL_EXSTYLE)
                    new_ex = (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
                    SetLong(hwnd, GWL_EXSTYLE, new_ex)
                except Exception:
                    pass

            # После применения стилей привязываем иконку.
            # Делаем 2-3 попытки на случай, если окно/handle ещё не стабилен.
            self._taskbar_icon_retry = 0
            self.after(60, self._set_taskbar_icon)
        except Exception:
            pass

    def _set_taskbar_icon(self):
        """Грузит icon.ico и шлёт WM_SETICON — даёт настоящую иконку
        в панели задач Windows и Alt+Tab вместо стандартной Tk-иконки."""
        if not IS_WIN:
            return

        # Даже если иконка не найдена, мы не хотим спамить:
        # повторяем несколько раз, а затем перестаём.
        if not os.path.exists(self.ICON_ICO):
            self._taskbar_icon_retry += 1
            if self._taskbar_icon_retry <= 3:
                self.after(400, self._set_taskbar_icon)
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
            # Пробуем выставить иконку на все кандидаты.
            candidates = []
            try:
                parent_hwnd = user32.GetParent(self.winfo_id())
                if parent_hwnd:
                    candidates.append(parent_hwnd)
            except Exception:
                pass
            self_hwnd = self.winfo_id()
            if self_hwnd:
                candidates.append(self_hwnd)

            for hwnd in candidates:
                if big:
                    try:
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big)
                    except Exception:
                        pass
                if small:
                    try:
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small)
                    except Exception:
                        pass

            self._taskbar_icon_retry = 0
        except Exception:
            self._taskbar_icon_retry += 1
            if self._taskbar_icon_retry <= 3:
                self.after(400, self._set_taskbar_icon)

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
                self._win_title(), menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            self.tray_icon = None

    def _update_tray_title(self):
        if self.tray_icon:
            try:
                self.tray_icon.title = self._win_title()
            except Exception:
                pass

    # ============================================================
    #                       выход
    # ============================================================
    def _on_quit(self):
        self._save_config()
        for reader in list(self._readers.values()):
            try:
                reader.stop()
            except Exception:
                pass
        try:
            if self._obs_server:
                self._obs_server.stop()
        except Exception:
            pass
        try:
            if self._settings_win and self._settings_win.winfo_exists():
                self._settings_win.destroy()
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

    extra_channels: list[dict] = []

    if len(sys.argv) > 1:
        channel  = sys.argv[1].strip().lstrip("#")
        platform = sys.argv[2].strip() if len(sys.argv) > 2 else "twitch"
        if platform == "twitch":
            channel = channel.lower()
    else:
        _last_ch, _last_pl = "", "twitch"
        try:
            _cfg_path = os.path.join(_user_dir(), "overlay_config.json")
            with open(_cfg_path, "r", encoding="utf-8") as _f:
                _saved      = json.load(_f)
                _saved_chs  = _saved.get("channels", [])
                if _saved_chs:
                    # берём первый сохранённый канал для диалога
                    _last_ch = _saved_chs[0].get("channel", "") or ""
                    _last_pl = _saved_chs[0].get("platform", "twitch") or "twitch"
                    extra_channels = _saved_chs[1:]
                else:
                    _last_ch = _saved.get("last_channel", "") or ""
                    _last_pl = _saved.get("last_platform", "twitch") or "twitch"
        except Exception:
            pass
        result = ask_channel(initial=_last_ch, platform=_last_pl)
        if not result:
            return
        channel  = result["channel"]
        platform = result["platform"]

    app = ChatOverlay(channel, platform=platform)

    # Восстанавливаем дополнительные каналы из конфига
    for extra in extra_channels:
        ec = (extra.get("channel") or "").strip()
        ep = (extra.get("platform") or "twitch").strip()
        if ec:
            try:
                app._add_channel(ec, ep)
            except Exception:
                pass

    app.mainloop()


if __name__ == "__main__":
    main()
