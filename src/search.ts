/**
 * Buscador por nombre.
 *
 * Indice plano en memoria: con 2.789 personas un filtro lineal sobre strings
 * ya normalizados tarda menos de un milisegundo, no hace falta nada mas.
 * La busqueda ignora tildes y mayusculas porque medio arbol esta cargado sin
 * acentos y nadie va a escribir "Munoz" con la enie correcta en el telefono.
 */
import { nameWithYears } from './format';
import type { TreeIndex } from './types';

export interface SearchEntry {
  id: string;
  label: string;
  /** Nombre normalizado, sobre el que se busca. */
  key: string;
  /** Ano de nacimiento, para ordenar por antiguedad. */
  year: number;
}

function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

export function buildSearchIndex(index: TreeIndex): SearchEntry[] {
  const entries: SearchEntry[] = [];
  for (const indi of index.indis.values()) {
    const label = nameWithYears(indi);
    const name = [indi.firstName, indi.lastName, indi.maidenName].filter(Boolean).join(' ');
    entries.push({
      id: indi.id,
      label,
      key: normalize(name),
      year: indi.birth?.date?.year ?? 9999,
    });
  }
  return entries;
}

/**
 * Devuelve como mucho `limit` coincidencias. Prioriza las que empiezan por el
 * texto buscado; dentro de cada grupo, primero los mas antiguos (los de arriba
 * del arbol suelen ser los que se buscan por apellido).
 */
export function searchPeople(entries: SearchEntry[], query: string, limit = 25): SearchEntry[] {
  const q = normalize(query);
  if (q.length < 2) return [];

  const prefix: SearchEntry[] = [];
  const contains: SearchEntry[] = [];

  for (const entry of entries) {
    if (entry.key.startsWith(q)) prefix.push(entry);
    else if (entry.key.includes(q)) contains.push(entry);
    if (prefix.length >= limit) break;
  }

  const byYear = (a: SearchEntry, b: SearchEntry) => a.year - b.year;
  return [...prefix.sort(byYear), ...contains.sort(byYear)].slice(0, limit);
}
