#!/usr/bin/env python3
"""
Compara el GEDCOM con la web original archivada y lista las discrepancias.

Por que existe: el GEDCOM se genero con `docs/parser-arbol-a-gedcom.py` a partir
del PDF, y ese PDF solo tenia SANGRIA para expresar la jerarquia. La sangria se
lee mal con facilidad, y de ahi salieron errores del tipo "persona colgada una
generacion mas arriba de la que le toca" (Jose Martin, Marcos...).

La copia archivada de la web (misma version 10z, 4 may 2015) trae la jerarquia
EXPLICITA en las clases `gen1..genN` de cada <li>, sin ambiguedad. Asi que la
web archivada es mejor fuente que el PDF, y este script la usa como referencia.

Uso:
    python3 scripts/verificar-contra-original.py

Salida: las personas cuyo padre/madre en el GEDCOM no coincide con el original.
No modifica nada. Para aplicar las correcciones: scripts/corregir-padres.py
"""

import html
import re
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGINAL = RAIZ / "docs" / "fuente-original-greywall-2017.html"
GEDCOM = RAIZ / "data" / "arbol-robson.ged"


# --------------------------------------------------------------------------
# 1. La web original
# --------------------------------------------------------------------------

def normalizar(texto: str) -> str:
    """Clave de comparacion: sin tildes, sin puntuacion, en minusculas."""
    import unicodedata
    t = unicodedata.normalize("NFD", texto)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9 ]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def leer_original():
    """
    Devuelve {clave_persona: (nombre, generacion, clave_del_padre_o_None)}.

    La jerarquia sale de la clase genN de cada <li>: el ascendiente de alguien de
    generacion N es la ultima persona vista de generacion N-1. Es una pila, y es
    fiable porque el nivel viene escrito en el propio HTML.
    """
    crudo = ORIGINAL.read_text(encoding="utf-8", errors="replace")

    # Cada <li class="genN"> abre una persona. El nombre es el texto hasta el
    # primer <br> o <em> (lo de despues son "Born:", "married ...", notas).
    patron = re.compile(r'<li class="gen(\d+)">(.*?)(?=<li class="gen\d+">|</ul>)',
                        re.S)

    personas = {}
    pila = {}          # generacion -> clave de la ultima persona vista
    duplicados = defaultdict(int)

    for m in patron.finditer(crudo):
        gen = int(m.group(1))
        bloque = m.group(2)

        # Nombre: primer trozo de texto del <li>, antes de <br>/<em>/<ul>
        cabecera = re.split(r"<br|<em|<ul", bloque, maxsplit=1)[0]
        nombre = html.unescape(re.sub(r"<[^>]+>", "", cabecera)).strip()
        nombre = re.sub(r"\s+", " ", nombre)
        if not nombre:
            continue

        # "Nombre (1937 - 2001)" -> nombre + anos, que sirven para desambiguar
        anios = re.search(r"\((.*?)\)", nombre)
        solo_nombre = re.sub(r"\s*\(.*", "", nombre).strip()
        clave_base = normalizar(solo_nombre)
        if not clave_base:
            continue

        clave = clave_base
        if anios:
            primer_anio = re.search(r"\d{4}", anios.group(1))
            if primer_anio:
                clave = f"{clave_base}|{primer_anio.group(0)}"

        # Homonimos sin fecha: se numeran para no pisarse entre si
        duplicados[clave] += 1
        if duplicados[clave] > 1:
            clave = f"{clave}#{duplicados[clave]}"

        padre = pila.get(gen - 1)
        personas[clave] = (solo_nombre, gen, padre)
        pila[gen] = clave
        # Al bajar de nivel, lo que hubiera por debajo ya no es ascendiente valido
        for g in list(pila):
            if g > gen:
                del pila[g]

    return personas


# --------------------------------------------------------------------------
# 2. El GEDCOM
# --------------------------------------------------------------------------

def leer_gedcom():
    crudo = GEDCOM.read_text(encoding="utf-8").replace("﻿", "")
    registros = re.split(r"\n(?=0 @)", crudo)

    indis, fams = {}, {}
    for r in registros:
        cabecera = r.split("\n")[0]
        mi = re.match(r"0 @(\w+)@ INDI", cabecera)
        mf = re.match(r"0 @(\w+)@ FAM", cabecera)
        if mi:
            nombre = re.search(r"\n1 NAME (.*)", r)
            nacimiento = re.search(r"\n1 BIRT\n(?:2 .*\n)*?2 DATE ([^\n]*)", r)
            anio = re.search(r"\d{4}", nacimiento.group(1)) if nacimiento else None
            indis[mi.group(1)] = {
                "nombre": nombre.group(1).replace("/", "").strip() if nombre else "",
                "anio": anio.group(0) if anio else None,
                "famc": (re.search(r"\n1 FAMC @(\w+)@", r) or [None]) and
                        (re.search(r"\n1 FAMC @(\w+)@", r).group(1)
                         if re.search(r"\n1 FAMC @(\w+)@", r) else None),
            }
        elif mf:
            padre = re.search(r"\n1 HUSB @(\w+)@", r)
            madre = re.search(r"\n1 WIFE @(\w+)@", r)
            fams[mf.group(1)] = {
                "padre": padre.group(1) if padre else None,
                "madre": madre.group(1) if madre else None,
                "hijos": re.findall(r"\n1 CHIL @(\w+)@", r),
            }
    return indis, fams


def clave_de(indi):
    base = normalizar(indi["nombre"])
    return f"{base}|{indi['anio']}" if indi["anio"] else base


# --------------------------------------------------------------------------
# 3. Clasificacion de la discrepancia
# --------------------------------------------------------------------------

TIPOS = {
    "GENERACION": "Colgado una generacion de mas: el padre real es HIJO de la "
                  "familia que el GEDCOM le asigna",
    "CONYUGE_FALTA": "El padre real es el conyuge, pero no esta registrado en "
                     "esa familia del GEDCOM",
    "NOMBRE": "Probable variante del mismo nombre (uno contiene al otro)",
    "OTRO": "Sin patron claro: revisar a mano",
}


def clasificar(padre_orig, padre_ged, famc, indis, fams, por_clave):
    n_orig = normalizar(padre_orig)
    n_ged = normalizar(padre_ged) if padre_ged else ""

    # Variante del mismo nombre: "Tomas Cowes" vs "Tomas Ricardo Cowes".
    # Por tokens, no por subcadena: los nombres del medio aparecen y desaparecen.
    if n_ged:
        t_orig, t_ged = set(n_orig.split()), set(n_ged.split())
        if t_orig <= t_ged or t_ged <= t_orig:
            return "NOMBRE"

    candidatos = por_clave.get(n_orig, [])
    pid = candidatos[0] if len(candidatos) == 1 else None

    if pid and famc and famc in fams:
        # ¿El padre real es descendiente de la familia asignada? Entonces la
        # persona cuelga por encima de donde le toca. Se mira hasta 3 niveles:
        # el error tipico es de uno, pero conviene cazar los encadenados.
        frontera = set(fams[famc]["hijos"])
        for _ in range(3):
            if pid in frontera:
                return "GENERACION"
            siguiente = set()
            for hijo in frontera:
                for fid, fam in fams.items():
                    if hijo in (fam["padre"], fam["madre"]):
                        siguiente.update(fam["hijos"])
            if not siguiente:
                break
            frontera = siguiente

    # La familia del GEDCOM tiene un solo conyuge registrado y el original
    # nombra a otra persona: falta el conyuge, que suele ser quien lleva la
    # sangre de la rama.
    if famc and famc in fams:
        if fams[famc]["padre"] is None or fams[famc]["madre"] is None:
            return "CONYUGE_FALTA"

    return "OTRO"


# --------------------------------------------------------------------------
# 4. Comparacion
# --------------------------------------------------------------------------

def main():
    if not ORIGINAL.exists():
        sys.exit(f"Falta la copia archivada: {ORIGINAL}\n"
                 "Se descarga del Internet Archive (ver README).")

    original = leer_original()
    indis, fams = leer_gedcom()

    # Indice del GEDCOM por clave, marcando los homonimos ambiguos
    por_clave = defaultdict(list)
    for iid, indi in indis.items():
        por_clave[clave_de(indi)].append(iid)

    discrepancias, ambiguos, sin_pareja = [], [], []

    for clave, (nombre, _gen, clave_padre) in original.items():
        clave_limpia = clave.split("#")[0]
        candidatos = por_clave.get(clave_limpia, [])

        if not candidatos:
            sin_pareja.append(nombre)
            continue
        if len(candidatos) > 1:
            ambiguos.append((nombre, candidatos))
            continue

        iid = candidatos[0]
        famc = indis[iid]["famc"]

        # Ascendiente segun el GEDCOM
        padre_ged = None
        if famc and famc in fams:
            pid = fams[famc]["padre"] or fams[famc]["madre"]
            if pid:
                padre_ged = indis[pid]["nombre"]

        # Ascendiente segun el original
        padre_orig = None
        if clave_padre:
            padre_orig = original[clave_padre][0]

        if padre_orig is None and padre_ged is None:
            continue

        # El original lista al ascendiente directo; el GEDCOM puede tener como
        # padre al conyuge de esa persona, que es igual de correcto.
        conyuges_ok = set()
        if famc and famc in fams:
            for rol in ("padre", "madre"):
                pid = fams[famc][rol]
                if pid:
                    conyuges_ok.add(normalizar(indis[pid]["nombre"]))

        if padre_orig and normalizar(padre_orig) not in conyuges_ok:
            discrepancias.append({
                "id": iid,
                "persona": nombre,
                "padre_gedcom": padre_ged or "(ninguno)",
                "padre_original": padre_orig,
                "famc": famc,
                "tipo": clasificar(padre_orig, padre_ged, famc, indis, fams, por_clave),
            })

    # ---------------- informe ----------------
    print(f"Personas en la web original : {len(original)}")
    print(f"Personas en el GEDCOM       : {len(indis)}")
    print(f"Sin equivalente en el GEDCOM: {len(sin_pareja)}")
    print(f"Nombres ambiguos (homonimos): {len(ambiguos)}")
    print(f"DISCREPANCIAS DE FILIACION  : {len(discrepancias)}")
    print()

    if discrepancias:
        por_tipo = defaultdict(list)
        for d in discrepancias:
            por_tipo[d["tipo"]].append(d)

        print("Reparto por tipo:")
        for tipo in ("GENERACION", "CONYUGE_FALTA", "NOMBRE", "OTRO"):
            if por_tipo[tipo]:
                print(f"  {tipo:14} {len(por_tipo[tipo]):4}   {TIPOS[tipo]}")
        print()

        for tipo in ("GENERACION", "CONYUGE_FALTA", "OTRO", "NOMBRE"):
            if not por_tipo[tipo]:
                continue
            print("=" * 78)
            print(f"{tipo}  ({len(por_tipo[tipo])})  —  {TIPOS[tipo]}")
            print("=" * 78)
            for d in sorted(por_tipo[tipo], key=lambda x: x["persona"]):
                print(f"\n  {d['persona']}  [{d['id']}]")
                print(f"    GEDCOM   -> hijo/a de {d['padre_gedcom']}  (familia {d['famc']})")
                print(f"    ORIGINAL -> hijo/a de {d['padre_original']}")
            print()

    if sin_pareja:
        print()
        print("=" * 78)
        print(f"En la web original pero no localizados en el GEDCOM ({len(sin_pareja)})")
        print("=" * 78)
        for n in sorted(sin_pareja)[:40]:
            print(f"  {n}")
        if len(sin_pareja) > 40:
            print(f"  ... y {len(sin_pareja) - 40} mas")

    return 1 if discrepancias else 0


if __name__ == "__main__":
    sys.exit(main())
