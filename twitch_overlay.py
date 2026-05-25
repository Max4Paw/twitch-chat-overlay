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
from tkinter import ttk, font as tkfont
import http.server
import socketserver
import urllib.parse
from collections import deque

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
        "name": "Emerald Night",
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
}
PALETTE = THEMES["twitch_dark"]


# ============================================================
#                  Кастомный диалог канала
# ============================================================
class ChannelDialog(tk.Toplevel):
    """Borderless-диалог для выбора платформы (Twitch / YouTube) и канала."""

    YT_RED  = "#cc0000"
    YT_HOV  = "#e60000"

    def __init__(self, parent=None, initial: str = "",
                 title: str = "Chat Overlay", platform: str = "twitch"):
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

        W, H = 380, 270
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

        self._header_dot = tk.Label(
            header, text="●", bg=P["BG_HEADER"], fg=P["ACCENT"],
            font=("Segoe UI", 12, "bold"), padx=10,
        )
        self._header_dot.pack(side="left")
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
        body = tk.Frame(outer, bg=P["BG"], padx=22, pady=14)
        body.pack(fill="both", expand=True)

        # — переключатель платформы —
        self._platform = tk.StringVar(value=platform)

        plat_row = tk.Frame(body, bg=P["BG"])
        plat_row.pack(fill="x", pady=(0, 12))

        def _refresh_ui():
            p = self._platform.get()
            is_yt = (p == "youtube")
            # кнопки
            self._tw_btn.config(
                bg=P["ACCENT"] if not is_yt else P["BG_INPUT"],
                fg="#ffffff"  if not is_yt else P["TEXT_MUTED"])
            self._yt_btn.config(
                bg=self.YT_RED if is_yt else P["BG_INPUT"],
                fg="#ffffff"   if is_yt else P["TEXT_MUTED"])
            # dot в шапке
            self._header_dot.config(
                fg=self.YT_RED if is_yt else P["ACCENT"])
            # текст поля
            self._head_lbl.config(
                text="YouTube Live" if is_yt else "Канал Twitch")
            self._hint_lbl.config(
                text=("Вставьте ссылку на стрим или video ID (11 символов)."
                      if is_yt else
                      "Введите имя канала, чат которого хотите смотреть."))
            self._prefix_lbl.config(
                text="▶" if is_yt else "#",
                fg=(self.YT_RED if is_yt else P["ACCENT"]))

        self._tw_btn = tk.Label(
            plat_row, text="🟣  Twitch",
            bg=P["ACCENT"] if platform == "twitch" else P["BG_INPUT"],
            fg="#ffffff" if platform == "twitch" else P["TEXT_MUTED"],
            font=("Segoe UI Semibold", 9), padx=14, pady=6, cursor="hand2",
        )
        self._tw_btn.pack(side="left")
        self._tw_btn.bind("<Button-1>", lambda e: [
            self._platform.set("twitch"), _refresh_ui()])

        self._yt_btn = tk.Label(
            plat_row, text="▶  YouTube",
            bg=self.YT_RED if platform == "youtube" else P["BG_INPUT"],
            fg="#ffffff" if platform == "youtube" else P["TEXT_MUTED"],
            font=("Segoe UI Semibold", 9), padx=14, pady=6, cursor="hand2",
        )
        self._yt_btn.pack(side="left", padx=(4, 0))
        self._yt_btn.bind("<Button-1>", lambda e: [
            self._platform.set("youtube"), _refresh_ui()])

        # — заголовок + подсказка —
        _is_yt = (platform == "youtube")
        self._head_lbl = tk.Label(
            body,
            text="YouTube Live" if _is_yt else "Канал Twitch",
            bg=P["BG"], fg=P["TEXT"], font=("Segoe UI Semibold", 13),
            anchor="w",
        )
        self._head_lbl.pack(fill="x")

        self._hint_lbl = tk.Label(
            body,
            text=("Вставьте ссылку на стрим или video ID (11 символов)."
                  if _is_yt else
                  "Введите имя канала, чат которого хотите смотреть."),
            bg=P["BG"], fg=P["TEXT_MUTED"], font=("Segoe UI", 9),
            anchor="w", pady=4,
        )
        self._hint_lbl.pack(fill="x")

        # — поле ввода —
        self._input_wrap = tk.Frame(body, bg=P["BORDER"], padx=1, pady=1)
        self._input_wrap.pack(fill="x", pady=(8, 0))

        input_inner = tk.Frame(self._input_wrap, bg=P["BG_INPUT"])
        input_inner.pack(fill="x")

        self._prefix_lbl = tk.Label(
            input_inner,
            text="▶" if _is_yt else "#",
            bg=P["BG_INPUT"],
            fg=self.YT_RED if _is_yt else P["ACCENT"],
            font=("Segoe UI Semibold", 13), padx=10,
        )
        self._prefix_lbl.pack(side="left")

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
        btns.pack(fill="x", side="bottom", pady=(14, 0))

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
        val = self.var.get().strip()
        plat = self._platform.get()
        if plat == "twitch":
            val = val.lstrip("#").lower()
        if not val:
            self._input_wrap.config(bg=PALETTE["DANGER"])
            self.after(700, lambda: self._input_wrap.config(bg=PALETTE["BORDER"]))
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


_OBS_BROWSER_HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Twitch Chat Overlay (OBS)</title>
  <style>
    :root { color-scheme: dark; }
    html, body { height: 100%; margin: 0; }
    body {
      background: transparent;
      font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
      overflow: hidden;
    }
    #wrap { height: 100%; display: flex; }
    #chat {
      flex: 1;
      padding: 10px 12px;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      gap: 6px;
      overflow: hidden;
    }
    .line { display: flex; gap: 8px; align-items: baseline; text-shadow: 0 1px 2px rgba(0,0,0,.55); }
    .t { color: rgba(255,255,255,.55); font-size: 12px; min-width: 48px; }
    .u { font-weight: 700; }
    .c { color: rgba(255,255,255,.7); }
    .m { color: rgba(255,255,255,.95); word-break: break-word; }
  </style>
</head>
<body>
  <div id="wrap">
    <div id="chat" aria-live="polite"></div>
  </div>
  <script>
    const chat = document.getElementById("chat");
    const MAX = 60;
    const colors = ["#ff7b72","#ffa657","#ffd93d","#7ee787","#56d4dd","#79c0ff","#d2a8ff","#ff9ec1","#ff8a65","#aed581","#80deea","#ce93d8"];
    function nickColor(nick) {
      let s = 0;
      for (let i = 0; i < nick.length; i++) s = (s + nick.charCodeAt(i)) >>> 0;
      return colors[s % colors.length];
    }
    function addLine(p) {
      if (!p || p.kind !== "msg") return;
      const [user, msg, ts] = [p.user || "", p.msg || "", p.ts || ""];
      const line = document.createElement("div");
      line.className = "line";
      const t = document.createElement("div"); t.className = "t"; t.textContent = ts ? ts : "";
      const u = document.createElement("div"); u.className = "u"; u.textContent = user; u.style.color = nickColor(user);
      const c = document.createElement("div"); c.className = "c"; c.textContent = ":";
      const m = document.createElement("div"); m.className = "m"; m.textContent = msg;
      line.append(t,u,c,m);
      chat.appendChild(line);
      while (chat.children.length > MAX) chat.removeChild(chat.firstChild);
    }
    async function loadHistory() {
      try {
        const r = await fetch("/obs/history.json", { cache: "no-store" });
        if (!r.ok) return;
        const data = await r.json();
        (data || []).forEach(addLine);
      } catch {}
    }
    let lastId = 0;
    function trackId(p) { if (p && p.id) lastId = Math.max(lastId, Number(p.id) || 0); }
    function addLineTracked(p) { trackId(p); addLine(p); }
    async function poll() {
      try {
        const r = await fetch("/obs/history.json?since=" + encodeURIComponent(String(lastId)), { cache: "no-store" });
        if (!r.ok) return;
        const data = await r.json();
        (data || []).forEach(addLineTracked);
      } catch {}
      setTimeout(poll, 1000);
    }
    function connectSseOrPoll() {
      if (typeof EventSource === "undefined") return poll();
      const es = new EventSource("/obs/events");
      let opened = false;
      es.onopen = () => { opened = true; };
      es.onmessage = (e) => {
        try {
          const p = JSON.parse(e.data);
          if (p && p.kind === "msg") addLineTracked(p);
        } catch {}
      };
      es.onerror = () => {
        try { es.close(); } catch {}
        if (!opened) return poll();
        setTimeout(connectSseOrPoll, 1500);
      };
    }
    loadHistory().then(() => {
      // проставим lastId из истории
      try {
        const nodes = chat.children;
        // id хранится только в payload, поэтому lastId обновится на первых SSE/poll ответах
      } catch {}
      connectSseOrPoll();
    });
  </script>
</body>
</html>
"""


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
    .line { display: flex; gap: 8px; align-items: baseline; }
    .t { color: #5a607a; font-size: 12px; min-width: 48px; }
    .u { font-weight: 700; }
    .c { color: #5a607a; }
    .m { color: #e6e8ef; word-break: break-word; }
  </style>
</head>
<body>
  <header>
    <div class="dot">●</div>
    <div>
      <div class="title">Twitch Chat Overlay</div>
      <div class="muted" id="sub">dock</div>
    </div>
  </header>
  <div id="chat" aria-live="polite"></div>
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
    function addLine(p) {
      if (!p || p.kind !== "msg") return;
      const [user, msg, ts] = [p.user || "", p.msg || "", p.ts || ""];
      const line = document.createElement("div");
      line.className = "line";
      const t = document.createElement("div"); t.className = "t"; t.textContent = ts ? ts : "";
      const u = document.createElement("div"); u.className = "u"; u.textContent = user; u.style.color = nickColor(user);
      const c = document.createElement("div"); c.className = "c"; c.textContent = ":";
      const m = document.createElement("div"); m.className = "m"; m.textContent = msg;
      line.append(t,u,c,m);
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
    sub.textContent = "dock · подключение…";
    let lastId = 0;
    function trackId(p) { if (p && p.id) lastId = Math.max(lastId, Number(p.id) || 0); }
    function handlePayload(p) {
      if (!p) return;
      trackId(p);
      if (p.kind === "msg") {
        addLine(p);
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

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        hub: WebHub = self.server.hub  # type: ignore[attr-defined]

        if path in ("/", "/obs", "/obs/"):
            body = b"OK"
            return self._send(200, "text/plain; charset=utf-8", body)

        if path in ("/obs/browser", "/obs/browser.html"):
            return self._send(200, "text/html; charset=utf-8", _OBS_BROWSER_HTML.encode("utf-8"))

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


class ObsWebServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 17655):
        self.host = host
        self.port = int(port)
        self.hub = WebHub()
        self._httpd = None
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        httpd = _ThreadingHTTPServer((self.host, self.port), _ObsHandler)
        httpd.hub = self.hub  # type: ignore[attr-defined]
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread.start()

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
        if kind in ("msg", "status", "system"):
            self._q.put((kind, (self._tag, val)))
        else:
            self._q.put(item)


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
        return {"dock": f"{base}/obs/dock", "browser": f"{base}/obs/browser"}

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
            w, h = 480, 540
            px = self.winfo_rootx() + self.winfo_width() // 2
            py = self.winfo_rooty() + self.winfo_height() // 2
            win.geometry(f"{w}x{h}+{px - w // 2}+{py - h // 2}")
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
        nb_style.configure("Settings.TNotebook",
                            background=self.BG, borderwidth=0)
        nb_style.configure("Settings.TNotebook.Tab",
                            background=self.BG_INPUT, foreground=self.TEXT_MUTED,
                            padding=(14, 5), font=("Segoe UI", 9))
        nb_style.map("Settings.TNotebook.Tab",
                     background=[("selected", self.BG_ELEV), ("active", self.BORDER)],
                     foreground=[("selected", self.TEXT), ("active", self.TEXT)])

        nb = ttk.Notebook(outer, style="Settings.TNotebook")
        nb.pack(fill="both", expand=True)

        # ========== Вкладка 1: OBS ==========
        obs_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=14, pady=14)
        nb.add(obs_tab, text="  OBS  ")

        enabled_var = tk.BooleanVar(value=self._obs_enabled)
        chk = tk.Checkbutton(
            obs_tab,
            text="Включить веб-страницу (Dock / Browser Source)",
            variable=enabled_var,
            bg=self.BG_ELEV, fg=self.TEXT,
            activebackground=self.BG_ELEV, activeforeground=self.TEXT,
            selectcolor=self.BG_INPUT,
            font=("Segoe UI", 10), anchor="w",
        )
        chk.pack(fill="x")

        port_row = tk.Frame(obs_tab, bg=self.BG_ELEV)
        port_row.pack(fill="x", pady=(12, 0))
        tk.Label(port_row, text="Порт:", bg=self.BG_ELEV, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 10)).pack(side="left")
        port_var = tk.StringVar(value=str(self._obs_port))
        port_entry_wrap = tk.Frame(port_row, bg=self.BORDER, padx=1, pady=1)
        port_entry_wrap.pack(side="left", padx=10)
        port_entry = tk.Entry(
            port_entry_wrap, textvariable=port_var, width=8,
            bg=self.BG_INPUT, fg=self.TEXT, insertbackground=self.ACCENT,
            relief="flat", bd=0, font=("Segoe UI", 10),
        )
        port_entry.pack(ipady=5, padx=6, pady=3)

        tk.Label(obs_tab,
                 text="Ссылки активны пока запущено приложение.",
                 bg=self.BG_ELEV, fg=self.TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(14, 6))

        links_row = tk.Frame(obs_tab, bg=self.BG_ELEV)
        links_row.pack(fill="x")

        def _copy_dock():
            self._copy_to_clipboard(self._obs_urls()["dock"])

        def _copy_browser():
            self._copy_to_clipboard(self._obs_urls()["browser"])

        copy_dock_btn = tk.Label(
            links_row, text="Скопировать Dock URL",
            bg=self.BG_INPUT, fg=self.TEXT, padx=12, pady=8,
            cursor="hand2", font=("Segoe UI Semibold", 9),
        )
        copy_dock_btn.pack(side="left")
        copy_dock_btn.bind("<Button-1>", lambda e: _copy_dock())
        self._hover(copy_dock_btn, self.BG_INPUT, self.BORDER, self.TEXT, self.TEXT)

        copy_browser_btn = tk.Label(
            links_row, text="Скопировать Browser URL",
            bg=self.BG_INPUT, fg=self.TEXT, padx=12, pady=8,
            cursor="hand2", font=("Segoe UI Semibold", 9),
        )
        copy_browser_btn.pack(side="left", padx=(10, 0))
        copy_browser_btn.bind("<Button-1>", lambda e: _copy_browser())
        self._hover(copy_browser_btn, self.BG_INPUT, self.BORDER, self.TEXT, self.TEXT)

        # ========== Вкладка 2: Оформление ==========
        theme_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=14, pady=14)
        nb.add(theme_tab, text="  Оформление  ")

        tk.Label(theme_tab, text="Тема интерфейса:",
                 bg=self.BG_ELEV, fg=self.TEXT,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))

        theme_items = [(k, THEMES[k]["name"]) for k in THEMES.keys()]
        name_to_key = {n: k for k, n in theme_items}
        theme_var = tk.StringVar(
            value=THEMES.get(self.theme_name, THEMES["twitch_dark"])["name"]
        )

        for _key, _name in theme_items:
            dot_color = THEMES[_key]["ACCENT"]
            rb_row = tk.Frame(theme_tab, bg=self.BG_ELEV)
            rb_row.pack(fill="x", pady=4)
            tk.Label(rb_row, text="●", bg=self.BG_ELEV, fg=dot_color,
                     font=("Segoe UI", 11)).pack(side="left", padx=(0, 6))
            rb = tk.Radiobutton(
                rb_row, text=_name, variable=theme_var, value=_name,
                bg=self.BG_ELEV, fg=self.TEXT,
                activebackground=self.BG_INPUT, activeforeground=self.TEXT,
                selectcolor=self.BG_INPUT,
                font=("Segoe UI", 10),
            )
            rb.pack(side="left")

        # ========== Вкладка 3: Фильтры ==========
        filter_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=14, pady=14)
        nb.add(filter_tab, text="  Фильтры  ")

        def _make_text_area(parent, label, hint, initial_lines):
            tk.Label(parent, text=label, bg=self.BG_ELEV, fg=self.TEXT,
                     font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 2))
            tk.Label(parent, text=hint, bg=self.BG_ELEV, fg=self.TEXT_MUTED,
                     font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))
            wrap = tk.Frame(parent, bg=self.BORDER, padx=1, pady=1)
            wrap.pack(fill="x", pady=(0, 12))
            txt = tk.Text(
                wrap, height=3, bg=self.BG_INPUT, fg=self.TEXT,
                insertbackground=self.ACCENT, relief="flat", bd=0,
                font=("Segoe UI", 10), padx=6, pady=4,
            )
            txt.insert("1.0", "\n".join(initial_lines))
            txt.pack(fill="x")
            return txt

        hl_text = _make_text_area(
            filter_tab,
            "★  Подсвечивать сообщения со словами:",
            "одно слово / ник на строку (без @)",
            self.highlight_words,
        )
        bu_text = _make_text_area(
            filter_tab,
            "🚫  Скрывать сообщения от пользователей:",
            "один никнейм на строку",
            self.banned_users,
        )
        bw_text = _make_text_area(
            filter_tab,
            "🔇  Скрывать сообщения со словами:",
            "одно слово на строку",
            self.banned_words,
        )

        # ========== Вкладка 4: Сообщения ==========
        msg_tab = tk.Frame(nb, bg=self.BG_ELEV, padx=14, pady=14)
        nb.add(msg_tab, text="  Сообщения  ")

        tk.Label(msg_tab, text="Стиль подложки сообщений:",
                 bg=self.BG_ELEV, fg=self.TEXT,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))

        msg_style_var = tk.StringVar(value=self.msg_style)

        # Описания и предпросмотр для каждого стиля
        _style_hints = {
            "none":   "Классический — только текст, без фона",
            "card":   "Каждое сообщение на отдельной карточке",
            "stripe": "Чередующиеся цветные полосы фона",
            "glow":   "Слабое свечение цветом темы/канала",
            "pill":   "Пилюля с акцентным цветом + отступ",
        }

        def _preview_color(sk: str) -> str:
            """Цвет предпросмотра для стиля."""
            if sk == "none":   return self.BG
            if sk == "card":   return self.BG_ELEV
            if sk == "stripe": return self.BG_ELEV
            if sk == "glow":   return _blend_color(self.BG, self.ACCENT, 0.14)
            if sk == "pill":   return _blend_color(self.BG_ELEV, self.ACCENT, 0.22)
            return self.BG_ELEV

        for sk, sname in MSG_STYLES.items():
            row = tk.Frame(msg_tab, bg=self.BG_ELEV)
            row.pack(fill="x", pady=5)

            rb = tk.Radiobutton(
                row, text=sname, variable=msg_style_var, value=sk,
                bg=self.BG_ELEV, fg=self.TEXT,
                activebackground=self.BG_INPUT, activeforeground=self.TEXT,
                selectcolor=self.BG_INPUT,
                font=("Segoe UI", 10), anchor="w",
            )
            rb.pack(side="left")

            hint = tk.Label(
                row, text=_style_hints.get(sk, ""),
                bg=self.BG_ELEV, fg=self.TEXT_MUTED,
                font=("Segoe UI", 8))
            hint.pack(side="left", padx=(6, 0))

            # Мини-превью цвета подложки
            prev_col = _preview_color(sk)
            prev = tk.Frame(row, bg=prev_col, width=52, height=20)
            prev.pack(side="right", padx=(0, 4))
            prev.pack_propagate(False)
            tk.Label(prev, text="Aa",
                     bg=prev_col, fg=self.TEXT,
                     font=("Segoe UI", 8)).pack(expand=True)

        # ========== Нижние кнопки ==========
        btns = tk.Frame(outer, bg=self.BG)
        btns.pack(fill="x", pady=(10, 0))

        err_lbl = tk.Label(btns, text="", bg=self.BG, fg=self.DANGER,
                           font=("Segoe UI", 9))
        err_lbl.pack(side="left")

        def _close():
            try:
                win.destroy()
            except Exception:
                pass

        def _parse_lines(widget):
            raw = widget.get("1.0", "end").strip()
            return [w.strip().lower() for w in raw.splitlines() if w.strip()]

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
            # тема
            selected_name = theme_var.get().strip()
            selected_key  = name_to_key.get(selected_name, "twitch_dark")
            if selected_key != self.theme_name:
                global PALETTE
                self.theme_name = selected_key
                PALETTE = THEMES[self.theme_name]
                self._apply_theme_values(THEMES[self.theme_name])
                self._apply_theme_runtime()
            # OBS
            self._apply_obs_settings(bool(enabled_var.get()), port)
            # фильтры
            self.highlight_words = _parse_lines(hl_text)
            self.banned_users    = _parse_lines(bu_text)
            self.banned_words    = _parse_lines(bw_text)
            # стиль сообщений
            new_style = msg_style_var.get()
            if new_style != self.msg_style:
                self.msg_style = new_style
                self._configure_row_tags()

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
        try:
            port_entry.focus_set()
            port_entry.select_range(0, "end")
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

    def _get_row_tag(self, channel_tag: str) -> str | None:
        """Возвращает имя tk-тега подложки для данного сообщения."""
        style = self.msg_style
        if style == "none":
            return None
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
        ml = msg.lower()
        return any(w and w in ml for w in self.highlight_words)

    def _log_system(self, msg):
        # Системные сообщения не выводим в чат — только в файл-лог.
        # Видимая обратная связь идёт через статус-бар (_set_status).
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._save_history_line(f"[{ts}] * {msg}")

    def _log_message(self, tag, user, msg):
        if self._is_banned(user, msg):
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S")

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

        if self._is_highlight(user, msg):
            segs = (
                [("★ ", "highlight_mark"), (f"{ts}  ", "time")]
                + src_segs
                + [(user, self._nick_tag(user)),
                   (": ", "colon"),
                   (msg.rstrip() + "\n", "highlight_msg")]
            )
        else:
            segs = (
                [(f" {ts}  ", "time")]
                + src_segs
                + [(user, self._nick_tag(user)),
                   (": ", "colon"),
                   (msg.rstrip() + "\n", "msg")]
            )

        self._append(segs, row_tag=row_tag)
        self._row_counter += 1
        self._save_history_line(f"[{ts}] [{tag}] {user}: {msg}")
        self._msg_count += 1
        self.count_lbl.config(text=f"{self._msg_count} сообщений")

    def _set_status(self, state, text=None):
        """Прямая установка статуса (backward compat)."""
        if state == "online":
            self._set_status_raw("online",
                                 text or f"подключено · {self.channel}")
        elif state == "warn":
            self._set_status_raw("warn", text or "ожидание...")
        else:
            self._set_status_raw("offline", text or "не подключено")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()

                if kind == "system":
                    # payload = (tag, text)
                    _, text = payload if isinstance(payload, tuple) else ("", payload)
                    self._log_system(text)

                elif kind == "msg":
                    # payload = (tag, (user, msg))  — от _TaggedQueue
                    if isinstance(payload, tuple) and len(payload) == 2:
                        tag, inner = payload
                        if isinstance(inner, tuple):
                            user, msg = inner
                        else:
                            # неожиданный формат — пропускаем
                            continue
                    else:
                        continue
                    self._log_message(tag, user, msg)
                    if self._obs_server:
                        try:
                            self._obs_server.hub.publish({
                                "kind": "msg",
                                "user": user,
                                "msg":  msg.rstrip(),
                                "ts":   datetime.datetime.now().strftime(
                                    "%H:%M:%S"),
                            })
                        except Exception:
                            pass

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
