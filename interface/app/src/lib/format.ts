// Formatage des dates et durées pour l'affichage (fuseau local, français).

/** Date ISO "YYYY-MM-DD" -> Date locale à midi (évite les décalages de fuseau). */
export function parseDay(iso: string): Date {
	const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
	return new Date(y, m - 1, d, 12);
}

export function toIsoDay(date: Date): string {
	const y = date.getFullYear();
	const m = String(date.getMonth() + 1).padStart(2, '0');
	const d = String(date.getDate()).padStart(2, '0');
	return `${y}-${m}-${d}`;
}

export function addDays(iso: string, days: number): string {
	const date = parseDay(iso);
	date.setDate(date.getDate() + days);
	return toIsoDay(date);
}

export function today(): string {
	return toIsoDay(new Date());
}

/** Lundi de la semaine contenant `iso`. */
export function mondayOf(iso: string): string {
	const date = parseDay(iso);
	const offset = (date.getDay() + 6) % 7;
	return addDays(iso, -offset);
}

const longDay = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
const shortDay = new Intl.DateTimeFormat('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' });
const plainDay = new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' });
const dateTime = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' });

/** « mardi 14 octobre » */
export const formatLongDay = (iso: string) => longDay.format(parseDay(iso));
/** « mar. 14 oct. » */
export const formatShortDay = (iso: string) => shortDay.format(parseDay(iso));
/** « 14/10/2026 » */
export const formatDay = (iso: string) => plainDay.format(parseDay(iso));
/** Horodatage UTC naïf de l'API -> date et heure locales */
export const formatDateTime = (iso: string) => dateTime.format(new Date(iso.endsWith('Z') ? iso : iso + 'Z'));

/** « 08:00:00 » -> « 08h00 » */
export const formatTime = (time: string) => time.slice(0, 5).replace(':', 'h');

/** Créneau « 08h00–12h00 » à partir de l'heure de début et de la durée. */
export function formatSlot(start: string, durationMin: number): string {
	const total = Number(start.slice(0, 2)) * 60 + Number(start.slice(3, 5)) + durationMin;
	const end = `${String(Math.floor(total / 60) % 24).padStart(2, '0')}h${String(total % 60).padStart(2, '0')}`;
	return `${formatTime(start)}–${end}`;
}

/** 95 -> « 1 h 35 » ; 45 -> « 45 min » */
export function formatMinutes(minutes: number): string {
	const m = Math.round(minutes);
	if (m < 60) return `${m} min`;
	const rest = m % 60;
	return rest ? `${Math.floor(m / 60)} h ${String(rest).padStart(2, '0')}` : `${m / 60} h`;
}

export const formatPercent = (rate: number) => `${Math.round(rate * 100)} %`;

export function plural(count: number, singular: string, pluralForm = singular + 's'): string {
	return `${count} ${count > 1 ? pluralForm : singular}`;
}
