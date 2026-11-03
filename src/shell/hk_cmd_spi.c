/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * "hk spi ..." shell commands: raw transfers on SPI_0, SS0 (Arduino header J7:
 * SCK D13, MOSI D11, MISO D12, SS D10) for a logic analyzer, using
 * devices/spi_raw.c. Reply protocol: hk_util.h.
 */

#include <errno.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>

#include "hk_util.h"
#include "spi_raw.h"

static uint8_t spi_tx[HK_MAX_BYTES];
static uint8_t spi_rx[HK_MAX_BYTES];

/* Parse "<hz> <mode 0-3>"; false if invalid. */
static bool parse_hz_mode(const char *hz_s, const char *mode_s, uint32_t *hz, uint8_t *mode)
{
	uint32_t m;

	if (!hk_parse_u32(hz_s, hz) || (*hz == 0U) || !hk_parse_u32(mode_s, &m) || (m > 3U)) {
		return false;
	}
	*mode = (uint8_t)m;
	return true;
}

/* hk spi xfer <hz> <mode 0-3> <hex...> */
static int cmd_spi_xfer(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t hz;
	uint8_t mode;
	int n;
	int ret;

	if (!spi_raw_ready()) {
		HK_ERR(sh, "spi xfer", -ENODEV, "spi0 not ready");
		return -ENODEV;
	}
	n = hk_parse_hex(argc - 3, &argv[3], spi_tx, HK_MAX_BYTES);
	if (!parse_hz_mode(argv[1], argv[2], &hz, &mode) || (n <= 0)) {
		HK_ERR(sh, "spi xfer", -EINVAL, "usage: xfer <hz> <mode 0-3> <hex>");
		return -EINVAL;
	}
	ret = spi_raw_transfer(hz, mode, spi_tx, spi_rx, n);
	if (ret < 0) {
		HK_ERR(sh, "spi xfer", ret, "spi_transceive failed");
		return ret;
	}
	shell_print(sh, "@ok spi xfer hz=%u mode=%s n=%d rx=%s", hz, argv[2], n,
		    hk_to_hex(spi_rx, n));
	return 0;
}

/* hk spi repeat <hz> <mode> <count 1-1000> <period_ms> <hex...> (analyzer bursts) */
static int cmd_spi_repeat(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t hz;
	uint8_t mode;
	uint32_t count;
	uint32_t period;
	uint32_t done;
	int n;
	int ret = 0;

	if (!spi_raw_ready()) {
		HK_ERR(sh, "spi repeat", -ENODEV, "spi0 not ready");
		return -ENODEV;
	}
	n = hk_parse_hex(argc - 5, &argv[5], spi_tx, HK_MAX_BYTES);
	if (!parse_hz_mode(argv[1], argv[2], &hz, &mode) || !hk_parse_u32(argv[3], &count) ||
	    (count == 0U) || (count > 1000U) || !hk_parse_u32(argv[4], &period) ||
	    (period > 10000U) || (n <= 0)) {
		HK_ERR(sh, "spi repeat", -EINVAL,
		       "usage: repeat <hz> <mode> <count 1-1000> <period_ms> <hex>");
		return -EINVAL;
	}
	for (done = 0; done < count; done++) {
		ret = spi_raw_transfer(hz, mode, spi_tx, spi_rx, n);
		if (ret < 0) {
			break;
		}
		if (period > 0U) {
			k_msleep(period);
		}
	}
	if (ret < 0) {
		HK_ERR(sh, "spi repeat", ret, "spi_transceive failed");
		return ret;
	}
	shell_print(sh, "@ok spi repeat count=%u n=%d rx=%s", done, n, hk_to_hex(spi_rx, n));
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_spi,
	SHELL_CMD_ARG(xfer, NULL, "xfer <hz> <mode 0-3> <hex> (spi0, SS0)", cmd_spi_xfer, 4, 16),
	SHELL_CMD_ARG(repeat, NULL, "repeat <hz> <mode> <count> <period_ms> <hex>",
		      cmd_spi_repeat, 6, 16),
	SHELL_SUBCMD_SET_END);

SHELL_SUBCMD_ADD((hk), spi, &sub_spi, "SPI_0 (SS0) commands", NULL, 1, 0);
