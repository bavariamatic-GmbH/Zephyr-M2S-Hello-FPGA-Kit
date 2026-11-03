/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Console output for messages that do not come from a shell command (start-up
 * messages, demo loop). See console_out.c for why printk() is not used.
 */

#ifndef CONSOLE_OUT_H_
#define CONSOLE_OUT_H_

/**
 * printk()-like output through the UART shell: the text goes out as a whole,
 * never in the middle of a line that a shell command is printing.
 * Thread context only, after host_wait_for_key() has started the shell.
 */
void console_out(const char *fmt, ...);

#endif /* CONSOLE_OUT_H_ */
