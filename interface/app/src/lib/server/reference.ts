import type { Api } from './api.ts';
import type { BedUnit, Health, Room, Specialty, Surgeon } from '#lib/types.ts';

/** Données de configuration utilisées pour afficher des noms à la place des identifiants. */
export async function loadReference(api: Api) {
	const [specialties, rooms, surgeons, bedUnits, health] = await Promise.all([
		api.get<Specialty[]>('/specialties'),
		api.get<Room[]>('/rooms'),
		api.get<Surgeon[]>('/surgeons'),
		api.get<BedUnit[]>('/bed-units'),
		api.get<Health>('/health')
	]);
	return { specialties, rooms, surgeons, bedUnits, health };
}

export type Reference = Awaited<ReturnType<typeof loadReference>>;
