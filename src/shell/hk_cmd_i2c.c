/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * "hk i2c ..." shell commands: raw transfers on I2C_0 (Arduino SDA/SCL, J7-9 /
 * J7-10) for a logic analyzer. Shows the Zephyr I2C API: i2c_read(),
 * i2c_write(), i2c_write_read(), i2c_configure(). Reply protocol: hk_util.h.
 */

#include <errno.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/printk.h>

#include "hk_util.h"

static const struct device *const i2c0 = DEVICE_DT_GET(DT_NODELABEL(i2c0));

/*
 * A failed transfer with pull-ups ends in well under a millisecond (address
 * NACK at 52 kHz: 20 bit times = 0.4 ms; a NACK after 256 bytes: 45 ms).
 * Without pull-ups on SDA/SCL (the kit has none on the Arduino nets) the MSS
 * I2C needs about 190 ms per failed transfer (measured 2026-11-03, std and
 * fast speed alike), and a scan of back-to-back transfers then hangs the
 * firmware for good. Longer than this means: no pull-ups.
 */
#define HK_I2C_SLOW_MS 50

static uint8_t i2c_tx[HK_MAX_BYTES];
static uint8_t i2c_rx[HK_MAX_BYTES];

static bool i2c_check(const struct shell *sh, const char *cmd)
{
	if (!device_is_ready(i2c0)) {
		HK_ERR(sh, cmd, -ENODEV, "i2c0 not ready");
		return false;
	}
	return true;
}

/* Final error line of a failed transfer, with a hint when it was slow. */
static void i2c_fail(const struct shell *sh, const char *cmd, int ret, int64_t t0)
{
	int64_t ms = k_uptime_get() - t0;

	if (ms > HK_I2C_SLOW_MS) {
		shell_print(sh, "@err %s %d transfer failed after %d ms (no pull-ups on SDA/SCL?)",
			    cmd, ret, (int)ms);
	} else {
		HK_ERR(sh, cmd, ret, "transfer failed (NACK?)");
	}
}

/*
 * The MSS I2C driver rejects zero-length messages (i2c_mchp_mss.c), so a
 * device is probed with a one-byte read.
 *
 * A missing device answers with NACK at once (-EIO). If the controller gets
 * no interrupt at all (e.g. SCL or SDA held low), the driver waits
 * K_TICKS(1000) and returns -EAGAIN. A probe slower than HK_I2C_SLOW_MS means
 * missing pull-ups. The scan stops at the first timeout or slow probe instead
 * of going on through all 112 addresses.
 */
static int cmd_i2c_scan(const struct shell *sh, size_t argc, char **argv)
{
	char list[3U * 0x78U + 1U] = "";
	size_t pos = 0;
	uint8_t dummy;
	int64_t t0;
	int ms;
	int ret;

	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	if (!i2c_check(sh, "i2c scan")) {
		return -ENODEV;
	}
	for (uint16_t addr = 0x08; addr < 0x78; addr++) {
		t0 = k_uptime_get();
		ret = i2c_read(i2c0, &dummy, 1, addr);
		ms = (int)(k_uptime_get() - t0);
		if (ret == 0) {
			pos += snprintk(&list[pos], sizeof(list) - pos, " %02x", addr);
		} else if (ret == -EAGAIN) {
			shell_print(sh, "@err i2c scan %d bus timeout at %02x (SCL/SDA low? pull-ups?)",
				    ret, addr);
			return ret;
		} else if (ms > HK_I2C_SLOW_MS) {
			shell_print(sh, "@err i2c scan %d probe of %02x took %d ms: no pull-ups on "
				    "SDA/SCL? scan stopped", -ETIMEDOUT, addr, ms);
			return -ETIMEDOUT;
		}
	}
	shell_print(sh, "@ok i2c scan%s", list);
	return 0;
}

static int cmd_i2c_write(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t addr;
	int n;
	int64_t t0;
	int ret;

	if (!i2c_check(sh, "i2c write")) {
		return -ENODEV;
	}
	n = hk_parse_hex(argc - 2, &argv[2], i2c_tx, HK_MAX_BYTES);
	if (!hk_parse_u32(argv[1], &addr) || (addr > 0x7F) || (n <= 0)) {
		HK_ERR(sh, "i2c write", -EINVAL, "usage: write <addr> <hex>");
		return -EINVAL;
	}
	t0 = k_uptime_get();
	ret = i2c_write(i2c0, i2c_tx, n, (uint16_t)addr);
	if (ret < 0) {
		i2c_fail(sh, "i2c write", ret, t0);
		return ret;
	}
	shell_print(sh, "@ok i2c write addr=%02x n=%d", addr, n);
	return 0;
}

static int cmd_i2c_read(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t addr;
	uint32_t len;
	int64_t t0;
	int ret;

	ARG_UNUSED(argc);
	if (!i2c_check(sh, "i2c read")) {
		return -ENODEV;
	}
	if (!hk_parse_u32(argv[1], &addr) || (addr > 0x7F) || !hk_parse_u32(argv[2], &len) ||
	    (len == 0U) || (len > HK_MAX_BYTES)) {
		HK_ERR(sh, "i2c read", -EINVAL, "usage: read <addr> <n 1..256>");
		return -EINVAL;
	}
	t0 = k_uptime_get();
	ret = i2c_read(i2c0, i2c_rx, len, (uint16_t)addr);
	if (ret < 0) {
		i2c_fail(sh, "i2c read", ret, t0);
		return ret;
	}
	shell_print(sh, "@ok i2c read addr=%02x rx=%s", addr, hk_to_hex(i2c_rx, len));
	return 0;
}

/* Write bytes, repeated start, read n bytes (register read). */
static int cmd_i2c_wr(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t addr;
	uint32_t len;
	int n;
	int64_t t0;
	int ret;

	if (!i2c_check(sh, "i2c wr")) {
		return -ENODEV;
	}
	n = hk_parse_hex(argc - 3, &argv[3], i2c_tx, HK_MAX_BYTES);
	if (!hk_parse_u32(argv[1], &addr) || (addr > 0x7F) || !hk_parse_u32(argv[2], &len) ||
	    (len == 0U) || (len > HK_MAX_BYTES) || (n <= 0)) {
		HK_ERR(sh, "i2c wr", -EINVAL, "usage: wr <addr> <n> <hex>");
		return -EINVAL;
	}
	t0 = k_uptime_get();
	ret = i2c_write_read(i2c0, (uint16_t)addr, i2c_tx, n, i2c_rx, len);
	if (ret < 0) {
		i2c_fail(sh, "i2c wr", ret, t0);
		return ret;
	}
	shell_print(sh, "@ok i2c wr addr=%02x rx=%s", addr, hk_to_hex(i2c_rx, len));
	return 0;
}

static int cmd_i2c_speed(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t speed;
	int ret;

	ARG_UNUSED(argc);
	if (!i2c_check(sh, "i2c speed")) {
		return -ENODEV;
	}
	if (strcmp(argv[1], "std") == 0) {
		speed = I2C_SPEED_STANDARD;
	} else if (strcmp(argv[1], "fast") == 0) {
		speed = I2C_SPEED_FAST;
	} else {
		HK_ERR(sh, "i2c speed", -EINVAL, "use std|fast");
		return -EINVAL;
	}
	ret = i2c_configure(i2c0, I2C_MODE_CONTROLLER | I2C_SPEED_SET(speed));
	if (ret < 0) {
		HK_ERR(sh, "i2c speed", ret, "i2c_configure failed");
		return ret;
	}
	shell_print(sh, "@ok i2c speed %s", argv[1]);
	return 0;
}


SHELL_STATIC_SUBCMD_SET_CREATE(sub_i2c,
	SHELL_CMD_ARG(scan, NULL, "Probe 0x08-0x77 (1-byte read)", cmd_i2c_scan, 1, 0),
	SHELL_CMD_ARG(write, NULL, "write <addr> <hex>", cmd_i2c_write, 3, 16),
	SHELL_CMD_ARG(read, NULL, "read <addr> <n>", cmd_i2c_read, 3, 0),
	SHELL_CMD_ARG(wr, NULL, "wr <addr> <n> <hex>: write, restart, read", cmd_i2c_wr, 4, 16),
	SHELL_CMD_ARG(speed, NULL, "speed std|fast", cmd_i2c_speed, 2, 0),
	SHELL_SUBCMD_SET_END);

SHELL_SUBCMD_ADD((hk), i2c, &sub_i2c, "I2C_0 commands", NULL, 1, 0);
