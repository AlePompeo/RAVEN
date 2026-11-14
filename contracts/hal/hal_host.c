/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Host HAL: deterministic simulated plant.
 *  - servo: first-order lag toward the commanded angle with a slew-rate
 *    limit, explicit Euler (needs dt <= tau; the harness enforces it);
 *  - ADC channels 0 and 1: servo angle mapped to 0..VREF plus seeded noise,
 *    clipped to the ADC range like a real converter;
 *  - noise: xorshift32, sum of 4 uniforms scaled to the requested
 *    standard deviation (approximately Gaussian, bounded).
 * State is file-static; nothing is allocated.
 */
#include "hal_host.h"

#include <math.h>

#include "hal.h"

#define UART_CAP 256u
#define AXES 2

typedef struct {
    hal_host_config_t cfg;
    int ready;
    float angle_deg;
    float cmd_deg;
    uint32_t rng;
} host_axis_t;

static host_axis_t g_axes[AXES];
static double g_time_s;
static uint8_t g_uart[UART_CAP];
static size_t g_uart_len;

static uint32_t rng_next(host_axis_t *axis)
{
    uint32_t x = axis->rng;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    axis->rng = x;
    return x;
}

/* Approximately N(0,1): sum of 4 U(-1,1) has variance 4/3. */
static float noise_unit(host_axis_t *axis)
{
    float s = 0.0f;
    int i;
    for (i = 0; i < 4; i++) {
        s += ((float)(rng_next(axis) >> 8) / 8388608.0f) - 1.0f; /* 2^23 */
    }
    return s * 0.8660254f; /* sqrt(3)/2 = 1/sqrt(4/3) */
}

static int axis_init(host_axis_t *axis, const hal_host_config_t *cfg)
{
    if (cfg == NULL) {
        return -1;
    }
    if (!(isfinite(cfg->plant_tau_s) && cfg->plant_tau_s > 0.0f) ||
        !(isfinite(cfg->rate_limit_dps) && cfg->rate_limit_dps > 0.0f) ||
        !(isfinite(cfg->sensor_noise_v) && cfg->sensor_noise_v >= 0.0f) ||
        !(isfinite(cfg->initial_angle_deg) &&
          cfg->initial_angle_deg >= HAL_SERVO_MIN_DEG &&
          cfg->initial_angle_deg <= HAL_SERVO_MAX_DEG)) {
        return -1;
    }
    axis->cfg = *cfg;
    axis->angle_deg = cfg->initial_angle_deg;
    axis->cmd_deg = cfg->initial_angle_deg;
    axis->rng = (cfg->seed != 0u) ? cfg->seed : 0x9E3779B9u;
    axis->ready = 1;
    return 0;
}

int hal_host_init(const hal_host_config_t *cfg)
{
    size_t i;
    host_axis_t axis = {0};
    if (axis_init(&axis, cfg) != 0) {
        return -1;
    }
    g_axes[0] = axis;
    g_axes[1].ready = 0;
    g_time_s = 0.0;
    for (i = 0; i < UART_CAP; i++) {
        g_uart[i] = 0u;
    }
    g_uart_len = 0u;
    return 0;
}

int hal_host_init_axis(int channel, const hal_host_config_t *cfg)
{
    if (!g_axes[0].ready || channel != 1) {
        return -1;
    }
    return axis_init(&g_axes[channel], cfg);
}

int hal_host_step(float dt_s)
{
    int i;
    if (!g_axes[0].ready || !(isfinite(dt_s) && dt_s > 0.0f)) {
        return -1;
    }
    for (i = 0; i < AXES; i++) {
        host_axis_t *axis = &g_axes[i];
        float rate;
        if (!axis->ready) {
            continue;
        }
        rate = (axis->cmd_deg - axis->angle_deg) / axis->cfg.plant_tau_s;
        if (rate > axis->cfg.rate_limit_dps) {
            rate = axis->cfg.rate_limit_dps;
        } else if (rate < -axis->cfg.rate_limit_dps) {
            rate = -axis->cfg.rate_limit_dps;
        }
        axis->angle_deg += rate * dt_s;
        if (axis->angle_deg < HAL_SERVO_MIN_DEG) {
            axis->angle_deg = HAL_SERVO_MIN_DEG;
        } else if (axis->angle_deg > HAL_SERVO_MAX_DEG) {
            axis->angle_deg = HAL_SERVO_MAX_DEG;
        }
    }
    g_time_s += (double)dt_s;
    return 0;
}

float hal_host_true_angle_deg(void)
{
    return g_axes[0].angle_deg;
}

int hal_host_true_angle_deg_axis(int channel, float *out_deg)
{
    if (out_deg == NULL || channel < 0 || channel >= AXES || !g_axes[channel].ready) {
        return -1;
    }
    *out_deg = g_axes[channel].angle_deg;
    return 0;
}

size_t hal_host_uart_bytes(void)
{
    return g_uart_len;
}

int hal_servo_write_deg(int channel, float deg)
{
    if (!g_axes[0].ready) {
        return HAL_ERR_IO;
    }
    if (channel < 0 || channel >= AXES || !g_axes[channel].ready) {
        return HAL_ERR_CHANNEL;
    }
    if (!isfinite(deg)) {
        return HAL_ERR_ARG;
    }
    if (deg < HAL_SERVO_MIN_DEG || deg > HAL_SERVO_MAX_DEG) {
        return HAL_ERR_RANGE;
    }
    g_axes[channel].cmd_deg = deg;
    return HAL_OK;
}

int hal_adc_read(int channel, float *out_volts)
{
    float v;
    if (out_volts == NULL) {
        return HAL_ERR_ARG;
    }
    if (!g_axes[0].ready) {
        return HAL_ERR_IO;
    }
    if (channel < 0 || channel >= AXES || !g_axes[channel].ready) {
        return HAL_ERR_CHANNEL;
    }
    v = g_axes[channel].angle_deg / HAL_SERVO_MAX_DEG * HAL_ADC_VREF_V;
    if (g_axes[channel].cfg.sensor_noise_v > 0.0f) {
        v += g_axes[channel].cfg.sensor_noise_v * noise_unit(&g_axes[channel]);
    }
    if (v < 0.0f) {
        v = 0.0f;
    } else if (v > HAL_ADC_VREF_V) {
        v = HAL_ADC_VREF_V;
    }
    *out_volts = v;
    return HAL_OK;
}

int hal_uart_write(const uint8_t *data, size_t len)
{
    size_t n = 0u;
    if (data == NULL && len > 0u) {
        return HAL_ERR_ARG;
    }
    while (n < len && g_uart_len < UART_CAP) {
        g_uart[g_uart_len] = data[n];
        g_uart_len++;
        n++;
    }
    return (int)n;
}

uint32_t hal_millis(void)
{
    return (uint32_t)(g_time_s * 1000.0);
}
