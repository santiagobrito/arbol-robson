#!/usr/bin/env python3
"""
Genera una pagina HTML por persona, mas el sitemap.

POR QUE HACEN FALTA
La aplicacion carga el GEDCOM por JavaScript, asi que el HTML que recibe un
buscador no contiene ni un solo nombre del arbol. Y los enlaces `#/I123` no son
URLs distintas para un rastreador: todo lo que hay tras la almohadilla se
ignora. Sin estas paginas, quitar el `noindex` no sirve de nada: quedaria una
unica pagina indexada sin contenido.

Cada pagina generada lleva la ficha en HTML plano (nombre, fechas, lugares y
enlaces a padres, hermanos, pareja e hijos) y despues carga la aplicacion
normal, que la sustituye por el arbol. El buscador ve la ficha; la persona ve
el arbol.

DONDE VIVEN
En el volumen, junto al GEDCOM, no dentro de la imagen: se derivan de un dato
que ya vive ahi y se regeneran sin reconstruir nada.

Uso:
    npm run build                        # primero, que de aqui salen los assets
    python3 scripts/generar-paginas.py
"""

import html
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GEDCOM = RAIZ / "data" / "arbol-robson.ged"
PLANTILLA = RAIZ / "dist" / "index.html"
DESTINO = RAIZ / "data" / "paginas"
SITEMAP = RAIZ / "data" / "sitemap.xml"
FOTOS = RAIZ / "data" / "fotos.json"

SITIO = "https://hugderobson.servidorweb.xyz"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


# --------------------------------------------------------------------------
# Lectura del GEDCOM
# --------------------------------------------------------------------------

def fecha_legible(cruda):
    """'19 FEB 1857' -> '19 de febrero de 1857'."""
    if not cruda:
        return ""
    cruda = cruda.strip()
    pre = ""
    m = re.match(r"^(ABT|BEF|AFT|CAL|EST)\s+(.*)$", cruda, re.I)
    if m:
        pre = {"abt": "hacia", "bef": "antes de", "aft": "despues de",
               "cal": "calculado", "est": "estimado"}[m.group(1).lower()]
        cruda = m.group(2)

    meses = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
             "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
    m = re.match(r"^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$", cruda, re.I)
    if m:
        texto = f"{int(m.group(1))} de {MESES[meses[m.group(2).upper()] - 1]} de {m.group(3)}"
    else:
        m = re.match(r"^([A-Z]{3})\s+(\d{4})$", cruda, re.I)
        texto = (f"{MESES[meses[m.group(1).upper()] - 1]} de {m.group(2)}"
                 if m else cruda)
    return f"{pre} {texto}".strip()


def leer():
    crudo = GEDCOM.read_text(encoding="utf-8").replace("﻿", "")
    indis, fams = {}, {}
    for reg in re.split(r"\n(?=0 @)", crudo):
        cab = reg.split("\n")[0]
        mi = re.match(r"0 @(\w+)@ INDI", cab)
        mf = re.match(r"0 @(\w+)@ FAM", cab)
        if mi:
            nom = re.search(r"\n1 NAME (.*)", reg)
            def evento(tag):
                vacio = {"fecha": "", "lugar": "", "anio": ""}
                bloque = re.search(rf"\n1 {tag}\n((?:2 .*\n?)*)", reg)
                if not bloque:
                    return vacio
                d = re.search(r"2 DATE (.*)", bloque.group(1))
                p = re.search(r"2 PLAC (.*)", bloque.group(1))
                return {"fecha": fecha_legible(d.group(1)) if d else "",
                        "lugar": p.group(1).strip() if p else "",
                        "anio": (re.search(r"\d{4}", d.group(1)).group(0)
                                 if d and re.search(r"\d{4}", d.group(1)) else "")}
            indis[mi.group(1)] = {
                "id": mi.group(1),
                "nombre": nom.group(1).replace("/", "").strip() if nom else "Sin nombre",
                "nac": evento("BIRT"),
                "def": evento("DEAT"),
                "notas": re.findall(r"\n1 NOTE (.*)", reg),
                "famc": (re.search(r"\n1 FAMC @(\w+)@", reg).group(1)
                         if re.search(r"\n1 FAMC @(\w+)@", reg) else None),
                "fams": re.findall(r"\n1 FAMS @(\w+)@", reg),
            }
        elif mf:
            hu = re.search(r"\n1 HUSB @(\w+)@", reg)
            wi = re.search(r"\n1 WIFE @(\w+)@", reg)
            mb = re.search(r"\n1 MARR\n((?:2 .*\n?)*)", reg)
            d = re.search(r"2 DATE (.*)", mb.group(1)) if mb else None
            p = re.search(r"2 PLAC (.*)", mb.group(1)) if mb else None
            fams[mf.group(1)] = {
                "padre": hu.group(1) if hu else None,
                "madre": wi.group(1) if wi else None,
                "hijos": re.findall(r"\n1 CHIL @(\w+)@", reg),
                "boda": {"fecha": fecha_legible(d.group(1)) if d else "",
                         "lugar": p.group(1).strip() if p else ""},
            }
    return indis, fams


# --------------------------------------------------------------------------
# Construccion del HTML
# --------------------------------------------------------------------------

E = html.escape


def anios(p):
    a, b = p["nac"]["anio"], p["def"]["anio"]
    if not a and not b:
        return ""
    return f" ({a or '?'}–{b or ''})"


def enlace(indis, pid):
    p = indis.get(pid)
    if not p:
        return ""
    return f'<a href="/persona/{E(pid)}">{E(p["nombre"])}{E(anios(p))}</a>'


def lista(titulo, enlaces):
    enlaces = [e for e in enlaces if e]
    if not enlaces:
        return ""
    items = "".join(f"<li>{e}</li>" for e in enlaces)
    return f"<h2>{titulo}</h2><ul>{items}</ul>"


def ficha(p, indis, fams, foto):
    partes = [f"<h1>{E(p['nombre'])}{E(anios(p))}</h1>"]

    if foto:
        partes.append(f'<img src="/data/fotos/{E(foto)}" alt="{E(p["nombre"])}" '
                      f'width="140" height="180" />')

    hechos = []
    for etiqueta, ev in (("Nacimiento", p["nac"]), ("Defuncion", p["def"])):
        texto = ", ".join(x for x in (ev["fecha"], ev["lugar"]) if x)
        if texto:
            hechos.append(f"<dt>{etiqueta}</dt><dd>{E(texto)}</dd>")
    if hechos:
        partes.append("<dl>" + "".join(hechos) + "</dl>")

    for nota in p["notas"][:4]:
        partes.append(f"<p>{E(nota)}</p>")

    famc = fams.get(p["famc"]) if p["famc"] else None
    if famc:
        partes.append(lista("Padres", [enlace(indis, famc["padre"]),
                                       enlace(indis, famc["madre"])]))
        partes.append(lista("Hermanos", [enlace(indis, h) for h in famc["hijos"]
                                         if h != p["id"]]))

    parejas, hijos = [], []
    for fid in p["fams"]:
        fam = fams.get(fid)
        if not fam:
            continue
        otro = fam["madre"] if fam["padre"] == p["id"] else fam["padre"]
        if otro:
            texto = enlace(indis, otro)
            boda = ", ".join(x for x in (fam["boda"]["fecha"], fam["boda"]["lugar"]) if x)
            parejas.append(f"{texto} <small>Casamiento: {E(boda)}</small>" if boda else texto)
        hijos += [enlace(indis, h) for h in fam["hijos"]]
    partes.append(lista("Pareja", parejas))
    partes.append(lista("Hijos", hijos))

    partes.append('<p><a href="/">Ver el arbol completo</a></p>')
    return "\n".join(x for x in partes if x)


def descripcion(p):
    trozos = [p["nombre"]]
    nac = ", ".join(x for x in (p["nac"]["fecha"], p["nac"]["lugar"]) if x)
    dfn = ", ".join(x for x in (p["def"]["fecha"], p["def"]["lugar"]) if x)
    if nac:
        trozos.append(f"nacio {nac}")
    if dfn:
        trozos.append(f"fallecio {dfn}")
    trozos.append("Arbol genealogico de los descendientes de Hugh Robson")
    return ". ".join(trozos) + "."


def main():
    for necesario in (GEDCOM, PLANTILLA):
        if not necesario.exists():
            sys.exit(f"Falta {necesario}. ¿Ejecutaste `npm run build` antes?")

    plantilla = PLANTILLA.read_text(encoding="utf-8")
    indis, fams = leer()
    fotos = json.loads(FOTOS.read_text(encoding="utf-8")) if FOTOS.exists() else {}

    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)

    urls = []
    for pid, p in indis.items():
        titulo = f"{p['nombre']}{anios(p)} — Arbol familiar Robson"
        desc = descripcion(p)
        bloque = (f'<div id="prerender">\n{ficha(p, indis, fams, fotos.get(pid))}\n</div>')

        pagina = plantilla
        pagina = re.sub(r"<title>.*?</title>", f"<title>{E(titulo)}</title>", pagina, count=1)
        pagina = re.sub(r'(<meta name="description" content=")[^"]*(")',
                        lambda m: m.group(1) + E(desc) + m.group(2), pagina, count=1)
        pagina = re.sub(r'(<meta property="og:title" content=")[^"]*(")',
                        lambda m: m.group(1) + E(titulo) + m.group(2), pagina, count=1)
        pagina = re.sub(r'(<meta property="og:description" content=")[^"]*(")',
                        lambda m: m.group(1) + E(desc) + m.group(2), pagina, count=1)
        # Canonica y la ficha en texto, justo al abrir el body
        pagina = pagina.replace("</head>",
                                f'    <link rel="canonical" href="{SITIO}/persona/{E(pid)}" />\n  </head>', 1)
        pagina = pagina.replace("<body>", f"<body>\n{bloque}", 1)

        (DESTINO / f"{pid}.html").write_text(pagina, encoding="utf-8")
        urls.append(f"{SITIO}/persona/{pid}")

    entradas = "".join(f"\n <url><loc>{u}</loc></url>" for u in urls)
    SITEMAP.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'\n <url><loc>{SITIO}/</loc><priority>1.0</priority></url>'
        f'{entradas}\n</urlset>\n', encoding="utf-8")

    peso = sum(f.stat().st_size for f in DESTINO.glob("*.html"))
    print(f"{len(urls)} paginas en {DESTINO.relative_to(RAIZ)}  ({peso // 1024 // 1024} MB)")
    print(f"sitemap con {len(urls) + 1} URLs -> {SITEMAP.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
