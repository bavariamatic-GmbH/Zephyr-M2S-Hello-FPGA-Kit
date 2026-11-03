/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Periodic demo: once a second read the LTR-329ALS (I2C) and send AA 55 on
 * SPI_0, printing both results on the console. The output can be switched
 * off with "hk loop off" so it does not mix with the replies to the GUI.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include "demo_loop.h"
#include "ltr329.h"
#include "spi_raw.h"

#define SAMPLE_PERIOD_MS 1000

static atomic_t loop_enabled = ATOMIC_INIT(1);

void demo_loop_set(bool on)
{
	atomic_set(&loop_enabled, on ? 1 : 0);
}

bool demo_loop_get(void)
{
	return atomic_get(&loop_enabled) != 0;
}

void demo_loop_run(bool sensor_ok, bool spi_ok)
{
	while (true) {
		if (demo_loop_get()) {
			if (sensor_ok) {
				ltr329_sample();
			}
			if (spi_ok) {
				spi_raw_sample();
			}
		}
		k_msleep(SAMPLE_PERIOD_MS);
	}
}
