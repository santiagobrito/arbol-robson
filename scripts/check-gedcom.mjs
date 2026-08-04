/**
 * Comprobacion rapida del GEDCOM contra el parser real que usa la app.
 * Uso: npm run check:gedcom [ruta-al-ged]
 *
 * No forma parte del build. Sirve para validar un GEDCOM nuevo ANTES de
 * copiarlo al volumen /data del contenedor.
 */
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { gedcomToJson } = require('topola');

const path = process.argv[2] ?? 'data/arbol-robson.ged';
const raw = readFileSync(path, 'utf8').replace(/^\uFEFF/, '');

const t0 = Date.now();
const json = gedcomToJson(raw);
const ms = Date.now() - t0;

const indis = json.indis;
const fams = json.fams;

const sinNombre = indis.filter((i) => !i.firstName && !i.lastName).length;
const conNacimiento = indis.filter((i) => i.birth?.date || i.birth?.dateRange).length;
const conDefuncion = indis.filter((i) => i.death).length;
const huerfanos = indis.filter((i) => !i.famc && !(i.fams?.length)).length;

// Mismo criterio que src/privacy.ts
const CORTE = 1930;
const protegidas = indis.filter((i) => {
  if (i.death) return false;
  const y = i.birth?.date?.year ?? i.birth?.dateRange?.from?.year ?? i.birth?.dateRange?.to?.year;
  return typeof y === 'number' && y > CORTE;
}).length;

const famsRotas = fams.filter((f) => {
  const ids = new Set(indis.map((i) => i.id));
  return [f.husb, f.wife, ...(f.children ?? [])]
    .filter(Boolean)
    .some((id) => !ids.has(id));
}).length;

console.log(`Archivo:              ${path}`);
console.log(`Parseo:               ${ms} ms`);
console.log(`Individuos:           ${indis.length}`);
console.log(`Familias:             ${fams.length}`);
console.log(`Sin nombre:           ${sinNombre}`);
console.log(`Con fecha nacimiento: ${conNacimiento}`);
console.log(`Con defuncion:        ${conDefuncion}`);
console.log(`Sin vinculos:         ${huerfanos}`);
console.log(`Familias con refs rotas: ${famsRotas}`);
console.log(`Ocultas por privacidad (sin defuncion y nac. > ${CORTE}): ${protegidas}`);

if (indis.length === 0) {
  console.error('\nERROR: no se parseo ningun individuo. Revisa la codificacion del archivo.');
  process.exit(1);
}
