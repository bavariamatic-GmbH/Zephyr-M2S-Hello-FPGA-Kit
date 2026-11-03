# Zephyr RTOS — Microchip SmartFusion2 M2S010

Development and build environment for **Zephyr RTOS firmware** targeting the **Microchip SmartFusion2 M2S Hello FPGA Kit**.

The repository uses Docker and VS Code Dev Containers to provide a reproducible and isolated build environment. Microchip **Libero SoC is not installed inside the container** and remains part of the external FPGA/hardware development environment.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/bavariamatic-GmbH/Zephyr-M2S-Hello-FPGA-Kit)

* **Web page:** <https://bavariamatic-gmbh.github.io/Zephyr-M2S-Hello-FPGA-Kit/> — this
  README, the test GUI, the Libero contract and a preview of the Zephyr board documentation
  proposed for upstream ([`docs/zephyr-upstream`](docs/zephyr-upstream/README.md)).
* **Build image:** `ghcr.io/bavariamatic-gmbh/zephyr-m2s-hello-fpga-kit` (used by the dev
  container and GitHub Codespaces).

---

## Table of Contents

* [Project Goals](#project-goals)
* [Architecture](#architecture)
* [Requirements](#requirements)
* [Repository Structure](#repository-structure)
* [Tool Versions](#tool-versions)
* [Environment Setup](#environment-setup)
* [VS Code Dev Container](#vs-code-dev-container)
* [Building the Firmware](#building-the-firmware)
* [I2C + SPI Demo](#i2c--spi-demo)
* [Pristine Build](#pristine-build)
* [Build Cache](#build-cache)
* [West and Zephyr](#west-and-zephyr)
* [Build Artifacts](#build-artifacts)
* [Libero SoC](#libero-soc)
* [Debugging](#debugging)
* [Updating Tool Versions](#updating-tool-versions)
* [CI/CD](#cicd)
* [Troubleshooting](#troubleshooting)
* [Project License](#project-license)

---

## Project Goals

The goal of this repository is to provide a reproducible development environment for firmware targeting:

* **Microchip SmartFusion2 M2S010**
* **M2S Hello FPGA Kit**
* **ARM Cortex-M3**
* **Zephyr RTOS**

The environment is designed primarily for:

* reproducible builds,
* local development,
* VS Code,
* CI/CD,
* a small Docker image,
* fast rebuilds using `ccache`,
* an isolated toolchain,
* separation of firmware and FPGA development tools.

---

## Architecture

The environment consists of two independent parts.

### Firmware

The Docker container contains:

```text
Debian
├── Python
├── west
├── CMake
├── Ninja
├── ccache
├── Zephyr SDK
└── ARM Cortex-M3 toolchain
```

The container is responsible exclusively for building Zephyr firmware.

### FPGA / Hardware

Microchip tools remain outside the container:

```text
Host
└── Microchip Libero SoC
    ├── SmartFusion2 MSS
    ├── FPGA fabric
    ├── clocks
    ├── pins
    └── hardware configuration
```

The Docker image **does not contain Libero SoC or Microchip license files**.

---

## Requirements

### Host

Required:

* Docker
* Docker BuildKit / Docker Buildx
* Git
* VS Code — optional
* VS Code Dev Containers extension — optional

Additional Microchip tools may be required for board programming, debugging, and FPGA/hardware development.

### Docker

Verify the installation:

```bash
docker --version
docker buildx version
```

BuildKit is recommended because it provides Docker build cache support.

### VS Code

If you are using VS Code, install the:

```text
Dev Containers
```

extension.

---

## Repository Structure

Repository structure (the root is a Zephyr application: the I2C + SPI demo
described in [I2C + SPI Demo](#i2c--spi-demo)):

```text
.
├── .devcontainer/
│   ├── devcontainer.json      published image (local + GitHub Codespaces)
│   └── dockerfile/
│       └── devcontainer.json  builds the image from ./Dockerfile
│
├── .github/workflows/
│   ├── container.yml          build image, build firmware, publish to ghcr.io
│   └── docs.yml               web page on GitHub Pages
│
├── .vscode/
│   ├── settings.json
│   ├── tasks.json
│   ├── ensure-west-workspace.sh
│   ├── workspace-menu.sh
│   └── host-menu.ps1          (Windows: .venv, test GUI)
│
├── boards/
│   └── m2s_hello_fpga_kit_m2s010.overlay
│
├── docs/
│   ├── libero-hello-fpga-vf256.md
│   ├── jlink-debug.md
│   ├── zephyr-upstream/       board page proposed for Zephyr (pull request)
│   └── site/                  web page: Sphinx config, Dockerfile of the docs tools
│
├── src/
│   ├── main.c                 start-up: initialise the modules, run the demo
│   ├── app/
│   │   ├── host_wait.c/.h     silent until the host sends a key (PIC32)
│   │   └── demo_loop.c/.h     LTR-329 + SPI once a second, "hk loop on|off"
│   ├── devices/               one module per device (driver API only)
│   │   ├── ltr329.c/.h        light sensor LTR-329ALS on I2C_0
│   │   ├── spi_raw.c/.h       raw transfers on SPI_0, SS0
│   │   ├── sst26.c/.h         SPI flash U8 (SST26VF064B) on SPI_1
│   │   └── leds.c/.h          debug LEDs LD1-LD3 on MSS GPIO_0..2
│   ├── platform/
│   │   └── sf2_mmuart.c       MMUART fractional baud divisor (230400 bit/s)
│   └── shell/                 "hk ..." commands for the test GUI
│       ├── hk_shell.c         root command "hk", ping / info / loop
│       ├── hk_util.c/.h       number/hex parsing, reply protocol
│       ├── hk_cmd_i2c.c       hk i2c ...
│       ├── hk_cmd_spi.c       hk spi ...
│       ├── hk_cmd_flash.c     hk flash ...
│       └── hk_cmd_led.c       hk led ...
│
├── tools/
│   └── hello_fpga_gui/         (Python/Tkinter test GUI)
│
├── Dockerfile
├── .dockerignore
├── .gitignore
├── compose.yaml
├── west.yml
├── CMakeLists.txt
└── prj.conf
```

Generated directories such as `build/` and `.ccache/` should not be committed to the repository.

---

## Tool Versions

The environment uses explicitly defined tool versions.

Current configuration:

| Tool       | Version                 |
| ---------- | ----------------------- |
| Base image | `python:3.12-slim-bookworm` (pinned by digest) |
| Python     | 3.12 (Zephyr 4.5 requires 3.12 or later) |
| Zephyr     | v4.5.0-rc3 (`west.yml`; v4.5.0 once tagged) |
| west       | 1.5.0                   |
| Zephyr SDK | 1.0.1 (checksums verified) |
| Toolchain  | ARM `arm-zephyr-eabi` in `/opt/zephyr-sdk/gnu` |
| CMake      | 3.30.5 (pip)            |
| Ninja      | Debian-provided version |
| ccache     | Debian-provided version |
| Board      | `m2s_hello_fpga_kit/m2s010` |

The SDK and `west` versions are defined in the `Dockerfile`; the Zephyr revision in
`west.yml`. The `m2s_hello_fpga_kit` board is part of Zephyr from 4.5, so older Zephyr
revisions do not build for it.

Avoid using `latest` for critical toolchain components.

---

## Environment Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Initialize West

If the repository uses a local manifest:

```bash
west init -l .
```

Then:

```bash
west update
```

Verify the environment:

```bash
west --version
```

---

# VS Code Dev Container

The recommended way to work with the project is to use VS Code Dev Containers.

Open the repository in VS Code:

```text
File → Open Folder
```

Then run:

```text
F1
→ Dev Containers: Reopen in Container
```

VS Code will:

1. pull the build image `ghcr.io/bavariamatic-gmbh/zephyr-m2s-hello-fpga-kit` (built from the
   repository `Dockerfile` by `.github/workflows/container.yml`),
2. start the container with the repository in `/workspaces/<folder name>`,
3. install the configured extensions,
4. create the west workspace and fetch Zephyr (`.vscode/ensure-west-workspace.sh`:
   `west init -l .`, `west update --narrow --fetch-opt=--depth=1`, about 20 s, Zephyr in
   `/workspaces/zephyr`).

To change the toolchain, use **Dev Containers: Reopen in Container** and select the
configuration *build image from Dockerfile* (`.devcontainer/dockerfile/devcontainer.json`).
It builds the image locally from `Dockerfile`.

A `build/` directory created by the old container (repository mounted at `/workspace`) has
absolute paths in its CMake cache: run a **pristine build** once.

## GitHub Codespaces

**Code → Codespaces → Create codespace on main** (or the badge at the top) starts the same
container in the cloud. When the codespace is ready, Zephyr is fetched and you can build at
once:

```bash
west build -b m2s_hello_fpga_kit/m2s010 -d build
```

Download `build/zephyr/zephyr.hex` (Explorer → right click → Download) and add it to the
Libero design. The board cannot be reached from a codespace: programming (Hello FPGA GUI) and
the test GUI run on your computer.

The codespace needs read access to the image: the package
`ghcr.io/bavariamatic-gmbh/zephyr-m2s-hello-fpga-kit` is linked to this repository by
`org.opencontainers.image.source`; make it **public** in the package settings so that forks
and other users can use it as well.

## Project web page

`docs/site` builds the web page with Sphinx: this README, the test GUI, `docs/*.md` and a
preview of the Zephyr board page in `docs/zephyr-upstream`. The pages are copied from these
files on every build; edit the originals.

VS Code tasks (on the host, need Docker):

| Task | What it does |
| --- | --- |
| **Docs: Live preview (http://localhost:8000)** | `docker compose up --build docs`: builds the page and rebuilds it on every change |
| **Docs: Build (strict, like CI)** | one full build with warnings as errors, output in `docs/site/_build/html` |
| **Docs: Stop preview** | stops the preview container |

`.github/workflows/docs.yml` builds the page with the same image (`docs/site/Dockerfile`) and
publishes it on GitHub Pages from `main` (repository setting **Pages → Source: GitHub
Actions**).

---

## Verify the Toolchain

Inside the container:

```bash
west --version
```

Then:

```bash
arm-zephyr-eabi-gcc --version
```

Also verify:

```bash
cmake --version
```

and:

```bash
ninja --version
```

The SDK should be installed at:

```text
/opt/zephyr-sdk
```

---

# Building the Firmware

The default board target is:

```text
m2s_hello_fpga_kit/m2s010
```

Build the firmware with:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

Run this command from the application directory, which must contain a
`CMakeLists.txt` file. To build an application in another directory, pass it
with `-s <application-directory>`.

After a successful build, the output will be located in:

```text
build/
```

---

## Building from VS Code

The default build task opens the **Zephyr: Workspace Menu** picker:

```text
Ctrl + Shift + B
```

Choose one of these actions:

- **Initialize + update** — initializes West from the local manifest if needed,
  then downloads or updates the Zephyr repositories and modules.
- **Update dependencies** — runs `west update` in an initialized workspace.
- **Build firmware** — builds the application for `m2s_hello_fpga_kit/m2s010`
  into `build/`.
- **Clean and Build** — the same as a pristine build (`west build -p always`).
- **Clean** — removes `build/`.

The menu is implemented in `.vscode/workspace-menu.sh`. Build tasks first run
`.vscode/ensure-west-workspace.sh` (task **Zephyr: Ensure workspace**), which
initializes West and runs `west update` when the workspace is not ready yet.

To open the same menu without the shortcut, use:

```text
F1
→ Tasks: Run Task
→ Zephyr: Workspace Menu
```

The individual tasks **Zephyr: Build** and **Zephyr: Pristine Build** are also
available from **Tasks: Run Task**.


---

# I2C + SPI Demo

The application in the repository root shows how to use the SmartFusion2 MSS
I2C and SPI controllers from Zephyr on the M2S Hello FPGA Kit (M2S010-VF256),
and offers shell commands for the test GUI in
[`tools/hello_fpga_gui`](tools/hello_fpga_gui/README.md).

| Part | Source | Peripheral | What it does |
| ---- | ------ | ---------- | ------------ |
| I2C demo | example `02_solution_i2c_driver` | `i2c0` (MSS I2C_0), standard speed | Reads `PART_ID` / `MANUFAC_ID` of the LTR-329ALS at `0x29`, enables ALS mode and prints the raw `CH0` / `CH1` values. |
| SPI demo | example `03_demo_spi_raw_cs1` | `spi0` (MSS SPI_0), SS0, 2 MHz request | Sends `0xAA 0x55` with `spi_transceive()` and prints the received bytes. |
| Shell `hk …` | `src/shell/` | `i2c0`, `spi0`, `spi1` | Raw I2C/SPI transfers and the SPI flash U8 for the GUI. |
| SPI flash | `src/devices/sst26.c` | `spi1` (MSS SPI_1), SS0 | SST26VF064B (U8): JEDEC ID, registers, unlock, read, page program, erase. |
| LEDs | `src/devices/leds.c` | `gpio0` pins 0–2 (MSS GPIO_0..2) | LD1–LD3 on, off or blinking (`hk led set <0\|1\|2\|all> <on\|off\|blink> [period_ms]`). |

The demo loop (I2C + SPI once a second) runs after reset; `hk loop off`
stops it (the GUI does this on connect).

### Files

The code is split into layers; each `.c` file has one job and a header
comment that says which Zephyr API it shows. A module only calls the layer
below it (`shell` → `devices` → Zephyr drivers).

| Layer | File | What it does |
| ----- | ---- | ------------ |
| start-up | `src/main.c` | Waits for the host, initialises the LEDs, the LTR-329 and SPI_0, then runs the demo loop. |
| application | `src/app/host_wait.c` | Blocks until the first byte from the host, then `shell_start()`; nothing is sent to the PIC32 before (see *Console connection*). |
| application | `src/app/demo_loop.c` | Once a second: LTR-329 sample and SPI `AA 55` transfer; `demo_loop_set()` / `demo_loop_get()` for `hk loop`. |
| devices | `src/devices/ltr329.c` | LTR-329ALS: `PART_ID` / `MANUFAC_ID`, ALS mode, `CH0` / `CH1` (`i2c_reg_read_byte()`, `i2c_reg_write_byte()`, `i2c_write_read()`), code of example 02. |
| devices | `src/devices/spi_raw.c` | `spi_raw_transfer()` on SPI_0, SS0 (`struct spi_config`, `spi_transceive()`), demo transfer of example 03. |
| devices | `src/devices/sst26.c` | SST26VF064B commands from the data sheet (9Fh, 05h, 35h, 06h, 03h, 02h, 20h, D8h, C7h, 98h, 66h/99h). The Zephyr `spi-nor` driver is not used: `spi_mchp_mss.c` clocks only as many bytes as the TX buffers hold, while `spi-nor` reads with a short TX and a long RX. |
| devices | `src/devices/leds.c` | LD1–LD3: on, off, blink (`gpio_dt_spec`, delayable work per LED, period 20–10000 ms). |
| platform | `src/platform/sf2_mmuart.c` | SmartFusion2 MMUART fractional divisor of the console UART (`SYS_INIT`, right after the ns16550 driver and before the console), taken over from SmartManipulator-X-Controller. |
| shell | `src/shell/hk_shell.c` | Root command `hk` and `hk ping`, `hk info`, `hk loop`. |
| shell | `src/shell/hk_util.c/.h` | Shared helpers: decimal / `0x` numbers, hex byte strings, the reply protocol `@ok …` / `@err …` / `@data …` (described in `hk_util.h`). |
| shell | `src/shell/hk_cmd_i2c.c`, `hk_cmd_spi.c`, `hk_cmd_flash.c`, `hk_cmd_led.c` | One file per command group; each adds itself to `hk` with `SHELL_SUBCMD_ADD()`, so a new group is one new file plus one line in `CMakeLists.txt`. |

* `prj.conf` — I2C, SPI, printk, shell on the console UART (no colours,
  640-character command buffer), libc settings from the I2C example.
* `boards/m2s_hello_fpga_kit_m2s010.overlay` — `uart0` at 230400 bps, enables
  `i2c0` (standard speed), `spi0` and `spi1`; LEDs `led0`–`led2` on `gpio0`
  pins 0–2, `GPIO_ACTIVE_LOW` (LD1–LD3 light when the pin is low, schematic
  sheet 6; the board DTS declares `led0` active high).

The board `m2s_hello_fpga_kit/m2s010` is part of Zephyr (pinned in `west.yml`),
so no `BOARD_ROOT` or `DTC_OVERLAY_FILE` arguments are needed.

### Build

```bash
west build -b m2s_hello_fpga_kit/m2s010 -d build
```

or **Ctrl + Shift + B → Build firmware** in VS Code.

### Libero design

The firmware needs a Libero design with MMUART_0, I2C_0, SPI_0, SPI_1 and
MSS GPIO_0..2 routed through the fabric to the kit pins. The required MSS
configuration, pins (from the kit schematic) and checks are in
[`docs/libero-hello-fpga-vf256.md`](docs/libero-hello-fpga-vf256.md). The
Libero project is created by `create_project.tcl` in the sibling repository
`Libero-Microchip-Hello-FPGA-Kit`; it runs synthesis only. Add
`build/zephyr/zephyr.hex` of this repository as eNVM client in Libero and
generate the bitstream there (see that repository's README).

The Libero project `maker_kit_i2c_spi` cannot be used on this kit: it targets
package `tq144`, the Hello FPGA Kit has an M2S010-VF256.

### Console connection

The console (`uart0`, MMUART_0) reaches the PC through the kit's USB port,
MCP2221A and PIC32 — the same path SmartManipulator-X-Controller uses:

1. Open the kit's USB serial port (COM port on Windows, `/dev/ttyACM0` on
   Linux) at **460800 bps**, 8N1, no flow control.
2. Send the character `&` once. The PIC32 forwards nothing before it.
3. The PIC32 talks to MMUART_0 at 230400 bps; the firmware runs `uart0` at
   that rate (overlay `current-speed`, fractional divisor in
   `src/platform/sf2_mmuart.c`). The ns16550 driver alone would give 223214 bps
   (-3.1 %); the divisor 13 + 36/64 gives 230414 bps.

4. Press any key (the GUI sends a newline). Only then does the firmware
   start: it prints the banner below, starts the demo loop and the shell.

**Why step 4:** output from the SmartFusion2 that reaches the PIC32 before
the PC has sent `&` stops the PIC32, and nothing comes through any more until
the USB cable is unplugged and plugged in again. The upstream Zephyr image,
which prints right after reset, does not start on this kit for that reason
(information from the author of the board port, 2026-11-02). This firmware
therefore has no boot banner (`CONFIG_BOOT_BANNER=n`), does not start the
shell by itself (`CONFIG_SHELL_AUTOSTART=n`) and waits in
`src/app/host_wait.c` for the first byte from the host. Do not add `printk()`
or log output that can run before `host_wait_for_key()`.

The GUI does steps 1–4 when **PIC32 bridge (&)** is ticked.

### Expected console output (UART0)

```text
I2C + SPI demo: m2s_hello_fpga_kit/m2s010
i2c0 ready: i2c@40002000
LTR-329ALS detected at 0x29, PART_ID=0x.., MANUFAC_ID=0x..
LTR-329ALS raw data: CH0=... CH1=... status=0x..
TX: AA 55 | RX: .. .. (CS=0)
hk:~$
```

### Debugging with a J-Link

Out of the box a J-Link cannot reach the Cortex-M3: JTAGSEL is pulled high
(FPGA TAP), J4 TRST is pulled low and J4 goes through a PIC32-controlled
multiplexer. The board change and the wiring are described in
[`docs/jlink-debug.md`](docs/jlink-debug.md).

### Test GUI

[`tools/hello_fpga_gui`](tools/hello_fpga_gui/README.md): console, LEDs
LD1–LD3 (on / off / blink), raw I2C and SPI for a logic analyzer (Arduino
header J7), SPI flash U8 functions, debug log saved to a file. Start it on the Windows host with **Tasks: Run Task →
GUI: Hello FPGA tester** or `tools\hello_fpga_gui\run_gui.bat`.

### Notes

* **SPI clock:** the MSS SPI driver (`spi_mchp_mss.c`) sets
  SCK = 50 MHz / (2 × (CLK_GEN + 1)) with CLK_GEN 1–15 (12.5 MHz down to
  1.5625 MHz). A request below 1.67 MHz falls back to 25 MHz, so the demo
  requests 2 MHz (SCK 1.79 MHz).
* **SPI chip select:** the demo and the GUI use SS0 of SPI_0 (Arduino D10).
* **Build warnings:** the application builds without warnings. The SPI
  example uses `.peripheral` and `SPI_OP_MODE_CONTROLLER` (the example's
  `.slave` / `SPI_OP_MODE_MASTER` are deprecated in Zephyr 4.5). One warning
  remains and comes from Zephyr itself, not from this project:
  `drivers/spi/spi_mchp_mss.c:194: unused variable 'xfer'` (Zephyr
  v4.5.0-rc3).
* **I2C timeout:** the MSS I2C driver waits `K_TICKS(1000)` for a transfer;
  `prj.conf` sets 1000 ticks/s so that is 1 s instead of 10 s. `hk i2c scan`
  stops with `@err i2c scan -11 bus timeout ...` at the first timeout. The
  shell runs one command at a time, so a hanging command blocks all others.
* **I2C bit rate:** `i2c_configure(... I2C_SPEED_STANDARD)` selects
  PCLK / 960 in `i2c_mchp_mss.c`: about 52 kHz with the 50 MHz APB clock.
* **I2C pull-ups:** none on the kit's Arduino SDA/SCL nets; fit external ones.
* **PAC1710 (U2)** is connected to the PIC32 only (I2C2), not to the
  SmartFusion2, and is not used.
* **SPI flash U8** is write-protected after power-up; `hk flash unlock`
  (WREN + ULBPR) is needed before program or erase.

---

# Pristine Build

A pristine build may be required after changing hardware configuration, Kconfig, or DeviceTree files.

Run:

```bash
west build \
    -p always \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

Alternatively:

```bash
rm -rf build
```

and then:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

The VS Code environment also provides:

```text
Zephyr: Pristine Build
```

---

# Build Cache

The project uses `ccache` to speed up subsequent builds.

The cache is stored on the host:

```text
.ccache/
```

and mounted inside the container as:

```text
/ccache
```

This means that removing and recreating the Docker container does not remove the compiler cache.

---

## Check Cache Statistics

Inside the container:

```bash
ccache --show-stats
```

You can also use VS Code:

```text
F1
→ Tasks: Run Task
→ Zephyr: Ccache Stats
```

---

## Clear the Cache

Run:

```bash
ccache --clear
```

or use:

```text
F1
→ Tasks: Run Task
→ Zephyr: Ccache Clear
```

The cache can also be removed completely:

```bash
rm -rf .ccache
```

This does not affect the source code.

---

# West and Zephyr

`west` is used to manage the Zephyr workspace and its dependencies.

In VS Code, initialize and download dependencies from **Zephyr: Workspace Menu**
by choosing **Initialize + update**. The task initializes from the local
manifest when necessary; if a workspace already exists, it only runs
`west update`.

For manual setup from the repository containing `west.yml`:

```bash
west init -l .
```

Then:

```bash
west update
```

The manifest is located at:

```text
west.yml
```

For reproducible builds, pin Zephyr to a specific release or revision instead of using:

```yaml
revision: main
```

Example:

```yaml
manifest:
  remotes:
    - name: zephyrproject-rtos
      url-base: https://github.com/zephyrproject-rtos

  projects:
    - name: zephyr
      remote: zephyrproject-rtos
      revision: <pinned-version>
      import: true
```

This ensures that subsequent builds use the same Zephyr source revision.

---

# Build Artifacts

The main build artifacts are located in:

```text
build/zephyr/
```

Typical files include:

```text
build/zephyr/zephyr.elf
build/zephyr/zephyr.hex
build/zephyr/zephyr.bin
```

### ELF

Primarily used for debugging.

```text
zephyr.elf
```

It contains debug information and symbols.

### HEX

Can be used by programming tools:

```text
zephyr.hex
```

### BIN

Raw firmware image:

```text
zephyr.bin
```

The exact programming method depends on the SmartFusion2 hardware configuration and programming environment.

---

# Libero SoC

**Libero SoC is not part of the Docker container.**

This is an intentional architectural decision.

The container is responsible for:

```text
Application
     ↓
Zephyr
     ↓
ARM Cortex-M3
     ↓
ELF / HEX / BIN
```

Libero is responsible for:

```text
SmartFusion2 hardware
        ↓
MSS
        ↓
Clock configuration
        ↓
FPGA fabric
        ↓
Pin configuration
        ↓
Hardware image
```

This separation avoids putting the following components into the Docker image:

* Libero SoC,
* Microchip license files,
* license server configuration,
* FPGA development tools.

---

## License Security

Microchip licenses should remain exclusively in the environment where they are required.

Do **not**:

* copy license files into the repository,
* add license files to the Dockerfile,
* include licenses in the Docker image,
* store licenses in a public container registry,
* publish licenses as CI artifacts.

---

# Debugging

Firmware can be debugged using:

* `zephyr.elf`,
* VS Code,
* Cortex-Debug,
* an appropriate hardware debugger/programmer.

The exact debugger configuration depends on the hardware interface and board setup.

Typical architecture:

```text
VS Code
   │
   ▼
Cortex-Debug
   │
   ▼
GDB
   │
   ▼
ARM Cortex-M3
   │
   ▼
SmartFusion2
```

Libero SoC is not required for debugging firmware already loaded into a configured hardware design.

---

# Docker Without VS Code

The Dev Container is not required.

Build the image directly:

```bash
docker build \
    -t ghcr.io/bavariamatic-gmbh/zephyr-m2s-hello-fpga-kit:1.0.1 \
    .
```

Start the container:

```bash
docker run --rm -it \
    -v "$PWD:/workspace" \
    -v "$PWD/.ccache:/ccache" \
    -w /workspace \
    ghcr.io/bavariamatic-gmbh/zephyr-m2s-hello-fpga-kit:1.0.1
```

Then build:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

---

# Docker Compose

If the repository contains `compose.yaml`, you can use:

```bash
docker compose run --rm zephyr
```

This avoids having to specify all Docker volume and environment parameters manually.

---

# Updating Tool Versions

SDK versions are defined in:

```text
Dockerfile
```

For example:

```dockerfile
ARG ZEPHYR_SDK_VERSION=1.0.1
```

The `west` version is defined as:

```dockerfile
ARG WEST_VERSION=1.5.0
```

After changing a tool version, rebuild the image:

```bash
docker build \
    --no-cache \
    -t ghcr.io/bavariamatic-gmbh/zephyr-m2s-hello-fpga-kit:<new-version> \
    .
```

Toolchain updates should not be performed automatically without validating the firmware.

Each update should be verified with:

1. firmware build,
2. firmware tests,
3. hardware testing on the M2S Hello FPGA Kit,
4. relevant integration tests,
5. updating the Docker image version.

---

# CI/CD

The same Dockerfile is used locally and in CI. Workflows in `.github/workflows`:

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `container.yml` | changes of `Dockerfile`, `.devcontainer/`, sources; manual | builds the image, builds the firmware in it (artifact `firmware-<sha>` with `zephyr.hex/.elf/.bin`), pushes the image to `ghcr.io` when the tag in `.devcontainer/devcontainer.json` is not published yet (or on a manual run) |
| `docs.yml` | changes of `README.md`, `docs/`, the GUI README; manual | builds the web page with warnings as errors, deploys it to GitHub Pages from `main` |

To publish a changed toolchain: change the `Dockerfile` and raise the image tag in
`.devcontainer/devcontainer.json` and `compose.yaml` in the same commit.

Pipeline of `container.yml`:

```text
Git push
    │
    ▼
CI runner
    │
    ▼
Docker image
    │
    ▼
west update
    │
    ▼
west build
    │
    ▼
firmware.elf
firmware.hex
firmware.bin
    │
    ▼
CI artifacts
```

`ccache` can also be persisted using the CI system's cache mechanism.

The CI environment should not contain:

* Microchip license files,
* a Libero installation,
* license server credentials,

when the pipeline is only responsible for building Zephyr firmware.

---

# Troubleshooting

## `west: command not found`

Check:

```bash
which west
```

It should return:

```text
/opt/venv/bin/west
```

Then:

```bash
west --version
```

---

## `source directory "." does not contain a CMakeLists.txt`

West is available, but the selected application directory does not contain a
Zephyr application. Add the application files, including `CMakeLists.txt`, to
the directory being built, or select the application directory explicitly:

```bash
west build -s <application-directory> \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

---

## `arm-zephyr-eabi-gcc: command not found`

Check:

```bash
ls /opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/
```

and:

```bash
echo $PATH
```

The PATH should contain:

```text
/opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin
```

---

## IntelliSense Problems

First perform a build:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

Then check:

```text
build/compile_commands.json
```

VS Code should use:

```text
C_Cpp.default.compileCommands
```

with:

```text
${workspaceFolder}/build/compile_commands.json
```

---

## Build Behaves Unexpectedly After Changing `prj.conf`

Perform a pristine build:

```bash
west build \
    -p always \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

---

## Problems After Changing DeviceTree

Remove the build directory:

```bash
rm -rf build
```

Then rebuild:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

---

## Ccache Does Not Speed Up the Build

Check:

```bash
ccache --show-stats
```

and:

```bash
echo $CCACHE_DIR
```

It should return:

```text
/ccache
```

Also verify that the directory exists:

```bash
ls -la /ccache
```

On the host:

```bash
ls -la .ccache
```

---

# Recommended Developer Workflow

After cloning the repository:

```bash
git clone <repository-url>
cd <repository>
```

Open the project in VS Code and run:

```text
Dev Containers: Reopen in Container
```

Inside the container:

```bash
west update
```

Build:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

After changing source code:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

`ccache` should speed up subsequent compilations.

After changing configuration:

```bash
west build \
    -p always \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

---

# Summary

The repository follows these principles:

```text
┌──────────────────────────────────────────────┐
│                 Development                  │
│                                              │
│  VS Code                                     │
│     │                                        │
│     ▼                                        │
│  Dev Container                               │
│     │                                        │
│     ├── Zephyr RTOS                          │
│     ├── west                                 │
│     ├── Zephyr SDK                           │
│     ├── ARM Cortex-M3 toolchain              │
│     ├── CMake                                │
│     ├── Ninja                                │
│     └── ccache                               │
│                                              │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
             M2S Hello FPGA Kit firmware
                       │
                       ├── ELF
                       ├── HEX
                       └── BIN


┌──────────────────────────────────────────────┐
│              Hardware / FPGA                 │
│                                              │
│  Microchip Libero SoC                        │
│       │                                      │
│       ├── MSS                                │
│       ├── clocks                             │
│       ├── FPGA fabric                        │
│       └── hardware configuration             │
│                                              │
│  Microchip licenses remain outside Docker.   │
│                                              │
└──────────────────────────────────────────────┘
```

The development environment provides:

* **reproducible builds**,
* **an isolated ARM toolchain**,
* **a small Docker image**,
* **VS Code Dev Container support**,
* **persistent `ccache`**,
* **explicit tool versioning**,
* **Zephyr + west**,
* **M2S Hello FPGA Kit support**,
* **Libero SoC outside Docker**,
* **no Microchip licenses inside the Docker image or repository**.

---

# Project License

The application source code and configuration contained in this repository are licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full license text.

Zephyr RTOS, Zephyr SDK, and other third-party tools and components are distributed under their respective licenses. Review the applicable license terms for each component before distributing the Docker image or other project artifacts.

```
```
