#!/usr/bin/env python3
"""Convierte el PDF 'Descendants of Hugh Robson' (texto con sangría) a GEDCOM 5.5.1."""
import re, sys, unicodedata

MESES = {'jan':'JAN','feb':'FEB','mar':'MAR','apr':'APR','may':'MAY','jun':'JUN',
         'jul':'JUL','aug':'AUG','sep':'SEP','oct':'OCT','nov':'NOV','dec':'DEC'}

FEM = set("""jane mary elizabeth margaret ellen euphemia janet anacleta juana rosalia helen
christine christina susana susan martha catherine catalina isabel isabella jean jessie
lucy amelia adela ethel emily emma eliza ida irene sylvia dora nora nelly nelida beatriz
beatrice esther marta maría maria ana anne agnes alice barbara carmen cecilia clara
diana dorothy edith edna elena elina elsa emelina enid erica estela estela ester eva
felisa flora florence florencia gladys grace graciela haydee hilda ida ileene ines inés
irma isolina ivonne jemima jennifer joan josephine juanita judith julia julieta karen
katherine kathleen laura leila lidia lilian lily lorena lorraine luisa lucía lucia
mabel magdalena marcela margarita mariana marina marisa mercedes micaela milagros
mirta monica mónica myriam nancy natalia nelida nilda noemi noemí norma olga patricia
paula phyllis priscilla rebecca rita romina rosa rosemary roxanna ruby sandra sara
sarah sheila silvia sofia sofía soledad stella susanna sylveen teresa thelma valeria
vanesa vera veronica verónica victoria violet virginia vivian yvonne zulema bessie""".split())

MASC = set("""hugh john thomas james william peter edward robert george andrew alexander
richard francis frederick charles henry david daniel joseph samuel walter arthur albert
donald neil ian colin duncan malcolm gordon keith ernest ernesto eduardo jorge juan
carlos luis pedro pablo miguel manuel santiago diego roberto ricardo raúl raul rodolfo
osvaldo oscar norman leonard clifton septimus ivan wilfred oswald roy nigel paul martin
martín matías matias nicolás nicolas gustavo horacio hector héctor guillermo gerardo
federico fernando felipe esteban enrique emilio domingo claudio cesar césar bernardo
benjamin alejandro alberto adrian adrián agustin agustín anibal antonio armando
bruno christian cristian damian damián dario darío denis dennis derek douglas edgar
edgardo elias facundo fabian francisco franco gabriel geoffrey gerald gilbert graham
harold harry herbert horace howard jason jonathan josé jose julio justo kenneth kevin
lawrence leslie lionel lorenzo lucas marcelo marcos mario mark matthew maurice maximiliano
michael nestor néstor nicholas patricio patrick philip ramon ramón raymond reginald
rene rené reynaldo rodrigo rupert sebastian sebastián sergio simon stanley stephen steven
stuart timothy tomas tomás ulises victor víctor vicente wayne""".split())

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s.lower())
                   if unicodedata.category(c) != 'Mn')

def sexo(nombre):
    if not nombre: return None
    pila = norm(nombre).replace('.', ' ').split()
    for p in pila:
        if p in FEM: return 'F'
        if p in MASC: return 'M'
    n = norm(nombre)
    if n.startswith(('daughter','hija')): return 'F'
    if n.startswith(('son ','hijo')): return 'M'
    return None

def fecha(s):
    """'10 Oct 1803' -> '10 OCT 1803'; 'ca 1845' -> 'ABT 1845'."""
    if not s: return None
    s = s.strip().rstrip('.,')
    if not s or s in ('?','-'): return None
    pre = ''
    m = re.match(r'^(ca|abt|about|bef|before|aft|after)\.?\s+(.*)$', s, re.I)
    if m:
        pre = {'ca':'ABT','abt':'ABT','about':'ABT','bef':'BEF','before':'BEF',
               'aft':'AFT','after':'AFT'}[m.group(1).lower()]
        s = m.group(2)
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})$', s)
    if m: return f"{pre+' ' if pre else ''}{int(m.group(1))} {MESES.get(m.group(2).lower(),'')} {m.group(3)}".strip()
    m = re.match(r'^([A-Za-z]{3})[a-z]*\.?\s+(\d{4})$', s)
    if m and m.group(1).lower() in MESES: return f"{pre+' ' if pre else ''}{MESES[m.group(1).lower()]} {m.group(2)}".strip()
    m = re.match(r'^(\d{4})$', s)
    if m: return f"{pre+' ' if pre else ''}{m.group(1)}".strip()
    return None

RE_PERSONA = re.compile(r'^(?P<nom>[^()]+?)\s*\((?P<f>[^)]*)\)\s*$')
RE_SIN_FECHA = re.compile(r'^(?P<nom>[A-Z?][^()]*?)\s*-\s*$')
RE_UNION = re.compile(r'^(?P<tipo>married|partner|Married)\s*(?P<idx>\[\d\])?\s*,?\s*(?P<resto>.*)$')

class P:
    _n = 0
    def __init__(s, nombre, fnac=None, fdef=None):
        P._n += 1; s.id = f"I{P._n}"
        s.nombre = nombre.strip(); s.fnac = fnac; s.fdef = fdef
        s.lnac = s.ldef = None; s.notas = []; s.sexo = sexo(nombre)
        s.fams = []; s.famc = None

class F:
    _n = 0
    def __init__(s):
        F._n += 1; s.id = f"F{F._n}"
        s.esposos = []; s.hijos = []; s.fecha = None; s.lugar = None

def partir_fechas(txt):
    if '-' not in txt: return (fecha(txt), None)
    a, _, b = txt.partition('-')
    return (fecha(a), fecha(b))

def parsear(lineas):
    personas, familias, problemas, raices = [], [], [], []
    pila = []          # (sangria, persona)
    ultima = None      # última persona creada
    ult_ent = None     # última entidad que puede recibir Born:/Died:
    ult_fam = None

    for nlin, cruda in lineas:
        sang = len(cruda) - len(cruda.lstrip())
        l = cruda.strip()

        # atributos
        m = re.match(r'^(Born|Died|Buried)\s*:?\s*(.*)$', l)
        if m and ult_ent:
            tipo, val = m.group(1), m.group(2).strip().rstrip('.')
            if tipo == 'Born': ult_ent.lnac = val
            else: ult_ent.ldef = val
            continue

        # unión
        mu = RE_UNION.match(l)
        if mu:
            resto = mu.group('resto').strip()
            objetivo = ultima
            if mu.group('idx') and mu.group('idx') != '[1]':
                for s, p in reversed(pila):
                    if s <= sang: objetivo = p; break
            if objetivo is None:
                problemas.append((nlin, l, 'unión sin persona previa')); continue
            fam = F(); familias.append(fam)
            fam.esposos.append(objetivo); objetivo.fams.append(fam)
            # fecha al principio del resto
            mf = re.match(r'^(?P<f>(?:ca\s+)?(?:\d{1,2}\s+)?[A-Za-z]{3,}\.?\s*\d{4}|\d{4})\s*,\s*(?P<r>.*)$', resto)
            if mf:
                fam.fecha = fecha(mf.group('f')); resto = mf.group('r')
            mp = RE_PERSONA.match(resto) or RE_SIN_FECHA.match(resto)
            if mp:
                nom = mp.group('nom').strip()
                fn = fd = None
                if 'f' in mp.groupdict() and mp.groupdict().get('f') is not None:
                    fn, fd = partir_fechas(mp.group('f'))
                sp = P(nom, fn, fd); personas.append(sp)
                if objetivo.sexo and not sp.sexo:
                    sp.sexo = 'F' if objetivo.sexo == 'M' else 'M'
                fam.esposos.append(sp); sp.fams.append(fam)
                ult_ent = sp
            elif resto and re.match(r'^[A-Z?][\w\'\.\-áéíóúñÁÉÍÓÚÑ]*(\s+[\w\'\.\-áéíóúñÁÉÍÓÚÑ]+){0,5}\s*-?\s*$', resto):
                sp = P(resto.rstrip(' -')); personas.append(sp)
                if objetivo.sexo and not sp.sexo:
                    sp.sexo = 'F' if objetivo.sexo == 'M' else 'M'
                fam.esposos.append(sp); sp.fams.append(fam)
                ult_ent = sp
            else:
                if resto: problemas.append((nlin, l, 'cónyuge no reconocido'))
                ult_ent = objetivo
            ult_fam = fam
            continue

        # persona
        mp = RE_PERSONA.match(l)
        sin_fecha = False
        if not mp:
            mp = RE_SIN_FECHA.match(l)
            sin_fecha = bool(mp)
        if mp and not l.lower().startswith(('born','died','buried')):
            nom = mp.group('nom').strip()
            if len(nom) < 2 or nom.lower() in ('the','and','of'): 
                problemas.append((nlin, l, 'nombre dudoso')); continue
            fn = fd = None
            if not sin_fecha:
                fn, fd = partir_fechas(mp.group('f'))
            per = P(nom, fn, fd); personas.append(per)
            while pila and pila[-1][0] >= sang - 2: pila.pop()
            if not pila: raices.append(per)
            if pila:
                padre = pila[-1][1]
                fam = padre.fams[-1] if padre.fams else None
                if fam is None:
                    fam = F(); familias.append(fam)
                    fam.esposos.append(padre); padre.fams.append(fam)
                fam.hijos.append(per); per.famc = fam
            pila.append((sang, per))
            ultima = per; ult_ent = per
            continue

        # resto: lugar de la boda u ocupación
        if ult_fam is not None and ult_fam.lugar is None and re.search(r'[A-Z]', l) and ',' in l and not l.endswith(':'):
            ult_fam.lugar = l.rstrip('.')
        elif ult_ent is not None:
            ult_ent.notas.append(l)
        else:
            problemas.append((nlin, l, 'línea suelta'))

    return personas, familias, problemas, raices

def gedcom(personas, familias):
    o = ['0 HEAD','1 SOUR CLAUDE','2 NAME Descendants of Hugh Robson (Graeme Wall, v10z, 2015)',
         '1 GEDC','2 VERS 5.5.1','2 FORM LINEAGE-LINKED','1 CHAR UTF-8',
         '1 SUBM @SUB1@','0 @SUB1@ SUBM','1 NAME Edicion familiar Brito Devoto']
    for p in personas:
        o.append(f"0 @{p.id}@ INDI")
        partes = p.nombre.rsplit(' ', 1)
        o.append(f"1 NAME {partes[0]} /{partes[1]}/" if len(partes) == 2 else f"1 NAME {p.nombre}")
        if p.sexo: o.append(f"1 SEX {p.sexo}")
        if p.fnac or p.lnac:
            o.append('1 BIRT')
            if p.fnac: o.append(f"2 DATE {p.fnac}")
            if p.lnac: o.append(f"2 PLAC {p.lnac}")
        if p.fdef or p.ldef:
            o.append('1 DEAT')
            if p.fdef: o.append(f"2 DATE {p.fdef}")
            if p.ldef: o.append(f"2 PLAC {p.ldef}")
        for n in p.notas[:6]:
            o.append(f"1 NOTE {n[:200]}")
        for f in p.fams: o.append(f"1 FAMS @{f.id}@")
        if p.famc: o.append(f"1 FAMC @{p.famc.id}@")
    for f in familias:
        o.append(f"0 @{f.id}@ FAM")
        h = [e for e in f.esposos if e.sexo == 'M']
        m = [e for e in f.esposos if e.sexo == 'F']
        u = [e for e in f.esposos if e.sexo is None]
        if not h and u: h = [u.pop(0)]
        if not m and u: m = [u.pop(0)]
        if h: o.append(f"1 HUSB @{h[0].id}@")
        if m: o.append(f"1 WIFE @{m[0].id}@")
        for c in f.hijos: o.append(f"1 CHIL @{c.id}@")
        if f.fecha or f.lugar:
            o.append('1 MARR')
            if f.fecha: o.append(f"2 DATE {f.fecha}")
            if f.lugar: o.append(f"2 PLAC {f.lugar}")
    o.append('0 TRLR')
    return '\n'.join(o)

if __name__ == '__main__':
    txt = open('/tmp/arbol.txt', encoding='utf-8', errors='replace').read()
    lineas = []
    for i, l in enumerate(txt.split('\n'), 1):
        if not l.strip(): continue
        if re.match(r'^\s*(13/7/2018|http://www\.greywall|Descendants of Hugh Robson\s*$)', l): continue
        if re.match(r'^\s*\d+/78\s*$', l.strip()): continue
        lineas.append((i, l))
    personas, familias, problemas, raices = parsear(lineas)
    # el patriarca figura en el título del documento, no como línea del árbol
    raiz = P('Hugh Robson', '1780', '19 FEB 1857'); raiz.sexo='M'
    raiz.lnac='Dumfriesshire, Scotland'; raiz.ldef='Buenos Aires, Argentina'
    raiz.notas=['Ploughman in Scotland, Estanciero in Argentina',
                'Emigrated to Argentina in 1825 on the sailing ship Symmetry']
    esposa = P('Jane Ferrish', 'ABT JUL 1779', '20 JUN 1849'); esposa.sexo='F'
    esposa.lnac='Kirkmichael, Dumfriesshire, Scotland'; esposa.ldef='Buenos Aires, Argentina'
    f0 = F(); f0.fecha='ABT 1802'
    f0.esposos=[raiz,esposa]; raiz.fams.append(f0); esposa.fams.append(f0)
    # los hijos del patriarca son las personas sin familia de origen y de menor sangría
    huerfanos = [p for p in raices if p.famc is None]
    for h in huerfanos:
        f0.hijos.append(h); h.famc = f0
    personas = [raiz, esposa] + personas
    familias = [f0] + familias
    print(f"hijos asignados al patriarca: {len(huerfanos)}")
    open('robson.ged', 'w', encoding='utf-8').write(gedcom(personas, familias))
    print(f"personas: {len(personas)}")
    print(f"familias: {len(familias)}")
    print(f"con fecha de nacimiento: {sum(1 for p in personas if p.fnac)}")
    print(f"sexo deducido: {sum(1 for p in personas if p.sexo)} de {len(personas)}")
    print(f"líneas problemáticas: {len(problemas)}")
    with open('problemas.txt', 'w', encoding='utf-8') as f:
        for n, l, m in problemas: f.write(f"{n}\t{m}\t{l}\n")
