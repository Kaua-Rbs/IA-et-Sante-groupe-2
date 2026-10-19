import { addDays, today } from '#lib/format.ts';
import type {
	PredictionAccuracy, SurgicalRequest, UnitOccupancy, VacationFill
} from '#lib/types.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	const user = locals.user;
	if (!user) return { dashboard: null };

	const api = locals.api;
	const start = today();
	const [occupancy, fills, pending, accuracy] = await Promise.all([
		api.get<UnitOccupancy[]>('/analytics/occupancy', { start, end: addDays(start, 13) }),
		api.get<VacationFill[]>('/analytics/vacations', { start, end: addDays(start, 6) }),
		user.isStaff
			? api.get<SurgicalRequest[]>('/requests', { status: 'pending', limit: 100 })
			: Promise.resolve(null),
		user.isStaff ? api.get<PredictionAccuracy>('/analytics/predictions') : Promise.resolve(null)
	]);
	return { dashboard: { occupancy, fills, pending, accuracy } };
};
