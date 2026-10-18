import { actionFailure } from '#lib/server/api.ts';
import { requireCapability } from '#lib/server/guards.ts';
import { loadReference } from '#lib/server/reference.ts';
import { addDays, mondayOf, today } from '#lib/format.ts';
import type { CohortPreview, CommitmentConflict, PlannedCase, Proposal, ReplanRun, ReplanningStatus, RoomSimulationPreview, Vacation, VacationFill, WardSimulationPreview } from '#lib/types.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	const param = url.searchParams.get('week');
	const start = mondayOf(param && /^\d{4}-\d{2}-\d{2}$/.test(param) ? param : today());
	const end = addDays(start, 6);
	const api = locals.api;

	const [fills, vacations, cases, reference, methods, simulationMethods, replanning, conflicts] = await Promise.all([
		api.get<VacationFill[]>('/analytics/vacations', { start, end }),
		api.get<Vacation[]>('/vacations', { start, end }),
		// Le détail des interventions est réservé au personnel ; les autres voient le remplissage
		locals.user?.isStaff
			? api.get<PlannedCase[]>('/cases', { start, end, status: 'planned' })
			: Promise.resolve([] as PlannedCase[]),
		loadReference(api),
		locals.user?.canPlan
			? api.get<string[]>('/planning/methods')
			: Promise.resolve([] as string[]),
		locals.user?.canPlan
			? api.get<string[]>('/planning/room-simulation-methods')
			: Promise.resolve([] as string[]),
		locals.user?.canPlan
			? api.get<ReplanningStatus>('/planning/replanning')
			: Promise.resolve(null),
		locals.user?.canPlan
			? api.get<CommitmentConflict[]>('/planning/commitment-conflicts')
			: Promise.resolve([] as CommitmentConflict[])
	]);

	const caseCount: Record<number, number> = {};
	for (const c of cases) caseCount[c.vacation_id] = (caseCount[c.vacation_id] ?? 0) + 1;

	return { start, end, fills, vacations, caseCount, methods, simulationMethods, replanning, conflicts, ...reference };
};

export const actions = {
	refreshProposals: async ({ locals }) => {
		requireCapability(locals.user, 'canPlan');
		try {
			const result = await locals.api.post<{ run: ReplanRun | null }>('/planning/replanning/run');
			return { replanRun: result.run, refreshQueued: result.run === null };
		} catch (error) {
			return actionFailure(error);
		}
	},

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
	},

	previewOptimization: async ({ request, locals }) => {
		requireCapability(locals.user, 'canPlan');
		const data = await request.formData();
		try {
			const preview = await locals.api.post<CohortPreview>('/planning/cohort-preview', {
				start: data.get('start'),
				end: data.get('end'),
				method: data.get('method'),
				budget_seconds: 1
			});
			return { preview };
		} catch (error) {
			return actionFailure(error);
		}
	},

	publishOptimization: async ({ request, locals }) => {
		requireCapability(locals.user, 'canPlan');
		const data = await request.formData();
		try {
			const published = await locals.api.post<Proposal[]>('/planning/cohort-proposals', {
				start: data.get('start'),
				end: data.get('end'),
				method: data.get('method'),
				budget_seconds: 1
			});
			return { published };
		} catch (error) {
			return actionFailure(error);
		}
	},

	previewSimulation: async ({ request, locals }) => {
		requireCapability(locals.user, 'canPlan');
		const data = await request.formData();
		try {
			const simulation = await locals.api.post<RoomSimulationPreview>('/planning/room-simulation-preview', {
				date: data.get('date'),
				method: data.get('method'),
				policy: data.get('policy'),
				realized_factor: Number(data.get('realized_factor')),
				outage: data.has('outage')
			});
			return { simulation };
		} catch (error) {
			return actionFailure(error);
		}
	},

	previewWard: async ({ request, locals }) => {
		requireCapability(locals.user, 'canPlan');
		const data = await request.formData();
		try {
			const ward = await locals.api.post<WardSimulationPreview>('/planning/ward-simulation-preview', {
				start: data.get('start'),
				end: data.get('end'),
				method: data.get('method'),
				policy: data.get('policy'),
				realized_factor: Number(data.get('realized_factor')),
				los_factor: Number(data.get('los_factor')),
				outage: data.has('outage')
			});
			return { ward };
		} catch (error) {
			return actionFailure(error);
		}
	}
} satisfies Actions;
