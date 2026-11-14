"""
Grafico 3D di un'onda (strumenti open source: NumPy, SciPy, Matplotlib).
Intensita' |E|^2 di un'onda piana di banda X dopo una cresta a lama, propagata per 2 km con il metodo di Fresnel (FFT).
Asse x: distanza dalla cresta; asse y: altezza sopra la linea di vista; asse z: intensita' relativa.
Uso: python onda_3d.py  -> onda_3d_diffrazione.png
"""
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
LAM, N, DY = 0.0357, 2 ** 14, 0.1
y = (np.arange(N) - N // 2) * DY; fy = np.fft.fftfreq(N, DY)
E = np.ones(N, complex); E[y <= 0] = 0
dx = 20.0; xs, rows = [], []
for k in range(1, 101):
    E = np.fft.ifft(np.fft.fft(E) * np.exp(-1j * np.pi * LAM * dx * fy ** 2))
    if k % 2 == 0:
        sel = (y >= -40) & (y <= 40); xs.append(k * dx); rows.append(np.abs(E[sel]) ** 2)
Z = np.array(rows); Y = y[(y >= -40) & (y <= 40)]; X = np.array(xs)
fig = plt.figure(figsize=(9, 6)); ax = fig.add_subplot(111, projection="3d")
Xg, Yg = np.meshgrid(Y[::10], X)
ax.plot_surface(Xg, Yg, Z[:, ::10], cmap="viridis", linewidth=0, antialiased=True)
ax.set_xlabel("altezza sulla linea di vista (m)"); ax.set_ylabel("distanza dalla cresta (m)"); ax.set_zlabel("intensita' relativa")
ax.set_title("Diffrazione di un'onda in banda X oltre una cresta (simulazione di Fresnel)")
fig.tight_layout(); fig.savefig("onda_3d_diffrazione.png", dpi=130); print("salvato onda_3d_diffrazione.png", Z.shape)
