/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Raw SPI transfers on MSS SPI_0, SS0. Shows the Zephyr SPI API:
 * struct spi_config, struct spi_buf / spi_buf_set and spi_transceive().
 * The demo transfer comes from the example apps/03_demo_spi_raw_cs1.
 *
 * Notes on the MSS SPI driver (drivers/spi/spi_mchp_mss.c, Zephyr 4.5):
 *  - frequency: PCLK = 50 MHz is divided by 2 * (CLK_GEN + 1), CLK_GEN 1..15
 *    (12.5 MHz .. 1.5625 MHz). A request below 50 MHz / 30 = 1.67 MHz (such
 *    as the 1 MHz of the original example) falls back to a 25 MHz SCK.
 *    2 MHz gives 50 MHz / 28 = 1.79 MHz.
 *  - peripheral: SS line of MSS SPI_0. The Libero design routes only
 *    SPI_0_SS0 (Arduino D10, ball M10), so SS1 of the original example
 *    reaches no pin.
 *  - the driver clocks as many bytes as the TX buffer holds, so TX and RX
 *    always have the same length here.
 */

#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/spi.h>

#include "console_out.h"
#include "spi_raw.h"

#define SPI_RAW_SS 0U /* SPI_0 slave select used by the Libero design */

#define DEMO_HZ   2000000U
#define DEMO_MODE 0U

static const struct device *const spi0 = DEVICE_DT_GET(DT_NODELABEL(spi0));

bool spi_raw_ready(void)
{
	return device_is_ready(spi0);
}

int spi_raw_transfer(uint32_t hz, uint8_t mode, const uint8_t *tx, uint8_t *rx, size_t len)
{
	const struct spi_config cfg = {
		.frequency = hz,
		.operation = SPI_OP_MODE_CONTROLLER | SPI_TRANSFER_MSB | SPI_WORD_SET(8) |
			     ((mode & 2U) ? SPI_MODE_CPOL : 0U) |
			     ((mode & 1U) ? SPI_MODE_CPHA : 0U),
		.peripheral = SPI_RAW_SS,
	};
	const struct spi_buf tx_buf = {.buf = (void *)tx, .len = len};
	const struct spi_buf rx_buf = {.buf = rx, .len = len};
	const struct spi_buf_set tx_set = {.buffers = &tx_buf, .count = 1};
	const struct spi_buf_set rx_set = {.buffers = &rx_buf, .count = 1};

	if (!device_is_ready(spi0)) {
		return -ENODEV;
	}
	if (mode > 3U) {
		return -EINVAL;
	}

	return spi_transceive(spi0, &cfg, &tx_set, &rx_set);
}

void spi_raw_sample(void)
{
	static const uint8_t tx_data[2] = {0xAA, 0x55};
	uint8_t rx_data[2] = {0};
	int ret;

	ret = spi_raw_transfer(DEMO_HZ, DEMO_MODE, tx_data, rx_data, sizeof(tx_data));
	if (ret < 0) {
		console_out("SPI raw transfer failed: %d\n", ret);
	} else {
		console_out("TX: %02X %02X | RX: %02X %02X (CS=%u)\n", tx_data[0], tx_data[1],
			    rx_data[0], rx_data[1], SPI_RAW_SS);
	}
}
