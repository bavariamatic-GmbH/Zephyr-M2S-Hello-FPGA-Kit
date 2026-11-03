---
name: hello-fpga-kit-uart-spi
description: "Use when working with the debug LEDs, the UART console, the USB host link through the kit's PIC32, MMUART bit rates, MSS SPI/I2C, the SPI flash U8 (SST26VF064B), the PAC1710 or the hk shell protocol of the test GUI on the Microchip M2S Hello FPGA Kit (SmartFusion2 M2S010-VF256) under Zephyr."
---

# M2S Hello FPGA Kit: PIC32 host link, UART, console and SPI

## Origin and validity

This skill is taken over from the SmartManipulator-X-Controller repository
(`bavariamatic-GmbH/SmartManipulator-X-Controller`, commit `0a0f8db`):

* `.agents/skills/smartfusion2/SKILL.md` (host serial transport),
* `.agents/skills/zephyr-smartfusion2/SKILL.md` (sections 27, 29, 30),
* `docs/hardware/wiring.md` (section "Host link"), `docs/hardware/tmc5160.md`,
  `docs/firmware/index.md` (section "Configuration"),
* `apps/SmartManipulator_Controller/src/communication.c` (MMUART fractional
  divisor).

Only the parts about the PIC32, UART, console and SPI are kept. The DYNAMIXEL
protocol and TMC5160 specifics stay in that repository.

The facts were verified on hardware there (dates below) with the
**SmartManipulator-X Libero design** (stage 2). Pin routing in this repository
depends on the Libero design actually loaded on the kit. If that design is a
different one, treat the pin table in section 5 as an example, not as a
fact, and ask for the Libero/MSS configuration instead of guessing (rule 11 of
the zephyr-smartfusion2 skill).

---

# 1. Host link (USB → MCP2221A → PIC32 → SmartFusion2)

The PC does not talk to the SmartFusion2 directly. The kit's USB Mini-B port
leads to an MCP2221A USB-UART bridge, then to a PIC32, and only the PIC32 is
wired to MMUART_0 of the SmartFusion2 (H12 TX / H13 RX, nets
`UART_TX_SF2` / `UART_RX_SF2`). Path: USB → MCP2221A → PIC32 (UART2) →
PIC32 (UART4) → SF2 MMUART_0.

The two UART segments run at **different bit rates**; the PIC32 converts
between them:

| Segment | Bit rate |
| --- | --- |
| PC ↔ MCP2221A ↔ PIC32 (UART2) | **460800 bps** (8N1, no flow control) |
| PIC32 (UART4) ↔ SmartFusion2 MMUART_0 | **230400 bps** |

The 230400 bps segment works on the hardware (2026-10-10). According to the
SmartManipulator documentation, Microchip's own Hello FPGA demo uses the same
rate on this path.

The host sees a USB serial device (for example `/dev/ttyACM0` on Linux, the
kit's COM port on Windows). The SmartFusion2 itself does not implement USB
CDC. Confirm the host device name before documenting it.

**The PIC32 forwards nothing until it has received the character `&`
(0x26).** After opening the port, the host:

1. opens the port at 460800 bps (8N1, no flow control),
2. sends `&`, which switches the PIC32 to UART pass-through,
3. waits about 100 ms and discards any bytes received so far,
4. then exchanges data in both directions.

**The PIC32 holds back a `%` (0x25) that ends a packet** until the next byte
arrives (measured on the kit, 2026-10-11: only this value, only towards the
SmartFusion2; `%` inside a packet passes normally). A host that sends packets
ending with 0x25 must send one more byte after them (SmartManipulator sends
`0x00`, which its firmware parser drops).

**Long bursts from the PC overrun the PIC32** (observed 2026-11-02, cause
inferred, not measured): the PIC32 receives at 460800 bps and sends on at
230400 bps. A 71-character shell line (`hk flash write ...`) was never echoed
and no later command was answered; lines up to about 30 characters always
worked. The test GUI sends in 16-byte chunks with a 3 ms pause
(`PIC32_TX_CHUNK` / `PIC32_TX_GAP_S` in `tools/hello_fpga_gui/hk/protocol.py`).
In a terminal, do not paste long lines.

**The SmartFusion2 must not send anything before the PC has sent `&`.**
Output that reaches the PIC32 earlier stops it; nothing passes until the USB
cable is replugged (information from the author of the Zephyr board port,
relayed by the user 2026-11-02: the upstream image prints at reset and does
not start on this kit; his original code waited for a key press).
SmartManipulator never had the problem because it sets
`CONFIG_PRINTK=n` / `CONFIG_BOOT_BANNER=n` and only answers requests. This
repository keeps the console but sets `CONFIG_BOOT_BANNER=n`,
`CONFIG_SHELL_AUTOSTART=n` and waits in `src/app/host_wait.c` for the first
byte from the host before any output; the GUI sends a newline after `&`.

Consequences:

* Changing the PC rate does not change the firmware rate, and the reverse.
  `current-speed` of `uart0` must equal the rate the PIC32 uses towards the
  SmartFusion2 (230400).
* Without the PIC32 (a USB-UART cable straight to the firmware UART), do not
  send `&` and open the cable at the firmware rate.

---

# 2. Console UART

* The board DTS (`m2s_hello_fpga_kit_m2s010.dts`) selects `uart0`
  (MMUART_0, `0x40000000`) as `zephyr,console` and `zephyr,shell-uart`.
* Use the `zephyr,console` chosen node (`DT_CHOSEN(zephyr_console)`) rather
  than hard-coding a UART node label. Add a `BUILD_ASSERT` that it is `okay`.
* The console UART may carry shell commands, logs and `printk` output. Do not
  send binary data over the same stream until those outputs are disabled or
  moved to another interface; otherwise diagnostic text corrupts the framing.
  To free the console UART for binary data, SmartManipulator sets:
  `CONFIG_UART_CONSOLE=n`, `CONFIG_PRINTK=n`, `CONFIG_BOOT_BANNER=n`,
  `CONFIG_EARLY_CONSOLE=n` (and `CONFIG_CONSOLE=n` in the board `.conf`).
* The spare `uart1` (MMUART_1, `0x40010000`) is the candidate diagnostics
  port: in the SmartManipulator Libero design it is on Arduino D1 TX (G3) /
  D0 RX (F3) for a 3.3 V USB-UART cable. Using it needs an explicit
  DeviceTree and Kconfig change.
* Because the console reaches the PC through the PIC32, a terminal on the
  kit's USB port must open at 460800 bps and send `&` first (section 1).

---

# 3. MMUART bit rate

* `uart0` and `uart1` are `ns16550` nodes in
  `dts/arm/microchip/smartfusion2/m2s010.dtsi` with
  `current-speed = <115200>` and the MSS peripheral clock (50 MHz on this
  board). Override `current-speed` in the application overlay.
* The Zephyr ns16550 driver programs only the integer divisor. At 50 MHz PCLK
  that is 13 for 230400 bps, i.e. 223214 bps (**-3.1 %**), too far off for a
  reliable link.
* The SmartFusion2 MMUART also has a fractional divisor in 1/64 steps (DFR,
  enabled by MM0.EFBR). SmartManipulator reprograms the divisor as
  DLR/DMR + DFR/64 after the ns16550 driver has initialized the UART and
  before reception is enabled: 13 + 36/64 = 230414 bps (+0.006 %).
  Register layout: SmartFusion2 MSS MMUART (UG0331), identical to the
  PolarFire SoC MSS MMUART driver (`mss_uart.h` / `mss_uart_regs.h`):

  | Register | Offset | Use |
  | --- | --- | --- |
  | DLR | `0x00` | divisor LSB (LCR.DLAB = 1) |
  | DMR | `0x04` | divisor MSB (LCR.DLAB = 1) |
  | LCR | `0x0C` | bit 7 = DLAB |
  | MM0 | `0x30` | bit 7 = EFBR (enable fractional baud rate) |
  | DFR | `0x3C` | fractional divisor, 1/64 units |

  Divisor in 1/64 units, rounded: `4 * PCLK / baud`. Sequence: set LCR.DLAB,
  write DMR and DLR (integer part), clear LCR.DLAB, set MM0.EFBR, write DFR
  (fraction). Reference implementation:
  `sf2_mmuart_set_fractional_baud()` in SmartManipulator's
  `src/communication.c`, guarded by
  `DT_NODE_HAS_COMPAT(node, ns16550) && CONFIG_SOC_SERIES_SMARTFUSION2`, with
  a `BUILD_ASSERT` that rejects any rate more than 0.5 % off.
  In this repository the same code is in `src/platform/sf2_mmuart.c`, run as
  `SYS_INIT(..., PRE_KERNEL_1, 55)`: after the ns16550 driver
  (`CONFIG_SERIAL_INIT_PRIORITY` = 50) and before the UART console
  (`CONFIG_CONSOLE_INIT_PRIORITY` = 60), with the rate taken from the
  `current-speed` of the `zephyr,console` UART.
* The MSS clocks in Libero (M3 100 MHz, APB_0/1 50 MHz) must stay equal to
  the board DTS (`cpu` 100 MHz, `clkc` `clock-frequencies = <100000000
  50000000>`). If either side changes, update the other and recompute the
  MMUART divisor.

---

# 4. MSS SPI

* `spi0` (MSS SPI_0, `0x40001000`) and `spi1` (MSS SPI_1, `0x40011000`) are
  `microchip,mpfs-spi` nodes in `m2s010.dtsi`, disabled by default, with
  `clock-frequency = <50000000>`. Enable them in the application overlay.
  Driver: `drivers/spi/spi_mchp_mss.c` (`CONFIG_SPI_MCHP_MSS`).
* Chip select: the MSS SPI hardware slave-select lines SS0-SS7. A device node's
  `reg = <N>` (or `spi_config.slave` / `.peripheral` for raw transfers) is the
  SS line N.
* **Clock limit:** the MSS SPI driver searches CLK_GEN only from 1 to 15, so
  any `frequency` / `spi-max-frequency` below PCLK/30 = **1.67 MHz** falls
  back to CLK_GEN = 0 and runs SCK at **25 MHz**. Request at least 1.67 MHz.
  On SmartManipulator a TMC5160 was not detected with the old 1 MHz
  (= 25 MHz SCK) setting and was detected with 2 MHz (50 MHz / 28 =
  1.79 MHz), verified on hardware 2026-10-10.
* In Zephyr 4.5 `spi_config.slave` and `SPI_OP_MODE_MASTER` are deprecated;
  the replacements are `spi_config.peripheral` and `SPI_OP_MODE_CONTROLLER`.
* Known gap: `mss_spi_disable_ints()` in the pinned MSS SPI driver inverts its
  mask; the SCK idle level between transfers is not guaranteed. Check it with
  a logic analyser during bring-up.
* The MSS SPI_0 pads (J12-J14/K12) are wired to the PIC32, like the MMUART_0
  pads. To reach the Arduino header, SPI_0 must be routed through the FPGA
  fabric in the Libero design.

---

# 5. Pinout in the SmartManipulator-X Libero design (stage 2)

From `SmartManipulator-X-Libero/docs/firmware_interface.md`, last
cross-checked 2026-10-09. Valid only when that Libero design is loaded.

| MSS peripheral | Use there | Kit pins |
| --- | --- | --- |
| MMUART_0 (`uart0`) | Host link via PIC32 and MCP2221A USB | H12 TX / H13 RX |
| MMUART_1 (`uart1`) | Spare UART, 3.3 V USB-UART cable | Arduino D1 TX (G3) / D0 RX (F3) |
| SPI_0 (`spi0`) | SPI devices (SPI mode 3 there), max 2 MHz there | SCK D13, MOSI D11, MISO D12 |
| SPI_0 SS0-SS5 | Chip selects, DeviceTree `reg = <0>`-`<5>` | D10, D8, D7, D6, D5, D4 |
| GPIO_0-2 | LED1-LED3 | T12, T13, G13 |
| I2C_0 | Reserved | Arduino SDA/SCL |

Verified on hardware: MMUART_0 host link at 230400 bps, SPI_0 SCK, MOSI, MISO
and SS0 (2026-10-10). SS1-SS5, LEDs, `uart1` and I2C_0 were not tested there.

The Arduino nets and balls match the Hello FPGA Kit schematics Rev. 1
(`Hello_FPGA_Kit_schematics_rev1.pdf` in SmartManipulator's
`docs/hardware/datasheets/`). 3V3 on J9-4 comes from an MCP1727 LDO fed by
USB 5 V.

---

# 6. Libero design of this repository (M2S010-VF256)

The kit has an **M2S010-VF256** (schematic sheets 2 and 4). The Libero project
`maker_kit_i2c_spi` targets `tq144` (`Zephyr.prjx`) and does not fit this kit;
do not take pins from it.

The contract for this repository is
[`docs/libero-hello-fpga-vf256.md`](../../../docs/libero-hello-fpga-vf256.md)
(all through the fabric):

| MSS signal | Ball | Kit net / connector |
| --- | --- | --- |
| MMUART_0 TX / RX | H12 / H13 | `UART_TX_SF2` / `UART_RX_SF2` (PIC32) |
| I2C_0 SDA / SCL | P8 / R8 | Arduino SDA / SCL, J7-9 / J7-10 |
| SPI_0 SCK / MOSI / MISO / SS0 | R13 / R11 / T11 / M10 | Arduino D13 / D11 / D12 / D10, J7-6/4/5/3 |
| SPI_1 SCK / MOSI / MISO / SS0 | T6 / M9 / N10 / M7 | U8 SST26VF064B: C / SI / SO / S# |
| GPIO_0 / 1 / 2 | T12 / T13 / G13 | LD1 / LD2 / LD3 (active low) |

The Libero project is created by `create_project.tcl` in the sibling
repository `Libero-Microchip-Hello-FPGA-Kit` (System Builder parameter names
taken from the working `maker_kit_i2c_spi` report `zephyr_sb_SYS_BLD.xml`).

Rules:

* Console: `uart0` at `current-speed = <230400>` plus the fractional divisor
  (`src/platform/sf2_mmuart.c`). The user confirmed (2026-11-02) that the
  SmartManipulator-X firmware with this setting connects to its GUI over the
  kit's USB port.
* Use SS line 0 on both SPI controllers (`.peripheral = 0`).
* U8 W# (R6) and HOLD# (M8) have 10 kΩ pull-ups (R47, R48); leave them
  unassigned or high.
* No pull-ups on the Arduino SDA/SCL nets: I2C needs external ones.
* The MSS SPI_0 pads (J12-J14, K12) and I2C_1 pads (H16, J16) go to the PIC32.
* J7-7 is GND (J7-8 not connected).

---

# 7. Devices on the kit (schematic Rev. 1)

* **LD1–LD3** (sheet 6): anode to 3.3 V, 330 Ω to `LEDx_DEBUG` → on when the
  pin is low. Zephyr's board DTS has `led0` `GPIO_ACTIVE_HIGH`; override it
  with `GPIO_ACTIVE_LOW` (this repository's overlay). LD4/LD5 are on the PIC32
  (RD2/RD3).

* **U8 SST26VF064B** (8 MB SPI flash), on SF2 fabric balls T6 / M7 / M9 /
  N10 / R6 / M8. Data sheet DS20005119: JEDEC ID `BF 26 43`; 03h read (no
  dummy, max 40 MHz), 02h page program (256 B), 20h sector erase (4 KB), D8h
  block erase (8/32/64 KB by address), C7h chip erase, 98h ULBPR (after WREN),
  66h/99h reset; SPI modes 0 and 3. **Write-protected after power-up** until
  ULBPR; program/erase on a protected block are ignored, so verify by reading
  back. Status register: BUSY bit 0, WEL bit 1. Configuration register: IOC
  bit 1, BPNV bit 3, WPEN bit 7.
* **U2 PAC1710** (current/power monitor, sense resistor R89 0.025 Ω on the
  1.2 V core rail), I2C address `1001 100` = 0x4C. It is on the PIC32's I2C2
  (RA2/RA3, `I2C_2_SCL_PAC` / `I2C_2_SDA_PAC`, ALERT# on RA4), **not on the
  SmartFusion2**. SF2 firmware cannot read it.
* SF2 I2C_1 pads (H16/J16) go to the PIC32's I2C1 (RA14/RA15) with 2.2 kΩ
  pull-ups (R109, R110). SF2 SPI_0 pads go to the PIC32's SPI2.

* **JTAG / J-Link** (sheets 4, 5): JTAGSEL (M12) pulled high by R84 1 kΩ
  (R85 to GND not fitted) → FPGA TAP, not the Cortex-M3 debug port; J4 TRST
  pulled low by R29; J4 goes through U14/U15 selected by PIC32 RD1
  (`JTAG_SELECT`, R108 to GND = header). A J-Link needs JTAGSEL low (board
  change) and nTRST driven high. Details: `docs/jlink-debug.md`.

---

# 8. Zephyr 4.5 MSS driver limits (checked in the source)

* `spi_mchp_mss.c` clocks `spi_context_total_tx_len()` frames: a transfer with
  RX longer than TX stops after the TX bytes. Give TX and RX the same length.
  The upstream `spi-nor` flash driver (short TX command, long RX) therefore
  does not work on this controller; `src/devices/sst26.c` uses equal-length buffers.
* The controller runs with `SPS` (slave select held for the whole transfer),
  `CLKMODE = 1`: SCK = PCLK / (2 × (CLK_GEN + 1)) with CLK_GEN 1-15 chosen as
  the first with PCLK / (2 × CLK_GEN) ≤ request; otherwise CLK_GEN = 0 = 25 MHz.
* `i2c_mchp_mss.c` waits `K_TICKS(1000)` for a transfer to finish: 10 s at the
  default 100 ticks/s. Observed 2026-11-02: `hk i2c scan` without a working
  bus blocked the shell thread far beyond the GUI timeout, so every later
  command (also `hk flash ...`) got no answer. This repository sets
  `CONFIG_SYS_CLOCK_TICKS_PER_SEC=1000` (1 s) and stops the scan at the first
  `-EAGAIN`. The shell runs one command at a time: a command that hangs
  blocks all others.
* `i2c_mchp_mss.c` rejects zero-length messages (`-EINVAL`): probe devices with
  a one-byte read. Standard speed = PCLK / 960, fast = PCLK / 256.

---

# 9. Shell protocol for tools

The shell commands in `src/shell/` end every `hk` command with one line `@ok <cmd> [k=v ...]`
or `@err <cmd> <errno> <text>`; flash reads add `@data <addr8> <hex>` lines.
A new command group goes into its own file `src/shell/hk_cmd_<name>.c`
(`SHELL_SUBCMD_ADD((hk), <name>, &sub_<name>, ...)`, helpers from
`hk_util.h`) and calls a module in `src/devices/`; add the file to
`CMakeLists.txt`. Keep this format when adding commands: `tools/hello_fpga_gui` parses it
(`hk/protocol.py`) and `hk/sim.py` simulates it. Commands end with `\n`, so
the PIC32's held `%` byte never ends a line.
