"""Simulated board for running the GUI and the tests without hardware.

It answers the same "hk" shell commands as src/shell/ with the same reply
lines. The devices behind it are models, not measurements:

* SST26VF064B: 8 MB of 0xFF, write-protected after "power-up" until
  "hk flash unlock", program only clears bits (1 -> 0), WEL needed per command.
* I2C: one device at 0x29 with LTR-329ALS register addresses from the example
  02_solution_i2c_driver. PART_ID / MANUFAC_ID values are placeholders of
  this simulator (0xA0 / 0x05), not read from a data sheet.
* SPI_0: MISO returns the inverted MOSI bytes so a transfer is visible.

Use the port name "SIM" in the GUI.
"""

from __future__ import annotations

import threading
import time

from . import protocol

PROMPT = "hk:~$ "


class _Sst26:
    def __init__(self):
        self.mem = bytearray(b"\xff" * protocol.SST26_SIZE)
        self.locked = True
        self.wel = False
        self.hz = 2000000

    # The firmware reports success when the device accepted WREN and finished;
    # a protected array ignores program/erase. The model does the same, so the
    # GUI's read-back verify is what reveals a locked device.
    def program(self, addr: int, data: bytes) -> int:
        if addr < 0 or addr + len(data) > protocol.SST26_SIZE:
            return -22
        if not self.locked:
            for i, b in enumerate(data):
                self.mem[addr + i] &= b
        return 0

    def erase(self, kind: str, addr: int) -> int:
        if kind == "sector":
            start = addr - addr % protocol.SST26_SECTOR
            size = protocol.SST26_SECTOR
        elif kind == "block":
            # Model: 64 KB blocks everywhere (real part: 8/32/64 KB by address)
            start = addr - addr % 0x10000
            size = 0x10000
        else:
            start, size = 0, protocol.SST26_SIZE
        if not self.locked:
            self.mem[start:start + size] = b"\xff" * size
        return 0


class _Ltr329:
    def __init__(self):
        self.regs = {protocol.LTR329_PART_ID: 0xA0, protocol.LTR329_MANUFAC_ID: 0x05,
                     protocol.LTR329_ALS_CONTR: 0x00, protocol.LTR329_MEAS_RATE: 0x03,
                     protocol.LTR329_ALS_PS_STATUS: 0x00}
        self.pointer = 0
        self.counter = 0

    def write(self, data: bytes) -> None:
        self.pointer = data[0]
        if len(data) > 1:
            self.regs[self.pointer] = data[1]

    def read(self, n: int) -> bytes:
        out = bytearray()
        active = self.regs.get(protocol.LTR329_ALS_CONTR, 0) & 1
        self.regs[protocol.LTR329_ALS_PS_STATUS] = 0x04 if active else 0x00
        if active:
            self.counter = (self.counter + 37) % 5000
            ch1, ch0 = 100 + self.counter // 3, 200 + self.counter
            self.regs[0x88], self.regs[0x89] = ch1 & 0xFF, ch1 >> 8
            self.regs[0x8A], self.regs[0x8B] = ch0 & 0xFF, ch0 >> 8
        for i in range(n):
            out.append(self.regs.get(self.pointer + i, 0x00))
        return bytes(out)


class SimBoard:
    """pyserial-like object: write() commands, read() console output."""

    def __init__(self, loop_period_s: float = 1.0):
        self._out = bytearray()
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._line = b""
        self._closed = False
        self._unplugged = False
        self.loop = True
        self.flash = _Sst26()
        self.i2c = {protocol.LTR329_ADDR: _Ltr329()}
        self.bridge = False
        self.leds = [["off", 500] for _ in range(3)]
        self._emit("*** Booting Zephyr OS (simulator) ***")
        self._emit("I2C + SPI demo: m2s_hello_fpga_kit/m2s010 (SIM)")
        self._emit(PROMPT, newline=False)
        self._loop_thread = threading.Thread(target=self._demo_loop,
                                             args=(loop_period_s,), daemon=True)
        self._loop_thread.start()

    # ------------------------------------------------------- pyserial API
    @property
    def in_waiting(self) -> int:
        with self._lock:
            return len(self._out)

    def unplug(self) -> None:
        """Simulate a pulled USB cable: read() and write() fail from now on."""
        with self._cv:
            self._unplugged = True
            self._cv.notify_all()

    def read(self, n: int = 1) -> bytes:
        with self._cv:
            if self._unplugged:
                raise OSError("device disconnected (simulated)")
            if not self._out and not self._closed:
                self._cv.wait(0.05)
            data = bytes(self._out[:n])
            del self._out[:n]
            return data

    def write(self, data: bytes) -> int:
        if self._unplugged:
            raise OSError("device disconnected (simulated)")
        for b in data:
            if not self.bridge:
                if b == ord("&"):
                    self.bridge = True
                continue
            if b in (0x0A, 0x0D):
                line = self._line.decode("ascii", "replace")
                self._line = b""
                if line or b == 0x0A:
                    self._execute(line)
            else:
                self._line += bytes([b])
        return len(data)

    def reset_input_buffer(self) -> None:
        with self._lock:
            self._out.clear()

    def close(self) -> None:
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    # ------------------------------------------------------- internals
    def _emit(self, text: str, newline: bool = True) -> None:
        with self._cv:
            self._out += (text + ("\r\n" if newline else "")).encode()
            self._cv.notify_all()

    def _demo_loop(self, period: float) -> None:
        while not self._closed:
            time.sleep(period)
            if self.loop and self.bridge and not self._closed:
                self._emit("LTR-329ALS raw data: CH0=200 CH1=100 status=0x04")
                self._emit("TX: AA 55 | RX: 55 AA (CS=0)")

    def _execute(self, line: str) -> None:
        self._emit(line)  # shell echo
        args = line.split()
        if args:
            if args[0] == "hk":
                try:
                    self._hk(args[1:])
                except (IndexError, ValueError):
                    self._emit("@err hk -22 bad arguments")
            else:
                self._emit(f"{args[0]}: command not found")
        self._emit(PROMPT, newline=False)

    def _err(self, cmd: str, errno: int, text: str) -> None:
        self._emit(f"@err {cmd} {errno} {text}")

    def _hk(self, a):
        if a[0] == "ping":
            self._emit("@ok ping")
        elif a[0] == "info":
            self._emit(f"@ok info board=m2s_hello_fpga_kit/m2s010 i2c0=1 spi0=1 spi1=1 "
                       f"loop={int(self.loop)} flash_hz={self.flash.hz}")
        elif a[0] == "loop":
            if len(a) > 1:
                self.loop = a[1] == "on"
            self._emit(f"@ok loop {'on' if self.loop else 'off'}")
        elif a[0] == "i2c":
            self._i2c(a[1:])
        elif a[0] == "spi":
            self._spi(a[1:])
        elif a[0] == "flash":
            self._flash(a[1:])
        elif a[0] == "led":
            self._led(a[1:])
        else:
            self._emit(f"hk: {a[0]}: unknown parameter")

    def _i2c(self, a):
        cmd = a[0]
        if cmd == "scan":
            self._emit("@ok i2c scan" + "".join(f" {x:02x}" for x in sorted(self.i2c)))
            return
        if cmd == "speed":
            self._emit(f"@ok i2c speed {a[1]}")
            return
        addr = int(a[1], 0)
        dev = self.i2c.get(addr)
        if dev is None:
            self._err(f"i2c {cmd}", -5, "transfer failed (NACK?)")
            return
        if cmd == "write":
            data = protocol.parse_hex_bytes("".join(a[2:]))
            dev.write(data)
            self._emit(f"@ok i2c write addr={addr:02x} n={len(data)}")
        elif cmd == "read":
            self._emit(f"@ok i2c read addr={addr:02x} rx={dev.read(int(a[2], 0)).hex()}")
        elif cmd == "wr":
            dev.write(protocol.parse_hex_bytes("".join(a[3:])))
            self._emit(f"@ok i2c wr addr={addr:02x} rx={dev.read(int(a[2], 0)).hex()}")

    def _spi(self, a):
        hz = int(a[1], 0)
        if a[0] == "xfer":
            data = protocol.parse_hex_bytes("".join(a[3:]))
            rx = bytes(b ^ 0xFF for b in data)
            self._emit(f"@ok spi xfer hz={hz} mode={a[2]} n={len(data)} rx={rx.hex()}")
        elif a[0] == "repeat":
            data = protocol.parse_hex_bytes("".join(a[5:]))
            count = int(a[3], 0)
            time.sleep(min(count * int(a[4], 0), 2000) / 1000.0)
            rx = bytes(b ^ 0xFF for b in data)
            self._emit(f"@ok spi repeat count={count} n={len(data)} rx={rx.hex()}")

    def _led(self, a):
        if a[0] == "status":
            st = " ".join(f"led{i}={m}:{p}" for i, (m, p) in enumerate(self.leds))
            self._emit(f"@ok led status {st} ready=111")
            return
        target, mode = a[1], a[2]
        period = int(a[3], 0) if len(a) > 3 else 500
        if mode not in ("on", "off", "blink"):
            self._err("led set", -22, "use on|off|blink")
            return
        if mode == "blink" and not 20 <= period <= 10000:
            self._err("led set", -22, "led not ready or period not 20..10000 ms")
            return
        idx = range(3) if target == "all" else [int(target, 0)]
        for i in idx:
            if not 0 <= i < 3:
                self._err("led set", -22, "led must be 0, 1, 2 or all")
                return
            self.leds[i][0] = mode
            if mode == "blink":
                self.leds[i][1] = period
        self._emit(f"@ok led set {target} {mode} period={period}")

    def _flash(self, a):
        f = self.flash
        cmd = a[0]
        if cmd == "id":
            self._emit("@ok flash id jedec=" + protocol.SST26_JEDEC_ID)
        elif cmd == "status":
            sr = 0x00
            self._emit(f"@ok flash status sr={sr:02x} cr=08")
        elif cmd == "unlock":
            f.locked = False
            self._emit("@ok flash unlock")
        elif cmd == "reset":
            f.wel = False
            self._emit("@ok flash reset")
        elif cmd == "freq":
            if len(a) > 1:
                f.hz = int(a[1], 0)
            self._emit(f"@ok flash freq hz={f.hz}")
        elif cmd == "read":
            addr, length = int(a[1], 0), int(a[2], 0)
            if length < 1 or length > protocol.FLASH_READ_CHUNK or \
                    addr + length > protocol.SST26_SIZE:
                self._err("flash read", -22, "read failed or out of range")
                return
            for off in range(0, length, 32):
                n = min(32, length - off)
                self._emit(f"@data {addr + off:08x} {f.mem[addr + off:addr + off + n].hex()}")
            self._emit(f"@ok flash read addr={addr:08x} len={length}")
        elif cmd == "write":
            addr = int(a[1], 0)
            data = protocol.parse_hex_bytes("".join(a[2:]))
            ret = f.program(addr, data)
            if ret:
                self._err("flash write", ret, "program failed (locked? run unlock)")
            else:
                self._emit(f"@ok flash write addr={addr:08x} n={len(data)}")
        elif cmd == "erase":
            kind = a[1]
            addr = int(a[2], 0) if kind != "chip" else 0
            ret = f.erase(kind, addr)
            if ret:
                self._err("flash erase", ret, "erase failed (locked? run unlock)")
            else:
                self._emit(f"@ok flash erase {kind} addr={addr:08x} ms=18")
