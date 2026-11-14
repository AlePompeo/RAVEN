/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Minimal Hardware Abstraction Layer (C99).
 *
 * The control code includes only this header; the harness links either
 * hal_host.c (simulated plant, host build) or a target implementation
 * (e.g. hal_esp32.c). No dynamic allocation, no globals declared here.
 * All functions are non-blocking and return quickly.
 */
#ifndef HAL_H
#define HAL_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Status codes: 0 on success, negative on error. */
#define HAL_OK            0
#define HAL_ERR_ARG     (-1) /* NULL pointer, NaN/inf, bad length */
#define HAL_ERR_CHANNEL (-2) /* channel index not available */
#define HAL_ERR_RANGE   (-3) /* value outside the documented range */
#define HAL_ERR_IO      (-4) /* peripheral failure / not initialised */

/* Valid ranges. */
#define HAL_SERVO_MIN_DEG 0.0f   /* degrees */
#define HAL_SERVO_MAX_DEG 180.0f /* degrees */
#define HAL_ADC_VREF_V    3.3f   /* volts; reading is in [0, HAL_ADC_VREF_V] */

/*
 * Command a servo. channel: implementation-defined, 0 is always valid.
 * deg: target angle in degrees, must be finite and in [0, 180]
 * (out of range is rejected, never silently clamped).
 * Returns HAL_OK, HAL_ERR_CHANNEL, HAL_ERR_ARG (NaN/inf), HAL_ERR_RANGE.
 */
int hal_servo_write_deg(int channel, float deg);

/*
 * Read an ADC channel as a voltage in volts, range [0, HAL_ADC_VREF_V].
 * *out_volts is written only on HAL_OK.
 * Returns HAL_OK, HAL_ERR_ARG (out_volts NULL), HAL_ERR_CHANNEL, HAL_ERR_IO.
 */
int hal_adc_read(int channel, float *out_volts);

/*
 * Write len bytes to the debug/telemetry UART (not the harness stdout).
 * Returns the number of bytes accepted (>= 0, may be < len when the
 * buffer is full) or a negative HAL_ERR_* (HAL_ERR_ARG if data is NULL
 * and len > 0).
 */
int hal_uart_write(const uint8_t *data, size_t len);

/*
 * Milliseconds since start. Monotonic, wraps at 2^32 (about 49.7 days);
 * compare with unsigned subtraction.
 */
uint32_t hal_millis(void);

#ifdef __cplusplus
}
#endif

#endif /* HAL_H */
