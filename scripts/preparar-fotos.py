#!/usr/bin/env python3
"""
Prepara las fotos del arbol: miniaturas + manifiesto.

COMO SE USA
Deja los originales en `data/fotos-originales/`, con el nombre de la persona o
su identificador:

    data/fotos-originales/Hugh Robson.jpg
    data/fotos-originales/I2788.jpg          <- equivalente

y ejecuta:

    python3 scripts/preparar-fotos.py

Genera `data/fotos/<ID>.jpg` (miniaturas) y `data/fotos.json` (el manifiesto que
lee la web). Los originales NO se despliegan: se quedan en tu disco.

POR QUE MINIATURAS Y NO LAS ORIGINALES
Una vista del arbol puede dibujar hasta 400 tarjetas. A 200 kB por foto serian
80 MB en el movil de quien lo abra. Topola pinta las fotos a 70x90 puntos, asi
que se generan a 140x180 (el doble, para pantallas retina): ~10 kB cada una.

POR QUE SE BORRAN LOS METADATOS
Una foto sacada con el movil lleva EXIF: coordenadas GPS, fecha, modelo del
telefono. Publicar eso de personas vivas es peor que publicar su fecha de
nacimiento. Al reescribir la imagen con Pillow, el EXIF no se copia.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Falta Pillow.  pip install Pillow")

RAIZ = Path(__file__).resolve().parent.parent
ORIGINALES = RAIZ / "data" / "fotos-originales"
DESTINO = RAIZ / "data" / "fotos"
MANIFIESTO = RAIZ / "data" / "fotos.json"
GEDCOM = RAIZ / "data" / "arbol-robson.ged"

ANCHO, ALTO = 140, 180        # 2x de los 70x90 a los que Topola las dibuja
CALIDAD = 82
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".bmp"}


def normalizar(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def leer_personas():
    """{nombre_normalizado: [ids]} y el conjunto de ids validos."""
    porn, ids = {}, set()
    for reg in re.split(r"\n(?=0 @)", GEDCOM.read_text(encoding="utf-8")):
        m = re.match(r"0 @(I\w+)@ INDI", reg.split("\n")[0])
        if not m:
            continue
        ids.add(m.group(1))
        nom = re.search(r"\n1 NAME (.*)", reg)
        if nom:
            porn.setdefault(normalizar(nom.group(1).replace("/", "")), []).append(m.group(1))
    return porn, ids


def resolver(stem, porn, ids):
    """Del nombre del archivo al identificador de la persona."""
    if stem in ids:
        return stem, None
    candidatos = porn.get(normalizar(stem), [])
    if len(candidatos) == 1:
        return candidatos[0], None
    if not candidatos:
        return None, "no hay nadie con ese nombre en el arbol"
    return None, f"el nombre es ambiguo, coincide con {len(candidatos)}: {', '.join(candidatos)}"


def miniatura(origen, destino):
    """Recorta al centro en proporcion 7:9 y reescribe sin metadatos."""
    with Image.open(origen) as img:
        img = ImageOps.exif_transpose(img)      # respeta la orientacion del movil
        img = img.convert("RGB")
        # ImageOps.fit recorta lo que sobra en vez de deformar la cara
        img = ImageOps.fit(img, (ANCHO, ALTO), method=Image.LANCZOS, centering=(0.5, 0.4))
        img.save(destino, "JPEG", quality=CALIDAD, optimize=True, progressive=True)
    return destino.stat().st_size


def main():
    if not GEDCOM.exists():
        sys.exit(f"No encuentro el GEDCOM en {GEDCOM}")

    ORIGINALES.mkdir(parents=True, exist_ok=True)
    DESTINO.mkdir(parents=True, exist_ok=True)

    porn, ids = leer_personas()
    manifiesto, problemas = {}, []

    fuentes = sorted(p for p in ORIGINALES.iterdir()
                     if p.is_file() and p.suffix.lower() in EXTENSIONES)
    if not fuentes:
        print(f"No hay nada en {ORIGINALES.relative_to(RAIZ)}.")
        print("Deja ahi las fotos con el nombre de la persona (o su ID) y vuelve a ejecutar.")

    for src in fuentes:
        ident, error = resolver(src.stem, porn, ids)
        if error:
            problemas.append((src.name, error))
            continue
        salida = DESTINO / f"{ident}.jpg"
        try:
            peso = miniatura(src, salida)
        except Exception as exc:
            problemas.append((src.name, f"no se pudo procesar: {exc}"))
            continue
        manifiesto[ident] = salida.name
        print(f"  {src.name:38} -> {salida.name}  ({peso // 1024} kB)")

    # Miniaturas que ya estaban y cuyo original ya no esta: se conservan, pero
    # se avisa. Borrar en silencio una foto que alguien mando es peor que dejarla.
    for previa in DESTINO.glob("I*.jpg"):
        if previa.stem not in manifiesto and previa.stem in ids:
            manifiesto[previa.stem] = previa.name
            print(f"  (se conserva {previa.name}: no esta su original)")

    MANIFIESTO.write_text(json.dumps(manifiesto, indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")

    print()
    print(f"{len(manifiesto)} fotos en el manifiesto -> {MANIFIESTO.relative_to(RAIZ)}")
    if problemas:
        print(f"\n{len(problemas)} sin asignar:")
        for nombre, motivo in problemas:
            print(f"  {nombre}: {motivo}")
        print("\nRenombra el archivo con el nombre exacto que aparece en el arbol,")
        print("o directamente con el identificador (por ejemplo I2788.jpg).")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
