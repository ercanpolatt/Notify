# Focus Notifier ⏰

**A lightweight desktop productivity tool built with Python and Tkinter. Set a time, get a Windows notification, and stay on track — even when the window is closed.**


**"You can download the executable by going to the -> dest folder, clicking on -> main.exe, and selecting ->'Download' (Ctrl + Shift + S) from the top right corner."**
---

## Features

**Notification Tab**
- Pick an alarm time using a scrollable drum-roller (mouse wheel or drag)
- Set a custom notification title and message
- Optional sound alarm (beeps when the time is reached)
- Live countdown showing time remaining until the alarm

**Stopwatch Tab**
- Circular progress ring that completes every 60 seconds
- Large digital display with centisecond precision
- Lap recording with scrollable history
- Start / Pause / Lap / Reset controls

**System Tray**
- Closing the window minimizes the app to the system tray
- Notifications and the stopwatch keep running in the background
- Right-click the tray icon to show the window or quit

---

## Requirements

```
pip install winotify pystray Pillow
```

> Windows only. Uses `winsound` (built-in) for the alarm sound.

---

## Usage

```bash
python focus_notifier.py
```

1. Scroll the hour and minute drums to set your alarm time
2. Enter a title and message for the notification
3. Check **Sesli alarm çal** if you want a sound when it fires
4. Click **BAŞLAT** — the countdown starts immediately
5. Close the window; the app keeps running in the system tray

---
