/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Host-only companion of hal.h: configures and advances the simulated
 * plant. Not part of the portable HAL; control code must not include it.
 */
#ifndef HAL_HOST_H
#define HAL_HOST_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float plant_tau_s;       /* first-order time constant, s, > 0 */
    float rate_limit_dps;    /* servo slew-rate limit, deg/s, > 0 */
    float sensor_noise_v;    /* noise standard deviation, V, >= 0 */
    float initial_angle_deg; /* in [0, 180] */
    uint32_t seed;           /* noise generator seed (any value) */
} hal_host_config_t;

/* Returns 0 on success, -1 on invalid configuration (nothing changed). */
int hal_host_init(const hal_host_config_t *cfg);

/* Configure an additional simulated servo/ADC channel independently.
 * The host must first be initialised with hal_host_init. Channel 0 is
 * reserved for that initialisation; channel 1 is the second axis.
 * Returns 0 on success, -1 on invalid configuration (nothing changed). */
int hal_host_init_axis(int channel, const hal_host_config_t *cfg);

/* Advance the plant by dt_s seconds (> 0, finite). Returns 0 or -1. */
int hal_host_step(float dt_s);

/* True (noise-free) servo angle in degrees, for the harness metrics. */
float hal_host_true_angle_deg(void);

/* Noise-free angle of an initialised channel; writes only on success. */
int hal_host_true_angle_deg_axis(int channel, float *out_deg);

/* Bytes written through hal_uart_write since init. */
size_t hal_host_uart_bytes(void);

#ifdef __cplusplus
}
#endif

#endif /* HAL_HOST_H */
