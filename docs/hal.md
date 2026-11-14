<!-- SPDX-License-Identifier: Apache-2.0 -->
# HAL minima per il codice di controllo (livello L0)

Obiettivo (spec §12): lo stesso codice di controllo gira su host, dentro `ExecSimulation`, e in seguito su un target (ESP32/Arduino) cambiando solo l'implementazione della HAL.

## File

| File | Ruolo |
|---|---|
| `contracts/hal/hal.h` | API portabile C99: `hal_servo_write_deg`, `hal_adc_read`, `hal_uart_write`, `hal_millis`. Nessuna allocazione, nessuna variabile globale nell'header. |
| `contracts/hal/hal_host.c` + `hal_host.h` | Implementazione host: servo del primo ordine con limite di velocita', ADC con rumore deterministico (xorshift32 con seed). Configurata dal harness tramite `hal_host_config_t`, nessun parsing di stdin nella HAL. `hal_host.h` e' solo host: il codice di controllo non deve includerlo. |
| `backend/plugins/servo_ctrl_c/control.[ch]` | Controllore PI con clamp d'uscita e anti-windup (integrazione condizionale). Dipende solo da `math.h`, non dalla HAL. |
| `backend/plugins/servo_ctrl_c/servo_ctrl.c` | Harness host: protocollo `key=value` su stdin/stdout. |

## Contratto delle funzioni

| Funzione | Unita' / intervallo valido | Ritorno |
|---|---|---|
| `int hal_servo_write_deg(int channel, float deg)` | `deg` finito in [0, 180] gradi; il fuori range e' rifiutato, mai saturato in silenzio. Canale 0 sempre valido. | `HAL_OK` (0), `HAL_ERR_CHANNEL` (-2), `HAL_ERR_ARG` (-1, NaN/inf), `HAL_ERR_RANGE` (-3), `HAL_ERR_IO` (-4, non inizializzato) |
| `int hal_adc_read(int channel, float *out_volts)` | volt in [0, `HAL_ADC_VREF_V` = 3.3]; `*out_volts` scritto solo su `HAL_OK` | `HAL_OK`, `HAL_ERR_ARG` (puntatore NULL), `HAL_ERR_CHANNEL`, `HAL_ERR_IO` |
| `int hal_uart_write(const uint8_t *data, size_t len)` | byte; non bloccante | byte accettati (>= 0, anche < `len`) oppure `HAL_ERR_ARG` |
| `uint32_t hal_millis(void)` | millisecondi dall'avvio, monotono, wrap a 2^32 (~49,7 giorni): confrontare con sottrazione unsigned | valore |

La HAL host inizializza il canale 0 con `hal_host_init` e può configurare il canale 1 con
`hal_host_init_axis`: i due assi hanno stato, configurazione e rumore indipendenti, ma condividono
l'avanzamento temporale `hal_host_step`. `hal_host_true_angle_deg_axis` legge l'angolo effettivo
di un canale inizializzato; `hal_host_true_angle_deg` rimane il lettore del canale 0. Una nuova
`hal_host_init` disabilita il canale 1. Questa capacità, da sola, non costituisce un modello di
gimbal o un inseguimento della Terra.

Il programma host separato `gimbal_tracker` riusa due controllori PI e i due assi della HAL.
Nell'analisi GrazingLink è una scelta opzionale: parte allineato alla prima direzione, interpola
linearmente elevazione e azimut (per quest'ultimo usa il percorso più corto fra campioni) e simula
con passi al massimo di un secondo. Ogni servo ha corsa 0–180°, costante di tempo 2 s, velocità
massima 90°/s, PI con kp=1 e ki=0,5, nessun rumore e anti-windup; l'azimut iniziale corrisponde
al centro della corsa, l'elevazione 0° a 90° del servo. I parametri sono ipotesi illustrative,
non calibrazioni di un gimbal reale. Si segnalano gli intervalli con richieste oltre i limiti
meccanici; l'errore angolare tridimensionale produce la perdita gaussiana nel margine. Per questa
modalità non viene applicato anche l'errore costante `tracking_error_deg`. L'interpolazione non
ricostruisce movimenti più rapidi tra i campioni e il modello di antenna gaussiano non descrive
necessariamente i lobi fuori dall'asse. La simulazione non è validata su hardware.

## Protocollo dell'esempio `servo_ctrl_c`

Ingresso (`key=value`, una riga ciascuno, ogni chiave una sola volta): `setpoint_deg` [-720, 720], `kp` [0, 1000], `ki` [0, 1000], `steps` intero [1, 100000], `dt_s` [1e-4, 1], `plant_tau_s` [`dt_s`, 100] (con tau < dt l'Eulero esplicito e' instabile), `sensor_noise_v` [0, 0.1] (deviazione standard in volt), `seed` intero [0, 2^32-1]. Opzionali: `anti_windup` (0|1, default 1), `plant_rate_dps` ((0, 1000], default 90).

Uscita: `final_angle_deg`, `steady_error_deg` (media dell'angolo vero sull'ultimo 10 % dei passi), `max_overshoot_deg`, `settle_time_s` (ultimo istante con errore > 1 grado), `saturated_steps`. Tutti finiti. Ingresso non valido (chiave mancante/sconosciuta/duplicata, NaN/inf, fuori range, riga > 159 caratteri): codice di uscita 2, stdout vuoto, motivo su stderr.

Compilazione: `make build-c` (o `make build-servo`, con `SERVO_EXTRA_CFLAGS=-fsanitize=address,undefined` se il runtime e' installato). Il binario finisce in `backend/plugins/servo_ctrl_c/bin/` (ignorato da git).

## Portare su ESP32 (solo descrizione, NON eseguito)

Nota: nessuna build o esecuzione su ESP32 o Arduino e' stata fatta. Quanto segue e' il piano di porting, non un risultato verificato.

1. Scrivere `contracts/hal/hal_esp32.c` che implementa le quattro funzioni di `hal.h`:
   - `hal_servo_write_deg`: ESP-IDF, periferica LEDC (PWM a 50 Hz, durata 1-2 ms mappata su 0-180 gradi, da calibrare sul servo reale); Arduino-ESP32, libreria `ESP32Servo` oppure `ledcWrite`. Non usare `analogWrite` per il PWM su ESP32.
   - `hal_adc_read`: ESP-IDF `adc_oneshot` (con calibrazione), restituendo volt; con WiFi attivo usare solo ADC1 (GPIO32-39), perche' ADC2 non e' utilizzabile. Il fondo scala dipende dall'attenuazione scelta: allineare `HAL_ADC_VREF_V` oppure documentare la differenza.
   - `hal_uart_write`: `uart_write_bytes` (ESP-IDF) o `Serial.write` (Arduino), non bloccante o con timeout esplicito.
   - `hal_millis`: `esp_timer_get_time() / 1000` troncato a 32 bit, o `millis()` su Arduino.
2. Il ciclo del controllore sostituisce il ciclo di `servo_ctrl.c`: un task FreeRTOS periodico con `vTaskDelayUntil` a `dt_s` (mai busy-wait) che chiama `hal_adc_read`, `pi_step`, `hal_servo_write_deg`. `control.c` si compila invariato.
3. Build: un componente ESP-IDF (`CMakeLists.txt` con `idf_component_register`) oppure una libreria PlatformIO che include `contracts/hal/hal.h` e `control.c`, escludendo `hal_host.c`, `hal_host.h` e `servo_ctrl.c`.
4. Da verificare sul target: sostituzione di `float`/`math.h` (FPU single-precision sull'ESP32 classico), timing reale del loop, campionamento ADC e rumore reale, limiti meccanici del servo. L'anti-windup e il clamp sono dimostrati solo contro il modello host.

Limite dichiarato: L0 valida la logica di controllo, non il timing hardware.
