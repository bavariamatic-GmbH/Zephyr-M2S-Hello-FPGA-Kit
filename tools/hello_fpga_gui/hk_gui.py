#!/usr/bin/env python3
"""Hello FPGA Kit test GUI: console, LEDs, raw I2C/SPI, SPI flash U8, debug log.

Talks to the firmware's "hk" shell commands (src/shell/) over the kit's
USB port (MCP2221A -> PIC32 -> MMUART_0). See README.md in this folder.

    python hk_gui.py [--port COMx|SIM] [--baud 460800] [--no-pic32-bridge]
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable, List, Optional

from hk import protocol
from hk.link import CommandResult, Link
from hk.sim import SimBoard

try:
    import serial  # pyserial
    import serial.tools.list_ports
except ImportError:  # pragma: no cover - checked at start-up
    serial = None

APP_TITLE = "Hello FPGA Kit – LED / I2C / SPI / SPI Flash tester"
SIM_PORT = "SIM"
LOG_DIR = Path(__file__).resolve().parent / "logs"
# LED indicator: redraw period, and the shortest blink period it can still
# draw (shorter ones are shown as a steady half-bright LED)
LED_TICK_MS = 25
LED_DRAW_MIN_MS = 4 * LED_TICK_MS
# The board answers within a few ms; a failed I2C probe slower than this means
# no pull-ups on SDA/SCL (firmware src/shell/hk_cmd_i2c.c, HK_I2C_SLOW_MS)
I2C_SLOW_PROBE_S = 0.08
MONO = ("Consolas", 10) if sys.platform.startswith("win") else ("DejaVu Sans Mono", 10)

log = logging.getLogger("hk.gui")


# =========================================================================
# Logging: file (always DEBUG) + queue for the Debug tab
# =========================================================================

class QueueLogHandler(logging.Handler):
    def __init__(self, q: "queue.Queue"):
        super().__init__()
        self.q = q

    def emit(self, record):
        try:
            self.q.put_nowait(("log", record.levelno, self.format(record)))
        except Exception:  # pragma: no cover
            pass


def setup_logging(ui_queue: "queue.Queue") -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"hk_gui_{dt.datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
                            "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    root.addHandler(fh)
    qh = QueueLogHandler(ui_queue)
    qh.setFormatter(fmt)
    qh.setLevel(logging.DEBUG)
    root.addHandler(qh)
    return path


# =========================================================================
# Small widgets
# =========================================================================

def labeled_entry(parent, label: str, width: int, value: str = "", row=0, col=0):
    ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(0, 4), pady=2)
    var = tk.StringVar(value=value)
    ent = ttk.Entry(parent, textvariable=var, width=width)
    ent.grid(row=row, column=col + 1, sticky="w", pady=2)
    return var, ent


class ResultLog(ScrolledText):
    """Read-only log of results with colours."""

    def __init__(self, parent, height=10):
        super().__init__(parent, height=height, font=MONO, wrap="none", state="disabled")
        self.tag_configure("ok", foreground="#1b7f1b")
        self.tag_configure("err", foreground="#c62828")
        self.tag_configure("info", foreground="#1f4e9a")
        self.tag_configure("dim", foreground="#666666")

    def add(self, text: str, tag: str = "info") -> None:
        self.configure(state="normal")
        stamp = dt.datetime.now().strftime("%H:%M:%S ")
        self.insert("end", stamp, "dim")
        self.insert("end", text + "\n", tag)
        self.see("end")
        self.configure(state="disabled")

    def clear(self) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")


# =========================================================================
# Application
# =========================================================================

class App(tk.Tk):
    def __init__(self, args):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1150x780")
        self.minsize(980, 640)

        self.ui_queue: "queue.Queue" = queue.Queue()
        self.log_path = setup_logging(self.ui_queue)
        log.info("GUI started, log file %s", self.log_path)

        self.link = Link(on_line=self._on_line, on_raw=self._on_raw,
                         on_lost=lambda reason: self._ui(lambda: self._link_lost(reason)))
        self.busy = False
        self.port_name = ""
        self.lost_port = ""  # port to reconnect to when the USB cable is back
        self.raw_debug = tk.BooleanVar(value=False)
        # Plain copy for the reader thread: Tk variables belong to the UI thread
        self._raw_debug_on = False
        self.raw_debug.trace_add(
            "write", lambda *_: setattr(self, "_raw_debug_on", self.raw_debug.get()))
        self.history: List[str] = []
        self.hist_idx = 0
        self.flash_dump = b""
        self.flash_dump_addr = 0

        self._style()
        self._build_topbar(args)
        self._build_notebook()
        self._build_statusbar()
        self._refresh_ports()
        if args.port:
            self.port_var.set(args.port)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._poll_queue)
        self._set_connected(False)

    # ------------------------------------------------------------- styling
    def _style(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Status.TLabel", padding=(6, 2))
        style.configure("Conn.TLabel", font=("TkDefaultFont", 10, "bold"))
        style.configure("Big.TButton", padding=(10, 4))
        style.configure("Danger.TButton", foreground="#b71c1c")

    # ------------------------------------------------------------- top bar
    def _build_topbar(self, args):
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(side="top", fill="x")

        ttk.Label(bar, text="Port").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(bar, textvariable=self.port_var, width=22)
        self.port_box.pack(side="left", padx=4)
        ttk.Button(bar, text="⟳", width=3, command=self._refresh_ports).pack(side="left")

        ttk.Label(bar, text="Baud").pack(side="left", padx=(12, 0))
        self.baud_var = tk.StringVar(value=str(args.baud))
        ttk.Combobox(bar, textvariable=self.baud_var, width=8,
                     values=["460800", "230400", "115200"]).pack(side="left", padx=4)

        self.bridge_var = tk.BooleanVar(value=not args.no_pic32_bridge)
        ttk.Checkbutton(bar, text="PIC32 bridge (&)", variable=self.bridge_var).pack(
            side="left", padx=(12, 0))
        self.stop_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Stop demo loop on connect",
                        variable=self.stop_loop_var).pack(side="left", padx=(12, 0))
        self.reconnect_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Auto-reconnect",
                        variable=self.reconnect_var).pack(side="left", padx=(12, 0))

        self.conn_btn = ttk.Button(bar, text="Connect", style="Big.TButton",
                                   command=self._toggle_connect)
        self.conn_btn.pack(side="left", padx=(16, 8))
        self.conn_label = ttk.Label(bar, text="●  disconnected", style="Conn.TLabel",
                                    foreground="#9e9e9e")
        self.conn_label.pack(side="left")

        self.info_label = ttk.Label(bar, text="", foreground="#555555")
        self.info_label.pack(side="right")

    def _refresh_ports(self):
        ports = []
        if serial is not None:
            for p in serial.tools.list_ports.comports():
                ports.append(p.device)
        ports.append(SIM_PORT)
        self.port_box["values"] = ports
        if not self.port_var.get() or self.port_var.get() not in ports:
            self.port_var.set(ports[0])
        log.debug("ports: %s", ", ".join(ports))

    # ------------------------------------------------------------- notebook
    def _build_notebook(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 4))
        self._build_console_tab()
        self._build_led_tab()
        self._build_i2c_tab()
        self._build_spi_tab()
        self._build_flash_tab()
        self._build_debug_tab()

    # ---- Console ---------------------------------------------------------
    def _build_console_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text="  Console  ")

        opts = ttk.Frame(tab)
        opts.pack(fill="x")
        self.ts_var = tk.BooleanVar(value=True)
        self.autoscroll_var = tk.BooleanVar(value=True)
        self.show_tx_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Timestamps", variable=self.ts_var).pack(side="left")
        ttk.Checkbutton(opts, text="Auto-scroll", variable=self.autoscroll_var).pack(
            side="left", padx=8)
        ttk.Checkbutton(opts, text="Show sent lines", variable=self.show_tx_var).pack(
            side="left")
        for text, cmd in [("Save…", self._save_console), ("Clear", self._clear_console)]:
            ttk.Button(opts, text=text, command=cmd).pack(side="right", padx=2)
        ttk.Separator(opts, orient="vertical").pack(side="right", fill="y", padx=6)
        for text, cmd in [("Loop OFF", "hk loop off"), ("Loop ON", "hk loop on"),
                          ("Info", "hk info"), ("Ping", "hk ping"), ("help", "hk")]:
            ttk.Button(opts, text=text,
                       command=lambda c=cmd: self._console_send(c)).pack(side="right", padx=2)

        self.console = ScrolledText(tab, font=MONO, wrap="char", background="#1e1e1e",
                                    foreground="#d4d4d4", insertbackground="#d4d4d4")
        self.console.pack(fill="both", expand=True, pady=6)
        self.console.configure(state="disabled")
        self.console.tag_configure("ts", foreground="#808080")
        self.console.tag_configure("tx", foreground="#4fc1ff")
        self.console.tag_configure("ok", foreground="#6a9955")
        self.console.tag_configure("err", foreground="#f44747")
        self.console.tag_configure("data", foreground="#ce9178")
        self.console.tag_configure("sys", foreground="#dcdcaa")

        line = ttk.Frame(tab)
        line.pack(fill="x")
        ttk.Label(line, text="Command").pack(side="left")
        self.cmd_var = tk.StringVar()
        ent = ttk.Entry(line, textvariable=self.cmd_var, font=MONO)
        ent.pack(side="left", fill="x", expand=True, padx=6)
        ent.bind("<Return>", lambda e: self._console_send(self.cmd_var.get(), clear=True))
        ent.bind("<Up>", lambda e: self._history(-1))
        ent.bind("<Down>", lambda e: self._history(1))
        ttk.Button(line, text="Send", command=lambda: self._console_send(
            self.cmd_var.get(), clear=True)).pack(side="left")
        ttk.Label(tab, text="Lines go to the Zephyr shell as typed, e.g. "
                  "'hk flash id', 'hk i2c scan', 'kernel uptime'. ↑/↓ = history.",
                  foreground="#666666").pack(anchor="w", pady=(4, 0))

    # ---- LEDs ------------------------------------------------------------
    def _build_led_tab(self):
        tab = ttk.Frame(self.nb, padding=10)
        self.nb.add(tab, text="  LEDs  ")
        box = ttk.LabelFrame(tab, text="Debug LEDs of the SmartFusion2 (schematic sheet 6, "
                             "active low)", padding=10)
        box.pack(fill="x")
        self.led_mode = [("off", 500)] * len(protocol.LEDS)
        self.led_since = [0.0] * len(protocol.LEDS)  # when the mode was first reported
        self.led_period = []
        self.led_canvas = []
        self.led_state_label = []
        for i, (name, ball, gpio) in enumerate(protocol.LEDS):
            cv = tk.Canvas(box, width=30, height=30, highlightthickness=0)
            cv.grid(row=i, column=0, padx=(0, 8), pady=4)
            cv.create_oval(4, 4, 26, 26, fill="#bdbdbd", outline="#616161", tags="led")
            self.led_canvas.append(cv)
            ttk.Label(box, text=f"{name}  (ball {ball}, MSS {gpio}, led{i})",
                      width=30).grid(row=i, column=1, sticky="w")
            for col, (text, mode) in enumerate([("On", "on"), ("Off", "off"),
                                                ("Blink", "blink")]):
                ttk.Button(box, text=text, width=8,
                           command=lambda i=i, m=mode: self._led_set(str(i), m)).grid(
                    row=i, column=2 + col, padx=2)
            var = tk.StringVar(value="500")
            self.led_period.append(var)
            ttk.Label(box, text="period ms").grid(row=i, column=5, padx=(10, 2))
            ttk.Spinbox(box, from_=protocol.LED_PERIOD_MIN_MS, to=protocol.LED_PERIOD_MAX_MS,
                        increment=50, textvariable=var, width=7).grid(row=i, column=6)
            lab = ttk.Label(box, text="off", width=16, font=MONO)
            lab.grid(row=i, column=7, padx=(10, 0), sticky="w")
            self.led_state_label.append(lab)

        allrow = ttk.Frame(tab, padding=(0, 10))
        allrow.pack(fill="x")
        ttk.Label(allrow, text="All LEDs:").pack(side="left")
        for text, mode in [("On", "on"), ("Off", "off"), ("Blink", "blink")]:
            ttk.Button(allrow, text=text, width=8,
                       command=lambda m=mode: self._led_set("all", m)).pack(side="left", padx=2)
        ttk.Button(allrow, text="Read status", command=self._led_status).pack(side="left",
                                                                            padx=(16, 0))
        ttk.Label(tab, text="Blink period = full on+off cycle, 20-10000 ms (firmware: "
                  "src/devices/leds.c). The indicator mirrors the mode reported by the board; "
                  "it does not measure the LED and its phase is not the LED's. Periods "
                  f"below {LED_DRAW_MIN_MS} ms are drawn half-bright.",
                  foreground="#666666").pack(anchor="w")
        self.led_log = ResultLog(tab, height=12)
        self.led_log.pack(fill="both", expand=True, pady=(8, 0))
        self.after(250, self._led_animate)

    def _led_set(self, target: str, mode: str):
        idx = 0 if target == "all" else int(target)
        try:
            period = protocol.parse_int(self.led_period[idx].get())
            if mode == "blink" and not (protocol.LED_PERIOD_MIN_MS <= period
                                        <= protocol.LED_PERIOD_MAX_MS):
                raise ValueError("period 20..10000 ms")
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid period: {exc}")
            return
        cmd = f"hk led set {target} {mode}" + (f" {period}" if mode == "blink" else "")

        def run():
            res = self.link.command(cmd)
            st = self.link.command("hk led status") if res.ok else None
            return res, st

        def done(r):
            res, st = r
            self._report(res, self.led_log)
            if st is not None and st.ok:
                self._led_show(st)
        self._worker(run, done, cmd)

    def _led_status(self):
        self._run_cmd("hk led status", self.led_log, self._led_show)

    def _led_show(self, res: CommandResult):
        modes = protocol.parse_led_status(res.reply)
        now = time.monotonic()
        for i, (mode, period) in enumerate(modes):
            if modes[i] != self.led_mode[i]:
                self.led_since[i] = now
            self.led_state_label[i].configure(
                text=f"{mode} {period} ms" if mode == "blink" else mode)
        self.led_mode = modes
        self._led_paint()

    def _led_paint(self):
        now = time.monotonic()
        for i, (mode, period) in enumerate(self.led_mode):
            if mode == "blink" and period < LED_DRAW_MIN_MS:
                color = "#a5d6a7"  # too fast to draw: half-bright
            else:
                # Every LED with its own period: on in the first half of a cycle
                ms = (now - self.led_since[i]) * 1000.0
                lit = mode == "on" or (mode == "blink" and ms % period < period / 2)
                color = "#43a047" if lit else "#bdbdbd"
            self.led_canvas[i].itemconfigure("led", fill=color)

    def _led_animate(self):
        self._led_paint()
        self.after(LED_TICK_MS, self._led_animate)

    # ---- I2C -------------------------------------------------------------
    def _build_i2c_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text="  I2C  ")
        top = ttk.Frame(tab)
        top.pack(fill="x")

        bus = ttk.LabelFrame(top, text="Bus I2C_0 (J7-9 SDA = P8, J7-10 SCL = R8)",
                             padding=8)
        bus.pack(side="left", fill="y", padx=(0, 6))
        ttk.Label(bus, text="Speed").grid(row=0, column=0, sticky="w")
        self.i2c_speed = tk.StringVar(value="std")
        ttk.Combobox(bus, textvariable=self.i2c_speed, values=["std", "fast"], width=6,
                     state="readonly").grid(row=0, column=1, sticky="w")
        ttk.Button(bus, text="Apply", command=lambda: self._run_cmd(
            f"hk i2c speed {self.i2c_speed.get()}", self.i2c_log)).grid(row=0, column=2, padx=4)
        ttk.Button(bus, text="Scan bus", style="Big.TButton", command=self._i2c_scan).grid(
            row=1, column=0, columnspan=3, sticky="we", pady=(8, 2))
        self.i2c_scan_label = ttk.Label(bus, text="—", font=MONO)
        self.i2c_scan_label.grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Label(bus, text="std: PCLK/960 ≈ 52 kHz\nfast: PCLK/256 ≈ 195 kHz\n"
                  "(i2c_mchp_mss.c, PCLK 50 MHz)", foreground="#666666").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        raw = ttk.LabelFrame(top, text="Raw transfer (for the logic analyzer)", padding=8)
        raw.pack(side="left", fill="both", expand=True, padx=6)
        self.i2c_addr, _ = labeled_entry(raw, "Address (7-bit)", 8, "0x29", 0, 0)
        self.i2c_tx, _ = labeled_entry(raw, "TX bytes (hex)", 40, "88", 1, 0)
        self.i2c_rxn, _ = labeled_entry(raw, "RX length", 8, "4", 2, 0)
        self.i2c_rep, _ = labeled_entry(raw, "Repeat × / period ms", 8, "1", 3, 0)
        self.i2c_period = tk.StringVar(value="100")
        ttk.Entry(raw, textvariable=self.i2c_period, width=8).grid(row=3, column=2, sticky="w")
        btns = ttk.Frame(raw)
        btns.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Write", command=lambda: self._i2c_raw("write")).pack(side="left")
        ttk.Button(btns, text="Read", command=lambda: self._i2c_raw("read")).pack(
            side="left", padx=4)
        ttk.Button(btns, text="Write → Read (restart)",
                   command=lambda: self._i2c_raw("wr")).pack(side="left")

        ltr = ttk.LabelFrame(top, text="LTR-329ALS @0x29 (example 02)", padding=8)
        ltr.pack(side="left", fill="y", padx=(6, 0))
        ttk.Button(ltr, text="Read PART/MANUFAC ID", command=self._ltr_ids).pack(fill="x")
        ttk.Button(ltr, text="Activate ALS (0x80 = 01)", command=self._ltr_activate).pack(
            fill="x", pady=4)
        ttk.Button(ltr, text="Read ALS CH0/CH1", command=self._ltr_read).pack(fill="x")
        self.ltr_label = ttk.Label(ltr, text="CH0 –   CH1 –", font=MONO)
        self.ltr_label.pack(anchor="w", pady=(8, 0))

        self.i2c_log = ResultLog(tab, height=14)
        self.i2c_log.pack(fill="both", expand=True, pady=(8, 0))

    # ---- SPI -------------------------------------------------------------
    def _build_spi_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text="  SPI  ")
        top = ttk.Frame(tab)
        top.pack(fill="x")

        cfg = ttk.LabelFrame(top, text="SPI_0, SS0 — J7: SCK 6 (D13), MOSI 4 (D11), "
                             "MISO 5 (D12), SS 3 (D10), GND 7", padding=8)
        cfg.pack(side="left", fill="both", expand=True)
        ttk.Label(cfg, text="SCK").grid(row=0, column=0, sticky="w")
        self.spi_clock_choices = protocol.spi_clock_choices()
        self.spi_sck = tk.StringVar(value=self._clock_label(2_000_000))
        ttk.Combobox(cfg, textvariable=self.spi_sck, width=14, state="readonly",
                     values=[c[0] for c in self.spi_clock_choices]).grid(
            row=0, column=1, sticky="w")
        ttk.Label(cfg, text="Mode").grid(row=0, column=2, sticky="e", padx=(12, 4))
        self.spi_mode = tk.StringVar(value="0")
        ttk.Combobox(cfg, textvariable=self.spi_mode, values=["0", "1", "2", "3"], width=4,
                     state="readonly").grid(row=0, column=3, sticky="w")
        self.spi_tx, _ = labeled_entry(cfg, "TX bytes (hex)", 52, "AA 55", 1, 0)
        self.spi_rep, _ = labeled_entry(cfg, "Repeat × / period ms", 8, "1", 2, 0)
        self.spi_period = tk.StringVar(value="10")
        ttk.Entry(cfg, textvariable=self.spi_period, width=8).grid(row=2, column=2, sticky="w")
        btns = ttk.Frame(cfg)
        btns.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Transfer", style="Big.TButton", command=self._spi_xfer).pack(
            side="left")
        ttk.Button(btns, text="Burst (repeat in firmware)", command=self._spi_burst).pack(
            side="left", padx=6)
        ttk.Label(cfg, text="SCK values are what spi_mchp_mss.c can generate from PCLK "
                  "50 MHz; below 1.67 MHz it falls back to 25 MHz.",
                  foreground="#666666").grid(row=4, column=0, columnspan=4, sticky="w",
                                             pady=(8, 0))

        self.spi_log = ResultLog(tab, height=18)
        self.spi_log.pack(fill="both", expand=True, pady=(8, 0))

    def _clock_label(self, request_hz: int) -> str:
        sck = protocol.mss_spi_sck(request_hz)
        return f"{sck / 1e6:.3f} MHz"

    def _clock_request(self, label: str) -> int:
        for text, req in self.spi_clock_choices:
            if text == label:
                return req
        return 2_000_000

    # ---- SPI flash -------------------------------------------------------
    def _build_flash_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text="  SPI Flash (U8)  ")

        left = ttk.Frame(tab)
        left.pack(side="left", fill="y")

        ident = ttk.LabelFrame(left, text="SST26VF064B on SPI_1, SS0", padding=8)
        ident.pack(fill="x")
        ttk.Label(ident, text="SCK").grid(row=0, column=0, sticky="w")
        self.flash_sck = tk.StringVar(value=self._clock_label(2_000_000))
        ttk.Combobox(ident, textvariable=self.flash_sck, width=12, state="readonly",
                     values=[c[0] for c in self.spi_clock_choices]).grid(
            row=0, column=1, sticky="w")
        ttk.Button(ident, text="Apply", command=self._flash_freq).grid(row=0, column=2, padx=4)
        row = ttk.Frame(ident)
        row.grid(row=1, column=0, columnspan=3, sticky="we", pady=(8, 0))
        for text, fn in [("Read ID", self._flash_id), ("Status", self._flash_status),
                         ("Unlock", self._flash_unlock), ("Reset", self._flash_reset)]:
            ttk.Button(row, text=text, command=fn).pack(side="left", padx=(0, 4))
        self.flash_id_label = ttk.Label(ident, text="JEDEC ID: –", font=MONO)
        self.flash_id_label.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.flash_sr_label = ttk.Label(ident, text="SR: –   CR: –", font=MONO)
        self.flash_sr_label.grid(row=3, column=0, columnspan=3, sticky="w")
        self.auto_unlock = tk.BooleanVar(value=True)
        ttk.Checkbutton(ident, text="Unlock (ULBPR) before write/erase",
                        variable=self.auto_unlock).grid(row=4, column=0, columnspan=3,
                                                        sticky="w", pady=(6, 0))

        rd = ttk.LabelFrame(left, text="Read", padding=8)
        rd.pack(fill="x", pady=6)
        self.fr_addr, _ = labeled_entry(rd, "Address", 12, "0x000000", 0, 0)
        self.fr_len, _ = labeled_entry(rd, "Length", 12, "256", 1, 0)
        b = ttk.Frame(rd)
        b.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(b, text="Read", command=self._flash_read).pack(side="left")
        ttk.Button(b, text="Save dump…", command=self._flash_save_dump).pack(side="left",
                                                                            padx=4)

        wr = ttk.LabelFrame(left, text="Write (page program)", padding=8)
        wr.pack(fill="x")
        self.fw_addr, _ = labeled_entry(wr, "Address", 12, "0x000000", 0, 0)
        self.fw_mode = tk.StringVar(value="text")
        mode = ttk.Frame(wr)
        mode.grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(mode, text="Text", value="text", variable=self.fw_mode).pack(
            side="left")
        ttk.Radiobutton(mode, text="Hex", value="hex", variable=self.fw_mode).pack(
            side="left", padx=6)
        self.fw_data = tk.Text(wr, height=4, width=36, font=MONO)
        self.fw_data.grid(row=2, column=0, columnspan=2, sticky="we", pady=4)
        self.fw_data.insert("1.0", "Hello FPGA Kit + Zephyr")
        self.fw_erase = tk.BooleanVar(value=True)
        self.fw_verify = tk.BooleanVar(value=True)
        ttk.Checkbutton(wr, text="Erase 4 KB sector(s) first", variable=self.fw_erase).grid(
            row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(wr, text="Verify (read back)", variable=self.fw_verify).grid(
            row=4, column=0, columnspan=2, sticky="w")
        b = ttk.Frame(wr)
        b.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(b, text="Write", command=self._flash_write).pack(side="left")
        ttk.Button(b, text="Write file…", command=self._flash_write_file).pack(side="left",
                                                                              padx=4)

        er = ttk.LabelFrame(left, text="Erase / test", padding=8)
        er.pack(fill="x", pady=6)
        self.fe_addr, _ = labeled_entry(er, "Address", 12, "0x000000", 0, 0)
        b = ttk.Frame(er)
        b.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(b, text="Sector 4 KB", command=lambda: self._flash_erase("sector")).pack(
            side="left")
        ttk.Button(b, text="Block", command=lambda: self._flash_erase("block")).pack(
            side="left", padx=4)
        ttk.Button(b, text="Chip…", style="Danger.TButton",
                   command=lambda: self._flash_erase("chip")).pack(side="left")
        ttk.Button(er, text="Self test at address (erase, write 256 B, verify)",
                   command=self._flash_selftest).grid(row=2, column=0, columnspan=2,
                                                       sticky="we", pady=(6, 0))

        right = ttk.Frame(tab)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.flash_progress = ttk.Progressbar(right, mode="determinate")
        self.flash_progress.pack(fill="x")
        self.flash_view = ScrolledText(right, font=MONO, wrap="none", height=20)
        self.flash_view.pack(fill="both", expand=True, pady=(6, 6))
        self.flash_log = ResultLog(right, height=8)
        self.flash_log.pack(fill="x")

    # ---- Debug -----------------------------------------------------------
    def _build_debug_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text="  Debug log  ")
        bar = ttk.Frame(tab)
        bar.pack(fill="x")
        ttk.Label(bar, text="Show level").pack(side="left")
        self.dbg_level = tk.StringVar(value="DEBUG")
        ttk.Combobox(bar, textvariable=self.dbg_level, width=9, state="readonly",
                     values=["DEBUG", "INFO", "WARNING", "ERROR"]).pack(side="left", padx=4)
        ttk.Checkbutton(bar, text="Log raw serial bytes (hex)",
                        variable=self.raw_debug).pack(side="left", padx=12)
        for text, fn in [("Save debug log as…", self._save_debug),
                         ("Open log folder", self._open_log_dir),
                         ("Clear view", lambda: self.debug_view.clear())]:
            ttk.Button(bar, text=text, command=fn).pack(side="right", padx=2)
        ttk.Label(tab, text=f"Log file (always DEBUG): {self.log_path}",
                  foreground="#666666").pack(anchor="w", pady=4)
        self.debug_view = ResultLog(tab, height=30)
        self.debug_view.tag_configure("DEBUG", foreground="#666666")
        self.debug_view.tag_configure("INFO", foreground="#1f4e9a")
        self.debug_view.tag_configure("WARNING", foreground="#b26a00")
        self.debug_view.tag_configure("ERROR", foreground="#c62828")
        self.debug_view.pack(fill="both", expand=True)

    # ------------------------------------------------------------- status bar
    def _build_statusbar(self):
        bar = ttk.Frame(self, relief="sunken")
        bar.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        self.busy_bar = ttk.Progressbar(bar, mode="indeterminate", length=120)
        self.busy_bar.pack(side="right", padx=6, pady=2)

    # =====================================================================
    # Connection
    # =====================================================================
    def _toggle_connect(self):
        self.lost_port = ""  # the user decides now: no auto-reconnect
        if self.link.is_open:
            self._disconnect()
        else:
            self._connect()

    def _connect(self, auto: bool = False) -> bool:
        name = self.port_var.get().strip()
        try:
            baud = int(self.baud_var.get())
        except ValueError:
            messagebox.showerror(APP_TITLE, "Invalid baud rate")
            return False
        try:
            if name == SIM_PORT:
                port = SimBoard()
            else:
                if serial is None:
                    messagebox.showerror(APP_TITLE, "pyserial is not installed "
                                         "(pip install -r requirements.txt)")
                    return False
                port = serial.Serial(name, baud, timeout=0.05, write_timeout=2)
        except Exception as exc:
            log.error("cannot open %s: %s", name, exc)
            if not auto:  # auto-reconnect: the port may not be ready yet, try again
                messagebox.showerror(APP_TITLE, f"Cannot open {name}:\n{exc}")
            return False
        log.info("connected to %s at %d bit/s, PIC32 bridge %s", name, baud,
                 "on" if self.bridge_var.get() else "off")
        self.link.open_port(port, pic32_bridge=self.bridge_var.get())
        self._set_connected(True, name)
        self._sys_line(f"connected to {name} @ {baud}"
                       + (" (PIC32 bridge: '&' sent)" if self.bridge_var.get() else ""))

        def after_connect():
            if self.stop_loop_var.get():
                self.link.command("hk loop off", timeout=3)
            info = self.link.command("hk info", timeout=3)
            leds = self.link.command("hk led status", timeout=3)
            if leds.ok:
                self._ui(lambda: self._led_show(leds))
            return info

        self._worker(after_connect, self._after_info)
        return True

    def _after_info(self, res: CommandResult):
        if res.ok:
            kv = res.reply.kv
            self.info_label.configure(
                text=f"{kv.get('board', '?')}  i2c0={kv.get('i2c0')} spi0={kv.get('spi0')} "
                     f"spi1={kv.get('spi1')} loop={kv.get('loop')}")
            self.status_var.set("Board answered 'hk info'")
        else:
            self.info_label.configure(text="no answer to 'hk info'")
            self.status_var.set(f"No reply from firmware: {res.error or res.summary()}. "
                                "Check port, baud, PIC32 bridge, firmware.")

    def _disconnect(self):
        self.link.close()
        self._set_connected(False)
        self._sys_line("disconnected")
        log.info("disconnected")

    def _set_connected(self, on: bool, name: str = ""):
        if on:
            self.port_name = name
        self.conn_btn.configure(text="Disconnect" if on else "Connect")
        self.conn_label.configure(text=f"●  {name}" if on else "●  disconnected",
                                  foreground="#2e7d32" if on else "#9e9e9e")
        if not on:
            self.info_label.configure(text="")

    def _link_lost(self, reason: str):
        """The port failed (USB cable unplugged, board without power)."""
        name = self.port_name
        self._set_connected(False)
        self.conn_label.configure(text=f"●  {name}: connection lost", foreground="#c62828")
        self._sys_line(f"connection to {name} lost ({reason})")
        if self.reconnect_var.get() and name != SIM_PORT:
            self.lost_port = name
            self.status_var.set(f"Connection to {name} lost – USB cable unplugged? "
                                f"Reconnecting when {name} is back …")
            self.after(1000, self._watch_lost_port)
        else:
            self.status_var.set(f"Connection to {name} lost – USB cable unplugged?")

    def _watch_lost_port(self):
        """Reconnect once the lost port is there again (cable plugged back in)."""
        name = self.lost_port
        if not name or self.link.is_open or not self.reconnect_var.get():
            return
        present = serial is not None and any(
            p.device == name for p in serial.tools.list_ports.comports())
        if present and not self.busy:
            log.info("%s is back, reconnecting", name)
            self.port_var.set(name)
            if self._connect(auto=True):
                self.lost_port = ""
                self._sys_line(f"{name} is back: reconnected")
                return
        self.after(1000, self._watch_lost_port)

    def _board_answers(self, answers: bool):
        """Show whether the firmware still answers (checked after a command timeout)."""
        if not self.link.is_open:
            return
        if answers:
            self.conn_label.configure(text=f"●  {self.port_name}", foreground="#2e7d32")
            return
        self.conn_label.configure(text=f"●  {self.port_name}: board does not answer",
                                  foreground="#ef6c00")
        msg = ("Board does not answer, not even 'hk ping': firmware busy or hung. "
               "Press the board's reset button or replug USB, then Disconnect / Connect.")
        self.status_var.set(msg)
        self._sys_line(msg)
        log.warning(msg)

    def _on_close(self):
        try:
            self.link.close()
        finally:
            log.info("GUI closed")
            self.destroy()

    # =====================================================================
    # Threads -> UI
    # =====================================================================
    def _on_line(self, text: str, direction: str):
        self.ui_queue.put(("line", direction, text, time.time()))

    def _on_raw(self, data: bytes, direction: str):
        if self._raw_debug_on:
            logging.getLogger("hk.raw").debug("%s %s", direction.upper(), data.hex(" "))

    def _poll_queue(self):
        try:
            for _ in range(500):
                item = self.ui_queue.get_nowait()
                if item[0] == "line":
                    self._console_line(*item[1:])
                elif item[0] == "log":
                    self._debug_line(item[1], item[2])
                elif item[0] == "call":
                    item[1]()
        except queue.Empty:
            pass
        self.after(40, self._poll_queue)

    def _worker(self, fn: Callable, done: Optional[Callable] = None, label: str = ""):
        """Run fn() in a thread (one at a time), then done(result) in the UI."""
        if self.busy:
            self.status_var.set("Busy – wait for the current operation")
            return
        if not self.link.is_open:
            self.status_var.set("Not connected")
            return
        self.busy = True
        self.busy_bar.start(12)
        if label:
            self.status_var.set(label + " …")

        def run():
            timeouts = self.link.timeouts
            try:
                result = fn()
                err = None
            except Exception as exc:  # report, do not kill the GUI
                log.exception("operation failed")
                result, err = None, exc
            # A command got no reply: does the firmware still answer?
            answers = None
            if self.link.timeouts != timeouts and self.link.is_open:
                answers = self.link.command("hk ping", timeout=1.5).ok
            elif self.link.is_open:
                answers = True

            def finish():
                self.busy = False
                self.busy_bar.stop()
                if answers is not None:
                    self._board_answers(answers)
                if err is not None:
                    self.status_var.set(f"Error: {err}")
                    messagebox.showerror(APP_TITLE, str(err))
                elif done is not None:
                    done(result)

            self.ui_queue.put(("call", finish))

        threading.Thread(target=run, daemon=True).start()

    def _ui(self, fn: Callable):
        """Schedule fn() on the UI thread (from a worker)."""
        self.ui_queue.put(("call", fn))

    def _run_cmd(self, cmd: str, out: ResultLog, on_ok: Callable = None, timeout=5.0):
        def done(res: CommandResult):
            self._report(res, out)
            if res.ok and on_ok is not None:
                on_ok(res)
        self._worker(lambda: self.link.command(cmd, timeout), done, cmd)

    def _report(self, res: CommandResult, out: ResultLog):
        out.add(f"{res.summary()}   ({res.duration_s * 1000:.0f} ms)",
                "ok" if res.ok else "err")
        self.status_var.set(res.summary())

    # =====================================================================
    # Console
    # =====================================================================
    def _console_line(self, direction: str, text: str, stamp: float):
        if direction == "tx" and not self.show_tx_var.get():
            return
        c = self.console
        c.configure(state="normal")
        if self.ts_var.get():
            c.insert("end", dt.datetime.fromtimestamp(stamp).strftime("%H:%M:%S.%f")[:-3]
                     + " ", "ts")
        if direction == "tx":
            tag = "tx"
            text = "» " + text
        elif direction == "sys":
            tag = "sys"
        elif "@ok" in text:
            tag = "ok"
        elif "@err" in text:
            tag = "err"
        elif "@data" in text:
            tag = "data"
        else:
            tag = ""
        c.insert("end", text + "\n", tag)
        # keep the widget responsive: at most 20000 lines
        if int(c.index("end-1c").split(".")[0]) > 20000:
            c.delete("1.0", "2000.0")
        if self.autoscroll_var.get():
            c.see("end")
        c.configure(state="disabled")
        if direction == "rx":
            logging.getLogger("hk.console").debug("RX %s", text)
        elif direction == "tx":
            logging.getLogger("hk.console").debug("TX %s", text)

    def _sys_line(self, text: str):
        self._console_line("sys", f"[gui] {text}", time.time())

    def _console_send(self, text: str, clear: bool = False):
        text = text.strip()
        if not text:
            return
        if not self.link.is_open:
            self.status_var.set("Not connected")
            return
        if not self.history or self.history[-1] != text:
            self.history.append(text)
        self.hist_idx = len(self.history)
        if clear:
            self.cmd_var.set("")
        if text.startswith("hk"):
            self._worker(lambda: self.link.command(text, timeout=10),
                         lambda r: self.status_var.set(r.summary()), text)
        else:
            try:
                self.link.send_line(text)
            except Exception as exc:
                self.status_var.set(str(exc))

    def _history(self, step: int):
        if not self.history:
            return "break"
        self.hist_idx = max(0, min(len(self.history), self.hist_idx + step))
        self.cmd_var.set(self.history[self.hist_idx] if self.hist_idx < len(self.history)
                         else "")
        return "break"

    def _clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _save_console(self):
        path = filedialog.asksaveasfilename(
            title="Save console", defaultextension=".txt",
            initialfile=f"console_{dt.datetime.now():%Y%m%d_%H%M%S}.txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if path:
            Path(path).write_text(self.console.get("1.0", "end-1c"), encoding="utf-8")
            log.info("console saved to %s", path)
            self.status_var.set(f"Console saved: {path}")

    # =====================================================================
    # I2C
    # =====================================================================
    def _i2c_scan(self):
        # Without pull-ups a failed probe takes ~190 ms and a scan (112 probes
        # back to back) hangs firmware built before the slow-probe check in
        # src/shell/hk_cmd_i2c.c. One probe first, scan only if it was fast.
        def run():
            probe = self.link.command("hk i2c read 0x08 1")
            if probe.reply is None:
                return probe, probe  # no answer: report it, no scan
            if not probe.ok and probe.duration_s > I2C_SLOW_PROBE_S:
                return probe, None
            return probe, self.link.command("hk i2c scan", timeout=15)

        def done(r):
            probe, res = r
            if res is None:
                text = (f"scan not started: probe of 0x08 took {probe.duration_s * 1000:.0f} ms "
                        "(normal: a few ms) – no pull-ups on SDA/SCL (J7-9 / J7-10)?")
                self.i2c_log.add(text, "err")
                self.status_var.set(text)
                self.i2c_scan_label.configure(text="no pull-ups?")
                return
            self._report(res, self.i2c_log)
            if res.ok:
                found = res.reply.words[2:]
                self.i2c_scan_label.configure(
                    text=" ".join(f"0x{a}" for a in found) if found else "no device")
        self._worker(run, done, "hk i2c scan")

    def _i2c_raw(self, kind: str):
        try:
            addr = protocol.parse_int(self.i2c_addr.get())
            if not 0 <= addr <= 0x7F:
                raise ValueError("address must be 0x00..0x7F")
            reps = max(1, protocol.parse_int(self.i2c_rep.get()))
            period = max(0, protocol.parse_int(self.i2c_period.get())) / 1000.0
            if kind == "write":
                data = protocol.parse_hex_bytes(self.i2c_tx.get())
                cmd = f"hk i2c write 0x{addr:02x} {data.hex()}"
            elif kind == "read":
                n = protocol.parse_int(self.i2c_rxn.get())
                cmd = f"hk i2c read 0x{addr:02x} {n}"
            else:
                data = protocol.parse_hex_bytes(self.i2c_tx.get())
                n = protocol.parse_int(self.i2c_rxn.get())
                cmd = f"hk i2c wr 0x{addr:02x} {n} {data.hex()}"
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid input: {exc}")
            return

        def run():
            last = None
            for i in range(reps):
                last = self.link.command(cmd)
                res = last
                self._ui(lambda r=res: self._report(r, self.i2c_log))
                if not last.ok:
                    break
                if i + 1 < reps:
                    time.sleep(period)
            return last

        self._worker(run, None, cmd)

    def _ltr_ids(self):
        def run():
            a = self.link.command(f"hk i2c wr 0x{protocol.LTR329_ADDR:02x} 1 "
                                  f"{protocol.LTR329_PART_ID:02x}")
            b = self.link.command(f"hk i2c wr 0x{protocol.LTR329_ADDR:02x} 1 "
                                  f"{protocol.LTR329_MANUFAC_ID:02x}")
            return a, b

        def done(r):
            for res in r:
                self._report(res, self.i2c_log)
            if all(x.ok for x in r):
                self.ltr_label.configure(text=f"PART_ID 0x{r[0].reply.kv['rx']}  "
                                              f"MANUFAC_ID 0x{r[1].reply.kv['rx']}")
        self._worker(run, done, "LTR-329 IDs")

    def _ltr_activate(self):
        self._run_cmd(f"hk i2c write 0x{protocol.LTR329_ADDR:02x} "
                      f"{protocol.LTR329_ALS_CONTR:02x}01", self.i2c_log)

    def _ltr_read(self):
        def run():
            st = self.link.command(f"hk i2c wr 0x{protocol.LTR329_ADDR:02x} 1 "
                                   f"{protocol.LTR329_ALS_PS_STATUS:02x}")
            data = self.link.command(f"hk i2c wr 0x{protocol.LTR329_ADDR:02x} 4 "
                                     f"{protocol.LTR329_ALS_DATA_CH1_0:02x}")
            return st, data

        def done(r):
            st, data = r
            self._report(st, self.i2c_log)
            self._report(data, self.i2c_log)
            if st.ok and data.ok:
                raw = bytes.fromhex(data.reply.kv["rx"])
                ch1 = raw[0] | raw[1] << 8
                ch0 = raw[2] | raw[3] << 8
                status = int(st.reply.kv["rx"], 16)
                ready = "ready" if status & 0x04 else "not ready"
                self.ltr_label.configure(text=f"CH0 {ch0}   CH1 {ch1}   "
                                              f"status 0x{status:02X} ({ready})")
        self._worker(run, done, "LTR-329 ALS")

    # =====================================================================
    # SPI
    # =====================================================================
    def _spi_params(self):
        data = protocol.parse_hex_bytes(self.spi_tx.get())
        if len(data) > 256:
            raise ValueError("at most 256 bytes")
        return self._clock_request(self.spi_sck.get()), int(self.spi_mode.get()), data

    def _spi_xfer(self):
        try:
            hz, mode, data = self._spi_params()
            reps = max(1, protocol.parse_int(self.spi_rep.get()))
            period = max(0, protocol.parse_int(self.spi_period.get())) / 1000.0
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid input: {exc}")
            return
        cmd = f"hk spi xfer {hz} {mode} {data.hex()}"

        def run():
            for i in range(reps):
                res = self.link.command(cmd)
                self._ui(lambda r=res: self._spi_result(r, data))
                if not res.ok:
                    break
                if i + 1 < reps:
                    time.sleep(period)
        self._worker(run, None, "SPI transfer")

    def _spi_result(self, res: CommandResult, tx: bytes):
        if res.ok:
            rx = bytes.fromhex(res.reply.kv.get("rx", ""))
            self.spi_log.add(f"TX {protocol.to_hex(tx)}  |  RX {protocol.to_hex(rx)}   "
                             f"(SCK {self.spi_sck.get()}, mode {self.spi_mode.get()}, "
                             f"{res.duration_s * 1000:.0f} ms)", "ok")
            self.status_var.set("SPI transfer OK")
        else:
            self._report(res, self.spi_log)

    def _spi_burst(self):
        try:
            hz, mode, data = self._spi_params()
            reps = protocol.parse_int(self.spi_rep.get())
            period = protocol.parse_int(self.spi_period.get())
            if not 1 <= reps <= 1000 or not 0 <= period <= 10000:
                raise ValueError("repeat 1..1000, period 0..10000 ms")
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid input: {exc}")
            return
        timeout = 5 + reps * (period / 1000.0 + 0.01)
        self._run_cmd(f"hk spi repeat {hz} {mode} {reps} {period} {data.hex()}",
                      self.spi_log, timeout=timeout)

    # =====================================================================
    # SPI flash
    # =====================================================================
    def _flash_freq(self):
        hz = self._clock_request(self.flash_sck.get())
        self._run_cmd(f"hk flash freq {hz}", self.flash_log)

    def _flash_id(self):
        def ok(res):
            jedec = res.reply.kv.get("jedec", "")
            match = jedec.lower() == protocol.SST26_JEDEC_ID
            pretty = " ".join(jedec[i:i + 2].upper() for i in range(0, len(jedec), 2))
            self.flash_id_label.configure(
                text=f"JEDEC ID: {pretty}  "
                     + ("✔ SST26VF064B" if match else "✘ expected BF 26 43"),
                foreground="#1b7f1b" if match else "#c62828")
        self._run_cmd("hk flash id", self.flash_log, ok)

    def _flash_status(self):
        def ok(res):
            sr = int(res.reply.kv["sr"], 16)
            cr = int(res.reply.kv["cr"], 16)
            self.flash_sr_label.configure(
                text=f"SR 0x{sr:02X} ({protocol.decode_status(sr)})   "
                     f"CR 0x{cr:02X} ({protocol.decode_config(cr)})")
        self._run_cmd("hk flash status", self.flash_log, ok)

    def _flash_unlock(self):
        self._run_cmd("hk flash unlock", self.flash_log)

    def _flash_reset(self):
        self._run_cmd("hk flash reset", self.flash_log)

    def _check(self, res: CommandResult):
        """Report a step from a worker; raise to stop the sequence on error."""
        self._ui(lambda: self._report(res, self.flash_log))
        if not res.ok:
            raise RuntimeError(res.summary())
        return res

    def _progress(self, value: float, maximum: float):
        def set_():
            self.flash_progress.configure(maximum=max(maximum, 1), value=value)
        self._ui(set_)

    def _read_range(self, addr: int, length: int) -> bytes:
        out = bytearray()
        pos = addr
        while len(out) < length:
            n = min(protocol.FLASH_READ_CHUNK, length - len(out))
            res = self.link.command(f"hk flash read 0x{pos:06x} {n}", timeout=10)
            if not res.ok:
                self._ui(lambda r=res: self._report(r, self.flash_log))
                raise RuntimeError(res.summary())
            chunk = b"".join(bytes.fromhex(d.words[1]) for d in res.data)
            if len(chunk) != n:
                raise RuntimeError(f"read 0x{pos:06x}: got {len(chunk)} of {n} bytes")
            out += chunk
            pos += n
            self._progress(len(out), length)
        return bytes(out)

    def _write_range(self, addr: int, data: bytes, erase: bool, verify: bool) -> str:
        t0 = time.monotonic()
        if self.auto_unlock.get():
            self._check(self.link.command("hk flash unlock"))
        if erase:
            first = addr - addr % protocol.SST26_SECTOR
            last = (addr + len(data) - 1) - (addr + len(data) - 1) % protocol.SST26_SECTOR
            for sec in range(first, last + 1, protocol.SST26_SECTOR):
                self._check(self.link.command(f"hk flash erase sector 0x{sec:06x}",
                                              timeout=5))
        done = 0
        while done < len(data):
            chunk = data[done:done + protocol.WRITE_CHUNK]
            res = self.link.command(f"hk flash write 0x{addr + done:06x} {chunk.hex()}")
            if not res.ok:
                self._check(res)
            done += len(chunk)
            self._progress(done, len(data))
        msg = f"wrote {len(data)} B at 0x{addr:06X}"
        if verify:
            back = self._read_range(addr, len(data))
            if back != data:
                bad = next(i for i in range(len(data)) if back[i] != data[i])
                raise RuntimeError(
                    f"verify FAILED at 0x{addr + bad:06X}: wrote {data[bad]:02X}, read "
                    f"{back[bad]:02X} (protected? erased? run Unlock / Status)")
            msg += ", verify OK"
        return msg + f" in {time.monotonic() - t0:.2f} s"

    def _flash_read(self):
        try:
            addr = protocol.parse_int(self.fr_addr.get())
            length = protocol.parse_int(self.fr_len.get())
            if length < 1 or length > 65536 or addr < 0 or \
                    addr + length > protocol.SST26_SIZE:
                raise ValueError("length 1..65536 inside 0x000000..0x7FFFFF")
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid input: {exc}")
            return

        def done(data: bytes):
            self.flash_dump, self.flash_dump_addr = data, addr
            self._show_dump(data, addr)
            self.flash_log.add(f"read {len(data)} B at 0x{addr:06X}", "ok")
            self.status_var.set(f"Flash read {len(data)} bytes")
        self._worker(lambda: self._read_range(addr, length), done, "Flash read")

    def _show_dump(self, data: bytes, addr: int):
        self.flash_view.delete("1.0", "end")
        self.flash_view.insert("1.0", protocol.hexdump(data, addr))

    def _flash_save_dump(self):
        if not self.flash_dump:
            messagebox.showinfo(APP_TITLE, "Read something first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save flash dump", defaultextension=".bin",
            initialfile=f"u8_{self.flash_dump_addr:06X}_{len(self.flash_dump)}.bin",
            filetypes=[("Binary", "*.bin"), ("Hex dump text", "*.txt")])
        if not path:
            return
        if path.lower().endswith(".txt"):
            Path(path).write_text(protocol.hexdump(self.flash_dump, self.flash_dump_addr),
                                  encoding="utf-8")
        else:
            Path(path).write_bytes(self.flash_dump)
        log.info("flash dump saved to %s", path)
        self.status_var.set(f"Saved {path}")

    def _flash_write_data(self) -> bytes:
        text = self.fw_data.get("1.0", "end-1c")
        if self.fw_mode.get() == "hex":
            return protocol.parse_hex_bytes(text)
        data = text.encode("utf-8")
        if not data:
            raise ValueError("no data")
        return data

    def _start_write(self, addr: int, data: bytes):
        if addr < 0 or addr + len(data) > protocol.SST26_SIZE:
            messagebox.showerror(APP_TITLE, "Data does not fit into the 8 MB flash")
            return
        erase, verify = self.fw_erase.get(), self.fw_verify.get()

        def done(msg):
            self.flash_log.add(msg, "ok")
            self.status_var.set(msg)
        self._worker(lambda: self._write_range(addr, data, erase, verify), done,
                     f"Flash write {len(data)} B")

    def _flash_write(self):
        try:
            addr = protocol.parse_int(self.fw_addr.get())
            data = self._flash_write_data()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid input: {exc}")
            return
        self._start_write(addr, data)

    def _flash_write_file(self):
        path = filedialog.askopenfilename(title="File to write into U8")
        if not path:
            return
        try:
            addr = protocol.parse_int(self.fw_addr.get())
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid address: {exc}")
            return
        data = Path(path).read_bytes()
        if not messagebox.askyesno(APP_TITLE, f"Write {len(data)} bytes from\n{path}\n"
                                   f"at 0x{addr:06X}?"):
            return
        self._start_write(addr, data)

    def _flash_erase(self, kind: str):
        try:
            addr = protocol.parse_int(self.fe_addr.get()) if kind != "chip" else 0
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid address: {exc}")
            return
        if kind == "chip" and not messagebox.askyesno(
                APP_TITLE, "Erase the WHOLE 8 MB SPI flash U8?", icon="warning"):
            return
        cmd = f"hk flash erase {kind}" + ("" if kind == "chip" else f" 0x{addr:06x}")

        def run():
            if self.auto_unlock.get():
                self._check(self.link.command("hk flash unlock"))
            return self._check(self.link.command(cmd, timeout=10))
        self._worker(run, lambda r: self.status_var.set(r.summary()), cmd)

    def _flash_selftest(self):
        try:
            addr = protocol.parse_int(self.fe_addr.get())
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid address: {exc}")
            return
        addr -= addr % protocol.SST26_PAGE
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S").encode()
        pattern = (b"HK-SELFTEST " + stamp + b" ")
        pattern = (pattern + bytes(range(256)))[:protocol.SST26_PAGE]
        if not messagebox.askyesno(APP_TITLE, f"Self test erases the 4 KB sector at "
                                   f"0x{addr - addr % protocol.SST26_SECTOR:06X}. Continue?"):
            return

        def run():
            res = self._check(self.link.command("hk flash id"))
            if res.reply.kv.get("jedec") != protocol.SST26_JEDEC_ID:
                raise RuntimeError(f"unexpected JEDEC ID {res.reply.kv.get('jedec')}")
            msg = self._write_range(addr, pattern, erase=True, verify=True)
            return addr, msg

        def done(r):
            a, msg = r
            self.flash_log.add(f"SELF TEST PASSED: {msg}", "ok")
            self.status_var.set(f"Self test passed: {msg}")
            self.flash_dump, self.flash_dump_addr = pattern, a
            self._show_dump(pattern, a)
            messagebox.showinfo(APP_TITLE, f"Self test passed.\n{msg}")
        self._worker(run, done, "Flash self test")

    # =====================================================================
    # Debug log
    # =====================================================================
    def _debug_line(self, level: int, text: str):
        if level < logging.getLevelName(self.dbg_level.get()):
            return
        self.debug_view.add(text, logging.getLevelName(level))

    def _save_debug(self):
        path = filedialog.asksaveasfilename(
            title="Save debug log", defaultextension=".log",
            initialfile=f"hk_debug_{dt.datetime.now():%Y%m%d_%H%M%S}.log",
            filetypes=[("Log", "*.log"), ("Text", "*.txt")])
        if path:
            for h in logging.getLogger().handlers:
                h.flush()
            Path(path).write_bytes(self.log_path.read_bytes())
            log.info("debug log copied to %s", path)
            self.status_var.set(f"Debug log saved: {path}")

    def _open_log_dir(self):
        try:
            if sys.platform.startswith("win"):
                os.startfile(LOG_DIR)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(LOG_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(LOG_DIR)])
        except Exception as exc:
            messagebox.showinfo(APP_TITLE, f"Log folder: {LOG_DIR}\n({exc})")


def main(argv=None):
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--port", help="serial port, or SIM for the simulated board")
    parser.add_argument("--baud", type=int, default=protocol.PC_BAUD_DEFAULT,
                        help="PC port bit rate (kit USB port: 460800)")
    parser.add_argument("--no-pic32-bridge", action="store_true",
                        help="do not send '&' (USB-UART cable straight to MMUART_0)")
    args = parser.parse_args(argv)
    app = App(args)
    app.mainloop()


if __name__ == "__main__":
    main()
