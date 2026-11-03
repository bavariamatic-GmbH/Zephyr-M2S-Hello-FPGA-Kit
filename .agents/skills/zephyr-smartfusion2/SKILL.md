---

name: zephyr-smartfusion2
description: Development and maintenance guidelines for Zephyr RTOS firmware targeting
the Microchip SmartFusion2 M2S Hello FPGA Kit. Covers the ARM Cortex-M3
toolchain, Docker-based reproducible builds, VS Code Dev Containers,
west workspace management, ccache, DeviceTree, Kconfig, firmware
artifacts, and the separation of Zephyr firmware development from
Microchip Libero SoC and its licensing environment.
---------------------------------------------------

# Zephyr SmartFusion2 Development Skill

## Purpose

This skill defines the engineering rules and workflow for this repository.

The repository contains firmware for the:

* Microchip SmartFusion2 M2S010
* M2S Hello FPGA Kit
* ARM Cortex-M3
* Zephyr RTOS

The project uses Docker as the reproducible firmware build environment and
VS Code Dev Containers as the primary development environment.

Microchip Libero SoC is intentionally kept outside the Docker environment.

---

# 1. Repository Architecture

The project is split into two environments.

## Firmware environment

The Docker container is responsible for:

* Zephyr RTOS
* west
* Zephyr SDK
* ARM Cortex-M3 toolchain
* CMake
* Ninja
* ccache
* firmware compilation
* firmware artifacts

The expected flow is:

```text
Application
    |
    v
Zephyr RTOS
    |
    v
ARM Cortex-M3
    |
    v
ELF / HEX / BIN
```

## Hardware environment

Microchip Libero SoC is responsible for:

* SmartFusion2 MSS configuration
* clock configuration
* FPGA fabric
* pin configuration
* hardware generation
* FPGA-related artifacts

The expected separation is:

```text
Docker
  |
  +-- Zephyr firmware
  +-- ARM toolchain
  +-- ELF / HEX / BIN

Host
  |
  +-- Libero SoC
  +-- SmartFusion2 hardware project
  +-- Microchip licensing
```

Do not merge these environments unless explicitly requested.

---

# 2. Target Board

The default Zephyr target is:

```text
m2s_hello_fpga_kit/m2s010
```

Use this target for normal builds.

Example:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

Do not silently change the board target.

If a different board is requested, verify that the requested Zephyr board target exists before modifying build configuration.

---

# 3. Toolchain

The project targets:

```text
ARM Cortex-M3
```

The expected compiler is:

```text
arm-zephyr-eabi-gcc
```

The Zephyr SDK is installed under:

```text
/opt/zephyr-sdk
```

The ARM toolchain is expected under (Zephyr SDK 1.0 layout):

```text
/opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin
```

The board `m2s_hello_fpga_kit/m2s010` exists in Zephyr 4.5 and later, which needs
Python 3.12 or later and Zephyr SDK 1.0.

Do not introduce another ARM toolchain unless explicitly required.

Do not install unrelated Zephyr toolchains such as:

* RISC-V
* ARC
* Xtensa
* x86
* LLVM

unless the project requirements change.

---

# 4. Version Pinning

Reproducibility is a project requirement.

Important versions must be explicitly pinned.

The Dockerfile currently defines:

```text
WEST_VERSION
ZEPHYR_SDK_VERSION
```

The Zephyr source revision must also be pinned in:

```text
west.yml
```

Do not replace a pinned revision with:

```text
main
```

or another moving branch unless explicitly requested.

Avoid:

```text
latest
```

for critical build dependencies.

When updating a toolchain version:

1. update the version explicitly;
2. rebuild the Docker image;
3. build the firmware;
4. test the firmware;
5. verify the M2S Hello FPGA Kit;
6. document the change.

---

# 5. Docker Rules

The Dockerfile is the single source of truth for the firmware build environment.

VS Code Dev Containers must use the repository root Dockerfile.

Do not create a second independent toolchain installation inside:

```text
.devcontainer/
```

unless there is a specific reason.

The preferred architecture is:

```text
.devcontainer/devcontainer.json
        |
        v
../Dockerfile
```

This ensures that:

* local Docker builds,
* VS Code builds,
* CI builds

use the same environment.

Since 2026-11-03 the default `.devcontainer/devcontainer.json` uses the image
`ghcr.io/bavariamatic-gmbh/zephyr-m2s-hello-fpga-kit:<tag>`, which
`.github/workflows/container.yml` builds from the root Dockerfile (needed for
GitHub Codespaces). `.devcontainer/dockerfile/devcontainer.json` builds the
same Dockerfile locally. Rules:

* A Dockerfile change needs a new tag in `.devcontainer/devcontainer.json`
  and `compose.yaml` in the same commit; the workflow publishes a tag once.
* No `workspaceMount`, `workspaceFolder` or bind `mounts` in the dev
  container configurations: GitHub Codespaces does not support them. Do not
  hard-code `/workspace` in scripts or tasks; use `${workspaceFolder}`.
* Documentation tools (Sphinx, Graphviz) live in `docs/site/Dockerfile`, not
  in the firmware image (section 6).

---

# 6. Docker Image Size

Keep the Docker image small.

Only install dependencies required for Zephyr firmware development.

Do not install:

* Libero SoC
* SoftConsole
* FPGA synthesis tools
* FPGA programming tools
* unrelated compiler toolchains
* GUI applications
* unnecessary development packages

Use:

```text
debian:bookworm-slim
```

or another explicitly pinned minimal base image.

Clean package-manager caches after installation.

---

# 7. Microchip Licenses

Microchip licenses must never be stored in:

* Git
* GitHub
* Docker images
* Dockerfiles
* CI artifacts
* `.devcontainer`
* project configuration
* public container registries

Do not add license server credentials to environment files committed to Git.

Do not attempt to install or configure Libero SoC inside the firmware container.

If a task requires Libero SoC, treat it as a host-side workflow.

---

# 8. ccache

The project uses:

```text
ccache
```

The cache directory is:

```text
/ccache
```

and should normally be persisted from the host:

```text
.ccache/
```

Do not commit `.ccache/`.

The cache is an optimization only.

Never rely on cached files for correctness.

If build behavior appears inconsistent, perform a pristine build before investigating further:

```bash
west build \
    -p always \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

If necessary, clear the cache:

```bash
ccache --clear
```

---

# 9. Build Directory

Generated build output belongs in:

```text
build/
```

Do not commit the build directory.

A normal build is:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

A pristine build is:

```bash
west build \
    -p always \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

---

# 10. When to Use a Pristine Build

Recommend a pristine build after changes to:

* `prj.conf`
* Kconfig configuration
* DeviceTree overlays
* board configuration
* CMake configuration
* Zephyr version
* toolchain version

For ordinary C/C++ source changes, a normal incremental build is preferred.

---

# 11. DeviceTree

DeviceTree configuration is hardware-specific.

Before modifying a DeviceTree overlay:

1. inspect the existing board configuration;
2. identify the relevant peripheral;
3. preserve existing compatible nodes and aliases unless there is a reason to change them;
4. verify generated DeviceTree output after the build.

Do not invent peripheral addresses, interrupts, clocks, or pin mappings.

If hardware information is missing, ask for the relevant Libero/MSS configuration instead of guessing.

---

# 12. Kconfig

Application configuration belongs primarily in:

```text
prj.conf
```

Before adding a Kconfig option:

1. verify that the symbol exists in the selected Zephyr revision;
2. understand its dependencies;
3. avoid enabling unnecessary subsystems;
4. keep configuration minimal.

Do not copy large generic Zephyr configurations into `prj.conf`.

---

# 13. west

Use `west` for Zephyr workspace management.

Typical initialization:

```bash
west init -l .
west update
```

Use:

```bash
west build
```

for firmware builds.

Do not replace the Zephyr build process with an unrelated CMake invocation unless required.

When changing Zephyr dependencies, update `west.yml` intentionally and verify the resulting dependency graph.

---

# 14. Build Artifacts

Important artifacts normally appear under:

```text
build/zephyr/
```

Expected artifacts include:

```text
zephyr.elf
zephyr.hex
zephyr.bin
```

Use:

```text
zephyr.elf
```

for debugging.

Use:

```text
zephyr.hex
zephyr.bin
```

when a programming workflow requires those formats.

Do not assume that HEX or BIN can be programmed directly into SmartFusion2 without considering the hardware/eNVM configuration.

---

# 15. Libero and Firmware Integration

Zephyr firmware and Libero hardware configuration are related but separate.

The firmware may depend on hardware assumptions such as:

* clock configuration
* peripheral availability
* memory layout
* MSS configuration
* interrupt routing
* pin configuration

If a firmware change requires hardware changes, clearly identify the dependency.

Do not silently modify Libero-related assumptions without evidence from the hardware design.

---

# 16. VS Code

The recommended development environment is:

```text
VS Code
    +
Dev Containers
    +
repository Dockerfile
```

The workspace should be mounted as:

```text
/workspace
```

The Zephyr SDK should already exist inside the container.

Do not install another Zephyr SDK through VS Code unless explicitly requested.

VS Code should use:

```text
build/compile_commands.json
```

for C/C++ IntelliSense when available.

---

# 17. CI/CD

CI should use the same Dockerfile as local development.

Preferred flow:

```text
Git
 |
 v
Docker image
 |
 v
west update
 |
 v
west build
 |
 +-- zephyr.elf
 +-- zephyr.hex
 +-- zephyr.bin
```

CI should not require Microchip Libero when the pipeline is only building Zephyr firmware.

Workflows of this repository (`.github/workflows`):

* `container.yml`: builds the image, builds the firmware in it
  (`bash .vscode/ensure-west-workspace.sh`, `west build`), uploads the
  firmware as artifact, pushes the image to ghcr.io for a new tag.
* `docs.yml`: builds the web page (`docs/site`, `sphinx-build -W`) with
  `docs/site/Dockerfile` and deploys it to GitHub Pages. Pages under
  `docs/site/generated/` are copies made at build time; edit the originals.
  A Markdown link to a file that is not a page becomes a GitHub link; a broken
  heading anchor fails the build.

Do not put Microchip license files into CI unless a separate hardware-generation pipeline explicitly requires them.

---

# 18. Safe Change Procedure

Before making significant changes:

1. inspect the existing repository structure;
2. inspect `Dockerfile`;
3. inspect `west.yml`;
4. inspect `prj.conf`;
5. inspect DeviceTree overlays;
6. determine whether the change affects only firmware or also hardware;
7. preserve version pinning;
8. make the smallest appropriate change;
9. perform a build;
10. perform a pristine build if configuration changed;
11. report any assumptions.

Do not rewrite configuration files unnecessarily.

---

# 19. Dependency Changes

When adding a dependency:

* prefer an existing system package;
* avoid unnecessary Python packages;
* pin Python dependencies where practical;
* avoid downloading arbitrary binaries;
* prefer official upstream release artifacts;
* verify checksums for critical downloaded toolchains;
* keep the Docker image reproducible.

Do not add network-dependent installation steps that are unnecessary at runtime.

---

# 20. Security

Never commit:

* passwords
* access tokens
* SSH private keys
* Microchip license files
* license server credentials
* proprietary binaries
* generated credentials

Use environment variables, secret managers, or host-side configuration when credentials are genuinely required.

Do not expose secrets through Docker image layers.

---

# 21. Troubleshooting Priority

When a build fails, use this order:

### 1. Check the board

```bash
west boards | grep m2s010
```

### 2. Check Zephyr

```bash
west --version
```

### 3. Check the compiler

```bash
arm-zephyr-eabi-gcc --version
```

### 4. Check the SDK

```bash
ls /opt/zephyr-sdk
```

### 5. Check the workspace

```bash
west list
```

### 6. Perform a pristine build

```bash
west build \
    -p always \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

### 7. Inspect generated files

Check:

```text
build/zephyr/
build/compile_commands.json
```

Do not immediately change tool versions to solve a build problem.

---

# 22. Documentation

When modifying the project architecture, update:

```text
README.md
```

When modifying agent/development rules, update:

```text
.agents/skills/zephyr-smartfusion2/SKILL.md
```

Keep the README focused on human usage.

Keep this skill focused on engineering rules and agent behavior.

Do not duplicate the entire README here.

Board-specific facts about the USB host link through the kit's PIC32, the
console UART, MMUART bit rates and MSS SPI live in:

```text
.agents/skills/hello-fpga-kit-uart-spi/SKILL.md
```

Read it before changing UART, console or SPI configuration.

---

# 23. Definition of Done

A firmware change is considered complete when:

* the source compiles successfully;
* the correct board target is used;
* no unintended toolchain changes were introduced;
* `west` dependencies are consistent;
* configuration changes have been validated;
* a pristine build succeeds when required;
* generated artifacts are available;
* no secrets or licenses were added to the repository;
* documentation is updated when behavior or workflow changes.

For hardware-dependent changes, also validate the firmware on the M2S Hello FPGA Kit whenever hardware access is available.

---

# 24. Default Build Command

Unless the task explicitly requires another configuration, use:

```bash
west build \
    -b m2s_hello_fpga_kit/m2s010 \
    -d build
```

The default architecture is:

```text
Microchip SmartFusion2 M2S010
        |
        v
ARM Cortex-M3
        |
        v
Zephyr RTOS
        |
        v
Zephyr SDK / arm-zephyr-eabi
```

The default development environment is:

```text
VS Code
   |
   v
Dev Container
   |
   v
Repository Dockerfile
```

The default hardware-development boundary is:

```text
Zephyr firmware -> Docker

Libero SoC       -> Host
Microchip license -> Host
```

Always preserve this separation unless the project requirements explicitly change.
