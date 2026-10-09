import { addDays, today } from '#lib/format.ts';
import type { UnitOccupancy } from '#lib/types.ts';
import type { PageServerLoad } from './$types';

const PERIODS = [7, 14, 28];

export const load: PageServerLoad = async ({ locals, url }) => {
	const param = url.searchParams.get('start');
	const start = param && /^\d{4}-\d{2}-\d{2}$/.test(param) ? param : today();
	const days = PERIODS.find((p) => String(p) === url.searchParams.get('days')) ?? 14;
	const occupancy = await locals.api.get<UnitOccupancy[]>('/analytics/occupancy', {
		start,
		end: addDays(start, days - 1)
	});
	return { occupancy, start, days, periods: PERIODS };
};
