/**
 * Modo privacidad.
 *
 * Regla: se ocultan los datos de quien NO tiene defuncion registrada y nacio
 * despues del ano de corte (1930 por defecto). De esas personas solo queda
 * visible el nombre.
 *
 * El filtro se aplica una sola vez, justo despues de parsear y ANTES de
 * construir el indice de busqueda o dibujar nada. Asi los datos ocultos no
 * llegan nunca al DOM, ni por la ficha ni por el buscador ni por el SVG.
 *
 * LIMITE CONOCIDO, a proposito: el nombre completo sigue visible, porque sin
 * el no se puede buscar a un familiar. La proteccion real de este sitio es la
 * autenticacion HTTP, no este filtro.
 */
import type { AppConfig } from './config';
import { yearOf } from './format';
import type { JsonFam, JsonGedcomData, JsonIndi, TreeIndex } from './types';

function isPresumedLiving(indi: JsonIndi, cfg: AppConfig): boolean {
  if (indi.death) return false;

  const birthYear = yearOf(indi.birth);
  if (birthYear === undefined) {
    // Sin ninguna fecha no hay forma de estimar. Configurable.
    return cfg.privacyHideUndated;
  }
  return birthYear > cfg.privacyBirthYearCutoff;
}

/** Copia del individuo sin los campos sensibles. */
function redact(indi: JsonIndi): JsonIndi {
  const { birth, death, events, notes, ...rest } = indi;
  return rest;
}

/**
 * Devuelve un indice del arbol con la privacidad ya aplicada.
 * `hidden` lleva los ids afectados para que la ficha pueda avisarlo.
 */
export function buildIndex(json: JsonGedcomData, cfg: AppConfig): TreeIndex {
  const hidden = new Set<string>();
  const indis = new Map<string, JsonIndi>();

  for (const indi of json.indis) {
    const protect = cfg.privacyMode && isPresumedLiving(indi, cfg);
    if (protect) hidden.add(indi.id);
    // hideId: la ficha y la URL ya muestran el identificador; en la tarjeta sobra.
    indis.set(indi.id, { ...(protect ? redact(indi) : indi), hideId: true });
  }

  // La fecha de casamiento delata igual: si a los dos conyuges les ocultamos el
  // nacimiento pero se ve "casados en 1977", el dato sensible se reconstruye
  // solo. Se oculta en cuanto uno de los dos este protegido.
  const fams = new Map<string, JsonFam>();
  for (const fam of json.fams) {
    const affected =
      (fam.husb !== undefined && hidden.has(fam.husb)) ||
      (fam.wife !== undefined && hidden.has(fam.wife));
    fams.set(fam.id, affected ? { ...fam, marriage: undefined } : fam);
  }

  return { indis, fams, hidden };
}
