/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Periodic demo: once a second read the LTR-329ALS and run one SPI transfer.
 */

#ifndef DEMO_LOOP_H_
#define DEMO_LOOP_H_

#include <stdbool.h>

/** Switch the periodic output on or off (shell: "hk loop on|off"). */
void demo_loop_set(bool on);

/** True if the periodic output is on (it is on after reset). */
bool demo_loop_get(void);

/**
 * Run the demo forever. sensor_ok / spi_ok tell which parts are available.
 * Does not return.
 */
void demo_loop_run(bool sensor_ok, bool spi_ok);

#endif /* DEMO_LOOP_H_ */
