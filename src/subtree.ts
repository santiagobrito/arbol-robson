/**
 * Poda del arbol.
 *
 * Este archivo es lo que hace que la app funcione en un telefono. El GEDCOM
 * tiene 2.789 personas; dibujarlas todas en SVG deja cualquier movil inservible,
 * y un reloj de arena desde el ancestro comun expandiria practicamente el arbol
 * entero. Asi que antes de pasarle nada a Topola se extrae un subgrafo acotado
 * alrededor de la persona enfocada: N generaciones y un tope duro de nodos.
 *
 * La expansion es por generaciones completas: se acepta una generacion entera o
 * ninguna, para no dejar la mitad de los hermanos fuera del dibujo.
 *
 * Todo lo que sale de aqui es referencialmente consistente: no queda ni un
 * famc/fams/child apuntando a alguien que no esta en el subconjunto. Topola
 * accede a esas referencias sin comprobarlas y reventaria con una colgada.
 */
import type { JsonFam, JsonGedcomData, JsonIndi, TreeIndex, ViewMode } from './types';

export interface SubtreeResult {
  json: JsonGedcomData;
  /** true si se corto por el tope de nodos o de generaciones. */
  truncated: boolean;
  /** Personas dibujadas / personas del arbol completo. */
  shown: number;
  total: number;
}

interface Selection {
  indis: Set<string>;
  fams: Set<string>;
}

function spouseOf(fam: JsonFam, id: string): string | undefined {
  if (fam.husb === id) return fam.wife;
  if (fam.wife === id) return fam.husb;
  return undefined;
}

/**
 * Recorre generaciones hacia abajo. Cada paso incorpora las familias de la
 * generacion actual, sus conyuges y sus hijos, y solo se confirma si cabe
 * entero dentro del presupuesto de nodos.
 */
function expandDescendants(
  index: TreeIndex,
  start: string[],
  sel: Selection,
  maxGens: number,
  maxNodes: number,
): boolean {
  let level = start;
  for (let gen = 0; gen < maxGens && level.length > 0; gen++) {
    const newIndis = new Set<string>();
    const newFams = new Set<string>();
    const next: string[] = [];

    for (const id of level) {
      const indi = index.indis.get(id);
      if (!indi?.fams) continue;

      for (const famId of indi.fams) {
        const fam = index.fams.get(famId);
        if (!fam) continue;
        if (!sel.fams.has(famId)) newFams.add(famId);

        const spouse = spouseOf(fam, id);
        if (spouse && index.indis.has(spouse) && !sel.indis.has(spouse)) {
          newIndis.add(spouse);
        }
        for (const child of fam.children ?? []) {
          if (!index.indis.has(child) || sel.indis.has(child) || newIndis.has(child)) continue;
          newIndis.add(child);
          next.push(child);
        }
      }
    }

    if (newIndis.size === 0 && newFams.size === 0) return false;
    if (sel.indis.size + newIndis.size > maxNodes) return true;

    newIndis.forEach((id) => sel.indis.add(id));
    newFams.forEach((id) => sel.fams.add(id));
    level = next;
  }
  // Solo hay recorte real si a los del borde les quedan familias sin dibujar.
  return level.some((id) => (index.indis.get(id)?.fams?.length ?? 0) > 0);
}

/** Idem hacia arriba: familia de origen y ambos progenitores por generacion. */
function expandAncestors(
  index: TreeIndex,
  start: string[],
  sel: Selection,
  maxGens: number,
  maxNodes: number,
): boolean {
  let level = start;
  for (let gen = 0; gen < maxGens && level.length > 0; gen++) {
    const newIndis = new Set<string>();
    const newFams = new Set<string>();
    const next: string[] = [];

    for (const id of level) {
      const famId = index.indis.get(id)?.famc;
      if (!famId) continue;
      const fam = index.fams.get(famId);
      if (!fam) continue;
      if (!sel.fams.has(famId)) newFams.add(famId);

      for (const parent of [fam.husb, fam.wife]) {
        if (!parent || !index.indis.has(parent)) continue;
        if (sel.indis.has(parent) || newIndis.has(parent)) continue;
        newIndis.add(parent);
        next.push(parent);
      }
    }

    if (newIndis.size === 0 && newFams.size === 0) return false;
    if (sel.indis.size + newIndis.size > maxNodes) return true;

    newIndis.forEach((id) => sel.indis.add(id));
    newFams.forEach((id) => sel.fams.add(id));
    level = next;
  }
  return level.some((id) => !!index.indis.get(id)?.famc);
}

/**
 * Recorta las referencias que apuntan fuera del subconjunto y descarta las
 * familias que quedan vacias, para que Topola no encuentre ninguna referencia
 * colgante (no las comprueba: accede directo y falla).
 */
function materialize(index: TreeIndex, sel: Selection): JsonGedcomData {
  const keptFams = new Set(sel.fams);

  for (const famId of [...keptFams]) {
    const fam = index.fams.get(famId)!;
    const visible =
      (fam.husb && sel.indis.has(fam.husb)) ||
      (fam.wife && sel.indis.has(fam.wife)) ||
      (fam.children ?? []).some((id) => sel.indis.has(id));
    // Una familia sin ningun miembro visible no aporta y confunde el layout.
    if (!visible) keptFams.delete(famId);
  }

  const fams: JsonFam[] = [...keptFams].map((famId) => {
    const fam = index.fams.get(famId)!;
    return {
      ...fam,
      husb: fam.husb && sel.indis.has(fam.husb) ? fam.husb : undefined,
      wife: fam.wife && sel.indis.has(fam.wife) ? fam.wife : undefined,
      children: (fam.children ?? []).filter((id) => sel.indis.has(id)),
    };
  });

  const indis: JsonIndi[] = [...sel.indis].map((id) => {
    const indi = index.indis.get(id)!;
    return {
      ...indi,
      famc: indi.famc && keptFams.has(indi.famc) ? indi.famc : undefined,
      fams: (indi.fams ?? []).filter((famId) => keptFams.has(famId)),
    };
  });

  return { indis, fams };
}

/**
 * Extrae el subarbol dibujable alrededor de `rootId`.
 * En modo 'both' los ancestros se expanden primero: suelen ser bastantes menos
 * que los descendientes, asi que se garantiza que la rama de arriba aparece
 * antes de que el tope de nodos se coma el presupuesto.
 */
export function extractSubtree(
  index: TreeIndex,
  rootId: string,
  mode: ViewMode,
  maxGens: number,
  maxNodes: number,
): SubtreeResult {
  const sel: Selection = { indis: new Set([rootId]), fams: new Set() };
  let truncated = false;

  if (mode === 'asc' || mode === 'both') {
    truncated = expandAncestors(index, [rootId], sel, maxGens, maxNodes) || truncated;
  }
  if (mode === 'desc' || mode === 'both') {
    truncated = expandDescendants(index, [rootId], sel, maxGens, maxNodes) || truncated;
  }
  if (mode === 'asc') {
    // En vista de ascendientes se anade la pareja de la persona enfocada para
    // que la tarjeta raiz muestre el matrimonio, sin abrir su descendencia.
    const indi = index.indis.get(rootId);
    for (const famId of indi?.fams ?? []) {
      const fam = index.fams.get(famId);
      const spouse = fam && spouseOf(fam, rootId);
      if (fam && spouse && index.indis.has(spouse)) {
        sel.fams.add(famId);
        sel.indis.add(spouse);
      }
    }
  }

  return {
    json: materialize(index, sel),
    truncated,
    shown: sel.indis.size,
    total: index.indis.size,
  };
}
