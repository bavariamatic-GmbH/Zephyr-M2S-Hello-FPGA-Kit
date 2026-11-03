/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * SmartFusion2 MMUART fractional baud rate for the console UART.
 *
 * Taken over from SmartManipulator-X-Controller
 * (apps/SmartManipulator_Controller/src/communication.c,
 * sf2_mmuart_set_fractional_baud()); the bit rate comes from the devicetree
 * current-speed of the zephyr,console UART instead of DXL_HOST_BAUDRATE.
 *
 * The kit's USB port reaches MMUART_0 through the PIC32, which talks to the
 * SmartFusion2 at 230400 bit/s. The ns16550 driver programs only the integer
 * divisor. With the 50 MHz MSS peripheral clock that is 13 for 230400 bit/s,
 * i.e. 223214 bit/s (-3.1 %), too far off for a reliable link. The
 * SmartFusion2 MMUART also has a fractional divisor in 1/64 steps (DFR,
 * enabled by MM0.EFBR), so the divisor is reprogrammed as DLR/DMR + DFR/64:
 * 13 + 36/64 gives 230414 bit/s (+0.006 %).
 *
 * Register layout: SmartFusion2 MSS MMUART (UG0331), identical to the
 * PolarFire SoC MSS MMUART driver (mss_uart.h / mss_uart_regs.h).
 *
 * It runs as a SYS_INIT hook right after the ns16550 driver
 * (PRE_KERNEL_1, CONFIG_SERIAL_INIT_PRIORITY) and before the UART console
 * (PRE_KERNEL_1, CONFIG_CONSOLE_INIT_PRIORITY), so the first character
 * (boot banner) already goes out at the correct rate.
 */

#include <stdint.h>
#include <zephyr/devicetree.h>
#include <zephyr/init.h>
#include <zephyr/sys/sys_io.h>
#include <zephyr/arch/cpu.h>
#include <zephyr/sys/util.h>
#include <zephyr/toolchain.h>

#define CONSOLE_UART_NODE DT_CHOSEN(zephyr_console)

BUILD_ASSERT(DT_NODE_HAS_STATUS(CONSOLE_UART_NODE, okay),
	     "The board's zephyr,console UART must be enabled");

#if DT_NODE_HAS_COMPAT(CONSOLE_UART_NODE, ns16550) && defined(CONFIG_SOC_SERIES_SMARTFUSION2)

#define SF2_MMUART_BASE     DT_REG_ADDR(CONSOLE_UART_NODE)
#define SF2_MMUART_DLR      0x00U /* divisor LSB (LCR.DLAB = 1) */
#define SF2_MMUART_DMR      0x04U /* divisor MSB (LCR.DLAB = 1) */
#define SF2_MMUART_LCR      0x0CU
#define SF2_MMUART_MM0      0x30U
#define SF2_MMUART_DFR      0x3CU /* fractional divisor, 1/64 units */
#define SF2_MMUART_LCR_DLAB BIT(7)
#define SF2_MMUART_MM0_EFBR BIT(7)

/** Bit rate of the console UART (devicetree current-speed). */
#define SF2_MMUART_BAUD DT_PROP(CONSOLE_UART_NODE, current_speed)

/** Clock of the console UART: MSS peripheral clock from the clock controller. */
#define SF2_MMUART_PCLK                                                                            \
	DT_PROP_BY_IDX(DT_CLOCKS_CTLR(CONSOLE_UART_NODE), clock_frequencies,                       \
		       DT_CLOCKS_CELL(CONSOLE_UART_NODE, clkid))

/** Divisor in 1/64 units, rounded: PCLK / (16 * baud) * 64 = 4 * PCLK / baud. */
#define SF2_MMUART_DIVISOR_X64                                                                     \
	((uint32_t)(((4ULL * SF2_MMUART_PCLK) + (SF2_MMUART_BAUD / 2U)) / SF2_MMUART_BAUD))

/** Bit rate that the divisor actually produces. */
#define SF2_MMUART_ACTUAL_BAUD ((uint32_t)((4ULL * SF2_MMUART_PCLK) / SF2_MMUART_DIVISOR_X64))

BUILD_ASSERT(SF2_MMUART_DIVISOR_X64 / 64U >= 2U && SF2_MMUART_DIVISOR_X64 / 64U <= 0xFFFFU,
	     "Console UART bit rate out of range for the MMUART divisor");
BUILD_ASSERT((SF2_MMUART_ACTUAL_BAUD > SF2_MMUART_BAUD
		      ? SF2_MMUART_ACTUAL_BAUD - SF2_MMUART_BAUD
		      : SF2_MMUART_BAUD - SF2_MMUART_ACTUAL_BAUD) *
			     200U <
		     SF2_MMUART_BAUD,
	     "Console UART bit rate error above 0.5 % with this peripheral clock");

/* Priority 55 lies between the ns16550 driver and the UART console. */
#define SF2_MMUART_INIT_PRIORITY 55
BUILD_ASSERT(CONFIG_SERIAL_INIT_PRIORITY < SF2_MMUART_INIT_PRIORITY,
	     "Fractional baud rate must be set after the ns16550 driver init");
#if defined(CONFIG_UART_CONSOLE)
BUILD_ASSERT(SF2_MMUART_INIT_PRIORITY < CONFIG_CONSOLE_INIT_PRIORITY,
	     "Fractional baud rate must be set before the UART console init");
#endif

/** Program the integer and fractional baud divisors of the console MMUART. */
static int sf2_mmuart_set_fractional_baud(void)
{
	const uint32_t integer = SF2_MMUART_DIVISOR_X64 / 64U;
	const uint32_t fraction = SF2_MMUART_DIVISOR_X64 % 64U;
	const uint8_t lcr = sys_read8(SF2_MMUART_BASE + SF2_MMUART_LCR);

	sys_write8(lcr | SF2_MMUART_LCR_DLAB, SF2_MMUART_BASE + SF2_MMUART_LCR);
	sys_write8((uint8_t)(integer >> 8), SF2_MMUART_BASE + SF2_MMUART_DMR);
	sys_write8((uint8_t)integer, SF2_MMUART_BASE + SF2_MMUART_DLR);
	sys_write8(lcr & (uint8_t)~SF2_MMUART_LCR_DLAB, SF2_MMUART_BASE + SF2_MMUART_LCR);
	sys_write8(sys_read8(SF2_MMUART_BASE + SF2_MMUART_MM0) | SF2_MMUART_MM0_EFBR,
		   SF2_MMUART_BASE + SF2_MMUART_MM0);
	sys_write8((uint8_t)fraction, SF2_MMUART_BASE + SF2_MMUART_DFR);

	return 0;
}

SYS_INIT(sf2_mmuart_set_fractional_baud, PRE_KERNEL_1, 55);

#endif
