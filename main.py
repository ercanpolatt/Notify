"""
Focus Notifier — v3
  • Sekme 1: Bildirim + geri sayım + isteğe bağlı sesli alarm
  • Sekme 2: Kronometre
  • Saat seçici: Scroll / sürükle tarzı drum-roll picker
  • Sistem tepsisi desteği
"""

import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime
import threading
import time
import math
import wave, struct, os, tempfile
import pystray
from PIL import Image, ImageDraw
from winotify import Notification

# ══════════════════════════════════════════════════
#  RENK PALETİ — Koyu Saat / Terminal Estetiği
# ══════════════════════════════════════════════════
BG       = "#0D0D14"
PANEL    = "#13131F"
CARD     = "#18182A"
CARD2    = "#1F1F35"
BORDER   = "#272742"
ACCENT   = "#00D4FF"   # siyan
ACCENT2  = "#FF4F8B"   # pembe-kırmızı
GREEN    = "#00FFB2"
AMBER    = "#FFB830"
TEXT     = "#E8EAF6"
SUBTEXT  = "#525278"
DIM      = "#2A2A44"

F_MONO   = ("Consolas", 11)
F_MONO_L = ("Consolas", 36, "bold")
F_MONO_M = ("Consolas", 22, "bold")
F_MONO_S = ("Consolas", 13, "bold")
F_UI     = ("Segoe UI", 9)
F_UI_B   = ("Segoe UI Semibold", 9)
F_UI_T   = ("Segoe UI Semibold", 15)
F_SM     = ("Segoe UI", 8)

# ══════════════════════════════════════════════════
#  SES — WAV üret + çal (çoklu yöntem)
# ══════════════════════════════════════════════════
def generate_beep_wav(path, freq=880, duration=0.3, volume=0.9, repeat=6):
    """Sinüs dalgası tabanlı alarm sesi üret."""
    sample_rate = 44100
    n = int(sample_rate * duration)
    silence = int(sample_rate * 0.07)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for _ in range(repeat):
            for i in range(n):
                env = 1.0
                if i < n * 0.1:
                    env = i / (n * 0.1)
                elif i > n * 0.9:
                    env = (n - i) / (n * 0.1)
                val = int(32767 * volume * env *
                          math.sin(2 * math.pi * freq * i / sample_rate))
                wf.writeframes(struct.pack('<h', val))
            for _ in range(silence):
                wf.writeframes(struct.pack('<h', 0))

# Betik ile aynı klasöre kaydet (temp silinirse sorun olmasın)
_app_dir   = os.path.dirname(os.path.abspath(__file__))
_beep_path = os.path.join(_app_dir, "fn_alarm.wav")
generate_beep_wav(_beep_path)


def _play_via_powershell(path):
    """PowerShell SoundPlayer ile senkron çal — en güvenilir yöntem."""
    import subprocess
    ps_cmd = (
        f"$p = New-Object System.Media.SoundPlayer('{path}');"
        f"$p.PlaySync();"
    )
    subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
        creationflags=0x08000000   # CREATE_NO_WINDOW
    )


def _play_via_winsound(path):
    import winsound
    winsound.PlaySound(
        path,
        winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    )


def play_alarm():
    """Alarm sesini ayrı thread'de çal; birincil başarısız olursa fallback."""
    def _run():
        try:
            _play_via_powershell(_beep_path)
        except Exception:
            try:
                _play_via_winsound(_beep_path)
            except Exception:
                pass
    threading.Thread(target=_run, daemon=True).start()

# ══════════════════════════════════════════════════
#  GLOBAL DURUM
# ══════════════════════════════════════════════════
running       = False
tray_icon     = None
root          = None
alarm_enabled = None   # BooleanVar — pencere oluşturulunca set edilecek

# ══════════════════════════════════════════════════
#  TRAY
# ══════════════════════════════════════════════════
def create_tray_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill="#00D4FF")
    d.ellipse([10, 10, 54, 54], outline="#0D0D14", width=4)
    d.line([32, 16, 32, 32], fill="#0D0D14", width=3)
    d.line([32, 32, 46, 42], fill="#0D0D14", width=3)
    return img

def _show_window():
    root.deiconify(); root.lift(); root.focus_force()

def show_window(icon=None, item=None):
    root.after(0, _show_window)

def quit_app(icon=None, item=None):
    global running
    running = False
    if tray_icon: tray_icon.stop()
    root.after(0, root.destroy)

def setup_tray():
    global tray_icon
    menu = pystray.Menu(
        pystray.MenuItem("Göster", show_window, default=True),
        pystray.MenuItem("Çıkış",  quit_app)
    )
    tray_icon = pystray.Icon("FocusNotifier", create_tray_image(), "Focus Notifier", menu)
    tray_icon.run()

def on_close():
    root.withdraw()
    if tray_icon is None:
        threading.Thread(target=setup_tray, daemon=True).start()

# ══════════════════════════════════════════════════
#  BİLDİRİM & ZAMANLAYICI
# ══════════════════════════════════════════════════
def send_notification(title, message):
    toast = Notification(app_id="FocusNotifier", title=title, msg=message, duration="short")
    toast.show()

def scheduler_thread(target_h, target_m, title, message, sound):
    global running
    target_str = f"{target_h:02d}:{target_m:02d}"
    while running:
        now = datetime.now()
        if now.strftime("%H:%M") == target_str:
            send_notification(title, message)
            if sound:
                play_alarm()
            running = False
            # UI'yi ana thread'den güncelle
            root.after(0, _alarm_fired)
            return
        time.sleep(1)


def _alarm_fired():
    """Alarm çaldıktan sonra UI'yi sıfırla."""
    set_status0("✓ Alarm çaldı!", GREEN)
    start_btn0.config(state="normal", bg=ACCENT)
    stop_btn0.config(state="disabled", bg=DIM)
    cd_lbl.config(text="ALARM ÇALDI", fg=GREEN)

# ══════════════════════════════════════════════════
#  DRUM-ROLL PICKER (kaydırılabilir saat/dakika)
# ══════════════════════════════════════════════════
class DrumPicker(tk.Canvas):
    """Dikey kaydırmalı drum-roll sayı seçici."""

    ITEM_H = 38
    VISIBLE = 3   # görünen satır sayısı (tek sayı olmalı)

    def __init__(self, master, values, init_val, fg=ACCENT, **kw):
        h = self.ITEM_H * self.VISIBLE
        super().__init__(master, width=70, height=h,
                         bg=CARD2, highlightthickness=0, **kw)
        self._values = values
        self._fg     = fg
        self._idx    = values.index(init_val) if init_val in values else 0
        self._drag_y = None
        self._offset = 0.0   # piksel kayma (animasyon için)

        self.bind("<MouseWheel>",      self._on_wheel)
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._draw()

    # ── Çizim ──────────────────────────────────────
    def _draw(self):
        self.delete("all")
        W = 70
        H = self.ITEM_H * self.VISIBLE
        mid = H // 2

        # Arka plan
        self.create_rectangle(0, 0, W, H, fill=CARD2, outline="")

        # Seçili satır vurgusu
        self.create_rectangle(0, mid - self.ITEM_H//2,
                              W, mid + self.ITEM_H//2,
                              fill=CARD, outline=ACCENT, width=1)

        # Sayılar
        n = len(self._values)
        half = self.VISIBLE // 2
        for rel in range(-half - 1, half + 2):
            real_idx = (self._idx + rel) % n
            val = self._values[real_idx]
            y = mid + rel * self.ITEM_H + self._offset
            dist = abs(rel - self._offset / self.ITEM_H)
            if dist < 0.1:
                col = self._fg
                fsize = 22
                fw = "bold"
            elif dist < 1.2:
                # Aradaki geçiş
                alpha = max(0, 1 - dist)
                col = self._blend(self._fg, SUBTEXT, alpha)
                fsize = int(13 + 9 * max(0, 1 - dist))
                fw = "normal"
            else:
                col = SUBTEXT
                fsize = 13
                fw = "normal"
            self.create_text(W // 2, y,
                             text=f"{val:02d}",
                             font=("Consolas", fsize, fw),
                             fill=col, anchor="center")

        # Üst/alt fade maskesi
        for i, y0 in [(0, 0), (1, mid + self.ITEM_H//2)]:
            fade_h = self.ITEM_H
            fill = CARD2 if i == 0 else CARD2
            end_y = y0 + fade_h if i == 0 else y0
            start_y = y0 if i == 0 else y0 + fade_h
            # Basit dikdörtgen mask
            if i == 0:
                self.create_rectangle(0, 0, W, mid - self.ITEM_H//2,
                                      fill=CARD2, outline="", stipple="")
            else:
                self.create_rectangle(0, mid + self.ITEM_H//2, W, H,
                                      fill=CARD2, outline="")

        # Üst / Alt çizgi
        self.create_line(0, mid - self.ITEM_H//2, W, mid - self.ITEM_H//2,
                         fill=ACCENT, width=1)
        self.create_line(0, mid + self.ITEM_H//2, W, mid + self.ITEM_H//2,
                         fill=ACCENT, width=1)

    @staticmethod
    def _blend(hex1, hex2, t):
        r1,g1,b1 = int(hex1[1:3],16), int(hex1[3:5],16), int(hex1[5:7],16)
        r2,g2,b2 = int(hex2[1:3],16), int(hex2[3:5],16), int(hex2[5:7],16)
        r = int(r1*t + r2*(1-t))
        g = int(g1*t + g2*(1-t))
        b = int(b1*t + b2*(1-t))
        return f"#{r:02X}{g:02X}{b:02X}"

    # ── Etkileşim ──────────────────────────────────
    def _on_wheel(self, e):
        delta = -1 if e.delta > 0 else 1
        self._idx = (self._idx + delta) % len(self._values)
        self._draw()

    def _on_press(self, e):
        self._drag_y = e.y
        self._base_idx = self._idx

    def _on_drag(self, e):
        if self._drag_y is None: return
        dy = self._drag_y - e.y
        steps = int(dy / self.ITEM_H)
        self._idx = (self._base_idx + steps) % len(self._values)
        self._offset = -(dy % self.ITEM_H - (self.ITEM_H if dy % self.ITEM_H > self.ITEM_H/2 else 0))
        self._draw()

    def _on_release(self, e):
        self._offset = 0.0
        self._drag_y = None
        self._draw()

    # ── Değer okuma ────────────────────────────────
    def get(self):
        return self._values[self._idx]

    def set_val(self, v):
        if v in self._values:
            self._idx = self._values.index(v)
            self._draw()


# ══════════════════════════════════════════════════
#  SEKMELİ PANEL sistemi (sade, özel çizim)
# ══════════════════════════════════════════════════
class TabBar(tk.Canvas):
    def __init__(self, master, tabs, on_change, **kw):
        super().__init__(master, height=44, bg=PANEL,
                         highlightthickness=0, **kw)
        self._tabs     = tabs
        self._active   = 0
        self._on_change = on_change
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<ButtonPress-1>", self._on_click)

    def _draw(self):
        self.delete("all")
        W = self.winfo_width() or 480
        n = len(self._tabs)
        tw = W // n
        for i, label in enumerate(self._tabs):
            x0 = i * tw
            x1 = x0 + tw
            active = (i == self._active)
            bg = CARD if active else PANEL
            self.create_rectangle(x0, 0, x1, 44, fill=bg, outline="")
            col = ACCENT if active else SUBTEXT
            self.create_text((x0+x1)//2, 22, text=label,
                             font=F_UI_B, fill=col)
            if active:
                self.create_line(x0, 43, x1, 43, fill=ACCENT, width=2)

    def _on_click(self, e):
        W = self.winfo_width() or 480
        tw = W // len(self._tabs)
        idx = e.x // tw
        if 0 <= idx < len(self._tabs) and idx != self._active:
            self._active = idx
            self._draw()
            self._on_change(idx)

    def set_active(self, idx):
        self._active = idx
        self._draw()


# ══════════════════════════════════════════════════
#  YARDIMCILAR
# ══════════════════════════════════════════════════
def hover(w, normal, hov, nfg=TEXT, hfg=TEXT):
    w.bind("<Enter>", lambda e: w.config(bg=hov, fg=hfg))
    w.bind("<Leave>", lambda e: w.config(bg=normal, fg=nfg))

def styled_btn(parent, text, bg, fg, cmd, w=None, h=None):
    kw = dict(font=F_UI_B, bg=bg, fg=fg, activebackground=bg,
              activeforeground=fg, bd=0, relief="flat", cursor="hand2",
              command=cmd)
    if w: kw["width"] = w
    if h: kw["height"] = h
    btn = tk.Button(parent, text=text, **kw)
    hover(btn, bg, _lighten(bg), fg, fg)
    return btn

def _lighten(c, a=28):
    r=min(255,int(c[1:3],16)+a); g=min(255,int(c[3:5],16)+a); b=min(255,int(c[5:7],16)+a)
    return f"#{r:02X}{g:02X}{b:02X}"


# ══════════════════════════════════════════════════
#  PENCERE
# ══════════════════════════════════════════════════
root = tk.Tk()
root.title("Focus Notifier")
root.geometry("480x620")
root.resizable(False, False)
root.configure(bg=PANEL)
root.protocol("WM_DELETE_WINDOW", on_close)

alarm_enabled = tk.BooleanVar(value=True)

# ══════════════════════════════════════════════════
#  BAŞLIK BAR
# ══════════════════════════════════════════════════
header = tk.Frame(root, bg=BG, height=56)
header.pack(fill="x")
header.pack_propagate(False)

tk.Label(header, text="⏱  FOCUS NOTIFIER",
         font=("Consolas", 13, "bold"), bg=BG, fg=ACCENT).place(x=20, y=16)

clock_lbl = tk.Label(header, font=("Consolas", 13, "bold"), bg=BG, fg=SUBTEXT)
clock_lbl.place(x=340, y=16)

def update_clock():
    clock_lbl.config(text=datetime.now().strftime("%H:%M:%S"))
    root.after(1000, update_clock)
update_clock()

# Ince çizgi
tk.Frame(root, bg=ACCENT, height=1).pack(fill="x")

# ══════════════════════════════════════════════════
#  SEKME SİSTEMİ
# ══════════════════════════════════════════════════
tab_labels = ["  🔔  BİLDİRİM  ", "  ⏱  KRONOMETRİ  "]

content_frame = tk.Frame(root, bg=CARD)
content_frame.pack(fill="both", expand=True)

pages = {}

def switch_tab(idx):
    for i, f in pages.items():
        f.place_forget()
    pages[idx].place(x=0, y=0, relwidth=1, relheight=1)

tab_bar = TabBar(root, tab_labels, switch_tab)
tab_bar.pack(fill="x")
tab_bar.update_idletasks()

# ── SAYFA ÇERÇEVELERI ──
for i in range(2):
    f = tk.Frame(content_frame, bg=CARD)
    pages[i] = f

switch_tab(0)   # varsayılan

# ══════════════════════════════════════════════════
#  SAYFA 0 — BİLDİRİM
# ══════════════════════════════════════════════════
pg0 = pages[0]

# ── Saat Seçici ─────────────────────────────────
lbl_frame = tk.Frame(pg0, bg=CARD)
lbl_frame.place(x=0, y=12, width=480)
tk.Label(lbl_frame, text="ALARM SAATİNİ SEÇ",
         font=("Consolas", 9), bg=CARD, fg=SUBTEXT).pack()

picker_outer = tk.Frame(pg0, bg=CARD)
picker_outer.place(x=0, y=34, width=480)

# Picker kapsayıcı (ortala)
picker_wrap = tk.Frame(picker_outer, bg=CARD)
picker_wrap.pack(anchor="center")

hour_picker   = DrumPicker(picker_wrap, list(range(24)),
                           datetime.now().hour,   fg=ACCENT)
sep_lbl = tk.Label(picker_wrap, text=":", font=("Consolas", 32, "bold"),
                   bg=CARD, fg=ACCENT)
minute_picker = DrumPicker(picker_wrap, list(range(60)),
                           datetime.now().minute, fg=ACCENT2)

hour_picker.grid(row=0, column=0, padx=8)
sep_lbl.grid(row=0, column=1, pady=4)
minute_picker.grid(row=0, column=2, padx=8)

tk.Label(picker_wrap, text="saat", font=F_SM, bg=CARD, fg=SUBTEXT).grid(row=1,column=0)
tk.Label(picker_wrap, text="dk",   font=F_SM, bg=CARD, fg=SUBTEXT).grid(row=1,column=2)

# ── Başlık & Mesaj ─────────────────────────────
def field0(parent, label, var, y):
    tk.Label(parent, text=label, font=("Consolas", 8),
             bg=CARD, fg=SUBTEXT).place(x=28, y=y)
    e = tk.Entry(parent, textvariable=var, font=F_MONO,
                 bg=CARD2, fg=TEXT, insertbackground=ACCENT,
                 bd=0, highlightthickness=1,
                 highlightcolor=ACCENT, highlightbackground=BORDER)
    e.place(x=28, y=y+17, width=424, height=32)
    return e

title_var = tk.StringVar(value="Mola Zamanı!")
msg_var   = tk.StringVar(value="Kalk, biraz gez, su iç! 💧")
field0(pg0, "BİLDİRİM BAŞLIĞI", title_var, 182)
field0(pg0, "MESAJ",            msg_var,   235)

# ── Sesli alarm seçeneği ───────────────────────
alarm_row = tk.Frame(pg0, bg=CARD)
alarm_row.place(x=28, y=282)

alarm_cb = tk.Checkbutton(alarm_row, text="  Sesli alarm çal",
                          variable=alarm_enabled,
                          font=F_UI, bg=CARD, fg=TEXT,
                          activebackground=CARD, activeforeground=ACCENT,
                          selectcolor=CARD2,
                          highlightthickness=0, bd=0, cursor="hand2")
alarm_cb.pack(side="left")

# ── Başlat / Durdur ────────────────────────────
btn_row0 = tk.Frame(pg0, bg=CARD)
btn_row0.place(x=28, y=314)

def do_start():
    global running
    if running:
        set_status0("Zaten çalışıyor!", AMBER); return
    h = hour_picker.get()
    m = minute_picker.get()
    ttl = title_var.get().strip()
    msg = msg_var.get().strip()
    if not ttl or not msg:
        set_status0("Başlık/mesaj boş!", ACCENT2); return
    running = True
    sound = alarm_enabled.get()
    threading.Thread(target=scheduler_thread,
                     args=(h, m, ttl, msg, sound), daemon=True).start()
    set_status0(f"✓ {h:02d}:{m:02d} için aktif", GREEN)
    start_btn0.config(state="disabled", bg=DIM)
    stop_btn0.config(state="normal",   bg=ACCENT2)
    start_countdown(h, m)

def do_stop():
    global running
    running = False
    set_status0("Durduruldu.", AMBER)
    start_btn0.config(state="normal", bg=ACCENT)
    stop_btn0.config(state="disabled", bg=DIM)
    cd_lbl.config(text="--:--:--", fg=SUBTEXT)

start_btn0 = styled_btn(btn_row0, "▶  BAŞLAT", ACCENT, BG, do_start)
start_btn0.pack(side="left", ipadx=18, ipady=8)

stop_btn0 = styled_btn(btn_row0, "■  DURDUR", DIM, SUBTEXT, do_stop)
stop_btn0.pack(side="left", padx=(12,0), ipadx=18, ipady=8)
stop_btn0.config(state="disabled")

# ── Durum mesajı ───────────────────────────────
status_row0 = tk.Frame(pg0, bg=CARD)
status_row0.place(x=28, y=362)
status_dot0 = tk.Label(status_row0, text="●", font=F_UI, bg=CARD, fg=SUBTEXT)
status_dot0.pack(side="left", padx=(0,4))
status_lbl0 = tk.Label(status_row0, text="Bekliyor...", font=F_UI, bg=CARD, fg=SUBTEXT)
status_lbl0.pack(side="left")

def set_status0(msg, color):
    status_dot0.config(fg=color)
    status_lbl0.config(text=msg, fg=color)

# ── GERİ SAYIM ─────────────────────────────────
cd_outer = tk.Frame(pg0, bg=CARD2, highlightthickness=1, highlightbackground=BORDER)
cd_outer.place(x=28, y=388, width=424, height=72)

tk.Label(cd_outer, text="KALAN SÜRE", font=("Consolas", 8),
         bg=CARD2, fg=SUBTEXT).place(x=16, y=8)

cd_lbl = tk.Label(cd_outer, text="--:--:--",
                  font=("Consolas", 32, "bold"), bg=CARD2, fg=SUBTEXT)
cd_lbl.place(x=0, y=18, width=424)

_cd_after_id = None

def start_countdown(target_h, target_m):
    global _cd_after_id
    if _cd_after_id:
        root.after_cancel(_cd_after_id)

    def tick():
        global _cd_after_id
        if not running:
            return
        now = datetime.now()
        target_today = now.replace(hour=target_h, minute=target_m,
                                   second=0, microsecond=0)
        if target_today <= now:
            # Yarınki alarm
            from datetime import timedelta
            target_today += timedelta(days=1)
        diff = int((target_today - now).total_seconds())
        if diff <= 0:
            cd_lbl.config(text="ALARM ÇALDI", fg=GREEN)
            return
        h = diff // 3600
        m = (diff % 3600) // 60
        s = diff % 60
        cd_lbl.config(text=f"{h:02d}:{m:02d}:{s:02d}", fg=ACCENT)
        _cd_after_id = root.after(1000, tick)

    tick()

# Alt bilgi
tk.Label(pg0, text="Kapat → sistem tepsisine küçülür",
         font=("Consolas", 7), bg=CARD, fg=SUBTEXT).place(x=28, y=476)

# ══════════════════════════════════════════════════
#  SAYFA 1 — KRONOMETRİ
# ══════════════════════════════════════════════════
pg1 = pages[1]

_sw_running  = False
_sw_start    = 0.0
_sw_elapsed  = 0.0
_sw_after    = None
_sw_laps     = []

sw_display_frame = tk.Frame(pg1, bg=CARD)
sw_display_frame.place(x=0, y=30, width=480)

# Dairesel progress (canvas)
SW_R = 110   # yarıçap
sw_canvas = tk.Canvas(pg1, width=SW_R*2+20, height=SW_R*2+20,
                       bg=CARD, highlightthickness=0)
sw_canvas.place(x=480//2 - (SW_R+10), y=20)

def draw_sw_circle(frac):
    sw_canvas.delete("all")
    cx = cy = SW_R + 10
    r = SW_R
    # Arka çember
    sw_canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                          outline=DIM, width=8)
    # İlerleme yayı
    if frac > 0:
        extent = -frac * 360
        sw_canvas.create_arc(cx-r, cy-r, cx+r, cy+r,
                             start=90, extent=extent,
                             outline=ACCENT, width=8, style="arc")
    # Merkez zaman
    sw_canvas.create_text(cx, cy, text=_format_sw(_sw_elapsed),
                          font=("Consolas", 28, "bold"), fill=TEXT)
    # Alt küçük metin
    frac_txt = f"{int(frac*100):03d}%"
    sw_canvas.create_text(cx, cy+38, text=frac_txt,
                          font=("Consolas", 10), fill=SUBTEXT)

def _format_sw(secs):
    h = int(secs) // 3600
    m = (int(secs) % 3600) // 60
    s = int(secs) % 60
    cs = int((secs - int(secs)) * 100)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}.{cs:02d}"

def sw_tick():
    global _sw_elapsed, _sw_after
    if _sw_running:
        _sw_elapsed = time.perf_counter() - _sw_start
    frac = (_sw_elapsed % 60) / 60
    draw_sw_circle(frac)
    _sw_after = root.after(30, sw_tick)

def sw_start_stop():
    global _sw_running, _sw_start
    if _sw_running:
        _sw_running = False
        sw_ss_btn.config(text="▶  DEVAM", bg=ACCENT)
    else:
        _sw_running = True
        _sw_start = time.perf_counter() - _sw_elapsed
        sw_ss_btn.config(text="⏸  DURDUR", bg=ACCENT2)
        if _sw_after is None:
            sw_tick()

def sw_lap():
    if _sw_running or _sw_elapsed > 0:
        idx = len(_sw_laps) + 1
        t = _format_sw(_sw_elapsed)
        _sw_laps.append(t)
        lap_listbox.insert(0, f"  #{idx:02d}   {t}")

def sw_reset():
    global _sw_running, _sw_elapsed, _sw_start, _sw_laps, _sw_after
    _sw_running = False
    _sw_elapsed = 0.0
    _sw_laps = []
    if _sw_after:
        root.after_cancel(_sw_after)
        _sw_after = None
    draw_sw_circle(0)
    lap_listbox.delete(0, "end")
    sw_ss_btn.config(text="▶  BAŞLAT", bg=ACCENT)

# Butonlar
sw_btn_row = tk.Frame(pg1, bg=CARD)
sw_btn_row.place(x=0, y=260, width=480)
sw_btn_inner = tk.Frame(sw_btn_row, bg=CARD)
sw_btn_inner.pack(anchor="center")

sw_ss_btn  = styled_btn(sw_btn_inner, "▶  BAŞLAT", ACCENT,  BG, sw_start_stop)
sw_lap_btn = styled_btn(sw_btn_inner, "⚑  LAP",    CARD2, ACCENT, sw_lap)
sw_rst_btn = styled_btn(sw_btn_inner, "↺  SIFIRLA", DIM,  SUBTEXT, sw_reset)

sw_ss_btn.pack(side="left", ipadx=16, ipady=8, padx=4)
sw_lap_btn.pack(side="left", ipadx=16, ipady=8, padx=4)
sw_rst_btn.pack(side="left", ipadx=16, ipady=8, padx=4)

# Lap listesi
tk.Label(pg1, text="LAP KAYITLARI", font=("Consolas", 8),
         bg=CARD, fg=SUBTEXT).place(x=28, y=308)

lap_frame = tk.Frame(pg1, bg=CARD2, highlightthickness=1, highlightbackground=BORDER)
lap_frame.place(x=28, y=326, width=424, height=140)

lap_scrollbar = tk.Scrollbar(lap_frame, bg=CARD2, troughcolor=CARD2,
                              highlightthickness=0, bd=0)
lap_scrollbar.pack(side="right", fill="y")

lap_listbox = tk.Listbox(lap_frame, font=("Consolas", 10),
                         bg=CARD2, fg=TEXT, selectbackground=BORDER,
                         highlightthickness=0, bd=0, relief="flat",
                         yscrollcommand=lap_scrollbar.set,
                         activestyle="none")
lap_listbox.pack(fill="both", expand=True)
lap_scrollbar.config(command=lap_listbox.yview)

# İlk çizim
draw_sw_circle(0)

# ══════════════════════════════════════════════════
#  ALT DURUM ÇUBUĞU
# ══════════════════════════════════════════════════
footer = tk.Frame(root, bg=BG, height=22)
footer.pack(fill="x", side="bottom")
tk.Label(footer,
         text="Kapat → sistem tepsisine küçülür  •  Arka planda çalışır",
         font=("Consolas", 7), bg=BG, fg=SUBTEXT).pack(side="left", padx=10)

root.mainloop()