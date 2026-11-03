/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Console output from threads other than the shell's.
 *
 * printk() writes to the console UART directly, past the shell. A printk()
 * from the main thread could therefore land in the middle of a line a shell
 * command is printing; observed 2026-11-03: the LTR-329 start-up message cut
 * "@ok info ... spi0=1 ..." into two lines, and the GUI lost the field.
 *
 * shell_vfprintf() takes the shell's TX mutex for the whole text, so it comes
 * out between two lines of a command reply at most, which the GUI ignores
 * (tools/hello_fpga_gui, only "@" lines are replies). The shell releases the
 * mutex while a command handler runs, so this does not wait for the command
 * to end. CONFIG_SHELL_TX_TIMEOUT_MS (prj.conf) is how long it waits for the
 * mutex before the text is dropped.
 */

#include <stdarg.h>
#include <zephyr/shell/shell.h>
#include <zephyr/shell/shell_uart.h>

#include "console_out.h"

void console_out(const char *fmt, ...)
{
	va_list args;

	va_start(args, fmt);
	shell_vfprintf(shell_backend_uart_get_ptr(), SHELL_NORMAL, fmt, args);
	va_end(args);
}
