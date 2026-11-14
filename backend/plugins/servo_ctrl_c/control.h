/* SPDX-License-Identifier: Apache-2.0 */
/*
 * PI controller with output clamp and anti-windup (conditional
 * integration). Portable C99: no HAL dependency, no allocation, no I/O.
 * Units: degrees and seconds. Gains are in output-deg per input-deg
 * (kp) and per input-deg*s (ki).
 */
#ifndef CONTROL_H
#define CONTROL_H

#ifdef __cplusplus
extern "C" {
#endif

#define CTRL_OK          0
#define CTRL_ERR_ARG   (-1) /* NULL pointer */
#define CTRL_ERR_VALUE (-2) /* NaN/inf or out-of-range value */

#define CTRL_KP_MAX   1000.0f
#define CTRL_KI_MAX   1000.0f
#define CTRL_DT_MIN_S 1e-4f
#define CTRL_DT_MAX_S 1.0f
#define CTRL_ANGLE_LIMIT_DEG 1000.0f /* |setpoint|, |measurement| bound */

typedef struct {
    float kp, ki, dt_s;
    float out_min, out_max;
    int anti_windup;     /* 1 = conditional integration, 0 = naive */
    float integral;      /* output-deg */
    int saturated;       /* last step hit the clamp */
} pi_ctrl_t;

/* kp, ki in [0, 1000]; dt_s in [1e-4, 1]; out_min < out_max, finite. */
int pi_init(pi_ctrl_t *c, float kp, float ki, float dt_s,
            float out_min, float out_max, int anti_windup);

/*
 * One control step. setpoint_deg and measurement_deg must be finite with
 * |x| <= CTRL_ANGLE_LIMIT_DEG. On success *out is in [out_min, out_max].
 * On error the state and *out are left untouched.
 */
int pi_step(pi_ctrl_t *c, float setpoint_deg, float measurement_deg,
            float *out);

#ifdef __cplusplus
}
#endif

#endif /* CONTROL_H */
