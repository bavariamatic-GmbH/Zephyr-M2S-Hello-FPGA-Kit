/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * LTR-329ALS ambient light sensor on I2C_0 (address 0x29).
 *
 * Shows the Zephyr I2C API: i2c_configure(), i2c_reg_read_byte(),
 * i2c_reg_write_byte() and i2c_write_read() (register address, repeated
 * start, data). Code from the example apps/02_solution_i2c_driver.
 */

#include <errno.h>
#include <stdint.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/util.h>

#include "console_out.h"
#include "ltr329.h"

#define I2C0_NODE DT_NODELABEL(i2c0)

/* Sensor address and registers */
#define LTR329_I2C_ADDR            0x29
#define LTR55X_ALS_CONTR           0x80
#define LTR55X_MEAS_RATE           0x85
#define LTR55X_PART_ID             0x86
#define LTR55X_MANUFAC_ID          0x87
#define LTR55X_ALS_DATA_CH1_0      0x88
#define LTR55X_ALS_PS_STATUS       0x8C
#define LTR55X_ALS_MODE_ACTIVE     BIT(0)
#define LTR55X_ALS_DATA_READY_MASK BIT(2)

#define SENSOR_STARTUP_DELAY_MS 100

BUILD_ASSERT(DT_NODE_HAS_STATUS(I2C0_NODE, okay),
	     "i2c0 must be enabled by the board DTS or application overlay");

static const struct device *const i2c0 = DEVICE_DT_GET(I2C0_NODE);

static int ltr329_write_reg(uint8_t reg, uint8_t value)
{
	return i2c_reg_write_byte(i2c0, LTR329_I2C_ADDR, reg, value);
}

static int ltr329_read_reg(uint8_t reg, uint8_t *value)
{
	return i2c_reg_read_byte(i2c0, LTR329_I2C_ADDR, reg, value);
}

/* Read the four data registers CH1 low/high, CH0 low/high in one transfer */
static int ltr329_read_als(uint16_t *ch1, uint16_t *ch0)
{
	uint8_t start_reg = LTR55X_ALS_DATA_CH1_0;
	uint8_t buffer[4];
	int ret;

	ret = i2c_write_read(i2c0, LTR329_I2C_ADDR, &start_reg, sizeof(start_reg), buffer,
			     sizeof(buffer));
	if (ret < 0) {
		return ret;
	}

	*ch1 = (uint16_t)buffer[0] | ((uint16_t)buffer[1] << 8);
	*ch0 = (uint16_t)buffer[2] | ((uint16_t)buffer[3] << 8);

	return 0;
}

int ltr329_init(void)
{
	uint8_t part_id;
	uint8_t manufacturer_id;
	int ret;

	if (!device_is_ready(i2c0)) {
		console_out("I2C controller %s is not ready.\n", i2c0->name);
		return -ENODEV;
	}

	ret = i2c_configure(i2c0, I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_STANDARD));
	if (ret < 0) {
		console_out("i2c_configure() failed: %d\n", ret);
		return ret;
	}

	k_msleep(SENSOR_STARTUP_DELAY_MS);

	ret = ltr329_read_reg(LTR55X_PART_ID, &part_id);
	if (ret < 0) {
		console_out("PART_ID read failed from I2C address 0x%02x: %d\n", LTR329_I2C_ADDR,
			    ret);
		return ret;
	}

	ret = ltr329_read_reg(LTR55X_MANUFAC_ID, &manufacturer_id);
	if (ret < 0) {
		console_out("MANUFAC_ID read failed from I2C address 0x%02x: %d\n", LTR329_I2C_ADDR,
			    ret);
		return ret;
	}

	console_out("i2c0 ready: %s\n", i2c0->name);
	console_out("LTR-329ALS detected at 0x%02x, PART_ID=0x%02x, MANUFAC_ID=0x%02x\n",
		    LTR329_I2C_ADDR, part_id, manufacturer_id);

	ret = ltr329_write_reg(LTR55X_ALS_CONTR, LTR55X_ALS_MODE_ACTIVE);
	if (ret < 0) {
		console_out("ALS_CONTR write failed: %d\n", ret);
		return ret;
	}

	ret = ltr329_write_reg(LTR55X_MEAS_RATE, 0x03);
	if (ret < 0) {
		console_out("MEAS_RATE write failed: %d\n", ret);
		return ret;
	}

	return 0;
}

void ltr329_sample(void)
{
	uint16_t als_ch1;
	uint16_t als_ch0;
	uint8_t status;
	int ret;

	ret = ltr329_read_reg(LTR55X_ALS_PS_STATUS, &status);
	if (ret < 0) {
		console_out("ALS status read failed: %d\n", ret);
		return;
	}

	if ((status & LTR55X_ALS_DATA_READY_MASK) == 0U) {
		console_out("ALS data not ready yet, status=0x%02x\n", status);
		return;
	}

	ret = ltr329_read_als(&als_ch1, &als_ch0);
	if (ret < 0) {
		console_out("ALS channel read failed: %d\n", ret);
		return;
	}

	console_out("LTR-329ALS raw data: CH0=%u CH1=%u status=0x%02x\n", als_ch0, als_ch1, status);
}
