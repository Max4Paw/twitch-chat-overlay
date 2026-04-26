# Twitch Chat Overlay

<p align="center">
  <img src="icon.png" alt="logo" width="128" height="128">
</p>

<p align="center">
  Прозрачное окно поверх всех приложений с чатом любого Twitch-канала.<br/>
  Anonymous, no OAuth, modern dark UI, system tray, taskbar icon, click-through chroma mode.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="python">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white" alt="windows">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
</p>

---

## Возможности

- **Анонимное подключение** к Twitch IRC — без OAuth-токена и регистрации.
- **Поверх всех окон** (always-on-top) — удобно во время игры/работы.
- **Регулируемая прозрачность** — слайдер 20–100% или хоткей `+`/`−`.
- **Прозрачный фон** (chroma key, Windows) — фон полностью невидим, через
  него можно кликать насквозь, остаётся только текст чата.
- **Перетаскивание** мышью + ресайз за края и угол.
- **Регулируемый размер шрифта** — кнопки `A+ / A−`, `Ctrl + колесо мыши`,
  `Ctrl + +/−`, `Ctrl + 0`.
- **Авто-скрытие шапки/футера** — когда курсор уходит с окна, остаётся
  только сам чат.
- **Сохранение истории** в `chat_history.txt` (можно отключить).
- **Системный трей** с меню (показать/скрыть, поверх окон, прозрачность,
  смена канала, выход).
- **Иконка в панели задач Windows** — настоящая, не дефолтная Tk.
- **Автоматическое переподключение** при обрыве связи.

---

## Скриншот

> _Добавьте свой скриншот в `docs/screenshot.png` и раскомментируйте строку ниже._

<!-- ![screenshot](docs/screenshot.png) -->

---

## Быстрый старт

### Запуск из исходников

```bash
git clone https://github.com/Max4Paw/twitch-chat-overlay.git
cd twitch-chat-overlay
pip install -r requirements.txt
python twitch_overlay.py
```

При запуске появится диалог — введите имя канала (без `#`).
Можно сразу указать канал в командной строке:

```bash
python twitch_overlay.py shroud
```

### Сборка `.exe` для Windows

```bat
build.bat
```

Скрипт сам поставит зависимости (PyInstaller, pystray, Pillow, keyboard),
соберёт автономный `dist\twitch_overlay.exe` с фиолетовой T-иконкой и
почистит кэш иконок Windows. Готовый файл можно переносить куда угодно —
он не зависит от установленного Python.

---

## Управление

### Кнопки в шапке (справа налево)

| Кнопка | Действие |
| --- | --- |
| `✕` | Закрыть |
| `📌` | Включить/выключить «поверх окон» |
| `⟳` | Сменить канал |
| `◐` | Прозрачный фон (chroma key, Windows) |
| `A+` / `A−` | Размер шрифта чата |
| `—` | Свернуть в трей |

### Горячие клавиши (когда окно в фокусе)

| Клавиши | Действие |
| --- | --- |
| `Esc` | Скрыть окно |
| `+` / `−` | Общая прозрачность |
| `Ctrl + +` / `Ctrl + −` | Размер шрифта |
| `Ctrl + 0` | Сбросить шрифт |
| `Ctrl + колесо мыши` | Размер шрифта |
| `Ctrl + Q` | Выход |

### Глобальные (если установлен `keyboard`)

| Клавиши | Действие |
| --- | --- |
| `Ctrl + Alt + H` | Скрыть/показать окно |
| `Ctrl + Alt + Q` | Выход |

---

## Зависимости

Минимально нужен Python 3.10+ со встроенным `tkinter`.
Опциональные пакеты:

| Пакет | Зачем нужен |
| --- | --- |
| `pystray` + `Pillow` | Иконка в системном трее с контекстным меню |
| `keyboard` | Глобальные горячие клавиши (работают из любого окна) |
| `pyinstaller` | Только для сборки `.exe` |

Установить всё разом:

```bash
pip install -r requirements.txt
```

---

## Файлы программы

| Файл | Описание |
| --- | --- |
| `twitch_overlay.py` | Основной скрипт |
| `icon.ico` / `icon.png` | Иконки приложения и трея |
| `twitch_overlay.spec` | Конфиг PyInstaller |
| `build.bat` | Скрипт сборки `.exe` под Windows |
| `overlay_config.json` | Сохраняется при выходе (geometry, alpha, шрифт) |
| `chat_history.txt` | Лог принятых сообщений |

---

## Как это работает

Подключение идёт по стандартному Twitch IRC-протоколу через сокет на
`irc.chat.twitch.tv:6667` под анонимным ником `justinfan*****`. Это
официально поддерживаемый Twitch'ем способ читать чат без авторизации,
поэтому не требуется ни регистрация, ни OAuth-токен — но и отправлять
сообщения нельзя, только читать.

Окно использует `tk.overrideredirect(True)` (без рамки), а через
Win32 API (`SetWindowLongPtrW` + `WS_EX_APPWINDOW`, `WM_SETICON`,
`SetCurrentProcessExplicitAppUserModelID`) появляется в taskbar
с собственной иконкой. Прозрачный фон реализован через
`-transparentcolor` (доступно только в Windows-версии Tk).

---

## Лицензия

[MIT](LICENSE) © 2026 Max4Paw
