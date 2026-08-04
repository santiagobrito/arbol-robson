#!/usr/bin/env python3
"""
Aplica correcciones de filiacion al GEDCOM: mueve a una persona de la familia
en la que esta como hijo/a a la que le corresponde.

Cada correccion toca tres sitios, y hacerlo a mano se olvida uno:
  - el `1 FAMC` del individuo
  - el `1 CHIL` de la familia de la que sale
  - el `1 CHIL` de la familia a la que entra

Uso:
    python3 scripts/corregir-filiacion.py            # muestra que haria
    python3 scripts/corregir-filiacion.py --aplicar  # lo escribe

Las correcciones estan abajo, en CORRECCIONES, con su justificacion. Verificadas
contra la copia archivada de la web original (scripts/verificar-contra-original.py).
"""

import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GEDCOM = RAIZ / "data" / "arbol-robson.ged"

# (id_persona, familia_actual, familia_correcta, motivo)
CORRECCIONES = [
    (
        "I2132", "F676", "F681",
        "Jose Martin Brito Devoto figuraba como hijo de Ernesto Argentino Devoto "
        "y Elizabeth Monroe Manzano, o sea como hermano de su propia madre. "
        "El original lo lista bajo Elizabeth Beatriz Devoto + Juan Ramon Brito.",
    ),
    (
        "I2131", "F681", "F684",
        "Marcos Brito Devoto figuraba como hermano de Eduardo Santiago. "
        "El original lo lista bajo Eduardo Santiago Brito Devoto + Marta Lier.",
    ),
]


def cargar():
    texto = GEDCOM.read_text(encoding="utf-8")
    registros = re.split(r"\n(?=0 @)", texto)
    return texto, registros


def nombre_de(registros, ident):
    for r in registros:
        if r.startswith(f"0 @{ident}@ INDI"):
            m = re.search(r"\n1 NAME (.*)", r)
            return m.group(1).replace("/", "").strip() if m else ident
    return ident


def aplicar(texto, persona, origen, destino):
    """Devuelve (texto_nuevo, lista_de_cambios_realizados)."""
    cambios = []

    # 1. FAMC del individuo
    patron_indi = re.compile(
        rf"(0 @{persona}@ INDI\n(?:(?!\n0 @).)*?)\n1 FAMC @{origen}@", re.S)
    texto, n = patron_indi.subn(rf"\g<1>\n1 FAMC @{destino}@", texto, count=1)
    if n:
        cambios.append(f"{persona}: FAMC {origen} -> {destino}")

    # 2. Quitar el CHIL de la familia de origen
    patron_quitar = re.compile(
        rf"(0 @{origen}@ FAM\n(?:(?!\n0 @).)*?)\n1 CHIL @{persona}@", re.S)
    texto, n = patron_quitar.subn(r"\g<1>", texto, count=1)
    if n:
        cambios.append(f"{origen}: quitado CHIL {persona}")

    # 3. Anadir el CHIL a la familia de destino, detras del ultimo CHIL que
    #    ya tenga (para que el orden de hermanos siga teniendo sentido).
    m = re.search(rf"0 @{destino}@ FAM\n(?:(?!\n0 @).)*", texto, re.S)
    if m:
        bloque = m.group(0)
        if f"\n1 CHIL @{persona}@" not in bloque:
            chils = list(re.finditer(r"\n1 CHIL @\w+@", bloque))
            corte = chils[-1].end() if chils else len(bloque.rstrip())
            nuevo = bloque[:corte] + f"\n1 CHIL @{persona}@" + bloque[corte:]
            texto = texto[:m.start()] + nuevo + texto[m.end():]
            cambios.append(f"{destino}: anadido CHIL {persona}")

    return texto, cambios


def main():
    escribir = "--aplicar" in sys.argv
    texto, registros = cargar()

    todos = []
    for persona, origen, destino, motivo in CORRECCIONES:
        print(f"\n{nombre_de(registros, persona)}  [{persona}]")
        print(f"  {origen} -> {destino}")
        print(f"  {motivo}")
        texto, cambios = aplicar(texto, persona, origen, destino)
        for c in cambios:
            print(f"    · {c}")
        if not cambios:
            print("    · sin cambios (¿ya estaba corregido?)")
        todos += cambios

    print(f"\n{len(todos)} modificaciones en total.")

    if not escribir:
        print("\nEn seco. Para escribirlo: python3 scripts/corregir-filiacion.py --aplicar")
        return 0

    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    copia = GEDCOM.with_suffix(f".ged.bak-{sello}")
    shutil.copy2(GEDCOM, copia)
    GEDCOM.write_text(texto, encoding="utf-8")
    print(f"Escrito. Copia de seguridad: {copia.name}")
    print("Ahora: npm run check:gedcom  y despues subirlo al volumen (ver README).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
