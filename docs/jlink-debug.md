# Debugging the Cortex-M3 with a SEGGER J-Link

The M2S Hello FPGA Kit has a JTAG header (J4), but **out of the box a J-Link
cannot connect to the Cortex-M3**: J-Link / J-Flash report "not connected".
This page explains why and what has to change on the board. All facts come
from the Hello FPGA Kit schematic Rev. 1 (sheets 4 and 5); the resistor values
and the state of `JTAG_SELECT` have **not been measured on a board yet** –
check them with a multimeter before soldering.

## Why the J-Link does not connect

### 1. JTAGSEL is pulled high: the header reaches the FPGA TAP, not the Cortex-M3

The SmartFusion2 JTAG pins (bank 3: `JTAG_TMS/M3_TMS/M3_SWDIO` N11,
`JTAG_TCK/M3_TCK` R14, `JTAG_TDI/M3_TDI` P16, `JTAG_TDO/M3_TDO/M3_SWO` P14,
`JTAG_TRSTB/M3_TRSTB` N13) are shared between two TAPs. The **JTAGSEL** pin
(ball M12) selects which one is connected:

| JTAGSEL | Connected to the JTAG pins | Used by |
| --- | --- | --- |
| High | FPGA fabric TAP (system controller) | FlashPro, Libero programming, the kit's PIC32 programmer |
| Low | Cortex-M3 debug port (SWJ-DP: JTAG or SWD) | J-Link, J-Flash, OpenOCD (`west flash` / `west debug`) |

On the kit (sheet 4): **R84 1 kΩ pulls JTAGSEL to 3.3 V, R85 1 kΩ to GND is
not fitted (NL)**. JTAGSEL is therefore always high. The J-Link expects an ARM
debug port and finds the Microchip FPGA TAP instead.

### 2. TRST on the header is pulled low

J4 pin 8 (`HDR_JTAG_TRST`) has **R29 1 kΩ to GND**. TRSTB low keeps the TAP
and the Cortex-M3 SWJ-DP in reset – also in SWD mode. The J-Link must drive
nTRST high.

### 3. The header goes through a multiplexer controlled by the PIC32

J4 is not wired directly to the SmartFusion2 (sheet 5). U14 (74CBTLV3257) and
U15 (74LVC1G157) select the JTAG source:

| `JTAG_SELECT` | Source of `SF2_JTAG_*` |
| --- | --- |
| Low (default, R108 4.7 kΩ to GND) | header J4 (`HDR_JTAG_*`) |
| High | PIC32 (`uC_JTAG_*`, the kit's USB programmer) |

`JTAG_SELECT` is driven by PIC32 pin 76 (OC2/RD1). If the PIC32 firmware
drives it high, J4 is disconnected. Measure it at R108: it must be close to
0 V while you use the J-Link. (The behaviour of the PIC32 firmware is not
known here.)

## Board modification

1. **JTAGSEL low:** remove **R84** and fit **R85** (1 kΩ to GND, 0402), or a
   0 Ω link to GND. Never fit both: 1 kΩ / 1 kΩ gives about 1.65 V, an
   undefined level.
2. Optional: make it switchable (e.g. a jumper from the R84/R85 node to GND),
   because **with JTAGSEL low the FPGA can no longer be programmed through
   JTAG** (FlashPro, Libero, the PIC32 USB programmer). Put JTAGSEL back high
   to program a new Libero bitstream.

## Wiring J4 to the J-Link

J4 is a 2×5, 2.54 mm header with the FlashPro layout, **not** the ARM 10- or
20-pin layout, so use single wires (or a J-Link 20-pin adapter cable with
flying leads).

| J4 pin | Kit net | J-Link 20-pin | J-Link signal |
| --- | --- | --- | --- |
| 1 | `HDR_JTAG_TCK` | 9 | TCK / SWCLK |
| 3 | `HDR_JTAG_TDO` | 13 | TDO / SWO |
| 5 | `HDR_JTAG_TMS` | 7 | TMS / SWDIO |
| 9 | `HDR_JTAG_TDI` | 5 | TDI |
| 8 | `HDR_JTAG_TRST` | 3 | nTRST (must be driven high) |
| even pins (GND) | GND | 4, 6, 8 … 20 | GND |
| even pin (3P3V) | 3.3 V | 1 | VTref |

The schematic places 3.3 V and GND on the even pins of J4; **identify the
3.3 V and GND pins with a multimeter** before connecting VTref. Power the kit
from USB; the J-Link only senses VTref.

SWD uses the same pins: SWDIO = TMS (J4-5), SWCLK = TCK (J4-1), SWO = TDO
(J4-3); nTRST must still be high.

## Using it

* **J-Link Commander / J-Flash / Ozone:** device family *SmartFusion2*
  (e.g. `M2S010`), interface JTAG or SWD, speed 1000 kHz to start with. SEGGER
  supports the M2S internal flash (eNVM) at address `0x00000000`, normal
  Cortex-M reset ([SEGGER KB: SmartFusion 2](https://kb.segger.com/SmartFusion_2)).
* **Zephyr:** the board's `support/openocd.cfg` (Zephyr
  `boards/microchip/m2s_hello_fpga_kit`) uses CMSIS-DAP over SWD and expects
  the Cortex-M3 DP ID `0x2ba01477`, so `west flash` / `west debug` also need
  JTAGSEL low. The upstream `board.cmake` defines only the `openocd` runner,
  so `west debug --runner jlink` is not available for this board as is. With
  a J-Link, debug `build/zephyr/zephyr.elf` in SEGGER Ozone, or start
  `JLinkGDBServer` (device `M2S010`, SWD or JTAG) and connect
  `arm-zephyr-eabi-gdb build/zephyr/zephyr.elf` to it (`target remote :2331`).
  This was not tried on the kit.
* **What the J-Link cannot do:** program the FPGA fabric (Libero bitstream).
  That needs JTAGSEL high and FlashPro / Libero / the kit's USB programmer.
  Programming the eNVM with J-Flash replaces the firmware that the Libero
  design put there (eNVM client `zephyr`).

## Checklist when it still does not connect

1. JTAGSEL (R85 side) at 0 V.
2. `JTAG_SELECT` (R108) at 0 V.
3. J4-8 (TRST) high while the J-Link is connected.
4. VTref = 3.3 V, common GND.
5. A Libero design is programmed and the MSS is running (the M3 debug port is
   inside the MSS).

## Sources

* Hello FPGA Kit schematic Rev. 1, sheet 4 (bank 3, JTAGSEL, R84/R85,
  R43/R44) and sheet 5 (U14, U15, R108, J4, R29, PIC32 RD1).
* Microchip, JTAG pins (JTAGSEL high = FPGA TAP, low = Cortex-M3 debug; TRSTB
  also resets the SWJ-DP):
  <https://onlinedocs.microchip.com/oxy/GUID-D4B0B980-06B2-4775-9723-AB191BC4A430-en-US-1/GUID-5243F358-14E6-442E-A1C6-858D410548F6.html>
  (page of the SmartFusion family; the SmartFusion2 pin names
  `JTAG_xxx/M3_xxx` show the same sharing).
* SEGGER Knowledge Base, SmartFusion 2: <https://kb.segger.com/SmartFusion_2>
