import { actionFailure } from '#lib/server/api.ts';
import { requireCapability } from '#lib/server/guards.ts';
import { loadReference } from '#lib/server/reference.ts';
import { addDays, mondayOf, today } from '#lib/format.ts';
import type { PlannedCase, Vacation, VacationFill } from '#lib/types.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	const param = url.searchParams.get('week');
	const start = mondayOf(param && /^\d{4}-\d{2}-\d{2}$/.test(param) ? param : today());
	const end = addDays(start, 6);
	const api = locals.api;

	const [fills, vacations, cases, reference] = await Promise.all([
		api.get<VacationFill[]>('/analytics/vacations', { start, end }),
		api.get<Vacation[]>('/vacations', { start, end }),
		// Le détail des interventions est réservé au personnel ; les autres voient le remplissage
		locals.user?.isStaff
			? api.get<PlannedCase[]>('/cases', { start, end, status: 'planned' })
			: Promise.resolve([] as PlannedCase[]),
		loadReference(api)
	]);

	const caseCount: Record<number, number> = {};
	for (const c of cases) caseCount[c.vacation_id] = (caseCount[c.vacation_id] ?? 0) + 1;

	return { start, end, fills, vacations, caseCount, ...reference };
};

export const actions = {
	createVacation: async ({ request, locals }) => {
		requireCapability(locals.user, 'canPlan');
		const data = await request.formData();
		const surgeon = data.get('surgeon_id')?.toString();
		try {
			await locals.api.post('/vacations', {
				room_id: Number(data.get('room_id')),
				specialty_id: Number(data.get('specialty_id')),
				surgeon_id: surgeon ? Number(surgeon) : null,
				date: data.get('date'),
				start_time: `${data.get('start_time')}:00`,
				duration_min: Number(data.get('duration_min'))
			});
		} catch (error) {
			return actionFailure(error);
		}
		return { success: 'Vacation ajoutée.' };
	},

	deleteVacation: async ({ request, locals }) => {
		requireCapability(locals.user, 'canPlan');
		const data = await request.formData();
		try {
			await locals.api.del(`/vacations/${data.get('vacationId')}`);
		} catch (error) {
			return actionFailure(error);
		}
		return { success: 'Vacation supprimée.' };
	}
} satisfies Actions;
