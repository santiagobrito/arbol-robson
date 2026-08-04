/**
 * Render del arbol con Topola + zoom/desplazamiento.
 *
 * Topola dibuja el SVG y fija su tamano (updateSvgSize). El zoom NO se aplica
 * sobre el SVG sino sobre un div contenedor mediante transform CSS: asi Topola
 * es duena absoluta del SVG y no hay que pelear con los transform que ella
 * misma pone en sus grupos. d3-zoom se encarga de rueda, arrastre y pinza,
 * incluido el multitouch, que es lo que importa en el movil.
 */
import { select, type Selection } from 'd3-selection';
import 'd3-transition'; // amplia Selection con .transition(), usado por los botones de zoom
import { zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from 'd3-zoom';
import {
  AncestorChart,
  ChartColors,
  DescendantChart,
  DetailedRenderer,
  HourglassChart,
  createChart,
} from 'topola';
import type { JsonGedcomData, ViewMode } from './types';

const CHART_TYPES = {
  asc: AncestorChart,
  desc: DescendantChart,
  both: HourglassChart,
} as const;

const SCALE_EXTENT: [number, number] = [0.15, 2.5];
/** Un arrastre mayor que esto no debe contarse como clic en una tarjeta. */
const DRAG_THRESHOLD_PX = 8;

export class TreeView {
  private readonly viewportSel: Selection<HTMLElement, unknown, null, undefined>;
  private readonly behavior: ZoomBehavior<HTMLElement, unknown>;
  private dragDistance = 0;
  private lastTransform: ZoomTransform = zoomIdentity;

  constructor(
    private readonly viewport: HTMLElement,
    private readonly pan: HTMLElement,
    private readonly svg: SVGSVGElement,
    private readonly onSelectPerson: (id: string) => void,
  ) {
    this.viewportSel = select(this.viewport);

    this.behavior = zoom<HTMLElement, unknown>()
      .scaleExtent(SCALE_EXTENT)
      .on('start', () => {
        this.dragDistance = 0;
      })
      .on('zoom', (event: { transform: ZoomTransform }) => {
        const t = event.transform;
        this.dragDistance += Math.abs(t.x - this.lastTransform.x) + Math.abs(t.y - this.lastTransform.y);
        this.lastTransform = t;
        this.pan.style.transform = `translate(${t.x}px, ${t.y}px) scale(${t.k})`;
      });

    this.viewportSel.call(this.behavior);
    // El doble clic de d3 hace zoom; en un arbol es mas util recentrar, y la
    // recentrado ya lo da el clic normal. Lo desactivamos para evitar saltos.
    this.viewportSel.on('dblclick.zoom', null);
  }

  /** Dibuja el subarbol y deja la persona raiz centrada en pantalla. */
  render(json: JsonGedcomData, rootId: string, mode: ViewMode): void {
    // Topola no limpia el SVG anterior: si no lo vaciamos se acumulan renders.
    this.svg.replaceChildren();

    const chart = createChart({
      json,
      chartType: CHART_TYPES[mode],
      renderer: DetailedRenderer,
      svgSelector: `#${this.svg.id}`,
      indiCallback: (info: { id: string }) => {
        if (this.dragDistance > DRAG_THRESHOLD_PX) return;
        this.onSelectPerson(info.id);
      },
      animate: false,
      updateSvgSize: true,
      horizontal: false,
      colors: ChartColors.COLOR_BY_SEX,
      locale: 'es',
    });

    const info = chart.render({ startIndi: rootId });
    this.centerOn(info.origin);
  }

  /**
   * Coloca el punto `origin` del SVG (donde Topola situa la persona raiz) en
   * el centro del area visible.
   */
  private centerOn(origin: [number, number]): void {
    const vw = this.viewport.clientWidth;
    const vh = this.viewport.clientHeight;

    // Escala fija y legible, NO "encajar todo en pantalla": un arbol de varios
    // cientos de nodos es kilometricamente ancho, y encajarlo deja las tarjetas
    // a tamano de mosca y al usuario sin saber donde esta. Se entra cerca de la
    // persona enfocada y ya se aleja quien quiera la vista general.
    const k = vw < 640 ? 0.75 : 1;

    // Ligeramente por encima del centro: en la vista de descendientes casi todo
    // el contenido interesante cae hacia abajo.
    const tx = vw / 2 - origin[0] * k;
    const ty = vh * 0.42 - origin[1] * k;
    this.transformTo(zoomIdentity.translate(tx, ty).scale(k));
  }

  private transformTo(t: ZoomTransform): void {
    this.lastTransform = t;
    this.behavior.transform(this.viewportSel, t);
  }

  zoomBy(factor: number): void {
    this.behavior.scaleBy(this.viewportSel.transition().duration(180), factor);
  }
}
