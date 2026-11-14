/* backend/plugins/fspl_c/fspl.c — SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <string.h>
#include <math.h>
int main(void) {
    char line[256]; double d = 0, f = 0;
    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "distance_km=%lf", &d) == 1) continue;
        sscanf(line, "freq_ghz=%lf", &f);
    }
    if (d <= 0 || f <= 0) return 2;
    printf("fspl_db=%.6f\n", 92.45 + 20.0 * log10(d) + 20.0 * log10(f));
    return 0;
}
