"""Tests for the protocol helpers and the link, against the simulated board.

Run from tools/hello_fpga_gui:  python -m unittest discover -s tests
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hk import protocol  # noqa: E402
from hk.link import Link  # noqa: E402
from hk.sim import SimBoard  # noqa: E402


class ProtocolTest(unittest.TestCase):
    def test_parse_ok_with_kv(self):
        r = protocol.parse_reply("@ok flash status sr=02 cr=08")
        self.assertTrue(r.ok)
        self.assertEqual(r.words, ["flash", "status"])
        self.assertEqual(r.kv, {"sr": "02", "cr": "08"})

    def test_parse_err(self):
        r = protocol.parse_reply("@err flash read -22 read failed or out of range")
        self.assertEqual(r.kind, "err")
        self.assertEqual(r.words, ["flash", "read"])
        self.assertEqual(r.errno, -22)
        self.assertEqual(r.message, "read failed or out of range")

    def test_parse_with_prompt_and_ansi(self):
        r = protocol.parse_reply("\x1b[1;32mhk:~$ \x1b[m@ok ping\r")
        self.assertIsNotNone(r)
        self.assertEqual(r.words, ["ping"])

    def test_non_reply(self):
        self.assertIsNone(protocol.parse_reply("LTR-329ALS raw data: CH0=1 CH1=2"))
        self.assertIsNone(protocol.parse_reply("hk:~$ hk flash id"))

    def test_hex(self):
        self.assertEqual(protocol.parse_hex_bytes("aa 55"), b"\xaa\x55")
        self.assertEqual(protocol.parse_hex_bytes("0xAA,0x55"), b"\xaa\x55")
        with self.assertRaises(ValueError):
            protocol.parse_hex_bytes("abc")
        with self.assertRaises(ValueError):
            protocol.parse_hex_bytes("zz")

    def test_spi_clock(self):
        # Driver: first CLK_GEN with 50 MHz / (2 * gen) <= request; SCK with CLKMODE 1
        self.assertEqual(protocol.mss_spi_clk_gen(2_000_000), 13)
        self.assertAlmostEqual(protocol.mss_spi_sck(2_000_000), 50e6 / 28)
        self.assertEqual(protocol.mss_spi_clk_gen(1_000_000), 0)  # 25 MHz fallback
        self.assertAlmostEqual(protocol.mss_spi_sck(1_000_000), 25e6)
        for label, req in protocol.spi_clock_choices():
            self.assertNotEqual(protocol.mss_spi_clk_gen(req), 0, label)
            self.assertEqual(f"{protocol.mss_spi_sck(req) / 1e6:.3f} MHz", label)

    def test_decode(self):
        self.assertEqual(protocol.decode_status(0x03), "BUSY, WEL")
        self.assertEqual(protocol.decode_config(0x08), "IOC=0, BPNV=1, WPEN=0")


class LinkSimTest(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.board = SimBoard(loop_period_s=0.05)
        self.link = Link(on_line=lambda t, d: self.lines.append((d, t)))
        self.link.open_port(self.board, pic32_bridge=True)

    def tearDown(self):
        self.link.close()

    def test_bridge_needed(self):
        board = SimBoard()
        link = Link()
        link.open_port(board, pic32_bridge=False)
        res = link.command("hk ping", timeout=0.5)
        link.close()
        self.assertFalse(res.ok)
        self.assertIn("no reply", res.error)

    def test_ping_info_loop(self):
        self.assertTrue(self.link.command("hk ping").ok)
        res = self.link.command("hk loop off")
        self.assertEqual(res.reply.words, ["loop", "off"])
        info = self.link.command("hk info")
        self.assertEqual(info.reply.kv["loop"], "0")
        self.assertEqual(info.reply.kv["spi1"], "1")

    def test_i2c(self):
        scan = self.link.command("hk i2c scan")
        self.assertEqual(scan.reply.words[2:], ["29"])
        self.assertTrue(self.link.command("hk i2c write 0x29 8001").ok)
        rd = self.link.command("hk i2c wr 0x29 4 88")
        self.assertEqual(len(bytes.fromhex(rd.reply.kv["rx"])), 4)
        nack = self.link.command("hk i2c read 0x50 1")
        self.assertFalse(nack.ok)
        self.assertEqual(nack.reply.errno, -5)

    def test_flash_locked_then_unlocked(self):
        self.assertEqual(self.link.command("hk flash id").reply.kv["jedec"], "bf2643")
        # Locked after power-up: program is ignored, read-back shows 0xFF
        self.assertTrue(self.link.command("hk flash write 0x100 a5a5").ok)
        rd = self.link.command("hk flash read 0x100 2")
        self.assertEqual(rd.data[0].words[1], "ffff")
        self.assertTrue(self.link.command("hk flash unlock").ok)
        self.assertTrue(self.link.command("hk flash erase sector 0x100").ok)
        self.assertTrue(self.link.command("hk flash write 0x100 a5a5").ok)
        rd = self.link.command("hk flash read 0x100 2")
        self.assertEqual(rd.data[0].words[1], "a5a5")

    def test_flash_read_lines(self):
        rd = self.link.command("hk flash read 0x0 100")
        self.assertTrue(rd.ok)
        self.assertEqual(len(rd.data), 4)  # 32 + 32 + 32 + 4 bytes
        self.assertEqual(rd.data[3].words, ["00000060", "ffffffff"])
        self.assertFalse(self.link.command("hk flash read 0x7fffff 2").ok)

    def test_leds(self):
        self.assertTrue(self.link.command("hk led set 1 blink 250").ok)
        self.assertTrue(self.link.command("hk led set 0 on").ok)
        st = protocol.parse_led_status(self.link.command("hk led status").reply)
        self.assertEqual(st, [("on", 500), ("blink", 250), ("off", 500)])
        self.assertTrue(self.link.command("hk led set all off").ok)
        st = protocol.parse_led_status(self.link.command("hk led status").reply)
        self.assertEqual([m for m, _ in st], ["off", "off", "off"])
        bad = self.link.command("hk led set 0 blink 5")
        self.assertFalse(bad.ok)
        self.assertEqual(bad.reply.errno, -22)

    def test_demo_loop_lines_are_not_replies(self):
        self.link.command("hk loop on")
        res = self.link.command("hk ping")
        self.assertTrue(res.ok)
        self.assertEqual(res.data, [])

    def test_late_reply_of_other_command_ignored(self):
        # "@ok info" arriving while "hk ping" waits must not end "hk ping"
        self.link._pending_active = True
        self.link._pending_tag = "ping"
        self.link._handle_line("@ok info board=x")
        self.assertIsNone(self.link._pending_final)
        self.link._handle_line("@ok ping")
        self.assertEqual(self.link._pending_final.words, ["ping"])
        self.link._pending_active = False

    def test_timeout_counted(self):
        before = self.link.timeouts
        self.assertFalse(self.link.command("kernel nothing", timeout=0.2).ok)
        self.assertEqual(self.link.timeouts, before + 1)


class LinkLostTest(unittest.TestCase):
    """USB cable pulled while connected."""

    def test_unplug_reported_once_and_link_closed(self):
        lost = []
        board = SimBoard(loop_period_s=0.05)
        link = Link(on_lost=lost.append)
        link.open_port(board, pic32_bridge=True)
        self.assertTrue(link.command("hk ping").ok)
        board.unplug()
        deadline = time.monotonic() + 2
        while not lost and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(lost), 1)
        self.assertFalse(link.is_open)
        res = link.command("hk ping", timeout=0.5)
        self.assertFalse(res.ok)
        self.assertIn("not connected", res.error)
        link.close()  # closing again is harmless and reports nothing
        self.assertEqual(len(lost), 1)

    def test_unplug_during_command(self):
        lost = []
        board = SimBoard(loop_period_s=0.05)
        link = Link(on_lost=lost.append)
        link.open_port(board, pic32_bridge=True)
        board.unplug()
        t0 = time.monotonic()
        res = link.command("hk ping", timeout=5)
        self.assertFalse(res.ok)
        self.assertLess(time.monotonic() - t0, 2)  # no 5 s wait
        self.assertEqual(len(lost), 1)

    def test_user_close_is_not_lost(self):
        lost = []
        link = Link(on_lost=lost.append)
        link.open_port(SimBoard(loop_period_s=0.05), pic32_bridge=True)
        link.close()
        time.sleep(0.1)
        self.assertEqual(lost, [])


class ChunkedWriteTest(unittest.TestCase):
    """Long lines go to the PIC32 in chunks of PIC32_TX_CHUNK bytes."""

    class Port:
        def __init__(self):
            self.writes = []

        def write(self, data):
            self.writes.append(bytes(data))

        def reset_input_buffer(self):
            pass

    def test_chunks(self):
        link = Link()
        link.port = self.Port()
        link._pace = True
        line = "hk flash write 0x000000 " + "ab" * 40
        link.send_line(line)
        writes = link.port.writes
        self.assertTrue(all(len(w) <= protocol.PIC32_TX_CHUNK for w in writes))
        self.assertEqual(b"".join(writes), line.encode() + b"\n")
        self.assertGreater(len(writes), 1)


if __name__ == "__main__":
    unittest.main()
