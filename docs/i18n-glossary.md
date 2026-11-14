# Glossario delle traduzioni (i18n)

Termine concordato per lingua, da usare in tutti i cataloghi (`frontend/src/i18n/{en,it}.json`). L'inglese è la
sorgente (vedi `docs/i18n.md`). Le sigle e le unità restano in caratteri latini in entrambe le lingue (dB, dBi, Mbps,
bit/s, Eb/N₀, C/N₀, ITU-R P.526, LOLA, DSN).

| Termine (en) | Spiegazione in una riga (en) | it |
|---|---|---|
| diffraction | The signal bends around the edge of an obstacle and arrives weaker instead of being cut off. | diffrazione |
| Fresnel zone | The football-shaped region around the straight path that must stay clear for the full signal. | zona di Fresnel |
| link margin | How many dB of signal are left over (positive) or missing (negative) for the link to work. | margine di link |
| libration | The Moon's slow wobble seen from Earth, which moves Earth up and down in the lunar sky by about a degree. | librazione |
| dB (decibel) | A ratio on a log scale: +3 dB is about double the power, −3 dB about half. | dB (decibel) |
| ridge | A long raised line of terrain between the lander and the Earth that can hide the Earth. | crinale |
| line of sight | A straight, unobstructed path between two antennas. | linea di vista |
| lander | The spacecraft resting on the Moon's surface that sends data to Earth. | lander |
| bit rate | How many bits of data per second the link carries. | velocità di trasmissione (bit rate) |
| antenna | The device that sends and receives the radio signal (a dish on the lander, a large dish of the DSN on Earth). | antenna |

Altri termini già fissati nella shell:

| en | it |
|---|---|
| Learning (mode) | Learning |
| Advanced (mode) | Avanzato |
| Simulate / Analyze / Sites / Lab / Assistant | Simula / Analizza / Siti / Laboratorio / Assistente |

Regole: un termine per concetto (niente sinonimi tra pagine); alla prima occorrenza in una pagina Learning, il termine
tecnico è seguito dalla spiegazione in una riga; in Avanzato basta il termine. "Lander" resta "lander" in italiano.
