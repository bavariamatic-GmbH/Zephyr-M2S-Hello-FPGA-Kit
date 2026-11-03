"""Reply parsing and helpers for the firmware's "hk" shell commands.

Firmware side: src/shell/. A command produces zero or more ``@data``
lines and exactly one final ``@ok ...`` or ``@err ...`` line. Everything else
on the console (boot text, shell prompt and echo, demo loop) is not a reply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# --- Kit USB bridge (see .agents/skills/hello-fpga-kit-uart-spi/SKILL.md) ---
#
# PC <-> MCP2221A <-> PIC32 runs at 460800 bit/s; the PIC32 talks to MMUART_0
# at 230400 bit/s and forwards nothing until it has received "&".
PC_BAUD_DEFAULT = 460800
PIC32_UART_MODE_COMMAND = b"&"
PIC32_SETTLE_S = 0.1
# The firmware stays silent after reset until it receives a first byte (the
# PIC32 must not get data from the SmartFusion2 before the PC is connected,
# firmware src/app/host_wait.c). The GUI sends this byte after connecting and
# waits until the shell has started.
FIRMWARE_WAKE = b"\n"
FIRMWARE_WAKE_S = 0.3
# The PIC32 holds back a 0x25 ("%") that ends a packet until the next byte.
PIC32_HELD_BYTE = 0x25
PIC32_PUSH_BYTE = b"\n"
# The PIC32 receives from the PC at 460800 bit/s but sends to the SmartFusion2
# at 230400 bit/s, so a long burst piles up in the PIC32. Observed
# 2026-11-02: a 71-character "hk flash write" line was never echoed and the
# link stayed dead afterwards (no echo of any later command); lines up to 30
# characters always worked. The GUI therefore sends in small chunks with a
# pause that lets the PIC32 pass each chunk on at 230400 bit/s
# (16 bytes = 0.7 ms) before the next one arrives.
PIC32_TX_CHUNK = 16
PIC32_TX_GAP_S = 0.003

# --- MSS clocks (docs/libero-hello-fpga-vf256.md) ---
APB_HZ = 50_000_000

# --- SST26VF064B (U8) ---
SST26_JEDEC_ID = "bf2643"
SST26_SIZE = 8 * 1024 * 1024
SST26_PAGE = 256
SST26_SECTOR = 4096
FLASH_READ_CHUNK = 1024  # firmware limit per "hk flash read"
WRITE_CHUNK = 128  # bytes per "hk flash write" / I2C / SPI command line

# --- LTR-329ALS (example 02_solution_i2c_driver) ---
LTR329_ADDR = 0x29
LTR329_ALS_CONTR = 0x80
LTR329_MEAS_RATE = 0x85
LTR329_PART_ID = 0x86
LTR329_MANUFAC_ID = 0x87
LTR329_ALS_DATA_CH1_0 = 0x88
LTR329_ALS_PS_STATUS = 0x8C

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_REPLY = re.compile(r"(@(?:ok|err|data))(?:\s+(.*))?$")
_INT = re.compile(r"^-?\d+$")


def clean_line(raw: str) -> str:
    """Remove VT100 sequences and control characters from a console line."""
    text = _ANSI.sub("", raw)
    return "".join(ch for ch in text if ch == "\t" or ch >= " ").rstrip()


@dataclass
class Reply:
    """One ``@ok`` / ``@err`` / ``@data`` line."""

    kind: str  # "ok", "err" or "data"
    text: str  # everything after the tag
    words: List[str] = field(default_factory=list)  # tokens without "="
    kv: Dict[str, str] = field(default_factory=dict)  # key=value tokens
    errno: Optional[int] = None  # @err only
    message: str = ""  # @err only

    @property
    def ok(self) -> bool:
        return self.kind == "ok"


def parse_reply(line: str) -> Optional[Reply]:
    """Return the reply contained in a console line, or None."""
    m = _REPLY.search(clean_line(line))
    if not m:
        return None
    kind = m.group(1)[1:]
    text = (m.group(2) or "").strip()
    tokens = text.split()
    reply = Reply(kind=kind, text=text)
    if kind == "err":
        for i, tok in enumerate(tokens):
            if _INT.match(tok):
                reply.errno = int(tok)
                reply.words = tokens[:i]
                reply.message = " ".join(tokens[i + 1:])
                break
        else:
            reply.words = tokens
        return reply
    for tok in tokens:
        if "=" in tok:
            key, _, val = tok.partition("=")
            reply.kv[key] = val
        else:
            reply.words.append(tok)
    return reply


# --- hex helpers ---

def parse_hex_bytes(text: str) -> bytes:
    """Parse "aa 55", "0xAA,0x55", "aa55" into bytes. Raises ValueError."""
    cleaned = re.sub(r"0x", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s,;:]", "", cleaned)
    if not cleaned:
        raise ValueError("no data")
    if len(cleaned) % 2:
        raise ValueError("odd number of hex digits")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError("not a hex string") from exc


def parse_int(text: str) -> int:
    """Parse a decimal or 0x-prefixed number. Raises ValueError."""
    return int(text.strip(), 0)


def to_hex(data: bytes, sep: str = " ") -> str:
    return sep.join(f"{b:02X}" for b in data)


def hexdump(data: bytes, base: int = 0, width: int = 16) -> str:
    lines = []
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        hexpart = " ".join(f"{b:02X}" for b in chunk).ljust(width * 3 - 1)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base + off:08X}  {hexpart}  |{text}|")
    return "\n".join(lines)


# --- MSS SPI clock (drivers/spi/spi_mchp_mss.c, Zephyr 4.5) ---
#
# The driver picks the first CLK_GEN = 1..15 with PCLK / (2 * CLK_GEN) <= request,
# else 0, and runs the controller with CLKMODE = 1, where (driver comment)
# SPICLK = PCLK / (2 * (CLK_GEN + 1)).

def mss_spi_clk_gen(request_hz: int, pclk: int = APB_HZ) -> int:
    for idx in range(1, 16):
        if pclk / (2 * idx) <= request_hz:
            return idx
    return 0


def mss_spi_sck(request_hz: int, pclk: int = APB_HZ) -> float:
    return pclk / (2 * (mss_spi_clk_gen(request_hz, pclk) + 1))


def spi_clock_choices(pclk: int = APB_HZ) -> List[tuple]:
    """(label, request_hz) for every SCK the driver can produce."""
    choices = []
    for gen in range(1, 16):
        request = int(pclk / (2 * gen)) + (1 if pclk % (2 * gen) else 0)
        sck = pclk / (2 * (gen + 1))
        choices.append((f"{sck / 1e6:.3f} MHz", request))
    return choices


# --- SST26 registers (data sheet DS20005119) ---

SR_BITS = [
    (0, "BUSY"),
    (1, "WEL"),
    (2, "WSE"),
    (3, "WSP"),
    (4, "WPLD"),
    (5, "SEC"),
]


def decode_status(sr: int) -> str:
    on = [name for bit, name in SR_BITS if sr & (1 << bit)]
    return ", ".join(on) if on else "none set"


def decode_config(cr: int) -> str:
    # Bit positions from the SST26VF064B data sheet configuration register:
    # bit 1 IOC, bit 3 BPNV, bit 7 WPEN.
    parts = [
        f"IOC={(cr >> 1) & 1}",
        f"BPNV={(cr >> 3) & 1}",
        f"WPEN={(cr >> 7) & 1}",
    ]
    return ", ".join(parts)


# --- Debug LEDs LD1-LD3 (schematic sheet 6, MSS GPIO_0..2) ---

LEDS = [("LD1", "T12", "GPIO_0"), ("LD2", "T13", "GPIO_1"), ("LD3", "G13", "GPIO_2")]
LED_PERIOD_MIN_MS = 20
LED_PERIOD_MAX_MS = 10000


def parse_led_status(reply: Reply) -> List[tuple]:
    """[(mode, period_ms), ...] for led0..led2 from '@ok led status ...'."""
    out = []
    for i in range(len(LEDS)):
        mode, _, period = reply.kv.get(f"led{i}", "off:0").partition(":")
        out.append((mode, int(period or 0)))
    return out
