# Libero design for the demo (M2S Hello FPGA Kit, M2S010-VF256)

The firmware in this repository and the test GUI (`tools/hello_fpga_gui`)
expect a Libero SoC design with the MSS configuration below. This document is
the contract between that design and the firmware
(`boards/m2s_hello_fpga_kit_m2s010.overlay`).

The design is created by the Tcl script in the sibling repository
`Libero-Microchip-Hello-FPGA-Kit` (`create_project.tcl`, I/O constraints in
`constraint/hk_io.pdc`); see its README.

> The Libero project `maker_kit_i2c_spi` is **not** usable on this kit: it
> targets package `tq144` (`Zephyr.prjx`), the Hello FPGA Kit has an
> **M2S010-VF256** (schematic, sheets 2 and 4).

Sources:

* Hello FPGA Kit schematic Rev. 1 (`Hello_FPGA_Kit_schematics_rev1.pdf`,
  sheets 4 "SPI & MISC connection", 5 "PIC32MX795F512L connection",
  8 "Regulator connection", 11 "Arduino interface connection").
* SmartManipulator-X-Controller, Libero contract (zephyr-smartfusion2 skill,
  section 29): MMUART_0 through the fabric to H12/H13 works on this kit at
  230400 bps (2026-10-10), MSS clocks M3 100 MHz / APB 50 MHz.

## 1. Device

| Item | Value |
| --- | --- |
| Family / die | SmartFusion2, M2S010 |
| Package | VF256 (schematic: `M2S010-VFG256`) |
| I/O banks used | Bank 1 (H12/H13), Bank 4 (Arduino J7, SPI flash) — 3.3 V on the kit |

## 2. MSS clocks

Keep them equal to the Zephyr board DTS (`cpu` 100 MHz, `clkc`
`clock-frequencies = <100000000 50000000>`):

| Clock | Frequency |
| --- | --- |
| M3_CLK | 100 MHz |
| APB_0_CLK (PCLK0) | 50 MHz |
| APB_1_CLK (PCLK1) | 50 MHz |

If APB changes, update the DTS; the MMUART divisor (`src/platform/sf2_mmuart.c`), the
SPI clock table and the I2C bit rate depend on it.

## 3. MSS peripherals and pins

All peripherals are connected to the **fabric** (not to their MSIO
dedicated pads) and placed on the balls below.

| MSS signal | Direction (fabric port) | Ball | Kit net / connector | Device |
| --- | --- | --- | --- | --- |
| MMUART_0 TXD | out | H12 | `UART_TX_SF2` | PIC32 (USB bridge) |
| MMUART_0 RXD | in | H13 | `UART_RX_SF2` | PIC32 (USB bridge) |
| I2C_0 SDA | inout (BIBUF) | P8 | `MSIO112NB4_P8_ARD_SDA_IO14`, J7-9 | Arduino SDA, analyzer |
| I2C_0 SCL | inout (BIBUF) | R8 | `MSIO112PB4_R8_ARD_SCL_IO15`, J7-10 | Arduino SCL, analyzer |
| SPI_0 CLK | out | R13 | `MSIO118NB4_R13_ARD_SCK/IO13`, J7-6 | Arduino D13, analyzer |
| SPI_0 SDO (MOSI) | out | R11 | `MSIO115NB4_R11_ARD_PWM_MOSI/IO11`, J7-4 | Arduino D11, analyzer |
| SPI_0 SDI (MISO) | in | T11 | `MSIO115PB4_T11_ARD_MISO/IO12`, J7-5 | Arduino D12, analyzer |
| SPI_0 SS0 | out | M10 | `MSIO114NB4_M10_ARD_PWM_SS_IO10`, J7-3 | Arduino D10, analyzer |
| SPI_1 CLK | out | T6 | `SPI_FLSH_SCK` | U8 pin 16 (C) |
| SPI_1 SDO (MOSI) | out | M9 | `SPI_FLSH_MOSI` | U8 pin 15 (DQ0 / SI) |
| SPI_1 SDI (MISO) | in | N10 | `SPI_FLSH_MISO` (via R46 22 Ω) | U8 pin 8 (DQ1 / SO) |
| SPI_1 SS0 | out | M7 | `SPI_FLSH_CS` | U8 pin 7 (S#) |
| GPIO_0 | out | T12 | `LED1_DEBUG` | LD1 (active low) |
| GPIO_1 | out | T13 | `LED2_DEBUG` | LD2 (active low) |
| GPIO_2 | out | G13 | `LED3_DEBUG` | LD3 (active low) |

J7 pin 7 is GND on the schematic (sheet 11; pin 8 is not connected): connect
the analyzer ground there.

Notes from the schematic:

* **U8 W# (pin 9, ball R6) and HOLD# (pin 1, ball M8)** have 10 kΩ pull-ups to
  3.3 V (R47, R48). Leave R6 and M8 unused in Libero, or drive them high; do
  not drive them low.
* **`SPI_FLSH_CS`** also has a pull-up (R49 1 kΩ) and `SPI_FLSH_SCK` a
  pull-down (R50 100 kΩ).
* **I2C pull-ups:** no pull-up resistors are drawn on the Arduino SDA/SCL nets
  (sheet 11). Fit external pull-ups to 3.3 V (or enable the I/O weak pull-up
  on P8 and R8 in the I/O Editor if that is enough for your bus speed and
  wiring). Without pull-ups I2C does not work.
* **Do not use the MSS SPI_0 / I2C_1 / MMUART dedicated pads** for this demo:
  SPI_0 pads (J12, J13, J14, K12) and I2C_1 pads (H16, J16) are wired to the
  PIC32 (sheets 4 and 5).
* **PAC1710 (U2)** is on the PIC32's I2C2 (`I2C_2_SCL_PAC`, `I2C_2_SDA_PAC`,
  RA2/RA3, sheet 5), not on the SmartFusion2. It is not reachable from this
  firmware.
* **LEDs LD1–LD3** (sheet 6 "DEBUG LED - SF2"): anode to 3.3 V, cathode via
  330 Ω to `LEDx_DEBUG`, so they light when the pin is **low**. The Zephyr
  board DTS declares `led0` active high; the application overlay overrides it
  with `GPIO_ACTIVE_LOW`. GPIO reset value 1 (System Builder
  `GPIO_7_0_SET_RESET_VAL:RESET_STATE_1`) keeps them off after reset. LD4/LD5
  belong to the PIC32.
* **`FLASH_GOLDEN_N`** (ball H11) has a 10 kΩ pull-up (R42). The SPI flash
  content is free for this demo (decision 2026-11-02).

## 4. Fabric I/O

* I2C: one `BIBUF` per line, as in `maker_kit_i2c_spi` (`zephyr.v`):
  `D = I2C_0_xxx_M2F`, `E = I2C_0_xxx_M2F_OE`, `Y -> I2C_0_xxx_F2M`.
* SPI_0 / SPI_1 controller mode: `SPI_x_CLK_F2M` tied to 0, `SPI_x_SS0_F2M`
  tied to 1 (or connected through a `BIBUF` as in `maker_kit_i2c_spi`).
* All Bank 4 / Bank 1 I/Os: LVCMOS 3.3 V (banks powered at 3.3 V on the kit).

## 5. eNVM

`create_project.tcl` enables the eNVM but adds no client. Add a data storage
client with this repository's `build/zephyr/zephyr.hex` (Intel-Hex, address
0) in Libero before generating the bitstream, not the SmartManipulator-X
firmware.

## 6. Check list after building the design

1. `sys_config_mss_clocks.h`: M3 100 MHz, APB_0 / APB_1 50 MHz.
2. I/O report: H12, H13, T12, T13, G13, P8, R8, R13, R11, T11, M10, T6, M9,
   N10, M7 assigned as in section 3.
3. Program the kit, open the GUI, **Connect**: the console shows the shell
   prompt `hk:~$` and **Info** reports `i2c0=1 spi0=1 spi1=1`.
4. SPI flash tab, **Read ID**: `BF 26 43` (SST26VF064B).
5. LEDs tab: **On / Off / Blink** on LD1–LD3.
