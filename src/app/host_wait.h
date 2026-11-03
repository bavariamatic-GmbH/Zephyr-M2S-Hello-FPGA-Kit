/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Start-up handshake with the host on the console UART (see host_wait.c).
 */

#ifndef HOST_WAIT_H_
#define HOST_WAIT_H_

/**
 * Block until the host has sent at least one byte (any key in a terminal,
 * the GUI sends a newline), then start the shell.
 * Nothing is written to the console UART before this returns.
 */
void host_wait_for_key(void);

#endif /* HOST_WAIT_H_ */
