"""
Quanto deve essere direttiva l'antenna di un rover lunare? (X-band, collegamento diretto verso una stazione da 34 m)
Formule standard: G = 10 log10(eta (pi D / lambda)^2), HPBW ~ 70 lambda / D, perdita di puntamento ~ 12 (err/HPBW)^2 dB.
Parametri radio = IPOTESI ILLUSTRATIVE (come in link_budget_grazing.py). Uso: python antenna_directivity.py
"""
import math
C = 299792458.0; K = -228.6
def gain_db(D, f, eta=0.55): return 10 * math.log10(eta * (math.pi * D * f / C) ** 2)
def hpbw(D, f): return 70 * (C / f) / D
def fspl(d_m, f): return 20 * math.log10(4 * math.pi * d_m * f / C)
d = 384400e3; f = 8.4e9
print("1) Antenne a paraboloide in banda X (8,4 GHz)")
print("   D (m)   guadagno (dBi)   HPBW (gradi)   perdita se l'errore e' meta' HPBW (dB)")
for D in (0.1, 0.2, 0.3, 0.5, 1.0):
    h = hpbw(D, f); print(f"   {D:5.2f}   {gain_db(D, f):10.1f}       {h:9.1f}        {12*0.25:6.1f}")
print("\n2) Guadagno del rover necessario per chiudere il collegamento (Pt 10 W, Tsys 30 K, Eb/N0 2,5 dB, perdite 3 dB, margine 3 dB)")
N0 = K + 10 * math.log10(30)   # dBW/Hz
for gr, nome in ((68.0, "stazione da 34 m (68 dBi)"), (62.5, "stazione da 18 m (~62,5 dBi, ipotesi)")):
    print(f"   Con {nome}:")
    print("   Rate        Gt necessario (dBi)   tipo di antenna            HPBW se parabola (gradi)")
    for rb in (1e3, 1e4, 1e5, 1e6, 1e7, 1e8):
        need = 3 + 2.5 + 10 * math.log10(rb) + N0 - 10 - gr + fspl(d, f) + 3
        if need < 3:
            tipo, hp = "omnidirezionale / patch", "n/d (quasi omni)"
        else:
            Dm = (C / f) / math.pi * math.sqrt(10 ** (need / 10) / 0.55)
            tipo, hp = f"parabola D = {Dm:4.2f} m", f"{hpbw(Dm, f):6.1f}"
        print(f"   {rb:9.0f}   {need:14.1f}          {tipo:26}  {hp}")
print("\n3) Perche' non basta il puntamento fisso")
print(f"   La Terra sottende circa {math.degrees(12742/384400):.1f} gradi; la librazione la sposta di circa +-6,7 gradi (lat) e +-7,9 gradi (lon).")
print("   Con un'antenna a HPBW stretta servono gimbal e inseguimento; con HPBW > ~30 gradi basta un montaggio fisso ma il guadagno e' ~15 dBi o meno.")
for hp in (10, 20, 30, 60):
    print(f"   HPBW {hp:3d} gradi -> guadagno circa {10*math.log10(30000/hp**2):5.1f} dBi (formula 30000/HPBW^2, grezza)")
