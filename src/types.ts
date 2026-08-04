import type { JsonFam, JsonGedcomData, JsonIndi } from 'topola';

export type { JsonFam, JsonGedcomData, JsonIndi };

/** Vistas disponibles del arbol. */
export type ViewMode = 'desc' | 'asc' | 'both';

/** Dataset completo indexado por id, para lookups O(1). */
export interface TreeIndex {
  indis: Map<string, JsonIndi>;
  fams: Map<string, JsonFam>;
  /** Ids de personas cuyos datos estan ocultos por el modo privacidad. */
  hidden: Set<string>;
}

/** Estado navegable de la aplicacion. Se serializa al hash de la URL. */
export interface AppState {
  personId: string;
  mode: ViewMode;
  generations: number;
}
