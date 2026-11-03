/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Why the firmware stays silent until the host sends a key
 * --------------------------------------------------------
 * On the Hello FPGA Kit the console UART (MMUART_0) is not connected to USB
 * directly but to the kit's PIC32, which bridges it to the PC. The PIC32
 * forwards data only after the PC has sent '&', and output from the
 * SmartFusion2 that arrives before that stops the PIC32 (information from the
 * author of the Zephyr board port: his original code waited for a key press
 * before printing). The upstream board image, which prints right after
 * reset, does not start on this kit for that reason.
 *
 * Therefore this firmware:
 *  - has no boot banner (CONFIG_BOOT_BANNER=n),
 *  - does not start the shell automatically (CONFIG_SHELL_AUTOSTART=n),
 *  - waits here for the first byte from the host, then starts the shell.
 * main() calls host_wait_for_key() before any output (console_out()).
 *
 * Shell API used: shell_backend_uart_get_ptr(), the transport's read() and
 * shell_start(). The shell UART backend is initialised at boot and buffers
 * received bytes even while the shell is not started.
 */

#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/shell/shell_uart.h>

#include "host_wait.h"

#define POLL_MS 10

void host_wait_for_key(void)
{
	const struct shell *sh = shell_backend_uart_get_ptr();
	uint8_t byte;
	size_t count = 0;

	/* Poll the shell backend's receive buffer until a byte arrives. */
	while (count == 0U) {
		(void)sh->iface->api->read(sh->iface, &byte, sizeof(byte), &count);
		if (count == 0U) {
			k_msleep(POLL_MS);
		}
	}

	/* Start the shell: drops the rest of the received bytes, prints the prompt. */
	(void)shell_start(sh);
}
