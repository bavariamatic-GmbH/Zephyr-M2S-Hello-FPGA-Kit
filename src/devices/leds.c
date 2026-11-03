/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Debug LEDs LD1-LD3: on, off and blink. Blinking runs from a delayable work
 * item per LED on the system work queue (GPIO calls outside ISR context).
 * Polarity comes from the devicetree (GPIO_ACTIVE_LOW in the board overlay),
 * so "1" always means LED on.
 */

#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

#include "leds.h"

#define LED_PERIOD_MIN_MS 20U
#define LED_PERIOD_MAX_MS 10000U

struct led_ctx {
	const struct gpio_dt_spec spec;
	struct k_work_delayable work;
	enum led_mode mode;
	uint32_t period_ms;
	bool level;
	bool ok;
};

static struct led_ctx leds[LEDS_COUNT] = {
	{.spec = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios)},
	{.spec = GPIO_DT_SPEC_GET(DT_ALIAS(led1), gpios)},
	{.spec = GPIO_DT_SPEC_GET(DT_ALIAS(led2), gpios)},
};

static K_MUTEX_DEFINE(leds_lock);

static void blink_handler(struct k_work *work)
{
	struct k_work_delayable *dwork = k_work_delayable_from_work(work);
	struct led_ctx *led = CONTAINER_OF(dwork, struct led_ctx, work);

	k_mutex_lock(&leds_lock, K_FOREVER);
	if (led->mode == LED_MODE_BLINK) {
		led->level = !led->level;
		(void)gpio_pin_set_dt(&led->spec, led->level);
		k_work_reschedule(&led->work, K_MSEC(led->period_ms / 2U));
	}
	k_mutex_unlock(&leds_lock);
}

int leds_init(void)
{
	int result = 0;

	for (unsigned int i = 0; i < LEDS_COUNT; i++) {
		struct led_ctx *led = &leds[i];

		k_work_init_delayable(&led->work, blink_handler);
		led->mode = LED_MODE_OFF;
		led->period_ms = 500U;
		led->ok = gpio_is_ready_dt(&led->spec) &&
			  (gpio_pin_configure_dt(&led->spec, GPIO_OUTPUT_INACTIVE) == 0);
		if (!led->ok) {
			result = -ENODEV;
		}
	}
	return result;
}

bool leds_ready(unsigned int idx)
{
	return (idx < LEDS_COUNT) && leds[idx].ok;
}

int leds_set(unsigned int idx, enum led_mode mode, uint32_t period_ms)
{
	struct led_ctx *led;
	int ret = 0;

	if (idx >= LEDS_COUNT) {
		return -EINVAL;
	}
	led = &leds[idx];
	if (!led->ok) {
		return -ENODEV;
	}
	if ((mode == LED_MODE_BLINK) &&
	    ((period_ms < LED_PERIOD_MIN_MS) || (period_ms > LED_PERIOD_MAX_MS))) {
		return -EINVAL;
	}

	/* Stop a running blink first; the handler checks the mode under the lock */
	(void)k_work_cancel_delayable(&led->work);

	k_mutex_lock(&leds_lock, K_FOREVER);
	led->mode = mode;
	switch (mode) {
	case LED_MODE_ON:
		led->level = true;
		ret = gpio_pin_set_dt(&led->spec, 1);
		break;
	case LED_MODE_BLINK:
		led->period_ms = period_ms;
		led->level = true;
		ret = gpio_pin_set_dt(&led->spec, 1);
		k_work_reschedule(&led->work, K_MSEC(period_ms / 2U));
		break;
	case LED_MODE_OFF:
	default:
		led->level = false;
		ret = gpio_pin_set_dt(&led->spec, 0);
		break;
	}
	k_mutex_unlock(&leds_lock);
	return ret;
}

void leds_get(unsigned int idx, enum led_mode *mode, uint32_t *period_ms)
{
	if (idx >= LEDS_COUNT) {
		*mode = LED_MODE_OFF;
		*period_ms = 0U;
		return;
	}
	k_mutex_lock(&leds_lock, K_FOREVER);
	*mode = leds[idx].mode;
	*period_ms = leds[idx].period_ms;
	k_mutex_unlock(&leds_lock);
}
