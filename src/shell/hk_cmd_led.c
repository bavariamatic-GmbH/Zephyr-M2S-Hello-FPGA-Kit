/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * "hk led ..." shell commands for the debug LEDs LD1-LD3 (MSS GPIO_0..2),
 * using devices/leds.c. Reply protocol: hk_util.h.
 */

#include <errno.h>
#include <string.h>
#include <zephyr/shell/shell.h>

#include "hk_util.h"
#include "leds.h"

static const char *led_mode_name(enum led_mode mode)
{
	return (mode == LED_MODE_ON) ? "on" : (mode == LED_MODE_BLINK) ? "blink" : "off";
}

/* hk led status */
static int cmd_led_status(const struct shell *sh, size_t argc, char **argv)
{
	enum led_mode m[LEDS_COUNT];
	uint32_t p[LEDS_COUNT];

	ARG_UNUSED(argc);
	ARG_UNUSED(argv);
	for (unsigned int i = 0; i < LEDS_COUNT; i++) {
		leds_get(i, &m[i], &p[i]);
	}
	shell_print(sh, "@ok led status led0=%s:%u led1=%s:%u led2=%s:%u ready=%d%d%d",
		    led_mode_name(m[0]), p[0], led_mode_name(m[1]), p[1], led_mode_name(m[2]), p[2],
		    leds_ready(0), leds_ready(1), leds_ready(2));
	return 0;
}

/* hk led set <0|1|2|all> <on|off|blink> [period_ms] */
static int cmd_led_set(const struct shell *sh, size_t argc, char **argv)
{
	enum led_mode mode;
	uint32_t idx;
	uint32_t period = 500U;
	unsigned int first;
	unsigned int last;
	int ret = 0;

	if (strcmp(argv[2], "on") == 0) {
		mode = LED_MODE_ON;
	} else if (strcmp(argv[2], "off") == 0) {
		mode = LED_MODE_OFF;
	} else if (strcmp(argv[2], "blink") == 0) {
		mode = LED_MODE_BLINK;
	} else {
		HK_ERR(sh, "led set", -EINVAL, "use on|off|blink");
		return -EINVAL;
	}
	if ((argc > 3) && !hk_parse_u32(argv[3], &period)) {
		HK_ERR(sh, "led set", -EINVAL, "period_ms must be a number");
		return -EINVAL;
	}
	if (strcmp(argv[1], "all") == 0) {
		first = 0U;
		last = LEDS_COUNT - 1U;
	} else if (hk_parse_u32(argv[1], &idx) && (idx < LEDS_COUNT)) {
		first = idx;
		last = idx;
	} else {
		HK_ERR(sh, "led set", -EINVAL, "led must be 0, 1, 2 or all");
		return -EINVAL;
	}
	for (unsigned int i = first; i <= last; i++) {
		ret = leds_set(i, mode, period);
		if (ret < 0) {
			HK_ERR(sh, "led set", ret, "led not ready or period not 20..10000 ms");
			return ret;
		}
	}
	shell_print(sh, "@ok led set %s %s period=%u", argv[1], argv[2], period);
	return 0;
}


SHELL_STATIC_SUBCMD_SET_CREATE(sub_led,
	SHELL_CMD_ARG(status, NULL, "Mode of LD1-LD3 (led0-led2)", cmd_led_status, 1, 0),
	SHELL_CMD_ARG(set, NULL, "set <0|1|2|all> <on|off|blink> [period_ms 20-10000]",
		      cmd_led_set, 3, 1),
	SHELL_SUBCMD_SET_END);

SHELL_SUBCMD_ADD((hk), led, &sub_led, "Debug LEDs LD1-LD3 (MSS GPIO_0..2)", NULL, 1, 0);
