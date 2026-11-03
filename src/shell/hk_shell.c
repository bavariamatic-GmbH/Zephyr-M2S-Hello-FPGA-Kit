/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Root shell command "hk" for the Hello FPGA Kit test GUI (tools/hello_fpga_gui)
 * and the general subcommands ping, info, loop.
 *
 * The other subcommand groups add themselves to "hk" with SHELL_SUBCMD_ADD():
 *   hk i2c ...    shell/hk_cmd_i2c.c    (I2C_0)
 *   hk spi ...    shell/hk_cmd_spi.c    (SPI_0, SS0)
 *   hk flash ...  shell/hk_cmd_flash.c  (SPI flash U8 on SPI_1)
 *   hk led ...    shell/hk_cmd_led.c    (LD1-LD3)
 * Reply protocol: see hk_util.h.
 */

#include <errno.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/shell/shell.h>

#include "demo_loop.h"
#include "hk_util.h"
#include "spi_raw.h"
#include "sst26.h"

static const struct device *const i2c0 = DEVICE_DT_GET(DT_NODELABEL(i2c0));

/* hk ping */
static int cmd_ping(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	shell_print(sh, "@ok ping");
	return 0;
}

/* hk info */
static int cmd_info(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	shell_print(sh, "@ok info board=%s i2c0=%d spi0=%d spi1=%d loop=%d flash_hz=%u",
		    CONFIG_BOARD_TARGET, device_is_ready(i2c0), spi_raw_ready(), sst26_ready(),
		    demo_loop_get(), sst26_get_frequency());
	return 0;
}

/* hk loop [on|off] */
static int cmd_loop(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		if (strcmp(argv[1], "on") == 0) {
			demo_loop_set(true);
		} else if (strcmp(argv[1], "off") == 0) {
			demo_loop_set(false);
		} else {
			HK_ERR(sh, "loop", -EINVAL, "use on|off");
			return -EINVAL;
		}
	}
	shell_print(sh, "@ok loop %s", demo_loop_get() ? "on" : "off");
	return 0;
}

/* "hk" and its subcommand set; groups in other files are added to (hk) */
SHELL_SUBCMD_SET_CREATE(sub_hk, (hk));
SHELL_CMD_REGISTER(hk, &sub_hk, "Hello FPGA Kit test commands", NULL);

SHELL_SUBCMD_ADD((hk), ping, NULL, "Reply @ok ping", cmd_ping, 1, 0);
SHELL_SUBCMD_ADD((hk), info, NULL, "Board and controller state", cmd_info, 1, 0);
SHELL_SUBCMD_ADD((hk), loop, NULL, "loop [on|off]: periodic LTR-329 + SPI demo", cmd_loop, 1, 1);
