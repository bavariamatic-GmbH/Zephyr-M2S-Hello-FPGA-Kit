# SPDX-License-Identifier: Apache-2.0
#
# I2C + SPI demo for the M2S Hello FPGA Kit (structure: see README.md).
#
#   src/main.c        start-up: initialise the modules, run the demo loop
#   src/app/          wait for the host, demo loop (LTR-329 + raw SPI every second)
#   src/devices/      one module per device: LTR-329 (I2C_0), raw SPI_0,
#                     SPI flash U8 (SPI_1), debug LEDs LD1-LD3
#   src/platform/     SmartFusion2 specifics (MMUART fractional baud divisor),
#                     console output next to the shell
#   src/shell/        "hk ..." shell commands for tools/hello_fpga_gui
#
# Zephyr picks up boards/m2s_hello_fpga_kit_m2s010.overlay automatically.

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(i2c_spi_demo LANGUAGES C)

target_include_directories(app PRIVATE
	src/app
	src/devices
	src/platform
	src/shell
)

target_sources(app PRIVATE
	src/main.c

	src/app/demo_loop.c
	src/app/host_wait.c

	src/devices/ltr329.c
	src/devices/spi_raw.c
	src/devices/sst26.c
	src/devices/leds.c

	src/platform/console_out.c
	src/platform/sf2_mmuart.c

	src/shell/hk_util.c
	src/shell/hk_shell.c
	src/shell/hk_cmd_i2c.c
	src/shell/hk_cmd_spi.c
	src/shell/hk_cmd_flash.c
	src/shell/hk_cmd_led.c
)
