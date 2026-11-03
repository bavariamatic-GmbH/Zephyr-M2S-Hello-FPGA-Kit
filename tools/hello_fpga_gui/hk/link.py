"""Serial link to the board: console lines and "hk" command/reply handling."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from . import protocol

log = logging.getLogger("hk.link")


@dataclass
class CommandResult:
    command: str
    ok: bool
    reply: Optional[protocol.Reply]
    data: List[protocol.Reply] = field(default_factory=list)
    duration_s: float = 0.0
    error: str = ""  # timeout / link error text

    def summary(self) -> str:
        if self.reply is None:
            return f"{self.command}: {self.error or 'no reply'}"
        if self.ok:
            return f"{self.command}: OK {self.reply.text}"
        return (f"{self.command}: ERROR {self.reply.errno} {self.reply.message}"
                .rstrip())


class LinkError(Exception):
    pass


class Link:
    """Console of the board over a pyserial-like port.

    ``port`` needs ``write(bytes)``, ``read(n)``, ``in_waiting``, ``close()``
    and ``reset_input_buffer()`` (pyserial ``Serial`` or ``sim.SimBoard``).
    ``on_line(text, direction)`` is called from the reader thread for every
    received line (direction "rx") and for every sent line ("tx").
    ``on_raw(data, direction)`` gets the raw bytes for the debug log.
    ``on_lost(reason)`` is called once, from the thread that noticed it, when
    the port fails (USB cable unplugged); the link is closed by then.
    """

    def __init__(self, on_line: Callable[[str, str], None] = None,
                 on_raw: Callable[[bytes, str], None] = None,
                 on_lost: Callable[[str], None] = None):
        self.port = None
        self.on_line = on_line or (lambda text, direction: None)
        self.on_raw = on_raw or (lambda data, direction: None)
        self.on_lost = on_lost or (lambda reason: None)
        self.timeouts = 0  # commands without reply since the link was created
        self._reader: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._cmd_lock = threading.Lock()  # one hk command at a time
        self._write_lock = threading.Lock()
        self._pending_cv = threading.Condition()
        self._pending_active = False
        self._pending_data: List[protocol.Reply] = []
        self._pending_final: Optional[protocol.Reply] = None
        self._pending_tag: Optional[str] = None
        self._partial = b""
        self._pace = False  # chunked writes for the PIC32 bridge

    # ------------------------------------------------------------------ open
    @property
    def is_open(self) -> bool:
        return self.port is not None

    def open_port(self, port, pic32_bridge: bool = True) -> None:
        """Attach an already opened port and start the reader thread."""
        self.port = port
        self._pace = pic32_bridge
        if pic32_bridge:
            self.enable_pic32_bridge()
        self._stop.clear()
        self._reader = threading.Thread(target=self._read_loop, name="hk-reader",
                                        daemon=True)
        self._reader.start()
        self.wake_firmware()

    def wake_firmware(self) -> None:
        """Send one byte so the firmware starts its shell (src/app/host_wait.c).

        After a reset the firmware waits for this byte before it prints
        anything. If it already runs, the byte only gives a new prompt.
        """
        log.info("waking the firmware: sending newline, waiting %.0f ms",
                 protocol.FIRMWARE_WAKE_S * 1000)
        self._write_raw(protocol.FIRMWARE_WAKE)
        time.sleep(protocol.FIRMWARE_WAKE_S)

    def enable_pic32_bridge(self) -> None:
        """Send "&" so the kit's PIC32 forwards to MMUART_0, then flush."""
        log.info("PIC32 bridge: sending '&', waiting %.0f ms",
                 protocol.PIC32_SETTLE_S * 1000)
        self._write_raw(protocol.PIC32_UART_MODE_COMMAND)
        time.sleep(protocol.PIC32_SETTLE_S)
        try:
            self.port.reset_input_buffer()
        except Exception:  # pragma: no cover - port specific
            pass

    def close(self) -> None:
        self._stop.set()
        if self._reader is not None and self._reader is not threading.current_thread():
            self._reader.join(timeout=1.0)
        self._reader = None
        if self.port is not None:
            try:
                self.port.close()
            except Exception:  # pragma: no cover - port specific
                pass
        self.port = None
        with self._pending_cv:
            self._pending_cv.notify_all()

    def _lost(self, reason: str) -> None:
        """The port failed: close it and report it once (not after close())."""
        if self._stop.is_set():
            return
        log.error("connection lost: %s", reason)
        self.close()
        self.on_line(f"[link] connection lost: {reason}", "sys")
        self.on_lost(reason)

    # ------------------------------------------------------------------ I/O
    def _write_raw(self, data: bytes) -> None:
        port = self.port
        if port is None:
            raise LinkError("not connected")
        if data and data[-1] == protocol.PIC32_HELD_BYTE:
            data += protocol.PIC32_PUSH_BYTE
        with self._write_lock:
            if self._pace and len(data) > protocol.PIC32_TX_CHUNK:
                # Small chunks so the PIC32 (460800 in, 230400 out) keeps up
                step = protocol.PIC32_TX_CHUNK
                for pos in range(0, len(data), step):
                    port.write(data[pos:pos + step])
                    if pos + step < len(data):
                        flush = getattr(port, "flush", None)
                        if flush is not None:
                            flush()  # pyserial: wait until sent
                        time.sleep(protocol.PIC32_TX_GAP_S)
            else:
                port.write(data)
        self.on_raw(data, "tx")

    def send_line(self, text: str) -> None:
        """Send one console line (adds the line end)."""
        self._write_raw(text.encode("ascii", "replace") + b"\n")
        self.on_line(text, "tx")

    def _read_loop(self) -> None:
        port = self.port
        while not self._stop.is_set():
            try:
                waiting = port.in_waiting
                data = port.read(waiting or 1)
            except Exception as exc:  # serial unplugged etc.
                self._lost(f"serial read failed: {exc}")
                break
            if not data:
                continue
            self.on_raw(data, "rx")
            self._partial += data
            while True:
                idx = self._partial.find(b"\n")
                if idx < 0:
                    break
                raw = self._partial[:idx]
                self._partial = self._partial[idx + 1:]
                self._handle_line(raw.decode("ascii", "replace"))

    def _handle_line(self, raw: str) -> None:
        text = protocol.clean_line(raw)
        if not text:
            return
        self.on_line(text, "rx")
        reply = protocol.parse_reply(text)
        if reply is None:
            return
        with self._pending_cv:
            if not self._pending_active:
                return
            if reply.kind != "data" and self._pending_tag and reply.words                     and reply.words[0] != self._pending_tag:
                # Late reply of an earlier command that timed out
                log.debug("ignoring reply not for this command: %s", text)
                return
            if reply.kind == "data":
                self._pending_data.append(reply)
            else:
                self._pending_final = reply
                self._pending_cv.notify_all()

    # ------------------------------------------------------------- commands
    def command(self, cmd: str, timeout: float = 5.0) -> CommandResult:
        """Send an hk command line and wait for its @ok/@err line."""
        with self._cmd_lock:
            if self.port is None:
                return CommandResult(cmd, False, None, error="not connected")
            with self._pending_cv:
                self._pending_active = True
                self._pending_data = []
                self._pending_final = None
                # "hk flash id" -> replies start with "flash"
                words = cmd.split()
                self._pending_tag = words[1] if len(words) > 1 and words[0] == "hk" else None
            start = time.monotonic()
            log.debug("command: %s", cmd)
            try:
                self.send_line(cmd)
            except Exception as exc:
                with self._pending_cv:
                    self._pending_active = False
                if not isinstance(exc, LinkError):
                    self._lost(f"serial write failed: {exc}")
                return CommandResult(cmd, False, None, error=str(exc))
            with self._pending_cv:
                end = start + timeout
                while self._pending_final is None and self.port is not None \
                        and not self._stop.is_set():
                    left = end - time.monotonic()
                    if left <= 0:
                        break
                    self._pending_cv.wait(left)
                final = self._pending_final
                data = list(self._pending_data)
                self._pending_active = False
            duration = time.monotonic() - start
            if final is None:
                if self.port is None:
                    return CommandResult(cmd, False, None, data, duration,
                                         error="connection lost")
                log.warning("timeout after %.2f s: %s", duration, cmd)
                self.timeouts += 1
                return CommandResult(cmd, False, None, data, duration,
                                     error=f"no reply within {timeout:.1f} s")
            result = CommandResult(cmd, final.ok, final, data, duration)
            log.debug("reply (%.3f s): %s", duration, result.summary())
            return result
