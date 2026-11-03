# Hello FPGA Kit test GUI

Desktop tool (Python + Tkinter) to check the demo firmware on the M2S Hello
FPGA Kit through the kit's USB port:

* **Console** – everything the board prints (Zephyr shell, demo loop), with
  timestamps, command line with history, save to file.
* **LEDs** – LD1–LD3 (MSS GPIO_0..2, balls T12/T13/G13): on, off, blink with
  a period of 20–10000 ms, single LEDs or all; indicator of the mode the board
  reports.
* **I2C** – I2C_0 scan, raw write / read / write→read with repeat for a logic
  analyzer, LTR-329ALS quick buttons (example 02).
* **SPI** – raw transfers on SPI_0 SS0 with the SCK values the MSS SPI driver
  can really produce, SPI mode 0–3, single transfers or bursts.
* **SPI Flash (U8)** – SST26VF064B: JEDEC ID, status/configuration registers,
  unlock (ULBPR), reset, read with hex dump and save, write text/hex/file with
  automatic sector erase and read-back verify, sector/block/chip erase, self
  test.
* **Debug log** – all GUI, link and console activity, optional raw serial
  bytes; every session is written to `logs/hk_gui_<date>_<time>.log` and can
  be saved elsewhere.

PAC1710 (U2) is **not** supported: on the kit it is connected only to the
PIC32's I2C2, not to the SmartFusion2 (schematic sheets 5 and 8).

## Requirements

* Firmware from this repository (shell commands `hk …`, `src/shell/`) on a
  Libero design as in [`docs/libero-hello-fpga-vf256.md`](../../docs/libero-hello-fpga-vf256.md).
* Python 3.9+ with Tkinter (python.org installer on Windows; `python3-tk` on
  Ubuntu) and `pyserial` (`requirements.txt`).

## Start

Windows, from VS Code opened **on the host** (not in the Dev Container – the
COM port is on Windows): **Tasks: Run Task → GUI: Hello FPGA tester → Run
Hello FPGA GUI**. The task creates `.venv` in the repository root on first
use. Alternatively double-click `run_gui.bat`.

Manually:

```text
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r tools\hello_fpga_gui\requirements.txt
cd tools\hello_fpga_gui
..\..\.venv\Scripts\python.exe hk_gui.py
```

Options: `--port COM5`, `--baud 460800`, `--no-pic32-bridge` (USB-UART cable
straight to MMUART_0), `--port SIM` (simulated board, no hardware).

## Connecting

1. Choose the kit's COM port, keep **460800** baud and **PIC32 bridge (&)**
   ticked: the PIC32 forwards data to the SmartFusion2 only after `&`, and
   talks to MMUART_0 at 230400 bit/s.
2. **Connect**. After `&` the GUI sends a newline: after a reset the
   firmware stays silent until it receives a first byte (output before `&`
   stops the PIC32, see `src/app/host_wait.c`). If the board was started
   with an older firmware that prints at reset and nothing comes back,
   unplug and replug the USB cable.
   With **Stop demo loop on connect** the GUI sends
   `hk loop off`, so the periodic LTR-329/SPI output does not mix with the
   replies, then `hk info`. The top bar shows the board and which controllers
   are ready (`i2c0=1 spi0=1 spi1=1`).
3. **USB cable pulled:** the top bar shows *connection lost*. With
   **Auto-reconnect** ticked the GUI reconnects (with `&` and the wake-up
   newline) as soon as the COM port is back.
4. **Board does not answer:** when a command gets no reply, the GUI sends
   `hk ping`; if that is not answered either, the top bar shows *board does
   not answer* – reset the board or replug USB, then Disconnect / Connect.

## Logic analyzer pins (J7, Arduino header)

| Signal | J7 pin | Arduino | Ball |
| --- | --- | --- | --- |
| SPI_0 SS0 | 3 | D10 | M10 |
| SPI_0 MOSI | 4 | D11 | R11 |
| SPI_0 MISO | 5 | D12 | T11 |
| SPI_0 SCK | 6 | D13 | R13 |
| GND | 7 | GND | – |
| I2C_0 SDA | 9 | SDA | P8 |
| I2C_0 SCL | 10 | SCL | R8 |

I2C needs external pull-ups (none on the kit's Arduino SDA/SCL nets).
Without them every failed transfer takes about 190 ms instead of well under
1 ms, and a scan (112 transfers back to back) hung firmware built before
2026-11-03 for good. The firmware now stops the scan at the first probe
slower than 50 ms (`@err i2c scan -116 … no pull-ups on SDA/SCL?`), and the
GUI's **Scan** sends one probe first and does not scan when it is slow.

## Notes

* **SPI clock:** `spi_mchp_mss.c` selects CLK_GEN 1–15 and runs
  SCK = 50 MHz / (2 × (CLK_GEN + 1)), 12.5 MHz down to 1.5625 MHz; a request
  below 1.67 MHz falls back to 25 MHz. The SCK lists contain only reachable
  values.
* **I2C speed:** std = PCLK/960 ≈ 52 kHz, fast = PCLK/256 ≈ 195 kHz
  (`i2c_mchp_mss.c`). Scan probes 0x08–0x77 with a one-byte read, because the
  driver does not accept zero-length messages.
* **SST26VF064B after power-up is write-protected.** Program and erase are
  ignored until **Unlock** (WREN + ULBPR); the GUI does it automatically
  unless you untick it. The read-back verify shows a protected device as
  "verify FAILED … read FF".
* **Block erase** erases 8, 32 or 64 KB depending on the address (data sheet
  block layout).

## Protocol

The GUI only uses the shell commands of `src/shell/`; every command ends
with one `@ok …` or `@err <cmd> <errno> <text>` line, flash reads add
`@data <addr> <hex>` lines. You can type the same commands in the console
tab, for example:

```text
hk info
hk i2c scan
hk i2c wr 0x29 4 88
hk spi xfer 2000000 0 aa55
hk flash id
hk flash read 0x0 64
hk led set 0 on
hk led set all blink 500
hk led status
```

## Tests

```text
cd tools/hello_fpga_gui
python -m unittest discover -s tests -v
```

The tests run the protocol parser and the link against `hk/sim.py`, a
simulated board (SST26 model, I2C device at 0x29). The simulator values are
test fixtures, not measurements.
