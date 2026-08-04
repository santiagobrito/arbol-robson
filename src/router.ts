/**
 * Rutas en el hash: #/I123 [ /modo [ /generaciones ] ].
 *
 * El formato corto #/I123 es el que se comparte por WhatsApp, asi que se
 * conserva mientras el modo y las generaciones sean los de por defecto.
 * Al abrir un enlace corto, cada quien ve el arbol con SU configuracion.
 */
import type { AppState, ViewMode } from './types';

const MODES: ViewMode[] = ['desc', 'asc', 'both'];

export function parseHash(hash: string, defaults: AppState): AppState {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  if (parts.length === 0) return { ...defaults };

  const [personId, rawMode, rawGens] = parts;
  const mode = MODES.includes(rawMode as ViewMode) ? (rawMode as ViewMode) : defaults.mode;

  const gens = Number(rawGens);
  const generations = Number.isFinite(gens) && gens >= 1 && gens <= 10 ? gens : defaults.generations;

  return { personId, mode, generations };
}

export function stateToHash(state: AppState, defaults: AppState): string {
  if (state.mode === defaults.mode && state.generations === defaults.generations) {
    return `#/${state.personId}`;
  }
  return `#/${state.personId}/${state.mode}/${state.generations}`;
}
