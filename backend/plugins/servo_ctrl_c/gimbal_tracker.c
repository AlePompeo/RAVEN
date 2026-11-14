/* SPDX-License-Identifier: Apache-2.0 */
/* Host-only two-axis trajectory simulation; input and output are degrees.
 * The first input line is "count interval_seconds", followed by count
 * lines of "azimuth elevation". Each output line is "azimuth elevation
 * limit", where limit indicates that either demanded axis exceeded the
 * illustrative 180 degree mechanical range. Azimuth is unwrapped using
 * the shortest change between samples. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "control.h"
#include "hal.h"
#include "hal_host.h"

#define MAX_POINTS 5000
#define MAX_INTERVAL_S 86400.0
#define MAX_DURATION_S (90.0 * 86400.0)

typedef struct {
    double az;
    double el;
} point_t;

static double clamp(double x, double lo, double hi)
{
    return x < lo ? lo : (x > hi ? hi : x);
}

int main(void)
{
    point_t points[MAX_POINTS];
    pi_ctrl_t ctrl[2];
    hal_host_config_t cfg = {2.0f, 90.0f, 0.0f, 90.0f, 1};
    double interval, dt, az0, prev_az;
    int count, i, substeps, j, axis;
    char extra;

    if (scanf("%d %lf", &count, &interval) != 2 || count < 1 || count > MAX_POINTS ||
        !isfinite(interval) || interval < CTRL_DT_MIN_S || interval > MAX_INTERVAL_S ||
        interval * (count - 1) > MAX_DURATION_S) {
        fprintf(stderr, "invalid trajectory header\n");
        return 2;
    }
    for (i = 0; i < count; i++) {
        double az, el;
        if (scanf("%lf %lf", &az, &el) != 2 || !isfinite(az) || !isfinite(el) ||
            az < 0.0 || az >= 360.0 || el < -90.0 || el > 90.0) {
            fprintf(stderr, "invalid trajectory point\n");
            return 2;
        }
        if (i == 0) {
            points[i].az = az;
        } else {
            double delta = remainder(az - points[i - 1].az, 360.0);
            points[i].az = points[i - 1].az + delta;
        }
        points[i].el = el;
    }
    if (scanf(" %c", &extra) == 1) {
        fprintf(stderr, "extra trajectory data\n");
        return 2;
    }
    substeps = (int)ceil(interval);
    dt = interval / substeps;
    az0 = points[0].az;
    prev_az = az0;
    if (hal_host_init(&cfg) != 0) {
        return 3;
    }
    cfg.initial_angle_deg = (float)(points[0].el + 90.0);
    cfg.seed = 2;
    if (hal_host_init_axis(1, &cfg) != 0) {
        return 3;
    }
    for (axis = 0; axis < 2; axis++) {
        if (pi_init(&ctrl[axis], 1.0f, 0.5f, (float)dt,
                    HAL_SERVO_MIN_DEG, HAL_SERVO_MAX_DEG, 1) != CTRL_OK) {
            return 3;
        }
        /* Starting aligned requires a matching initial actuator command. */
        ctrl[axis].integral = axis == 0 ? 90.0f : cfg.initial_angle_deg;
    }
    printf("%.9f %.9f 0\n", az0, points[0].el);
    for (i = 1; i < count; i++) {
        int limited = 0;
        for (j = 1; j <= substeps; j++) {
            double f = (double)j / substeps;
            double az = prev_az + (points[i].az - prev_az) * f;
            double el = points[i - 1].el + (points[i].el - points[i - 1].el) * f;
            double demanded[2] = {az - az0 + 90.0, el + 90.0};
            for (axis = 0; axis < 2; axis++) {
                float volts, cmd;
                if (demanded[axis] < 0.0 || demanded[axis] > 180.0) {
                    limited = 1;
                }
                if (hal_adc_read(axis, &volts) != HAL_OK ||
                    pi_step(&ctrl[axis], (float)clamp(demanded[axis], 0.0, 180.0),
                            volts / HAL_ADC_VREF_V * HAL_SERVO_MAX_DEG, &cmd) != CTRL_OK ||
                    hal_servo_write_deg(axis, cmd) != HAL_OK) {
                    return 3;
                }
            }
            if (hal_host_step((float)dt) != 0) {
                return 3;
            }
        }
        {
            float az, el;
            if (hal_host_true_angle_deg_axis(0, &az) != 0 ||
                hal_host_true_angle_deg_axis(1, &el) != 0) {
                return 3;
            }
            printf("%.9f %.9f %d\n", az0 + az - 90.0, el - 90.0, limited);
        }
        prev_az = points[i].az;
    }
    return ferror(stdout) ? 3 : 0;
}
