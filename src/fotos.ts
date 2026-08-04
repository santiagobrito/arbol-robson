/**
 * Fotos de las personas del arbol.
 *
 * Las fotos NO viven dentro del GEDCOM (como etiquetas OBJE) sino en un
 * manifiesto aparte, `/data/fotos.json`, con la forma {idPersona: archivo}.
 *
 * El motivo es de mantenimiento: las fotos van llegando con el tiempo, a medida
 * que las mandan los familiares. Si estuvieran dentro del GEDCOM, anadir una
 * exigiria regenerar el arbol entero; con el manifiesto basta con dejar el
 * archivo y correr `scripts/preparar-fotos.py`. El GEDCOM se puede regenerar
 * cuantas veces haga falta sin tocar las fotos, y al reves.
 *
 * Topola dibuja la foto en la tarjeta a partir de `JsonIndi.images`, asi que
 * aqui solo hay que rellenar ese campo.
 */
import type { AppConfig } from './config';
import type { TreeIndex } from './types';

type Manifiesto = Record<string, string>;

function esManifiesto(valor: unknown): valor is Manifiesto {
  return (
    !!valor &&
    typeof valor === 'object' &&
    !Array.isArray(valor) &&
    Object.values(valor as object).every((v) => typeof v === 'string')
  );
}

/**
 * Incorpora las fotos al indice. Devuelve cuantas se aplicaron.
 *
 * Se llama DESPUES de aplicar la privacidad, y respeta su resultado: a quien
 * este protegido no se le pone foto. Una cara identifica mucho mejor que una
 * fecha de nacimiento, asi que ocultar la fecha y dejar el retrato seria
 * absurdo.
 *
 * Nunca lanza: quedarse sin fotos es un desperfecto menor, no arrancar es un
 * fallo grave. Si el manifiesto no esta o esta corrupto, el arbol se dibuja igual.
 */
export async function aplicarFotos(index: TreeIndex, cfg: AppConfig): Promise<number> {
  let manifiesto: Manifiesto;
  try {
    const res = await fetch(cfg.fotosUrl, { cache: 'no-cache' });
    if (!res.ok) return 0;
    const datos: unknown = await res.json();
    if (!esManifiesto(datos)) return 0;
    manifiesto = datos;
  } catch {
    return 0;
  }

  let aplicadas = 0;
  for (const [id, archivo] of Object.entries(manifiesto)) {
    const indi = index.indis.get(id);
    if (!indi || index.hidden.has(id)) continue;
    // El nombre del archivo viene de un fichero del servidor, pero se codifica
    // igualmente: acaba dentro de un atributo href del SVG.
    indi.images = [{ url: cfg.fotosBase + encodeURIComponent(archivo) }];
    aplicadas++;
  }
  return aplicadas;
}
