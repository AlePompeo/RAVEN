# SPDX-License-Identifier: Apache-2.0
"""Rigenera le mappe dei corpi celesti e il cielo stellato (docs/design/credits.md).

Sorgenti (scaricate a mano in SRC, verificate prima del download, vedi credits.md):
  NASA SVS 4720 CGI Moon Kit: lroc_color_16bit_srgb_4k.tif, ldem_16_uint.tif
  NASA Earth Observatory Blue Marble NG (dicembre 2004, topografia e batimetria): world.topo.bathy.200412.3x5400x2700.jpg
  NASA 3D Resources (github.com/nasa/NASA-3D-Resources), Images and Textures/Mars: Mars.jpg
  NASA SDO AIA 304: 20261001_000830_2048_0304.jpg (sdo.gsfc.nasa.gov/assets/img/browse/2026/10/01/)
  NASA SVS 4851 Deep Star Maps 2020: starmap_2020_4k.exr

Requisiti solo di sviluppo: ImageMagick 7 (`magick`, con WebP ed EXR) e numpy.
Uso: .venv/bin/python docs/design/build-bodies.py SRC
"""

import base64
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "frontend/src/assets/bodies"
WORK = SRC / "work"


SIDECARS = {
    "moon": (
        "NASA Scientific Visualization Studio (public domain)",
        (
            'Derivato da NASA SVS 4720 "CGI Moon Kit" (https://svs.gsfc.nasa.gov/4720): lroc_color_16bit_srgb_4k.tif\n'
            "(LROC WAC) e ldem_16_uint.tif (LOLA). Credito: NASA's Scientific Visualization Studio."
        ),
    ),
    "earth": (
        "NASA Earth Observatory (public domain)",
        (
            "Derivato da NASA Blue Marble: Next Generation, dicembre 2004, con topografia e batimetria\n"
            "(world.topo.bathy.200412.3x5400x2700.jpg). Credito: NASA Earth Observatory."
        ),
    ),
    "mars": (
        "NASA (public domain)",
        (
            "Derivato da NASA 3D Resources, Images and Textures/Mars/Mars.jpg (repository nasa/NASA-3D-Resources),\n"
            '"free and without copyright" secondo il README del repository.'
        ),
    ),
    "sun": (
        "NASA/SDO and the AIA, EVE, and HMI science teams",
        (
            "Derivato da SDO AIA 304 (He II, 30,4 nm), 2026-10-01 00:08:30 UT, immagine di consultazione\n"
            "20261001_000830_2048_0304.jpg. Credito richiesto: Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams."
        ),
    ),
    "stars": (
        "NASA Scientific Visualization Studio (public domain)",
        (
            'Derivato da NASA SVS 4851 "Deep Star Maps 2020" (https://svs.gsfc.nasa.gov/4851): starmap_2020_4k.exr.\n'
            "Credito: NASA's Scientific Visualization Studio."
        ),
    ),
}


def magick(*args: str) -> None:
    subprocess.run(["magick", *args], check=True)


def raw_gray16(src: Path, w: int, h: int) -> np.ndarray:
    tmp = WORK / f"{src.stem}-{w}.gray"
    magick(
        str(src),
        "-channel",
        "R",
        "-separate",
        "+channel",
        "-filter",
        "Lanczos",
        "-resize",
        f"{w}x{h}!",
        "-depth",
        "16",
        "-endian",
        "MSB",
        f"gray:{tmp}",
    )
    return np.fromfile(tmp, dtype=">u2").astype(np.float64).reshape(h, w)


def raw_rgb_float(src: Path, w: int, h: int, extra: tuple[str, ...] = ()) -> np.ndarray:
    tmp = WORK / f"{src.stem}-{w}.rgb"
    magick(str(src), *extra, "-resize", f"{w}x{h}!", "-depth", "16", "-endian", "MSB", f"rgb:{tmp}")
    return np.fromfile(tmp, dtype=">u2").astype(np.float64).reshape(h, w, 3) / 65535.0


def write_webp(arr: np.ndarray, name: str, quality: int, dither: bool = False) -> int:
    """arr float 0..1 (HxW o HxWx3) -> WebP; dithering a ±0.5 LSB contro il banding sui gradienti scuri."""
    rng = np.random.default_rng(1969)
    a = arr * 255.0
    if dither:
        a = a + rng.uniform(-0.5, 0.5, a.shape)
    a = np.clip(np.round(a), 0, 255).astype(np.uint8)
    if a.ndim == 2:
        a = np.repeat(a[:, :, None], 3, axis=2)
    h, w, _ = a.shape
    ppm = WORK / f"{name}.ppm"
    with open(ppm, "wb") as f:
        f.write(f"P6 {w} {h} 255\n".encode())
        f.write(a.tobytes())
    out = OUT / name
    magick(str(ppm), "-quality", str(quality), "-define", "webp:method=6", str(out))
    return out.stat().st_size


def placeholder(name: str) -> str:
    """Anteprima minuscola (32x16) inline per il blur-up."""
    tmp = WORK / f"ph-{name}"
    magick(str(OUT / name), "-resize", "32x16!", "-quality", "40", str(tmp))
    return "data:image/webp;base64," + base64.b64encode(tmp.read_bytes()).decode()


def render_moon(src: Path, size: int, light: tuple[float, float, float]) -> int:
    """Disco lunare ortografico (vista dal lato visibile) con trasparenza fuori dal disco."""
    col = raw_rgb_float(src / "lroc_color_16bit_srgb_4k.tif", 2048, 1024)
    km = (
        (raw_gray16(src / "ldem_16_uint.tif", 2048, 1024) - 20000.0) / 2000.0 * 3.0
    )  # rilievo esagerato 3x
    h, w = km.shape
    y, x = np.mgrid[0:size, 0:size]
    nx = (x + 0.5) / size * 2 - 1
    ny = 1 - (y + 0.5) / size * 2
    r2 = nx * nx + ny * ny
    inside = r2 < 1
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    lon = np.arctan2(nx, nz)
    lat = np.arcsin(np.clip(ny, -1, 1))
    u = np.clip(((lon / (2 * np.pi) + 0.5) * w).astype(int), 0, w - 1)
    v = np.clip(((0.5 - lat / np.pi) * h).astype(int), 0, h - 1)
    dx = 2 * np.pi * 1737.4 / w * np.maximum(0.05, np.cos(lat))
    dy = np.pi * 1737.4 / h
    se = np.clip((km[v, (u + 1) % w] - km[v, (u - 1) % w]) / (2 * dx), -0.6, 0.6)
    sn = np.clip(
        (km[np.clip(v - 1, 0, h - 1), u] - km[np.clip(v + 1, 0, h - 1), u]) / (2 * dy), -0.6, 0.6
    )
    cl = np.maximum(np.sqrt(nx * nx + nz * nz), 1e-6)
    sl, cL = nx / cl, nz / cl
    px, py, pz = nx - se * cL + sn * ny * sl, ny - sn * cl, nz + se * sl + sn * ny * cL
    n = np.sqrt(px * px + py * py + pz * pz)
    px, py, pz = px / n, py / n, pz / n
    L = np.array(light) / np.linalg.norm(light)
    mu0g = nx * L[0] + ny * L[1] + nz * L[2]
    mu0 = np.where(mu0g < -0.05, 0, np.maximum(0, px * L[0] + py * L[1] + pz * L[2]))
    mu = np.maximum(0.02, pz)
    b = np.where(mu0 > 0, 0.62 * (2 * mu0 / (mu0 + mu)) * 0.5 + 0.38 * mu0, 0) * 0.92 + 0.012
    lin = np.power(col[v, u], 2.2) * b[:, :, None]
    rgb = np.power(np.clip(lin, 0, 1), 1 / 2.2)
    rr = np.sqrt(r2)
    alpha = np.clip((1 - rr) * size / 1.5, 0, 1) * inside
    rgba = np.dstack([rgb, alpha])
    raw = WORK / "moon-render.rgba"
    np.clip(np.round(rgba * 255), 0, 255).astype(np.uint8).tofile(raw)
    out = OUT / f"moon-crescent-{size}.webp"
    magick(
        "-size",
        f"{size}x{size}",
        "-depth",
        "8",
        f"rgba:{raw}",
        "-quality",
        "80",
        "-define",
        "webp:alpha-quality=90",
        str(out),
    )
    return out.stat().st_size


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    report: dict[str, dict] = {}

    # --- Luna: colore LROC (TIFF 16 bit sRGB 4k -> 2k e 1k) ---
    for w, q in ((2048, 82), (1024, 82)):
        col = raw_rgb_float(SRC / "lroc_color_16bit_srgb_4k.tif", w, w // 2)
        name = f"moon-color-{w // 1024}k.webp"
        report[name] = {"bytes": write_webp(col, name, q)}

    # --- Luna: rilievo LOLA (uint16 in mezzi metri, offset +20000) -> 8 bit normalizzato ---
    for w in (2048, 1024):
        hm = raw_gray16(SRC / "ldem_16_uint.tif", w, w // 2)
        km = (hm - 20000.0) / 2000.0  # chilometri rispetto a 1737.4 km
        lo, hi = float(km.min()), float(km.max())
        name = f"moon-height-{w // 1024}k.webp"
        report[name] = {
            "bytes": write_webp((km - lo) / (hi - lo), name, 88, dither=False),
            "km_min": lo,
            "km_max": hi,
        }

    # --- Terra: Blue Marble NG dicembre 2004 ---
    for w, q in ((2048, 80), (1024, 80)):
        col = raw_rgb_float(SRC / "world.topo.bathy.200412.3x5400x2700.jpg", w, w // 2)
        name = f"earth-color-{w // 1024}k.webp"
        report[name] = {"bytes": write_webp(col, name, q)}

    # --- Marte: mappa a colori NASA 3D Resources (1440x720, non ingrandita) ---
    for w, q in ((1440, 84), (1024, 82)):
        col = raw_rgb_float(SRC / "Mars.jpg", w, w // 2)
        name = f"mars-color-{'1k' if w == 1024 else '1440'}.webp"
        report[name] = {"bytes": write_webp(col, name, q)}

    # --- Sole: SDO AIA 304, ritaglio centrato sul disco, fuori da 1.25 R tutto nero (via la scritta) ---
    sun = raw_rgb_float(SRC / "20261001_000830_2048_0304.jpg", 2048, 2048)
    # disco: baricentro e raggio equivalente della zona > 0.15, escluso un bordo di 64 px (la scritta in basso)
    lum = sun.mean(axis=2)[64:1984, 64:1984]
    m = lum > 0.15
    ys, xs = np.nonzero(m)
    cy, cx = ys.mean() + 64, xs.mean() + 64
    r = float(np.sqrt(m.sum() / np.pi))
    yy, xx = np.mgrid[0:2048, 0:2048]
    d = np.hypot(yy - cy, xx - cx) / r
    sun = sun * np.clip((1.25 - d) / 0.12, 0, 1)[:, :, None]
    half = round(r * 1.25)
    crop = sun[int(cy) - half : int(cy) + half, int(cx) - half : int(cx) + half]
    tmp = WORK / "sun-crop.ppm"
    with open(tmp, "wb") as f:
        f.write(f"P6 {crop.shape[1]} {crop.shape[0]} 255\n".encode())
        f.write(np.clip(np.round(crop * 255), 0, 255).astype(np.uint8).tobytes())
    for w, q in ((1024, 80), (512, 80)):
        name = f"sun-aia304-{w}.webp"
        magick(str(tmp), "-resize", f"{w}x{w}", "-quality", str(q), str(OUT / name))
        report[name] = {"bytes": (OUT / name).stat().st_size, "disk_radius_fraction": 1 / 1.25}

    # --- Cielo: SVS Deep Star Maps 2020 (EXR lineare) -> tone mapping morbido, sRGB, dithering ---
    for w, q in ((3072, 70), (2048, 72)):
        st = raw_rgb_float(SRC / "starmap_2020_4k.exr", w, w // 2)
        st = 1.0 - np.exp(-st * 2.2)  # spalla morbida: stelle luminose senza bruciare
        st = np.power(st, 1 / 2.2)  # sRGB approssimato
        st = np.power(st, 1.7) * 0.9  # stelle deboli attenuate: cielo profondo, non rumoroso
        name = f"stars-{w}.webp"
        report[name] = {"bytes": write_webp(st, name, q)}

    # --- Luna renderizzata (falce) per la tile della home: stessa formula di frontend/src/viewports/shading.ts ---
    report["moon-crescent-720.webp"] = {"bytes": render_moon(SRC, 720, light=(-0.9, 0.12, -0.42))}

    for name in list(report):
        if name.endswith(".webp") and (
            "-2k" in name or "1440" in name or "1024" in name or "stars-3072" in name
        ):
            report[name]["placeholder"] = placeholder(name)
    for name in report:
        holder, text = SIDECARS[name.split("-")[0]]
        (OUT / f"{name}.license").write_text(
            f"SPDX-FileCopyrightText: {holder}\nSPDX-License-Identifier: LicenseRef-PublicDomain\n\n{text}\n"
            "Generato da docs/design/build-bodies.py; provenienza e verifica in docs/design/credits.md.\n"
        )
    ph = {k: v["placeholder"] for k, v in report.items() if "placeholder" in v}
    (REPO / "frontend/src/viewports/bodies/placeholders.ts").write_text(
        "// SPDX-License-Identifier: Apache-2.0\n"
        "// Generato da docs/design/build-bodies.py: anteprime 32x16 (blur-up) delle mappe principali.\n"
        "export const PLACEHOLDERS: Record<string, string> = " + json.dumps(ph, indent=2) + ";\n"
    )
    (WORK / "report.json").write_text(json.dumps(report, indent=2))
    for k, v in report.items():
        print(k, v["bytes"], {x: y for x, y in v.items() if x not in ("bytes", "placeholder")})


if __name__ == "__main__":
    main()
