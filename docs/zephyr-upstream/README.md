# Board documentation for the Zephyr pull request

New documentation for `boards/microchip/m2s_hello_fpga_kit` in Zephyr
(`zephyrproject-rtos/zephyr`, `main`). The current page describes flashing
with OpenOCD, which does not work on an unmodified kit, and nothing about the
console path through the PIC32.

```text
boards/microchip/m2s_hello_fpga_kit/doc/
├── index.rst                              new page
└── img/
    ├── m2s_hello_fpga_kit.webp            unchanged (copied from Zephyr)
    ├── hello_fpga_gui_programmer.webp     Hello FPGA GUI V1.3, FPGA Programmer tab, steps 1–4
    │                                      marked by annotate_gui.py
    ├── libero_envm_client.webp            TODO: screenshot from Libero
    └── libero_export_bitstream.webp       TODO: screenshot from Libero
```

## Before opening the pull request

1. **Two Libero screenshots** (the page refers to them; the docs build fails
   without them):
   * `libero_envm_client.webp`: System Builder → Memories → eNVM, dialog of
     the data storage client with `zephyr.hex`, Intel-Hex, address 0.
   * `libero_export_bitstream.webp`: Design Flow → Export Bitstream, dialog
     with format **DAT** selected.

   Convert each one (max. 600 px, ≤ 100 KB, Zephyr compliance `ImageSize`):

   ```text
   python docs/zephyr-upstream/to_webp.py libero_envm.png  docs/zephyr-upstream/boards/microchip/m2s_hello_fpga_kit/doc/img/libero_envm_client.webp
   python docs/zephyr-upstream/to_webp.py libero_export.png docs/zephyr-upstream/boards/microchip/m2s_hello_fpga_kit/doc/img/libero_export_bitstream.webp
   ```

   (needs `pip install pillow`).
2. Copy `boards/` over a Zephyr checkout on a branch from `main`.
3. Build the docs once: `cd doc && make html-fast` (or
   `west build -t htmldocs-fast`), check the page and the three Graphviz
   diagrams.
4. Run the compliance check: `./scripts/ci/check_compliance.py -m ImageSize -m Rst`.
5. Commit with a `Signed-off-by:` line (DCO, `git commit -s`), for example:

   ```text
   boards: microchip: m2s_hello_fpga_kit: rework documentation

   Describe how the kit is really programmed (Libero eNVM client, DAT
   export, Hello FPGA GUI), the console path through the PIC32 (460800 /
   230400 bit/s, '&' handshake, no output before it), why the OpenOCD
   runner cannot reach the Cortex-M3 on an unmodified kit, and the issues
   found with the MSS UART, I2C and SPI drivers on this board.
   ```

## Board code the page describes as "known issues"

These are bugs in the board files, not only documentation. Fixing them in
the same pull request (or a second commit) is better than documenting them;
then remove the matching paragraphs from `index.rst`:

| File | Now | Should be | Section in index.rst |
| --- | --- | --- | --- |
| `m2s_hello_fpga_kit_m2s010.dts` | `led0` `GPIO_ACTIVE_HIGH` | `GPIO_ACTIVE_LOW` (LD1–LD3 light when low, schematic sheet 6) | Debug LEDs |
| `m2s_hello_fpga_kit_m2s010.dts` | `uart0` without `current-speed` (115200 from the dtsi) | `current-speed = <230400>` (PIC32 rate) | Serial Port |
| `m2s_hello_fpga_kit_m2s010_defconfig` | `CONFIG_SYS_CLOCK_TICKS_PER_SEC=100` | `1000` (I2C timeout 1 s instead of 10 s) | I2C |
| `board.cmake`, `support/openocd.cfg` | OpenOCD default runner | keep, but only works after the JTAGSEL change | Debugging |
| `drivers/serial/uart_ns16550.c` | integer divisor only | fractional divisor for the SmartFusion2 MMUART | Console bit rate |

## What the page is based on

* Measurements on the kit in this repository (2026-11-02/03): console at
  230400 bit/s with the fractional divisor, `&` handshake, long-line
  overrun, I2C without pull-ups (≈200 ms per failed transfer, scan hang),
  SPI clock table, SST26 protection.
* Hello FPGA Kit schematic Rev. 1 (sheets 4, 5, 6, 11): pins, JTAGSEL,
  TRST, JTAG multiplexer, LED polarity, missing I2C pull-ups.
* Microchip Hello FPGA Kit Quickstart (programming steps, reserved design
  versions 4, 6, 7, Serial Terminal tab for custom designs).
* Libero SoC 2026.1 help, `export_bitstream_file -format DAT`.
* Information from the author of the board port: output before `&` stops
  the PIC32.

Not verified on a kit: the J-Link / CMSIS-DAP board change (derived from the
schematic) and the `uart_poll_in()` variant of the "wait for the host" code
(this repository uses the shell backend variant).
