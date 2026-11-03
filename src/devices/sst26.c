/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * Minimal SST26VF064B access on MSS SPI_1, SS0. See sst26.h.
 */

#include <errno.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/util.h>

#include "sst26.h"

#define SST26_CMD_JEDEC_ID 0x9FU
#define SST26_CMD_RDSR     0x05U
#define SST26_CMD_RDCR     0x35U
#define SST26_CMD_WREN     0x06U
#define SST26_CMD_READ     0x03U
#define SST26_CMD_PP       0x02U
#define SST26_CMD_SE       0x20U
#define SST26_CMD_BE       0xD8U
#define SST26_CMD_CE       0xC7U
#define SST26_CMD_ULBPR    0x98U
#define SST26_CMD_RSTEN    0x66U
#define SST26_CMD_RST      0x99U

/*
 * Busy-wait limits. Data sheet maximum: sector/block erase 25 ms, chip erase
 * 50 ms; page program time is not taken from the data sheet here, so the same
 * generous limit is used. The limits only end a hung wait.
 */
#define SST26_TIMEOUT_PROGRAM_MS 100
#define SST26_TIMEOUT_ERASE_MS   200

/* Command + 3 address bytes + one page */
#define SST26_XFER_MAX (4U + SST26_PAGE_SIZE)

static const struct device *const spi1 = DEVICE_DT_GET(DT_NODELABEL(spi1));

static struct spi_config cfg = {
	.frequency = 2000000,
	.operation = SPI_OP_MODE_CONTROLLER | SPI_TRANSFER_MSB | SPI_WORD_SET(8),
	.peripheral = 0,
};

static uint8_t tx_buf[SST26_XFER_MAX];
static uint8_t rx_buf[SST26_XFER_MAX];
static K_MUTEX_DEFINE(sst26_lock);

bool sst26_ready(void)
{
	return device_is_ready(spi1);
}

void sst26_set_frequency(uint32_t hz)
{
	k_mutex_lock(&sst26_lock, K_FOREVER);
	cfg.frequency = hz;
	k_mutex_unlock(&sst26_lock);
}

uint32_t sst26_get_frequency(void)
{
	return cfg.frequency;
}

/* One transfer of len bytes; TX and RX have the same length (see sst26.h). */
static int xfer(size_t len)
{
	const struct spi_buf tb = {.buf = tx_buf, .len = len};
	const struct spi_buf rb = {.buf = rx_buf, .len = len};
	const struct spi_buf_set tx = {.buffers = &tb, .count = 1};
	const struct spi_buf_set rx = {.buffers = &rb, .count = 1};

	if (!device_is_ready(spi1)) {
		return -ENODEV;
	}

	return spi_transceive(spi1, &cfg, &tx, &rx);
}

static int cmd_only(uint8_t cmd)
{
	tx_buf[0] = cmd;
	return xfer(1);
}

static int read_reg(uint8_t cmd, uint8_t *val)
{
	int ret;

	tx_buf[0] = cmd;
	tx_buf[1] = 0x00;
	ret = xfer(2);
	if (ret == 0) {
		*val = rx_buf[1];
	}
	return ret;
}

static void put_addr(uint8_t cmd, uint32_t addr)
{
	tx_buf[0] = cmd;
	tx_buf[1] = (uint8_t)(addr >> 16);
	tx_buf[2] = (uint8_t)(addr >> 8);
	tx_buf[3] = (uint8_t)addr;
}

static int wait_ready(int timeout_ms)
{
	int64_t end = k_uptime_get() + timeout_ms;
	uint8_t sr;
	int ret;

	do {
		ret = read_reg(SST26_CMD_RDSR, &sr);
		if (ret < 0) {
			return ret;
		}
		if ((sr & SST26_SR_BUSY) == 0U) {
			return 0;
		}
		k_msleep(1);
	} while (k_uptime_get() < end);

	return -ETIMEDOUT;
}

static int write_enable(void)
{
	uint8_t sr;
	int ret;

	ret = cmd_only(SST26_CMD_WREN);
	if (ret < 0) {
		return ret;
	}
	ret = read_reg(SST26_CMD_RDSR, &sr);
	if (ret < 0) {
		return ret;
	}
	/* WEL not set: no answer on MISO or the device did not accept WREN */
	return (sr & SST26_SR_WEL) ? 0 : -EIO;
}

int sst26_read_jedec_id(uint8_t id[3])
{
	int ret;

	k_mutex_lock(&sst26_lock, K_FOREVER);
	memset(tx_buf, 0, 4);
	tx_buf[0] = SST26_CMD_JEDEC_ID;
	ret = xfer(4);
	if (ret == 0) {
		memcpy(id, &rx_buf[1], 3);
	}
	k_mutex_unlock(&sst26_lock);
	return ret;
}

int sst26_read_status(uint8_t *sr)
{
	int ret;

	k_mutex_lock(&sst26_lock, K_FOREVER);
	ret = read_reg(SST26_CMD_RDSR, sr);
	k_mutex_unlock(&sst26_lock);
	return ret;
}

int sst26_read_config(uint8_t *cr)
{
	int ret;

	k_mutex_lock(&sst26_lock, K_FOREVER);
	ret = read_reg(SST26_CMD_RDCR, cr);
	k_mutex_unlock(&sst26_lock);
	return ret;
}

int sst26_unlock(void)
{
	int ret;

	k_mutex_lock(&sst26_lock, K_FOREVER);
	ret = write_enable();
	if (ret == 0) {
		ret = cmd_only(SST26_CMD_ULBPR);
	}
	if (ret == 0) {
		ret = wait_ready(SST26_TIMEOUT_PROGRAM_MS);
	}
	k_mutex_unlock(&sst26_lock);
	return ret;
}

int sst26_reset(void)
{
	int ret;

	k_mutex_lock(&sst26_lock, K_FOREVER);
	ret = cmd_only(SST26_CMD_RSTEN);
	if (ret == 0) {
		ret = cmd_only(SST26_CMD_RST);
	}
	k_mutex_unlock(&sst26_lock);
	return ret;
}

int sst26_read(uint32_t addr, uint8_t *buf, size_t len)
{
	int ret = 0;

	if ((addr >= SST26_SIZE) || (len > SST26_SIZE - addr)) {
		return -EINVAL;
	}

	k_mutex_lock(&sst26_lock, K_FOREVER);
	while (len > 0U) {
		size_t n = MIN(len, (size_t)SST26_PAGE_SIZE);

		put_addr(SST26_CMD_READ, addr);
		memset(&tx_buf[4], 0, n);
		ret = xfer(4U + n);
		if (ret < 0) {
			break;
		}
		memcpy(buf, &rx_buf[4], n);
		addr += n;
		buf += n;
		len -= n;
	}
	k_mutex_unlock(&sst26_lock);
	return ret;
}

int sst26_write(uint32_t addr, const uint8_t *buf, size_t len)
{
	int ret = 0;

	if ((addr >= SST26_SIZE) || (len > SST26_SIZE - addr)) {
		return -EINVAL;
	}

	k_mutex_lock(&sst26_lock, K_FOREVER);
	while (len > 0U) {
		/* Do not cross a 256-byte page boundary in one program command */
		size_t room = SST26_PAGE_SIZE - (addr % SST26_PAGE_SIZE);
		size_t n = MIN(len, room);

		ret = write_enable();
		if (ret < 0) {
			break;
		}
		put_addr(SST26_CMD_PP, addr);
		memcpy(&tx_buf[4], buf, n);
		ret = xfer(4U + n);
		if (ret < 0) {
			break;
		}
		ret = wait_ready(SST26_TIMEOUT_PROGRAM_MS);
		if (ret < 0) {
			break;
		}
		addr += n;
		buf += n;
		len -= n;
	}
	k_mutex_unlock(&sst26_lock);
	return ret;
}

int sst26_erase(enum sst26_erase type, uint32_t addr)
{
	int ret;

	if ((type != SST26_ERASE_CHIP) && (addr >= SST26_SIZE)) {
		return -EINVAL;
	}

	k_mutex_lock(&sst26_lock, K_FOREVER);
	ret = write_enable();
	if (ret == 0) {
		switch (type) {
		case SST26_ERASE_SECTOR:
			put_addr(SST26_CMD_SE, addr);
			ret = xfer(4);
			break;
		case SST26_ERASE_BLOCK:
			put_addr(SST26_CMD_BE, addr);
			ret = xfer(4);
			break;
		case SST26_ERASE_CHIP:
		default:
			ret = cmd_only(SST26_CMD_CE);
			break;
		}
	}
	if (ret == 0) {
		ret = wait_ready(SST26_TIMEOUT_ERASE_MS);
	}
	k_mutex_unlock(&sst26_lock);
	return ret;
}
