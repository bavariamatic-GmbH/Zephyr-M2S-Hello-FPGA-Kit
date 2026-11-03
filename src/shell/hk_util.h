/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Helpers shared by the "hk" shell commands (shell/hk_cmd_*.c).
 *
 * Reply protocol (one command at a time, parsed by tools/hello_fpga_gui):
 *   - zero or more data lines:   "@data <addr8> <hex>"   (flash read)
 *   - exactly one final line:    "@ok <command> [key=value ...]"
 *                            or  "@err <command> <errno> <text>"
 * Byte strings are lowercase hex without separators.
 *
 * Arguments: numbers in decimal or with 0x prefix; byte strings as hex, one or
 * more tokens ("aa55" or "aa 55").
 */

#ifndef HK_UTIL_H_
#define HK_UTIL_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <zephyr/shell/shell.h>

#define HK_MAX_BYTES 256U  /* I2C / SPI / flash-write payload per command */
#define HK_HEX_MAX   1024U /* longest byte string printed by hk_to_hex() */

/** Final error line of a command: "@err <cmd> <errno> <text>" */
#define HK_ERR(sh, cmd, err, text) shell_print(sh, "@err %s %d %s", cmd, (int)(err), text)

/** Parse a decimal or 0x-prefixed number; false if s is not a number. */
bool hk_parse_u32(const char *s, uint32_t *out);

/**
 * Parse hex tokens argv[0..argc-1] into out (at most max bytes).
 * @return number of bytes, or -EINVAL
 */
int hk_parse_hex(size_t argc, char **argv, uint8_t *out, size_t max);

/** Format bytes as lowercase hex (static buffer, valid until the next call). */
const char *hk_to_hex(const uint8_t *data, size_t len);

#endif /* HK_UTIL_H_ */
