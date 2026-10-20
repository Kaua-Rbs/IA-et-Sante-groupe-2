// Réserve pour les urgences : part de chaque vacation que l'ordonnanceur laisse libre.
import { today } from '#lib/format.ts';
import type { VacationFill } from '#lib/types.ts';

export interface EmergencyReserve {
	/** Minutes gardées libres sur les vacations à venir */
	reserved: number;
	/** Vacations à venir dont le programme empiète sur la réserve */
	breached: number;
	/** Vacations à venir */
	vacations: number;
}

/** La réserve n'a de sens que sur les vacations qui n'ont pas encore eu lieu. */
export function emergencyReserve(fills: VacationFill[], margin: number, from = today()): EmergencyReserve {
	const upcoming = fills.filter((f) => f.date >= from);
	return {
		reserved: upcoming.reduce((sum, f) => sum + f.duration_min * margin, 0),
		breached: upcoming.filter((f) => f.planned_minutes > f.duration_min * (1 - margin) + 1e-9).length,
		vacations: upcoming.length
	};
}
