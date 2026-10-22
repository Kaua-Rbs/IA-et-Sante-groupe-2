import { actionFailure } from '#lib/server/api.ts';
import { requireCapability } from '#lib/server/guards.ts';
import { loadReference } from '#lib/server/reference.ts';
import { addDays, mondayOf, today } from '#lib/format.ts';
import type {
	CohortPreview, CommitmentConflict, DeprogrammedCase, PlannedCase, Proposal, ReplanRun,
	ReplanningStatus, Unavailability, Vacation, VacationFill
} from '#lib/types.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	const param = url.searchParams.get('week');
	const start = mondayOf(param && /^\d{4}-\d{2}-\d{2}$/.test(param) ? param : today());
	const end = addDays(start, 6);
	const api = locals.api;

	const [fills, vacations, cases, reference, replanning, conflicts, weekClosures, upcomingClosures, deprogrammed] = await Promise.all([
		api.get<VacationFill[]>('/analytics/vacations', { start, end }),
		api.get<Vacation[]>('/vacations', { start, end }),
		// Le détail des interventions est réservé au personnel ; les autres voient le remplissage
		locals.user?.isStaff
			? api.get<PlannedCase[]>('/cases', { start, end, status: 'planned' })
			: Promise.resolve([] as PlannedCase[]),
		loadReference(api),
		locals.user?.canPlan
			? api.get<ReplanningStatus>('/planning/replanning')
			: Promise.resolve(null),
		locals.user?.canPlan
			? api.get<CommitmentConflict[]>('/planning/commitment-conflicts')
			: Promise.resolve([] as CommitmentConflict[]),
		api.get<Unavailability[]>('/unavailabilities', { start, end }),
		locals.user?.canPlan
			? api.get<Unavailability[]>('/unavailabilities', { start: today() })
			: Promise.resolve([] as Unavailability[]),
		locals.user?.isStaff
			? api.get<DeprogrammedCase[]>('/planning/deprogrammed')
			: Promise.resolve([] as DeprogrammedCase[])
	]);

	const caseCount: Record<number, number> = {};
	for (const c of cases) caseCount[c.vacation_id] = (caseCount[c.vacation_id] ?? 0) + 1;

	return {
		start, end, fills, vacations, caseCount, replanning, conflicts, weekClosures, upcomingClosures,
		deprogrammed, ...reference
	};
};

/** Recalcule les dates proposées après un aléa ; les réservations confirmées ne bougent pas. */
async function refresh(api: App.Locals['api']) {
	const result = await api.post<{ run: ReplanRun | null }>('/planning/replanning/run');
	return { replanRun: result.run, refreshQueued: result.run === null };
}

export const actions = {
	createUnavailability: async ({ request, locals }) => {
		requireCapability(locals.user, 'canPlan');
		const data = await request.formData();
		const [kind, id] = (data.get('target')?.toString() ?? '').split(':');
		const time = (key: string) => {
			const value = data.get(key)?.toString();
			return value ? `${value}:00` : null;
		};
		try {
			await locals.api.post('/unavailabilities', {
				room_id: kind === 'room' ? Number(id) : null,
				surgeon_id: kind === 'surgeon' ? Number(id) : null,
				start_date: data.get('start_date'),
				end_date: data.get('end_date') || data.get('start_date'),
				start_time: time('start_time'),
				end_time: time('end_time'),
				reason: data.get('reason')?.toString().trim() || null
			});
			return {
				...(await refresh(locals.api)),
				success: 'Aléa enregistré : les interventions futures sans place sont déprogrammées et reçoivent des dates A/B.'
			};
		} catch (error) {
			return actionFailure(error);
		}
	},

	deleteUnavailability: async ({ request, locals }) => {
		requireCapability(locals.user, 'canPlan');
		const data = await request.formData();
		try {
			await locals.api.del(`/unavailabilities/${data.get('id')}`);
			return { ...(await refresh(locals.api)), success: 'Aléa levé, propositions actualisées.' };
		} catch (error) {
			return actionFailure(error);
		}
	},

	refreshProposals: async ({ locals }) => {
		requireCapability(locals.user, 'canPlan');
		try {
			return await refresh(locals.api);
		} catch (error) {
			return actionFailure(error);
		}
	},

	previewOptimization: async ({ request, locals }) => {
		requireCapability(locals.user, 'canPlan');
		const data = await request.formData();
		try {
			const preview = await locals.api.post<CohortPreview>('/planning/cohort-preview', {
				start: data.get('start'),
				end: data.get('end'),
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
				budget_seconds: 1
			});
			return { published };
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
			const result = await locals.api.del<{ deprogrammed: number }>(`/vacations/${data.get('vacationId')}`);
			await refresh(locals.api);
			return {
				success: result.deprogrammed
					? `Vacation supprimée : ${result.deprogrammed} intervention(s) déprogrammée(s), dates A/B proposées ci-dessous.`
					: 'Vacation supprimée.'
			};
		} catch (error) {
			return actionFailure(error);
		}
	},

	/** Reprogrammer des interventions touchées par un aléa : dates A/B calculées aussitôt. */
	reprogram: async ({ request, locals }) => {
		requireCapability(locals.user, 'isClinical');
		const data = await request.formData();
		// Un motif par intervention, dans le même ordre que les identifiants
		const reasons = data.getAll('reason').map((r) => r.toString().slice(0, 250) || null);
		let moved = 0;
		let withoutDate = 0;
		for (const [i, id] of data.getAll('caseId').entries()) {
			try {
				// Le créneau est fermé : l'intervention est déprogrammée même sans autre date
				const proposals = await locals.api.post<Proposal[]>(`/cases/${id}/reschedule`, {
					reason: reasons[i] ?? null, keep_if_no_date: false
				});
				moved += 1;
				if (!proposals.length) withoutDate += 1;
			} catch (error) {
				return actionFailure(error);
			}
		}
		const note = withoutDate
			? ` ${withoutDate} sans date libre dans sa fenêtre : élargissez-la depuis sa fiche.`
			: '';
		return { success: `${moved} intervention(s) déprogrammée(s) : « Planifier » pour choisir la nouvelle date.${note}` };
	}
} satisfies Actions;
