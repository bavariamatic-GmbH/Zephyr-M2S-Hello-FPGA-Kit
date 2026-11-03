/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Helpers shared by the "hk" shell commands.
 */

#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <zephyr/sys/util.h>

#include "hk_util.h"

static char hexline[2U * HK_HEX_MAX + 1U];

bool hk_parse_u32(const char *s, uint32_t *out)
{
	char *end;
	unsigned long v = strtoul(s, &end, 0);

	if ((end == s) || (*end != '\0')) {
		return false;
	}
	*out = (uint32_t)v;
	return true;
}

static int hexval(char c)
{
	if ((c >= '0') && (c <= '9')) {
		return c - '0';
	}
	if ((c >= 'a') && (c <= 'f')) {
		return c - 'a' + 10;
	}
	if ((c >= 'A') && (c <= 'F')) {
		return c - 'A' + 10;
	}
	return -1;
}

int hk_parse_hex(size_t argc, char **argv, uint8_t *out, size_t max)
{
	size_t n = 0;

	for (size_t i = 0; i < argc; i++) {
		const char *s = argv[i];
		size_t len = strlen(s);

		if ((len >= 2U) && (s[0] == '0') && ((s[1] == 'x') || (s[1] == 'X'))) {
			s += 2;
			len -= 2U;
		}
		if ((len == 0U) || ((len % 2U) != 0U)) {
			return -EINVAL;
		}
		for (size_t j = 0; j < len; j += 2U) {
			int hi = hexval(s[j]);
			int lo = hexval(s[j + 1U]);

			if ((hi < 0) || (lo < 0) || (n >= max)) {
				return -EINVAL;
			}
			out[n++] = (uint8_t)((hi << 4) | lo);
		}
	}
	return (int)n;
}

const char *hk_to_hex(const uint8_t *data, size_t len)
{
	static const char digits[] = "0123456789abcdef";
	size_t n = MIN(len, (size_t)HK_HEX_MAX);

	for (size_t i = 0; i < n; i++) {
		hexline[2U * i] = digits[data[i] >> 4];
		hexline[2U * i + 1U] = digits[data[i] & 0x0FU];
	}
	hexline[2U * n] = '\0';
	return hexline;
}
