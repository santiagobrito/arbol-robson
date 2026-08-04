import './styles.css';
import { gedcomToJson } from 'topola';
import { TreeView } from './chart';
import { loadConfig, type AppConfig } from './config';
import { DetailsPanel } from './details';
import { buildIndex } from './privacy';
import { parseHash, stateToHash } from './router';
import { buildSearchIndex, searchPeople, type SearchEntry } from './search';
import { extractSubtree } from './subtree';
import type { AppState, TreeIndex, ViewMode } from './types';

const $ = <T extends Element = HTMLElement>(selector: string): T =>
  document.querySelector(selector) as T;

/** Persona por defecto: la mas antigua con descendencia, o sea la raiz del arbol. */
function pickDefaultPerson(index: TreeIndex, configured: string | null): string {
  if (configured && index.indis.has(configured)) return configured;

  let best: { id: string; year: number } | null = null;
  for (const indi of index.indis.values()) {
    if (!indi.fams?.length) continue;
    const year = indi.birth?.date?.year ?? 9999;
    if (!best || year < best.year) best = { id: indi.id, year };
  }
  return best?.id ?? index.indis.keys().next().value ?? '';
}

class App {
  private state: AppState;
  private readonly defaults: AppState;
  private readonly searchIndex: SearchEntry[];
  private readonly tree: TreeView;
  private readonly details: DetailsPanel;
  private searchTimer = 0;

  constructor(
    private readonly cfg: AppConfig,
    private readonly index: TreeIndex,
  ) {
    this.searchIndex = buildSearchIndex(index);
    this.defaults = {
      personId: pickDefaultPerson(index, cfg.defaultPersonId),
      mode: 'both',
      generations: cfg.defaultGenerations,
    };
    this.state = parseHash(location.hash, this.defaults);
    if (!index.indis.has(this.state.personId)) {
      this.state = { ...this.state, personId: this.defaults.personId };
    }

    this.tree = new TreeView(
      $('#viewport'),
      $('#pan'),
      $<SVGSVGElement>('#chart'),
      (id) => this.details.show(id),
    );

    this.details = new DetailsPanel($('#details'), index, {
      onNavigate: (id) => this.details.show(id),
      onRecenter: (id) => {
        this.details.hide();
        this.go({ personId: id });
      },
      onClose: () => this.details.hide(),
    });

    this.bindControls();
    window.addEventListener('hashchange', () => this.onHashChange());
    this.render();
  }

  /** Cambia el estado y deja que hashchange dispare el render (una sola via). */
  private go(patch: Partial<AppState>): void {
    const next = { ...this.state, ...patch };
    const hash = stateToHash(next, this.defaults);
    if (hash === location.hash) {
      this.state = next;
      this.render();
      return;
    }
    location.hash = hash;
  }

  private onHashChange(): void {
    const next = parseHash(location.hash, this.defaults);
    if (!this.index.indis.has(next.personId)) return;
    // Al saltar a otra persona (enlace compartido, atras del navegador) la
    // ficha abierta es de la anterior: dejarla puesta despista.
    if (next.personId !== this.state.personId) this.details.hide();
    this.state = next;
    this.render();
  }

  private render(): void {
    const { personId, mode, generations } = this.state;
    const result = extractSubtree(this.index, personId, mode, generations, this.cfg.maxNodes);

    this.tree.render(result.json, personId, mode);

    const indi = this.index.indis.get(personId);
    $('#current-person').textContent = [indi?.firstName, indi?.lastName].filter(Boolean).join(' ');

    const notice = $('#truncation-notice');
    if (result.truncated) {
      notice.textContent =
        `Mostrando ${result.shown} de ${result.total} personas. ` +
        'Toca a alguien del borde y elegi "Centrar el arbol aqui" para seguir.';
      notice.hidden = false;
    } else {
      notice.hidden = true;
    }

    for (const button of document.querySelectorAll<HTMLButtonElement>('[data-mode]')) {
      button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
    }
    const gensInput = $<HTMLInputElement>('#generations');
    gensInput.value = String(generations);
    $('#generations-value').textContent = String(generations);
  }

  private bindControls(): void {
    for (const button of document.querySelectorAll<HTMLButtonElement>('[data-mode]')) {
      button.addEventListener('click', () => this.go({ mode: button.dataset.mode as ViewMode }));
    }

    $('#generations').addEventListener('input', (event) => {
      const value = Number((event.target as HTMLInputElement).value);
      $('#generations-value').textContent = String(value);
      this.go({ generations: value });
    });

    $('#zoom-in').addEventListener('click', () => this.tree.zoomBy(1.35));
    $('#zoom-out').addEventListener('click', () => this.tree.zoomBy(1 / 1.35));

    const about = $<HTMLDialogElement>('#about');
    // El panel de créditos no puede afirmar algo que la configuración desmiente.
    // Va en castellano y en inglés: buena parte de la familia del árbol está en
    // Australia, Reino Unido, Estados Unidos y Canadá.
    for (const sufijo of ['', '-en']) {
      $(`#about-privacy-on${sufijo}`).hidden = !this.cfg.privacyMode;
      $(`#about-privacy-off${sufijo}`).hidden = this.cfg.privacyMode;
    }
    $('#about-open').addEventListener('click', () => about.showModal());

    const input = $<HTMLInputElement>('#search-input');
    const results = $('#search-results');

    input.addEventListener('input', () => {
      window.clearTimeout(this.searchTimer);
      this.searchTimer = window.setTimeout(() => this.renderSearch(input.value, results), 120);
    });
    input.addEventListener('focus', () => this.renderSearch(input.value, results));
    document.addEventListener('click', (event) => {
      if (!$('#search').contains(event.target as Node)) results.hidden = true;
    });
  }

  private renderSearch(query: string, container: HTMLElement): void {
    const matches = searchPeople(this.searchIndex, query);
    container.replaceChildren();

    if (matches.length === 0) {
      container.hidden = query.trim().length < 2;
      if (!container.hidden) {
        const empty = document.createElement('p');
        empty.className = 'search-empty';
        empty.textContent = 'Sin resultados';
        container.append(empty);
      }
      return;
    }

    for (const match of matches) {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'search-result';
      item.textContent = match.label;
      item.addEventListener('click', () => {
        container.hidden = true;
        $<HTMLInputElement>('#search-input').blur();
        this.details.hide();
        this.go({ personId: match.id });
      });
      container.append(item);
    }
    container.hidden = false;
  }
}

async function bootstrap(): Promise<void> {
  const status = $('#status');
  try {
    const cfg = await loadConfig();
    document.title = cfg.title;
    $('#app-title').textContent = cfg.title;

    status.textContent = 'Cargando el arbol...';
    const response = await fetch(cfg.gedcomUrl, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`No se pudo leer el GEDCOM (HTTP ${response.status})`);

    // Se quita el BOM: parse-gedcom no lo tolera en la etiqueta HEAD.
    const text = (await response.text()).replace(/^\uFEFF/, '');

    status.textContent = 'Procesando...';
    const index = buildIndex(gedcomToJson(text), cfg);
    if (index.indis.size === 0) throw new Error('El archivo GEDCOM no contiene personas.');

    status.hidden = true;
    $('#app').hidden = false;
    new App(cfg, index);
  } catch (error) {
    status.hidden = false;
    status.className = 'status status--error';
    status.textContent = error instanceof Error ? error.message : 'Error inesperado';
  }
}

void bootstrap();
