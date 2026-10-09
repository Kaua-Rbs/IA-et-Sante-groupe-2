// Résolution des identifiants en libellés à partir des listes de référence.

interface Named {
	id: number | string;
	name: string;
}

export function nameOf(list: Named[], id: number | string | null | undefined, fallback = '—'): string {
	if (id === null || id === undefined) return fallback;
	return list.find((item) => item.id === id)?.name ?? `#${id}`;
}

/** Libellé d'un patient pseudonymisé : identifiant externe, sinon début de l'UUID. */
export function patientLabel(patient: { id: string; external_ref: string | null } | undefined): string {
	if (!patient) return '—';
	return patient.external_ref ?? `Patient ${patient.id.slice(0, 8)}`;
}

export const sexLabel = (sex: number) => (sex === 1 ? 'Homme' : 'Femme');

/** Hospitalisation conventionnelle d'abord, puis ambulatoire, puis par nom. */
export function sortBedUnits<T extends { care_type: 'ambulatory' | 'conventional'; name: string }>(units: T[]): T[] {
	const order = { conventional: 0, ambulatory: 1 };
	return [...units].sort((a, b) => order[a.care_type] - order[b.care_type] || a.name.localeCompare(b.name));
}
