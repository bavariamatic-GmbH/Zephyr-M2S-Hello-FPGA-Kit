/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * LTR-329ALS ambient light sensor on I2C_0 (address 0x29).
 * Code from the example apps/02_solution_i2c_driver.
 */

#ifndef LTR329_H_
#define LTR329_H_

/**
 * Configure i2c0 (standard speed), read PART_ID / MANUFAC_ID and start ALS
 * measurements. Prints the result on the console.
 *
 * @return 0 on success, negative errno if the bus or the sensor is missing.
 */
int ltr329_init(void);

/** Read the sensor once and print CH0 / CH1 (or the reason it failed). */
void ltr329_sample(void);

#endif /* LTR329_H_ */
