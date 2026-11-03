/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Minimal SST26VF064B (U8, 8 MB SPI flash) access on MSS SPI_1, SS0.
 *
 * Opcodes and behaviour from the SST26VF064B/064BA data sheet (DS20005119):
 *   9Fh JEDEC ID (BF 26 43), 05h RDSR, 35h RDCR, 06h WREN, 04h WRDI,
 *   03h Read (3 address bytes, no dummy, max 40 MHz), 02h Page Program
 *   (256-byte page), 20h Sector Erase (4 KB), D8h Block Erase (8/32/64 KB,
 *   depending on the address), C7h Chip Erase, 98h ULBPR (global block
 *   protection unlock, needs WREN first), 66h/99h reset enable/reset.
 * The device is write-protected after power-up: call sst26_unlock() before the
 * first program or erase.
 *
 * Not the Zephyr spi-nor driver: spi_mchp_mss.c clocks only as many bytes as
 * the TX buffers hold, while spi-nor reads with a short TX and a long RX. Every
 * transfer here therefore uses TX and RX buffers of the same length.
 */

#ifndef SST26_H_
#define SST26_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <zephyr/sys/util.h>

#define SST26_SIZE        (8U * 1024U * 1024U)
#define SST26_PAGE_SIZE   256U
#define SST26_SECTOR_SIZE 4096U

/* Status register bits */
#define SST26_SR_BUSY BIT(0)
#define SST26_SR_WEL  BIT(1)

enum sst26_erase {
	SST26_ERASE_SECTOR, /* 20h, 4 KB */
	SST26_ERASE_BLOCK,  /* D8h, 8/32/64 KB depending on the address */
	SST26_ERASE_CHIP,   /* C7h */
};

/** True if the SPI_1 controller is ready. */
bool sst26_ready(void);

/** Set the requested SCK frequency in Hz (MSS SPI driver rounds it, see README). */
void sst26_set_frequency(uint32_t hz);
uint32_t sst26_get_frequency(void);

int sst26_read_jedec_id(uint8_t id[3]);
int sst26_read_status(uint8_t *sr);
int sst26_read_config(uint8_t *cr);

/** WREN + ULBPR: remove the block protection of the whole array. */
int sst26_unlock(void);

/** Software reset: RSTEN (66h) followed by RST (99h). */
int sst26_reset(void);

/** Read len bytes from addr (03h, in chunks of SST26_PAGE_SIZE). */
int sst26_read(uint32_t addr, uint8_t *buf, size_t len);

/** Program len bytes at addr (02h), split at 256-byte page boundaries. */
int sst26_write(uint32_t addr, const uint8_t *buf, size_t len);

/** Erase the sector/block containing addr, or the whole chip. */
int sst26_erase(enum sst26_erase type, uint32_t addr);

#endif /* SST26_H_ */
