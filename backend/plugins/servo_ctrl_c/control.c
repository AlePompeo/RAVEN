/* SPDX-License-Identifier: Apache-2.0 */
#include "control.h"

#include <math.h>
#include <stddef.h>

static int in_range(float v, float lim)
{
    return isfinite(v) && v >= -lim && v <= lim;
}

int pi_init(pi_ctrl_t *c, float kp, float ki, float dt_s,
            float out_min, float out_max, int anti_windup)
{
    if (c == NULL) {
        return CTRL_ERR_ARG;
    }
    if (!(isfinite(kp) && kp >= 0.0f && kp <= CTRL_KP_MAX) ||
        !(isfinite(ki) && ki >= 0.0f && ki <= CTRL_KI_MAX) ||
        !(isfinite(dt_s) && dt_s >= CTRL_DT_MIN_S && dt_s <= CTRL_DT_MAX_S) ||
        !(isfinite(out_min) && isfinite(out_max) && out_min < out_max)) {
        return CTRL_ERR_VALUE;
    }
    c->kp = kp;
    c->ki = ki;
    c->dt_s = dt_s;
    c->out_min = out_min;
    c->out_max = out_max;
    c->anti_windup = (anti_windup != 0);
    c->integral = 0.0f;
    c->saturated = 0;
    return CTRL_OK;
}

int pi_step(pi_ctrl_t *c, float setpoint_deg, float measurement_deg,
            float *out)
{
    float err, integ, u;
    if (c == NULL || out == NULL) {
        return CTRL_ERR_ARG;
    }
    if (!in_range(setpoint_deg, CTRL_ANGLE_LIMIT_DEG) ||
        !in_range(measurement_deg, CTRL_ANGLE_LIMIT_DEG)) {
        return CTRL_ERR_VALUE;
    }
    err = setpoint_deg - measurement_deg;
    integ = c->integral + c->ki * err * c->dt_s;
    u = c->kp * err + integ;
    c->saturated = 0;
    if (u > c->out_max) {
        u = c->out_max;
        c->saturated = 1;
        /* Conditional integration: freeze while pushing further into the clamp. */
        if (c->anti_windup && err > 0.0f) {
            integ = c->integral;
        }
    } else if (u < c->out_min) {
        u = c->out_min;
        c->saturated = 1;
        if (c->anti_windup && err < 0.0f) {
            integ = c->integral;
        }
    }
    /* Naive mode must still not overflow to inf in very long runs. */
    if (!isfinite(integ) || fabsf(integ) > 1e9f) {
        integ = c->integral;
    }
    c->integral = integ;
    *out = u;
    return CTRL_OK;
}
