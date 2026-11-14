/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <math.h>

#include "hal.h"
#include "hal_host.h"

int main(void)
{
    hal_host_config_t a = {1.0f, 20.0f, 0.01f, 30.0f, 7};
    hal_host_config_t b = {2.0f, 10.0f, 0.01f, 120.0f, 9};
    hal_host_config_t bad = b;
    float angle, first, second, unaffected;

    assert(hal_host_init_axis(1, &b) == -1);
    assert(hal_host_init(&a) == 0);
    assert(hal_adc_read(1, &angle) == HAL_ERR_CHANNEL);
    assert(hal_host_init_axis(1, &b) == 0);
    assert(hal_servo_write_deg(0, 60.0f) == HAL_OK);
    assert(hal_servo_write_deg(1, 80.0f) == HAL_OK);
    assert(hal_host_step(1.0f) == 0);
    assert(hal_host_true_angle_deg() == 50.0f);
    assert(hal_host_true_angle_deg_axis(1, &angle) == 0 && angle == 110.0f);
    bad.plant_tau_s = 0.0f;
    assert(hal_host_init_axis(1, &bad) == -1);
    assert(hal_host_true_angle_deg_axis(1, &angle) == 0 && angle == 110.0f);
    angle = -1.0f;
    assert(hal_host_true_angle_deg_axis(2, &angle) == -1 && angle == -1.0f);

    assert(hal_adc_read(0, &first) == HAL_OK);
    assert(hal_adc_read(1, &unaffected) == HAL_OK);
    assert(hal_adc_read(0, &second) == HAL_OK);
    assert(hal_host_init(&a) == 0);
    assert(hal_servo_write_deg(0, 60.0f) == HAL_OK);
    assert(hal_host_step(1.0f) == 0);
    assert(hal_adc_read(0, &unaffected) == HAL_OK && unaffected == first);
    assert(hal_adc_read(0, &unaffected) == HAL_OK && unaffected == second);
    assert(hal_adc_read(1, &unaffected) == HAL_ERR_CHANNEL);
    return 0;
}
