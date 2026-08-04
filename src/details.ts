/**
 * Ficha de persona.
 *
 * Se construye con el DOM directamente (nada de innerHTML con datos del
 * GEDCOM: los nombres y las notas son texto arbitrario del archivo y meterlos
 * como HTML seria un XSS con todas las letras).
 */
import { eventText, fullName, nameWithYears } from './format';
import type { JsonIndi, TreeIndex } from './types';

export interface DetailsCallbacks {
  /** Ir a otra persona sin mover el centro del arbol. */
  onNavigate: (id: string) => void;
  /** Redibujar el arbol tomando a esta persona como raiz. */
  onRecenter: (id: string) => void;
  onClose: () => void;
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function personLink(
  indi: JsonIndi | undefined,
  onNavigate: (id: string) => void,
): HTMLElement {
  if (!indi) return el('span', 'person-link person-link--unknown', 'Desconocido');
  const link = el('a', 'person-link', nameWithYears(indi));
  link.href = `#/${indi.id}`;
  link.addEventListener('click', (event) => {
    event.preventDefault();
    onNavigate(indi.id);
  });
  return link;
}

function section(title: string, items: HTMLElement[]): HTMLElement | null {
  if (items.length === 0) return null;
  const block = el('section', 'details-section');
  block.append(el('h3', 'details-section__title', title));
  const list = el('ul', 'details-list');
  for (const item of items) {
    const li = el('li');
    li.append(item);
    list.append(li);
  }
  block.append(list);
  return block;
}

function factRow(label: string, value: string): HTMLElement | null {
  if (!value) return null;
  const row = el('div', 'details-fact');
  row.append(el('span', 'details-fact__label', label), el('span', 'details-fact__value', value));
  return row;
}

export class DetailsPanel {
  private readonly body: HTMLElement;

  constructor(
    private readonly root: HTMLElement,
    private readonly index: TreeIndex,
    private readonly callbacks: DetailsCallbacks,
  ) {
    this.body = root.querySelector('.details__body') as HTMLElement;
    root.querySelector('.details__close')?.addEventListener('click', () => callbacks.onClose());
  }

  hide(): void {
    this.root.hidden = true;
  }

  show(id: string): void {
    const indi = this.index.indis.get(id);
    if (!indi) return;

    this.body.replaceChildren();
    this.body.append(this.header(indi), ...this.facts(indi), ...this.relations(indi));
    this.root.hidden = false;
    this.body.scrollTop = 0;
  }

  private header(indi: JsonIndi): HTMLElement {
    const head = el('div', 'details-header');
    head.append(el('h2', 'details-header__name', fullName(indi)));
    if (indi.maidenName && indi.maidenName !== indi.lastName) {
      head.append(el('p', 'details-header__maiden', `De soltera: ${indi.maidenName}`));
    }

    const recenter = el('button', 'btn btn--primary', 'Centrar el arbol aqui');
    recenter.type = 'button';
    recenter.addEventListener('click', () => this.callbacks.onRecenter(indi.id));

    const share = el('button', 'btn', 'Copiar enlace');
    share.type = 'button';
    share.addEventListener('click', () => {
      const url = `${location.origin}${location.pathname}#/${indi.id}`;
      void navigator.clipboard?.writeText(url).then(
        () => { share.textContent = 'Enlace copiado'; },
        () => { share.textContent = url; },
      );
      setTimeout(() => { share.textContent = 'Copiar enlace'; }, 2500);
    });

    const actions = el('div', 'details-header__actions');
    actions.append(recenter, share);
    head.append(actions);
    return head;
  }

  private facts(indi: JsonIndi): HTMLElement[] {
    const rows = [
      factRow('Nacimiento', eventText(indi.birth ?? {})),
      factRow('Defuncion', eventText(indi.death ?? {})),
    ].filter((row): row is HTMLElement => row !== null);

    const blocks: HTMLElement[] = [];
    if (rows.length > 0) {
      const facts = el('div', 'details-facts');
      facts.append(...rows);
      blocks.push(facts);
    }

    if (this.index.hidden.has(indi.id)) {
      blocks.push(
        el(
          'p',
          'details-notice',
          'Los datos personales de esta persona estan ocultos por privacidad.',
        ),
      );
    }

    for (const note of indi.notes ?? []) {
      blocks.push(el('p', 'details-note', note));
    }
    return blocks;
  }

  private relations(indi: JsonIndi): HTMLElement[] {
    const nav = this.callbacks.onNavigate;
    const blocks: (HTMLElement | null)[] = [];

    // Padres
    const famc = indi.famc ? this.index.fams.get(indi.famc) : undefined;
    const parents = [famc?.husb, famc?.wife]
      .filter((id): id is string => Boolean(id))
      .map((id) => personLink(this.index.indis.get(id), nav));
    blocks.push(section('Padres', parents));

    // Hermanos: los otros hijos de la familia de origen
    const siblings = (famc?.children ?? [])
      .filter((id) => id !== indi.id)
      .map((id) => personLink(this.index.indis.get(id), nav));
    blocks.push(section('Hermanos', siblings));

    // Parejas e hijos, familia por familia
    const spouses: HTMLElement[] = [];
    const children: HTMLElement[] = [];
    for (const famId of indi.fams ?? []) {
      const fam = this.index.fams.get(famId);
      if (!fam) continue;

      const spouseId = fam.husb === indi.id ? fam.wife : fam.husb;
      if (spouseId) {
        const row = el('div', 'details-spouse');
        row.append(personLink(this.index.indis.get(spouseId), nav));
        const marriage = eventText(fam.marriage ?? {});
        if (marriage) row.append(el('span', 'details-spouse__marriage', `Casamiento: ${marriage}`));
        spouses.push(row);
      }
      for (const childId of fam.children ?? []) {
        children.push(personLink(this.index.indis.get(childId), nav));
      }
    }
    blocks.push(section('Pareja', spouses));
    blocks.push(section('Hijos', children));

    return blocks.filter((block): block is HTMLElement => block !== null);
  }
}
