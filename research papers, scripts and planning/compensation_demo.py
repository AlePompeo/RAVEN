"""
GrazingLink: 'tabelle di compensazione' e controllo del margine.
A) Multi-fidelity: modello veloce (bordo a lama esatto) + correzione appresa da un simulatore piu' fedele (propagazione
   d'onda split-step su una cresta ARROTONDATA). La correzione e' una tabella R(nu, raggio) che si completa con un
   processo gaussiano (GP) e di cui si cercano i punti anomali (picchi).
B) Compensatore del bit rate: sceglie il rate massimo con margine previsto >= margine di sicurezza, tarato per un
   obiettivo di probabilita' di interruzione. NON e' reinforcement learning: e' feedforward + margine statistico.
Uso: python compensation_demo.py     (circa un minuto)
"""
import math, numpy as np
from scipy.special import fresnel
from scipy.interpolate import griddata
from sklearn.gaussian_process import GaussianProcessRegressor as GPR
from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel as Ck
rng = np.random.default_rng(3)
LAM, DIST, N, DY = 0.0357, 2000.0, 2 ** 14, 0.1
y = (np.arange(N) - N // 2) * DY; fy = np.fft.fftfreq(N, DY)

def knife_exact_db(nu):
    S, C = fresnel(nu); A = (0.5 - C) - 1j * (0.5 - S)
    return -20 * np.log10(np.abs((1 + 1j) / 2 * A))

def hi_fidelity_loss(R, dx=2.0):
    """Perdita (dB) a distanza DIST da una cresta di raggio R (R=0: lama), onda piana incidente, split-step di Fresnel."""
    E = np.ones(N, complex)
    if R == 0:
        E[y <= 0] = 0; x_end = 0.0
    else:
        w = math.sqrt(2 * R * 20.0)
        for x in np.arange(-w, w + dx, dx):
            E[y < -x * x / (2 * R)] = 0
            E = np.fft.ifft(np.fft.fft(E) * np.exp(-1j * math.pi * LAM * dx * fy ** 2))
        x_end = w + dx
    E = np.fft.ifft(np.fft.fft(E) * np.exp(-1j * math.pi * LAM * (DIST - x_end) * fy ** 2))
    I = np.abs(E) ** 2; I0 = I[(y > 300) & (y < 600)].mean()
    return -10 * np.log10(I / I0)

nus = np.round(np.arange(-1.5, 3.01, 0.05), 2); radii = [0, 5, 10, 20, 50, 100, 200, 400]
rows = []
for R in radii:
    L = hi_fidelity_loss(R)
    yo = -nus * math.sqrt(LAM * DIST / 2)
    hi = np.interp(yo, y, L)
    for nu, h in zip(nus, hi): rows.append((nu, math.log10(R + 1), R, h - knife_exact_db(nu)))
T = np.array(rows)     # colonne: nu, log10(R+1), R, residuo (dB)
print("A) Tabella di correzione: residuo = perdita 'vera' (cresta arrotondata) - perdita bordo a lama")
for R in radii:
    m = (T[:, 2] == R); r = T[m, 3]
    print(f"   raggio {R:4d} m: residuo medio {r.mean():6.2f} dB, minimo {r.min():6.2f}, massimo {r.max():6.2f}")

# completamento delle celle mancanti (25%)
X = T[:, :2]; z = T[:, 3]; n = len(z); idx = rng.permutation(n); miss = idx[: n // 4]; keep = idx[n // 4:]
gp = GPR(Ck(1.0) * RBF([0.5, 0.8]) + WhiteKernel(1e-3), normalize_y=True, n_restarts_optimizer=1).fit(X[keep], z[keep])
pred_gp = gp.predict(X[miss]); pred_lin = griddata(X[keep], z[keep], X[miss], method="linear")
ok = ~np.isnan(pred_lin)
rm = lambda a, b: math.sqrt(np.mean((a - b) ** 2))
print(f"\n   Celle mancanti ricostruite: {len(miss)} su {n}")
print(f"   RMSE senza compensazione (residuo = 0):   {rm(z[miss], 0):.2f} dB")
print(f"   RMSE interpolazione lineare:              {rm(z[miss][ok], pred_lin[ok]):.2f} dB")
print(f"   RMSE processo gaussiano (compensazione):  {rm(z[miss], pred_gp):.2f} dB")

# punti anomali: residuo del GP addestrato su tutte le celle
gp_all = GPR(Ck(1.0) * RBF([0.5, 0.8]) + WhiteKernel(1e-3), normalize_y=True).fit(X, z)
res = z - gp_all.predict(X); mad = 1.4826 * np.median(np.abs(res - np.median(res)))
flag = np.abs(res - np.median(res)) > 4 * mad
print(f"\n   Punti anomali (> 4 MAD): {flag.sum()} su {n}; con nu < -0,78: {(flag & (T[:,0] < -0.78)).sum()}, con nu >= -0,78: {(flag & (T[:,0] >= -0.78)).sum()}")
print("   (le oscillazioni di Fresnel per nu < -0,78 non sono catturate da una curva liscia: vanno trattate come incertezza)")
np.savetxt("tabella_compensazione.csv", np.c_[T[:, 2], T[:, 0], T[:, 3], gp_all.predict(X)], delimiter=",",
           header="raggio_m,nu,residuo_simulato_dB,residuo_GP_dB", comments="")

# ---------------- B) compensatore del bit rate ----------------
print("\nB) Compensatore del bit rate (feedforward + margine statistico)")
C0 = 299792458.0
def two_ray_db(eps_deg, h, lam, er=3.7 - 0.01j, sig=0.25):
    e = np.radians(eps_deg); s = np.sin(e); q = np.sqrt(er - np.cos(e) ** 2)
    r = ((s - q) / (s + q)) * np.exp(-(4 * math.pi * sig * s / lam) ** 2)
    return 20 * np.log10(np.abs(1 + r * np.exp(-1j * 4 * math.pi * h * s / lam)) + 1e-9)
def earth_el(td, lat=-86.0, lon=0.12):
    b = np.radians(6.68) * np.sin(2 * np.pi * td / 27.21 + 1); l = np.radians(7.9) * np.sin(2 * np.pi * td / 27.55)
    e = np.stack([np.cos(b) * np.cos(l), np.cos(b) * np.sin(l), np.sin(b)], -1)
    p, la = np.radians(lat), np.radians(lon)
    return np.degrees(np.arcsin(np.clip(e @ np.array([math.cos(p) * math.cos(la), math.cos(p) * math.sin(la), math.sin(p)]), -1, 1)))
f = 8.4e9; lam = C0 / f
td = np.arange(0, 30, 15 / 1440); el = earth_el(td)
th_h, d_ridge = 0.9, 2000.0
nu = -(el - th_h) * np.pi / 180 * np.sqrt(2 * d_ridge / lam)
J = knife_exact_db(nu)
fspl = 20 * math.log10(4 * math.pi * 384400e3 * f / C0)
def margin(rate, h_mast=2.0):
    g2 = two_ray_db(np.maximum(el, 0.05), h_mast, lam)
    return 10 + 15 + 68 - fspl - 3 - J + g2 - (-228.6 + 10 * math.log10(30)) - 10 * np.log10(rate) - 2.5
rates = np.array([1e4, 3e4, 1e5, 3e5, 1e6, 3e6])
pred = np.stack([margin(r, 2.0) for r in rates], 1)               # modello (mast 2,0 m)
truth_base = np.stack([margin(r, 2.15) for r in rates], 1)        # 'realta''': mast 2,15 m (fasi diverse) + rumore
sigma = 1.5
print(f"   Sito simile a Malapert, X-band, antenna 15 dBi, cresta a 2 km e a {th_h} gradi; 30 giorni; incertezza non modellata sigma={sigma} dB + errore di fase del multipath")
print("   backoff (dB)   interruzioni (% del tempo con link dichiarato)   dati consegnati (relativi)")
vol_ref = None
for k, name in ((0, "0"), (1, "1 sigma"), (2.33, "2,33 sigma"), (3, "3 sigma")):
    back = k * sigma; chosen = np.zeros(len(td)); out = 0; declared = 0; vol = 0.0
    for i in range(len(td)):
        ok = np.where(pred[i] - back >= 0)[0]
        if len(ok) == 0: continue
        j = ok[-1]; declared += 1; tm = truth_base[i, j] + rng.normal(0, sigma)
        if tm < 0: out += 1
        else: vol += rates[j] * 15 * 60
    if vol_ref is None: vol_ref = vol
    print(f"   {name:12}   {100*out/max(declared,1):8.1f}                                   {vol/vol_ref:6.2f}")
