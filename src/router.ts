/**
 * Rutas.
 *
 * Hay DOS formas de llegar a una persona y las dos tienen que funcionar:
 *
 *   /persona/I123            <- canonica. Es una URL de verdad, indexable, y
 *                               tiene detras un HTML generado con los datos.
 *   #/I123                   <- la de antes. Se sigue aceptando porque hay
 *                               enlaces compartidos por WhatsApp que la usan,
 *                               y romperlos seria romper lo unico que la
 *                               familia ya tiene en la mano.
 *
 * Al navegar dentro de la aplicacion se escribe siempre la canonica, asi que
 * cualquier enlace que alguien copie de la barra de direcciones ya es la buena.
 * El formato corto se conserva mientras el modo y las generaciones sean los de
 * por defecto: quien comparte no tiene por que arrastrar su configuracion.
 */
import type { AppState, ViewMode } from './types';

const MODES: ViewMode[] = ['desc', 'asc', 'both'];
const BASE = '/persona/';

function fromSegments(segmentos: string[], defaults: AppState): AppState | null {
  if (segmentos.length === 0) return null;

  const [personId, rawMode, rawGens] = segmentos;
  if (!/^[A-Za-z0-9_-]+$/.test(personId)) return null;

  const mode = MODES.includes(rawMode as ViewMode) ? (rawMode as ViewMode) : defaults.mode;
  const gens = Number(rawGens);
  const generations = Number.isFinite(gens) && gens >= 1 && gens <= 10 ? gens : defaults.generations;

  return { personId, mode, generations };
}

/** Lee el estado de la URL, venga por ruta o por hash. */
export function parseLocation(
  pathname: string,
  hash: string,
  defaults: AppState,
): AppState {
  if (pathname.startsWith(BASE)) {
    const desdeRuta = fromSegments(
      pathname.slice(BASE.length).split('/').filter(Boolean).map(decodeURIComponent),
      defaults,
    );
    if (desdeRuta) return desdeRuta;
  }

  const desdeHash = fromSegments(
    hash.replace(/^#\/?/, '').split('/').filter(Boolean),
    defaults,
  );
  return desdeHash ?? { ...defaults };
}

/** URL canonica de un estado. */
export function stateToPath(state: AppState, defaults: AppState): string {
  if (state.mode === defaults.mode && state.generations === defaults.generations) {
    return `${BASE}${state.personId}`;
  }
  return `${BASE}${state.personId}/${state.mode}/${state.generations}`;
}
