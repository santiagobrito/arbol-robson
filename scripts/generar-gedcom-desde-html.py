#!/usr/bin/env python3
"""
Genera el GEDCOM a partir de la copia archivada de la web original.

POR QUE ESTE Y NO EL DEL PDF
El conversor original (`docs/parser-arbol-a-gedcom.py`) leia el PDF, donde la
jerarquia se expresaba SOLO con sangria. Inferir generaciones a partir de
espacios falla, y fallo: aparecieron personas colgadas una generacion por encima
de la que les tocaba (Jose Martin Brito Devoto como hermano de su propia madre,
Marcos Brito Devoto como hermano de su padre, y ~97 casos mas).

La copia archivada de la web (Version 10z, 4 May 2015, la MISMA que genero el
PDF) trae la jerarquia explicita: <ul> anidados y clases gen1..genN. No hay nada
que inferir, asi que esta clase de error desaparece por construccion.

IDENTIFICADORES
Los IDs (I123, F45) son la URL publica de cada persona. Al regenerar se
reutilizan los del GEDCOM anterior siempre que la persona sea reconocible por
nombre + ano de nacimiento, para no romper los enlaces ya compartidos. Solo
recibe ID nuevo quien no existiera antes.

Uso:
    python3 scripts/generar-gedcom-desde-html.py            # a stdout, en seco
    python3 scripts/generar-gedcom-desde-html.py --escribir # sobreescribe el .ged
"""

import importlib.util
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGINAL = RAIZ / "docs" / "fuente-original-greywall-2017.html"
GEDCOM = RAIZ / "data" / "arbol-robson.ged"
PARSER_VIEJO = RAIZ / "docs" / "parser-arbol-a-gedcom.py"


def cargar_helpers():
    """Reutiliza sexo(), fecha() y partir_fechas() del conversor original.

    Se importan en vez de reescribirse para que el unico cambio real entre el
    GEDCOM viejo y el nuevo sea la ESTRUCTURA, no como se normaliza una fecha ni
    como se adivina el sexo. Asi el diff es revisable.
    """
    spec = importlib.util.spec_from_file_location("parser_viejo", PARSER_VIEJO)
    mod = importlib.util.module_from_spec(spec)
    # Se vacia argv para que el modulo viejo no dispare su bloque __main__, y se
    # restaura despues: si no, se lleva por delante nuestros propios flags.
    guardado = sys.argv[:]
    sys.argv = [guardado[0]]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = guardado
    return mod


V = cargar_helpers()


# --------------------------------------------------------------------------
# 1. Arbol del HTML
# --------------------------------------------------------------------------

SEPARADORES = {"br", "div", "p"}


class Nodo:
    def __init__(self, gen):
        self.gen = gen
        self.lineas = [""]      # texto propio, partido por <br>
        self.bodas = []         # cada <em> es una lista de lineas
        self.hijos = []
        self.persona = None


class LectorHTML(HTMLParser):
    """
    Construye el arbol de <li>. Se apoya en la clase genN y no solo en el
    anidamiento: si a algun <li> le faltara el cierre, el nivel escrito en la
    clase recoloca el nodo igual. Es la unica parte que no conviene que sea
    fragil, porque un fallo aqui se propaga a media rama.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = Nodo(0)
        self.pila = [self.raiz]
        self.em = None

    def _destino(self):
        return self.em if self.em is not None else self.pila[-1].lineas

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            clase = dict(attrs).get("class", "")
            m = re.search(r"gen(\d+)", clase)
            gen = int(m.group(1)) if m else self.pila[-1].gen + 1
            while len(self.pila) > 1 and self.pila[-1].gen >= gen:
                self.pila.pop()
            nodo = Nodo(gen)
            self.pila[-1].hijos.append(nodo)
            self.pila.append(nodo)
            self.em = None
        elif tag == "em":
            self.em = [""]
            self.pila[-1].bodas.append(self.em)
        elif tag in SEPARADORES:
            # <div> y <p> tambien cortan linea. La pagina usa DOS variantes de
            # marcado y en la mayoritaria los "Born:/Died:" van dentro de un
            # <div class="cN"> SIN <br> que lo separe del nombre. Sin este corte,
            # nombre y lugar de nacimiento acaban en la misma linea y la fecha
            # entre parentesis deja de estar al final: se pierden ~700 fechas.
            self._destino().append("")

    def handle_endtag(self, tag):
        if tag == "li":
            if len(self.pila) > 1:
                self.pila.pop()
            self.em = None
        elif tag == "em":
            self.em = None
        elif tag in SEPARADORES:
            self._destino().append("")

    def handle_data(self, data):
        d = self._destino()
        d[-1] += data.replace("\n", " ")


def limpiar(lineas):
    return [re.sub(r"\s+", " ", l).strip() for l in lineas if l.strip()]


# --------------------------------------------------------------------------
# 2. Del texto a personas
# --------------------------------------------------------------------------

RE_FECHA_INICIAL = re.compile(
    r"^((?:ca\.?|abt\.?|about|bef\.?|before|aft\.?|after)?\s*"
    r"(?:\d{1,2}\s*,?\s*)?(?:[A-Za-z]{3,9}\.?\s+)?\d{4})\s*[,.]?\s+(.+)$"
)


def partir_nombre(txt):
    """'Jane Ferrish (ca Jul 1779 - 20 Jun 1849)' -> (nombre, fnac, fdef)."""
    txt = txt.strip().rstrip("-").strip()
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", txt)
    if m:
        nombre = m.group(1).strip()
        fnac, fdef = V.partir_fechas(m.group(2))
        return nombre, fnac, fdef
    return txt, None, None


def leer_boda(lineas):
    """Interpreta un bloque <em>: pareja, fecha, lugar y datos de la pareja."""
    lineas = limpiar(lineas)
    if not lineas:
        return None

    cabeza = lineas[0]
    if not re.match(r"^(married|partner|engaged)", cabeza, re.I):
        # <em> que no describe un matrimonio (alguna nota suelta del original)
        return None

    resto = re.sub(r"^(married|partner|engaged)\s*(\[\d\])?\s*,?\s*", "",
                   cabeza, flags=re.I).strip()

    fecha_boda = None
    m = RE_FECHA_INICIAL.match(resto)
    if m:
        fecha_boda = V.fecha(m.group(1).replace(",", " "))
        resto = m.group(2)

    nombre, fnac, fdef = partir_nombre(resto)
    if not nombre:
        return None

    boda = {
        "fecha": fecha_boda, "lugar": None,
        "nombre": nombre, "fnac": fnac, "fdef": fdef,
        "lnac": None, "ldef": None, "notas": [],
    }

    # El resto del <em>: lugar de la boda primero, luego Born:/Died: de la
    # pareja y notas. El lugar solo se toma si viene antes que cualquier
    # Born:/Died:, que es como lo escribia el autor.
    visto_evento = False
    for l in lineas[1:]:
        if re.match(r"^Born\s*:", l, re.I):
            boda["lnac"] = l.split(":", 1)[1].strip().rstrip(".")
            visto_evento = True
        elif re.match(r"^Died\s*:", l, re.I):
            boda["ldef"] = l.split(":", 1)[1].strip().rstrip(".")
            visto_evento = True
        elif not visto_evento and boda["lugar"] is None and len(l) < 90:
            boda["lugar"] = l.rstrip(".")
        else:
            boda["notas"].append(l)
    return boda


def construir(nodo, personas, familias, padre_fam=None):
    """Recorre el arbol y crea las personas y familias."""
    lineas = limpiar(nodo.lineas)
    if not lineas:
        for h in nodo.hijos:
            construir(h, personas, familias, padre_fam)
        return

    nombre, fnac, fdef = partir_nombre(lineas[0])
    if not nombre:
        return

    p = V.P(nombre)
    p.fnac, p.fdef = fnac, fdef
    for l in lineas[1:]:
        if re.match(r"^Born\s*:", l, re.I):
            p.lnac = l.split(":", 1)[1].strip().rstrip(".")
        elif re.match(r"^Died\s*:", l, re.I):
            p.ldef = l.split(":", 1)[1].strip().rstrip(".")
        else:
            p.notas.append(l)
    personas.append(p)
    nodo.persona = p

    if padre_fam is not None:
        padre_fam.hijos.append(p)
        p.famc = padre_fam

    # Familias de esta persona. Los hijos que cuelgan de ella van a la PRIMERA,
    # que es lo que el original expresa: la web no distingue de que matrimonio
    # viene cada hijo cuando hay varios.
    fams = []
    for bloque in nodo.bodas:
        b = leer_boda(bloque)
        if not b:
            continue
        pareja = V.P(b["nombre"])
        pareja.fnac, pareja.fdef = b["fnac"], b["fdef"]
        pareja.lnac, pareja.ldef = b["lnac"], b["ldef"]
        pareja.notas = b["notas"]
        personas.append(pareja)

        f = V.F()
        f.fecha, f.lugar = b["fecha"], b["lugar"]
        f.esposos = [p, pareja]
        familias.append(f)
        p.fams.append(f)
        pareja.fams.append(f)
        fams.append(f)

    destino = fams[0] if fams else None
    if nodo.hijos and destino is None:
        # Tiene descendencia pero no consta matrimonio: hace falta una familia
        # con un solo miembro para no perder el vinculo.
        destino = V.F()
        destino.esposos = [p]
        familias.append(destino)
        p.fams.append(destino)

    for h in nodo.hijos:
        construir(h, personas, familias, destino)


# --------------------------------------------------------------------------
# 3. Conservar los identificadores anteriores
# --------------------------------------------------------------------------

def clave(nombre, anio):
    t = unicodedata.normalize("NFD", nombre.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return f"{re.sub(r'\\s+', ' ', t).strip()}|{anio or ''}"


def anio_de(f):
    m = re.search(r"\d{4}", f) if f else None
    return m.group(0) if m else None


def reutilizar_ids(personas, familias):
    """Reasigna los IDs del GEDCOM anterior a las mismas personas."""
    if not GEDCOM.exists():
        return 0, len(personas)

    viejo = GEDCOM.read_text(encoding="utf-8")
    disponibles = {}
    for reg in re.split(r"\n(?=0 @)", viejo):
        m = re.match(r"0 @(I\w+)@ INDI", reg.split("\n")[0])
        if not m:
            continue
        nm = re.search(r"\n1 NAME (.*)", reg)
        nac = re.search(r"\n1 BIRT\n(?:2 .*\n)*?2 DATE ([^\n]*)", reg)
        if not nm:
            continue
        k = clave(nm.group(1).replace("/", "").strip(), anio_de(nac.group(1) if nac else None))
        disponibles.setdefault(k, []).append(m.group(1))

    usados, conservados = set(), 0
    sin_id = []
    for p in personas:
        cola = disponibles.get(clave(p.nombre, anio_de(p.fnac)), [])
        elegido = next((i for i in cola if i not in usados), None)
        if elegido:
            p.id = elegido
            usados.add(elegido)
            conservados += 1
        else:
            sin_id.append(p)

    siguiente = max((int(i[1:]) for i in usados if i[1:].isdigit()), default=0) + 1
    for p in sin_id:
        while f"I{siguiente}" in usados:
            siguiente += 1
        p.id = f"I{siguiente}"
        usados.add(p.id)
        siguiente += 1

    return conservados, len(sin_id)


# --------------------------------------------------------------------------

def leer_cabecera(crudo, personas, familias):
    """
    Crea la pareja fundadora y devuelve su familia.

    Hugh Robson y Jane Ferrish no estan en ningun <li>: son la cabecera de la
    pagina (<h1> con el nombre, <h3> con las fechas, un div con lugares y un
    <em> con el matrimonio). Es un caso unico, asi que se extrae aparte en vez
    de complicar el lector con un tercer formato.
    """
    titulo = re.search(r"<h1>\s*Descendants of\s*(.*?)\s*</h1>", crudo, re.I | re.S)
    fechas = re.search(r"<h3>\s*\((.*?)\)\s*</h3>", crudo, re.I | re.S)
    if not titulo:
        return None

    p = V.P(re.sub(r"<[^>]+>", "", titulo.group(1)).strip())
    if fechas:
        p.fnac, p.fdef = V.partir_fechas(fechas.group(1))

    bloque = re.search(r'<div class="c2">(.*?)</div>', crudo, re.S)
    if bloque:
        for l in limpiar(re.split(r"<br\s*/?>", bloque.group(1))):
            texto = re.sub(r"<[^>]+>", "", l).strip()
            if re.match(r"^Born\s*:", texto, re.I):
                p.lnac = texto.split(":", 1)[1].strip().rstrip(".")
            elif re.match(r"^Died\s*:", texto, re.I):
                p.ldef = texto.split(":", 1)[1].strip().rstrip(".")
            elif texto:
                p.notas.append(texto)
    personas.append(p)

    boda = re.search(r"<em><strong>(married.*?)</strong></em>", crudo, re.S)
    if not boda:
        return None
    datos = leer_boda([re.sub(r"<[^>]+>", "", boda.group(1))])
    if not datos:
        return None

    pareja = V.P(datos["nombre"])
    pareja.fnac, pareja.fdef = datos["fnac"], datos["fdef"]
    # Los lugares de la pareja van en el div siguiente al <em> del matrimonio
    sig = re.search(r'<em><strong>married.*?</strong></em>.*?<div class="c2">(.*?)</div>',
                    crudo, re.S)
    if sig:
        for l in limpiar(re.split(r"<br\s*/?>", sig.group(1))):
            texto = re.sub(r"<[^>]+>", "", l).strip()
            if re.match(r"^Born\s*:", texto, re.I):
                pareja.lnac = texto.split(":", 1)[1].strip().rstrip(".")
            elif re.match(r"^Died\s*:", texto, re.I):
                pareja.ldef = texto.split(":", 1)[1].strip().rstrip(".")
    personas.append(pareja)

    f = V.F()
    f.fecha, f.lugar = datos["fecha"], datos["lugar"]
    f.esposos = [p, pareja]
    familias.append(f)
    p.fams.append(f)
    pareja.fams.append(f)
    return f


def main():
    escribir = "--escribir" in sys.argv
    crudo = ORIGINAL.read_text(encoding="utf-8", errors="replace")

    personas, familias = [], []
    familia_raiz = leer_cabecera(crudo, personas, familias)

    # Se alimenta al lector solo desde el primer <ul> del arbol: asi la cabecera,
    # que tiene su propio marcado, no confunde al analizador de <li>.
    inicio = crudo.find('<li class="gen1"')
    inicio = crudo.rfind("<ul>", 0, inicio) if inicio > 0 else 0

    lector = LectorHTML()
    lector.feed(crudo[inicio:])

    for raiz in lector.raiz.hijos:
        construir(raiz, personas, familias, familia_raiz)

    for p in personas:
        if p.sexo is None:
            p.sexo = V.sexo(p.nombre)

    conservados, nuevos = reutilizar_ids(personas, familias)
    salida = V.gedcom(personas, familias)

    print(f"Personas : {len(personas)}", file=sys.stderr)
    print(f"Familias : {len(familias)}", file=sys.stderr)
    print(f"IDs conservados del GEDCOM anterior: {conservados}", file=sys.stderr)
    print(f"IDs nuevos: {nuevos}", file=sys.stderr)

    if not escribir:
        # En seco el GEDCOM va a stdout, para poder redirigirlo y compararlo
        # con el actual antes de decidir nada. Las cifras van por stderr.
        print(salida)
        print("(en seco: el .ged del repositorio no se ha tocado; usa --escribir)",
              file=sys.stderr)
        return 0

    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    shutil.copy2(GEDCOM, GEDCOM.with_suffix(f".ged.bak-{sello}"))
    GEDCOM.write_text(salida + "\n", encoding="utf-8")
    print(f"Escrito {GEDCOM}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
