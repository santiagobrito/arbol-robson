/**
 * Configuracion en tiempo de ejecucion.
 *
 * El build es estatico, asi que la configuracion NO puede vivir en variables
 * de Vite: quedaria horneada en el bundle y cambiarla exigiria reconstruir la
 * imagen. En su lugar el entrypoint del contenedor escribe /config.json a
 * partir de las variables de entorno, y la app lo lee al arrancar.
 *
 * En desarrollo /config.json no existe: se usan los defaults, y cualquier
 * variable VITE_* del .env local los pisa.
 */

export interface AppConfig {
  /** Titulo visible y de la pestana. */
  title: string;
  /** URL del GEDCOM. Servida por nginx desde el volumen /data. */
  gedcomUrl: string;
  /** Oculta datos de personas presuntamente vivas. */
  privacyMode: boolean;
  /** Nacidos DESPUES de este ano se consideran presuntamente vivos. */
  privacyBirthYearCutoff: number;
  /**
   * Si es true, tambien se ocultan los datos de quienes no tienen ninguna
   * fecha (ni nacimiento ni defuncion). Mas seguro pero mas restrictivo:
   * en este arbol son ~795 personas.
   */
  privacyHideUndated: boolean;
  /** Persona que se muestra al entrar sin ancla en la URL. */
  defaultPersonId: string | null;
  /** Generaciones que se dibujan hacia arriba/abajo desde la persona enfocada. */
  defaultGenerations: number;
  /** Tope duro de nodos por render. Es lo que mantiene fluido el movil. */
  maxNodes: number;
}

const DEFAULTS: AppConfig = {
  title: 'Arbol familiar Robson',
  gedcomUrl: '/data/arbol-robson.ged',
  privacyMode: true,
  privacyBirthYearCutoff: 1930,
  privacyHideUndated: false,
  defaultPersonId: null,
  defaultGenerations: 4,
  maxNodes: 400,
};

function fromViteEnv(): Partial<AppConfig> {
  const env = import.meta.env;
  const out: Partial<AppConfig> = {};
  if (env.VITE_TITLE) out.title = env.VITE_TITLE;
  if (env.VITE_GEDCOM_URL) out.gedcomUrl = env.VITE_GEDCOM_URL;
  if (env.VITE_PRIVACY_MODE) out.privacyMode = env.VITE_PRIVACY_MODE !== 'false';
  if (env.VITE_PRIVACY_BIRTH_YEAR_CUTOFF) {
    out.privacyBirthYearCutoff = Number(env.VITE_PRIVACY_BIRTH_YEAR_CUTOFF);
  }
  if (env.VITE_DEFAULT_PERSON_ID) out.defaultPersonId = env.VITE_DEFAULT_PERSON_ID;
  return out;
}

/** Descarta valores nulos/NaN para que un config.json incompleto no rompa nada. */
function sanitize(raw: unknown): Partial<AppConfig> {
  if (!raw || typeof raw !== 'object') return {};
  const r = raw as Record<string, unknown>;
  const out: Partial<AppConfig> = {};

  if (typeof r.title === 'string' && r.title) out.title = r.title;
  if (typeof r.gedcomUrl === 'string' && r.gedcomUrl) out.gedcomUrl = r.gedcomUrl;
  if (typeof r.privacyMode === 'boolean') out.privacyMode = r.privacyMode;
  if (typeof r.privacyHideUndated === 'boolean') out.privacyHideUndated = r.privacyHideUndated;
  if (typeof r.defaultPersonId === 'string' && r.defaultPersonId) {
    out.defaultPersonId = r.defaultPersonId;
  }

  const cutoff = Number(r.privacyBirthYearCutoff);
  if (Number.isFinite(cutoff)) out.privacyBirthYearCutoff = cutoff;

  const gens = Number(r.defaultGenerations);
  if (Number.isFinite(gens) && gens >= 1) out.defaultGenerations = Math.min(gens, 10);

  const maxNodes = Number(r.maxNodes);
  if (Number.isFinite(maxNodes) && maxNodes >= 20) out.maxNodes = maxNodes;

  return out;
}

export async function loadConfig(): Promise<AppConfig> {
  let fromServer: Partial<AppConfig> = {};
  try {
    const res = await fetch('/config.json', { cache: 'no-store' });
    if (res.ok) fromServer = sanitize(await res.json());
  } catch {
    // En dev no existe: seguimos con defaults + VITE_*.
  }
  return { ...DEFAULTS, ...fromViteEnv(), ...fromServer };
}
