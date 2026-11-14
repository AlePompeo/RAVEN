# SPDX-License-Identifier: Apache-2.0
"""Rigenera gli asset auto-ospitati dell'interfaccia (docs/design/design-system.md).

- HB Sans: sottoinsieme latino di Mona Sans (OFL 1.1), assi wght 300-700 / wdth 100-125, rinominato
  perché "Mona" è un Reserved Font Name.
- Ritagli di NASA AS08-14-2383 (Earthrise, pubblico dominio) in WebP (+ JPEG di ripiego).

Requisiti (solo sviluppo, non dipendenze del progetto): fonttools, brotli, Pillow.
Sorgenti scaricate a mano in WORK/fontdl e WORK/imgdl:
  https://raw.githubusercontent.com/google/fonts/main/ofl/monasans/MonaSans%5Bwdth,wght%5D.ttf -> MonaSans.ttf
  https://raw.githubusercontent.com/google/fonts/main/ofl/monasans/OFL.txt -> MonaSans-OFL.txt
  https://images-assets.nasa.gov/image/as08-14-2383/as08-14-2383~orig.jpg -> earthrise-orig.jpg
Uso: python3 docs/design/build-assets.py WORK
"""

import subprocess
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

TMP = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
REPO = Path(__file__).resolve().parents[2]
FONT_OUT = REPO / "frontend/src/assets/fonts"
IMG_OUT = REPO / "frontend/src/assets/media"
UNICODES = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
    "U+2000-206F,U+20AC,U+2122,U+2212,U+2215,U+2248,U+2264-2265"
)
FAMILY = "HB Sans"


def font() -> None:
    FONT_OUT.mkdir(parents=True, exist_ok=True)
    work = TMP / "fontout"
    work.mkdir(parents=True, exist_ok=True)
    limited = work / "MonaSans-hx.ttf"
    subprocess.run(
        [
            sys.executable,
            "-P",
            "-m",
            "fontTools.varLib.instancer",
            str(TMP / "fontdl/MonaSans.ttf"),
            "wght=300:700",
            "wdth=100:125",
            "-o",
            str(limited),
        ],
        check=True,
        capture_output=True,
    )
    f = TTFont(limited)
    name = f["name"]
    # OFL 1.1 sez. 3: una versione modificata (subset) non può usare il Reserved Font Name "Mona".
    for rec in list(name.names):
        if rec.nameID in (1, 3, 4, 6, 16, 17, 21, 22, 25):
            text = rec.toUnicode()
            if rec.nameID in (1, 16, 21):
                new = FAMILY
            elif rec.nameID == 4:
                new = FAMILY + " Light"
            elif rec.nameID == 3:
                new = "2.000;HBSans-Light"
            elif rec.nameID == 6:
                new = "HBSans-Light"
            elif rec.nameID == 25:
                new = "HBSans"
            else:
                new = (
                    text.replace("Mona Sans", FAMILY)
                    .replace("MonaSans", "HBSans")
                    .replace("Mona", "HB")
                )
            rec.string = new
    for rec in name.names:
        assert "Mona" not in rec.toUnicode() or rec.nameID in (0, 13, 14), (
            rec.nameID,
            rec.toUnicode(),
        )
    # STAT/fvar instance names restano descrittivi (Regular, Bold...): nessun RFN.
    renamed = work / "HBSans.ttf"
    f.save(renamed)
    subprocess.run(
        [
            "pyftsubset",
            str(renamed),
            f"--unicodes={UNICODES}",
            "--layout-features=kern,liga,calt,tnum,lnum,case",
            "--flavor=woff2",
            f"--output-file={FONT_OUT / 'hb-sans-latin.woff2'}",
        ],
        check=True,
        capture_output=True,
    )
    (FONT_OUT / "OFL.txt").write_bytes((TMP / "fontdl/MonaSans-OFL.txt").read_bytes())
    print("font", (FONT_OUT / "hb-sans-latin.woff2").stat().st_size)


def images() -> None:
    from PIL import Image

    IMG_OUT.mkdir(parents=True, exist_ok=True)
    im = Image.open(TMP / "imgdl/earthrise-orig.jpg").convert("RGB")
    crops = {
        # wide: Terra al ~23% dall'alto, orizzonte nel terzo inferiore
        "wide": (0, 1150, 3000, 2900),
        # portrait (telefoni, palco a tutta altezza): cielo in alto per il testo, Terra al centro
        "portrait": (900, 600, 2500, 3000),
    }
    widths = {"wide": (1280, 1920), "portrait": (860,)}
    for key, box in crops.items():
        c = im.crop(box)
        for w in widths[key]:
            h = round(c.height * w / c.width)
            r = c.resize((w, h), Image.LANCZOS)
            out = IMG_OUT / f"earthrise-{key}-{w}.webp"
            r.save(out, "WEBP", quality=74, method=6)
            print(out.name, r.size, out.stat().st_size)
        if key == "wide":
            r = c.resize((1280, round(c.height * 1280 / c.width)), Image.LANCZOS)
            out = IMG_OUT / "earthrise-wide-1280.jpg"
            r.save(out, "JPEG", quality=72, optimize=True, progressive=True)
            print(out.name, r.size, out.stat().st_size)


if __name__ == "__main__":
    font()
    images()
