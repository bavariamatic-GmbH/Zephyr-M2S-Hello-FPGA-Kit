/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * "hk flash ..." shell commands for the SPI flash U8 (SST26VF064B on SPI_1,
 * SS0), using devices/sst26.c. Reply protocol: hk_util.h.
 */

#include <errno.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/util.h>

#include "hk_util.h"
#include "sst26.h"

#define HK_FLASH_MAX_RD 1024U /* flash read per command */
#define HK_DATA_LINE    32U   /* bytes per @data line */

BUILD_ASSERT(HK_FLASH_MAX_RD <= HK_HEX_MAX, "hk_to_hex() buffer too small");

static uint8_t flash_rd[HK_FLASH_MAX_RD];
static uint8_t flash_wr[HK_MAX_BYTES];

static bool flash_check(const struct shell *sh, const char *cmd)
{
	if (!sst26_ready()) {
		HK_ERR(sh, cmd, -ENODEV, "spi1 not ready");
		return false;
	}
	return true;
}

static int cmd_flash_id(const struct shell *sh, size_t argc, char **argv)
{
	uint8_t id[3];
	int ret;

	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	if (!flash_check(sh, "flash id")) {
		return -ENODEV;
	}
	ret = sst26_read_jedec_id(id);
	if (ret < 0) {
		HK_ERR(sh, "flash id", ret, "transfer failed");
		return ret;
	}
	shell_print(sh, "@ok flash id jedec=%02x%02x%02x", id[0], id[1], id[2]);
	return 0;
}

static int cmd_flash_status(const struct shell *sh, size_t argc, char **argv)
{
	uint8_t sr;
	uint8_t cr;
	int ret;

	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	if (!flash_check(sh, "flash status")) {
		return -ENODEV;
	}
	ret = sst26_read_status(&sr);
	if (ret == 0) {
		ret = sst26_read_config(&cr);
	}
	if (ret < 0) {
		HK_ERR(sh, "flash status", ret, "transfer failed");
		return ret;
	}
	shell_print(sh, "@ok flash status sr=%02x cr=%02x", sr, cr);
	return 0;
}

static int cmd_flash_unlock(const struct shell *sh, size_t argc, char **argv)
{
	int ret;

	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	if (!flash_check(sh, "flash unlock")) {
		return -ENODEV;
	}
	ret = sst26_unlock();
	if (ret < 0) {
		HK_ERR(sh, "flash unlock", ret, "WREN/ULBPR failed");
		return ret;
	}
	shell_print(sh, "@ok flash unlock");
	return 0;
}

static int cmd_flash_reset(const struct shell *sh, size_t argc, char **argv)
{
	int ret;

	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	if (!flash_check(sh, "flash reset")) {
		return -ENODEV;
	}
	ret = sst26_reset();
	if (ret < 0) {
		HK_ERR(sh, "flash reset", ret, "transfer failed");
		return ret;
	}
	shell_print(sh, "@ok flash reset");
	return 0;
}

static int cmd_flash_freq(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t hz;

	if (argc > 1) {
		if (!hk_parse_u32(argv[1], &hz) || (hz == 0U)) {
			HK_ERR(sh, "flash freq", -EINVAL, "usage: freq <hz>");
			return -EINVAL;
		}
		sst26_set_frequency(hz);
	}
	shell_print(sh, "@ok flash freq hz=%u", sst26_get_frequency());
	return 0;
}

/* hk flash read <addr> <len 1..1024> */
static int cmd_flash_read(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t addr;
	uint32_t len;
	int ret;

	ARG_UNUSED(argc);
	if (!flash_check(sh, "flash read")) {
		return -ENODEV;
	}
	if (!hk_parse_u32(argv[1], &addr) || !hk_parse_u32(argv[2], &len) || (len == 0U) ||
	    (len > HK_FLASH_MAX_RD)) {
		HK_ERR(sh, "flash read", -EINVAL, "usage: read <addr> <len 1..1024>");
		return -EINVAL;
	}
	ret = sst26_read(addr, flash_rd, len);
	if (ret < 0) {
		HK_ERR(sh, "flash read", ret, "read failed or out of range");
		return ret;
	}
	for (uint32_t off = 0; off < len; off += HK_DATA_LINE) {
		uint32_t n = MIN(HK_DATA_LINE, len - off);

		shell_print(sh, "@data %08x %s", addr + off, hk_to_hex(&flash_rd[off], n));
	}
	shell_print(sh, "@ok flash read addr=%08x len=%u", addr, len);
	return 0;
}

/* hk flash write <addr> <hex...> (erase the area first; 1 -> 0 only) */
static int cmd_flash_write(const struct shell *sh, size_t argc, char **argv)
{
	uint32_t addr;
	int n;
	int ret;

	if (!flash_check(sh, "flash write")) {
		return -ENODEV;
	}
	n = hk_parse_hex(argc - 2, &argv[2], flash_wr, HK_MAX_BYTES);
	if (!hk_parse_u32(argv[1], &addr) || (n <= 0)) {
		HK_ERR(sh, "flash write", -EINVAL, "usage: write <addr> <hex>");
		return -EINVAL;
	}
	ret = sst26_write(addr, flash_wr, n);
	if (ret < 0) {
		HK_ERR(sh, "flash write", ret, "program failed (locked? run unlock)");
		return ret;
	}
	shell_print(sh, "@ok flash write addr=%08x n=%d", addr, n);
	return 0;
}

/* hk flash erase sector|block <addr>  |  hk flash erase chip */
static int cmd_flash_erase(const struct shell *sh, size_t argc, char **argv)
{
	enum sst26_erase type;
	uint32_t addr = 0;
	int64_t t0;
	int ret;

	if (!flash_check(sh, "flash erase")) {
		return -ENODEV;
	}
	if (strcmp(argv[1], "sector") == 0) {
		type = SST26_ERASE_SECTOR;
	} else if (strcmp(argv[1], "block") == 0) {
		type = SST26_ERASE_BLOCK;
	} else if (strcmp(argv[1], "chip") == 0) {
		type = SST26_ERASE_CHIP;
	} else {
		HK_ERR(sh, "flash erase", -EINVAL, "use sector|block|chip");
		return -EINVAL;
	}
	if ((type != SST26_ERASE_CHIP) && ((argc < 3) || !hk_parse_u32(argv[2], &addr))) {
		HK_ERR(sh, "flash erase", -EINVAL, "usage: erase sector|block <addr>");
		return -EINVAL;
	}
	t0 = k_uptime_get();
	ret = sst26_erase(type, addr);
	if (ret < 0) {
		HK_ERR(sh, "flash erase", ret, "erase failed (locked? run unlock)");
		return ret;
	}
	shell_print(sh, "@ok flash erase %s addr=%08x ms=%d", argv[1], addr,
		    (int)(k_uptime_get() - t0));
	return 0;
}


SHELL_STATIC_SUBCMD_SET_CREATE(sub_flash,
	SHELL_CMD_ARG(id, NULL, "JEDEC ID (9Fh)", cmd_flash_id, 1, 0),
	SHELL_CMD_ARG(status, NULL, "Status (05h) and configuration (35h) registers",
		      cmd_flash_status, 1, 0),
	SHELL_CMD_ARG(unlock, NULL, "WREN + ULBPR (98h): remove block protection",
		      cmd_flash_unlock, 1, 0),
	SHELL_CMD_ARG(reset, NULL, "RSTEN + RST (66h, 99h)", cmd_flash_reset, 1, 0),
	SHELL_CMD_ARG(freq, NULL, "freq [hz]: SCK request for spi1", cmd_flash_freq, 1, 1),
	SHELL_CMD_ARG(read, NULL, "read <addr> <len 1..1024>", cmd_flash_read, 3, 0),
	SHELL_CMD_ARG(write, NULL, "write <addr> <hex> (page program)", cmd_flash_write, 3, 16),
	SHELL_CMD_ARG(erase, NULL, "erase sector|block <addr> | erase chip", cmd_flash_erase, 2,
		      1),
	SHELL_SUBCMD_SET_END);

SHELL_SUBCMD_ADD((hk), flash, &sub_flash, "SPI flash U8 (SST26VF064B on SPI_1)", NULL, 1, 0);
