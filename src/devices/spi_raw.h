/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Raw SPI transfers on MSS SPI_0, slave select SS0 (Arduino header J7:
 * SCK D13, MOSI D11, MISO D12, SS D10) - for a logic analyzer.
 */

#ifndef SPI_RAW_H_
#define SPI_RAW_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/** True if the SPI_0 controller is ready. */
bool spi_raw_ready(void);

/**
 * Full-duplex transfer of len bytes on SPI_0, SS0.
 *
 * @param hz    requested SCK (the MSS SPI driver rounds it, see README)
 * @param mode  SPI mode 0..3 (bit 1 = CPOL, bit 0 = CPHA)
 * @param tx    bytes to send
 * @param rx    received bytes, same length as tx
 * @return 0 or a negative errno
 */
int spi_raw_transfer(uint32_t hz, uint8_t mode, const uint8_t *tx, uint8_t *rx, size_t len);

/** Demo of the example 03: send AA 55 at 2 MHz, mode 0, print TX/RX. */
void spi_raw_sample(void);

#endif /* SPI_RAW_H_ */
