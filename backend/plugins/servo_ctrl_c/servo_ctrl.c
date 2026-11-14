/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Harness: flat key=value protocol on stdin/stdout (ExecSimulation).
 * stdin  (all required unless marked optional, each once):
 *   setpoint_deg [-720,720], kp [0,1000], ki [0,1000], steps [1,100000]
 *   (integer), dt_s [1e-4,1], plant_tau_s [dt_s,100], sensor_noise_v
 *   [0,0.1], seed [0,2^32-1] (integer),
 *   anti_windup (optional, 0|1, default 1),
 *   plant_rate_dps (optional, (0,1000], default 90)
 * stdout: final_angle_deg, steady_error_deg, max_overshoot_deg,
 *   settle_time_s, saturated_steps
 * Invalid input: exit code 2, nothing on stdout, reason on stderr.
 * Runtime failure (should not happen): exit code 3, nothing on stdout.
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "control.h"
#include "hal.h"
#include "hal_host.h"

#define SETTLE_BAND_DEG 1.0
#define MAX_STEPS 100000.0

enum { K_SETPOINT, K_KP, K_KI, K_STEPS, K_DT, K_TAU, K_NOISE, K_SEED,
       K_AW, K_RATE, K_COUNT };
static const char *const KEYS[K_COUNT] = {
    "setpoint_deg", "kp", "ki", "steps", "dt_s", "plant_tau_s",
    "sensor_noise_v", "seed", "anti_windup", "plant_rate_dps"
};

static int fail(const char *why)
{
    fprintf(stderr, "invalid input: %s\n", why);
    return 2;
}

/* Returns 0 on success, 2 on invalid input. */
static int parse_stdin(double v[K_COUNT], int seen[K_COUNT])
{
    char line[160];
    while (fgets(line, sizeof line, stdin) != NULL) {
        char *eq, *end, *nl;
        double x;
        int k;
        nl = strchr(line, '\n');
        if (nl == NULL && !feof(stdin)) {
            return fail("line too long");
        }
        if (nl != NULL) {
            *nl = '\0';
        }
        if (line[0] == '\0') {
            continue;
        }
        eq = strchr(line, '=');
        if (eq == NULL) {
            return fail("missing '='");
        }
        *eq = '\0';
        for (k = 0; k < K_COUNT; k++) {
            if (strcmp(line, KEYS[k]) == 0) {
                break;
            }
        }
        if (k == K_COUNT) {
            return fail("unknown key");
        }
        if (seen[k]) {
            return fail("duplicate key");
        }
        x = strtod(eq + 1, &end);
        if (end == eq + 1 || *end != '\0' || !isfinite(x)) {
            return fail("non-numeric or non-finite value");
        }
        v[k] = x;
        seen[k] = 1;
    }
    return 0;
}

static int is_integer_in(double x, double lo, double hi)
{
    return x >= lo && x <= hi && x == floor(x);
}

int main(void)
{
    double v[K_COUNT] = {0};
    int seen[K_COUNT] = {0};
    int rc, k, sat_steps = 0;
    double sp, dt, tau, final_deg, mean_deg = 0.0, overshoot = 0.0;
    double last_out_s = 0.0, dir;
    double *hist;
    size_t n_steps, tail, i;
    pi_ctrl_t ctrl;
    hal_host_config_t cfg;

    rc = parse_stdin(v, seen);
    if (rc != 0) {
        return rc;
    }
    for (k = 0; k < K_AW; k++) {
        if (!seen[k]) {
            return fail("missing key");
        }
    }
    if (!seen[K_AW]) {
        v[K_AW] = 1.0;
    }
    if (!seen[K_RATE]) {
        v[K_RATE] = 90.0;
    }
    sp = v[K_SETPOINT];
    dt = v[K_DT];
    tau = v[K_TAU];
    if (sp < -720.0 || sp > 720.0) {
        return fail("setpoint_deg out of range");
    }
    if (!is_integer_in(v[K_STEPS], 1.0, MAX_STEPS)) {
        return fail("steps must be an integer in [1,100000]");
    }
    if (!is_integer_in(v[K_SEED], 0.0, 4294967295.0)) {
        return fail("seed must be an integer in [0,2^32-1]");
    }
    if (!(dt >= 1e-4 && dt <= 1.0)) {
        return fail("dt_s out of range");
    }
    if (!(tau >= dt && tau <= 100.0)) {
        return fail("plant_tau_s must be in [dt_s,100]");
    }
    if (!(v[K_NOISE] >= 0.0 && v[K_NOISE] <= 0.1)) {
        return fail("sensor_noise_v out of range");
    }
    if (v[K_AW] != 0.0 && v[K_AW] != 1.0) {
        return fail("anti_windup must be 0 or 1");
    }
    if (!(v[K_RATE] > 0.0 && v[K_RATE] <= 1000.0)) {
        return fail("plant_rate_dps out of range");
    }
    if (pi_init(&ctrl, (float)v[K_KP], (float)v[K_KI], (float)dt,
                HAL_SERVO_MIN_DEG, HAL_SERVO_MAX_DEG,
                (int)v[K_AW]) != CTRL_OK) {
        return fail("gains out of range");
    }
    cfg.plant_tau_s = (float)tau;
    cfg.rate_limit_dps = (float)v[K_RATE];
    cfg.sensor_noise_v = (float)v[K_NOISE];
    cfg.initial_angle_deg = 0.0f;
    cfg.seed = (uint32_t)v[K_SEED];
    if (hal_host_init(&cfg) != 0) {
        return fail("plant configuration rejected");
    }

    n_steps = (size_t)v[K_STEPS];
    hist = (double *)malloc(n_steps * sizeof *hist); /* host harness only */
    if (hist == NULL) {
        fprintf(stderr, "out of memory\n");
        return 3;
    }
    dir = (sp > 0.0) ? 1.0 : ((sp < 0.0) ? -1.0 : 0.0);

    for (i = 0; i < n_steps; i++) {
        float volts, meas_deg, cmd;
        double a;
        if (hal_adc_read(0, &volts) != HAL_OK) {
            free(hist);
            fprintf(stderr, "adc failure\n");
            return 3;
        }
        meas_deg = volts / HAL_ADC_VREF_V * HAL_SERVO_MAX_DEG;
        if (pi_step(&ctrl, (float)sp, meas_deg, &cmd) != CTRL_OK ||
            hal_servo_write_deg(0, cmd) != HAL_OK ||
            hal_host_step((float)dt) != 0) {
            free(hist);
            fprintf(stderr, "control loop failure\n");
            return 3;
        }
        if (ctrl.saturated) {
            sat_steps++;
        }
        a = (double)hal_host_true_angle_deg();
        hist[i] = a;
        if ((a - sp) * dir > overshoot) {
            overshoot = (a - sp) * dir;
        }
        if (fabs(a - sp) > SETTLE_BAND_DEG) {
            last_out_s = (double)(i + 1u) * dt;
        }
    }
    (void)hal_uart_write((const uint8_t *)"done\n", 5u);

    final_deg = hist[n_steps - 1u];
    tail = n_steps / 10u;
    if (tail < 1u) {
        tail = 1u;
    }
    for (i = n_steps - tail; i < n_steps; i++) {
        mean_deg += hist[i];
    }
    mean_deg /= (double)tail;
    free(hist);

    printf("final_angle_deg=%.6f\n", final_deg);
    printf("steady_error_deg=%.6f\n", fabs(sp - mean_deg));
    printf("max_overshoot_deg=%.6f\n", overshoot);
    printf("settle_time_s=%.6f\n", last_out_s);
    printf("saturated_steps=%d\n", sat_steps);
    return 0;
}
