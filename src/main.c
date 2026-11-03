/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * I2C + SPI demo for the M2S Hello FPGA Kit (SmartFusion2 M2S010, Zephyr).
 *
 * Project structure:
 *   main.c               start-up: initialise the modules, run the demo
 *   app/host_wait.c      stay silent until the host sends a key (PIC32!)
 *   app/demo_loop.c      periodic demo (LTR-329 + SPI), "hk loop on|off"
 *   devices/ltr329.c     LTR-329ALS light sensor on I2C_0 (example 02)
 *   devices/spi_raw.c    raw transfers on SPI_0 SS0 (example 03)
 *   devices/sst26.c      SPI flash U8 SST26VF064B on SPI_1
 *   devices/leds.c       debug LEDs LD1-LD3 on MSS GPIO_0..2
 *   platform/sf2_mmuart.c console UART at 230400 bit/s (PIC32 USB bridge)
 *   shell/hk_*.c         shell commands "hk ..." used by tools/hello_fpga_gui
 *
 * Hardware: Libero design from Libero-Microchip-Hello-FPGA-Kit, pins in
 * docs/libero-hello-fpga-vf256.md.
 */

#include <stdbool.h>
#include <zephyr/kernel.h>

#include "console_out.h"
#include "demo_loop.h"
#include "host_wait.h"
#include "leds.h"
#include "ltr329.h"
#include "spi_raw.h"

int main(void)
{
	bool sensor_ok;
	bool spi_ok;

	/* Nothing may be sent to the PIC32 before the host is there */
	host_wait_for_key();

	console_out("I2C + SPI demo: %s\n", CONFIG_BOARD_TARGET);

	/* Debug LEDs LD1-LD3 for "hk led" (all off) */
	if (leds_init() < 0) {
		console_out("LEDs: not all LED GPIOs are ready\n");
	}

	/* I2C: light sensor LTR-329ALS */
	sensor_ok = (ltr329_init() == 0);

	/* SPI_0 for the raw transfers */
	spi_ok = spi_raw_ready();
	if (!spi_ok) {
		console_out("SPI bus is not ready\n");
	}

	/* The shell ("hk ...") runs in its own thread; main runs the demo */
	demo_loop_run(sensor_ok, spi_ok);

	return 0;
}
