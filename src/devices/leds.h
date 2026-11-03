/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Debug LEDs LD1-LD3 (devicetree aliases led0..led2): on, off, blink.
 */

#ifndef LEDS_H_
#define LEDS_H_

#include <stdint.h>

#define LEDS_COUNT 3U

enum led_mode {
	LED_MODE_OFF,
	LED_MODE_ON,
	LED_MODE_BLINK,
};

/** Configure the LED GPIOs (all off). Returns 0 or a negative errno. */
int leds_init(void);

/** True if LED idx (0..2) has a ready GPIO controller. */
bool leds_ready(unsigned int idx);

/**
 * Set LED idx (0..2) to off, on or blink. For blink, period_ms is the full
 * period (on + off), 20..10000 ms.
 */
int leds_set(unsigned int idx, enum led_mode mode, uint32_t period_ms);

/** Current mode and blink period of LED idx. */
void leds_get(unsigned int idx, enum led_mode *mode, uint32_t *period_ms);

#endif /* LEDS_H_ */
