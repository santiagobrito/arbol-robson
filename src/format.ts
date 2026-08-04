/**
 * Formato de nombres y fechas en castellano.
 *
 * Topola trae formatDate/formatDateOrRange, pero su tabla de calificadores
 * ("abt", "cal", "est") no incluye castellano, asi que las fichas mostrarian
 * abreviaturas en ingles. Son treinta lineas: las escribimos nosotros.
 */
import type { DateOrRange, JsonIndi } from 'topola';

type GedcomDate = NonNullable<DateOrRange['date']>;

const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

const CALIFICADORES: Record<string, string> = {
  abt: 'h.', // hacia
  cal: 'calc.',
  est: 'est.',
};

function formatDate(date: GedcomDate | undefined): string {
  if (!date) return '';
  if (date.text) return date.text;
  if (date.year === undefined) return '';

  let out: string;
  if (date.day !== undefined && date.month !== undefined) {
    out = `${date.day} de ${MESES[date.month - 1] ?? '?'} de ${date.year}`;
  } else if (date.month !== undefined) {
    out = `${MESES[date.month - 1] ?? '?'} de ${date.year}`;
  } else {
    out = String(date.year);
  }

  const q = date.qualifier ? CALIFICADORES[date.qualifier.toLowerCase()] : undefined;
  return q ? `${q} ${out}` : out;
}

/** Formatea una fecha o un rango GEDCOM (BET/BEF/AFT) en castellano. */
export function formatDateOrRange(value: DateOrRange | undefined): string {
  if (!value) return '';
  if (value.date) return formatDate(value.date);

  const range = value.dateRange;
  if (!range) return '';
  const from = formatDate(range.from);
  const to = formatDate(range.to);

  if (from && to) return `entre ${from} y ${to}`;
  if (to) return `antes de ${to}`;
  if (from) return `despues de ${from}`;
  return '';
}

/** Ano de un evento, para ordenar y para etiquetas cortas. */
export function yearOf(value: DateOrRange | undefined): number | undefined {
  if (!value) return undefined;
  return value.date?.year ?? value.dateRange?.from?.year ?? value.dateRange?.to?.year;
}

/** Nombre completo. Devuelve un marcador si el GEDCOM no trae ninguno. */
export function fullName(indi: JsonIndi | undefined): string {
  if (!indi) return 'Desconocido';
  const name = [indi.firstName, indi.lastName].filter(Boolean).join(' ').trim();
  return name || 'Sin nombre';
}

/**
 * Etiqueta corta para listas: "Ana Robson (1902-1988)".
 * Respeta el modo privacidad porque lee los datos ya filtrados.
 */
export function nameWithYears(indi: JsonIndi | undefined): string {
  if (!indi) return 'Desconocido';
  const nacimiento = yearOf(indi.birth);
  const defuncion = yearOf(indi.death);
  if (!nacimiento && !defuncion) return fullName(indi);
  return `${fullName(indi)} (${nacimiento ?? '?'}–${defuncion ?? ''})`;
}

/** Texto de un evento: "12 de marzo de 1885, Buenos Aires, Argentina". */
export function eventText(event: { place?: string } & DateOrRange = {}): string {
  return [formatDateOrRange(event), event.place].filter(Boolean).join(', ');
}
