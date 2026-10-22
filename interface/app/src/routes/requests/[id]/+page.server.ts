import { actionFailure } from '#lib/server/api.ts';
import { requireCapability } from '#lib/server/guards.ts';
import { loadReference } from '#lib/server/reference.ts';
import type {
	Patient, PlannedCase, Prediction, Proposal, SurgicalRequest, Vacation
} from '#lib/types.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, params }) => {
	requireCapability(locals.user, 'isStaff');
	const api = locals.api;
	const request = await api.get<SurgicalRequest>(`/requests/${params.id}`);
	const [patient, predictions, proposals, cases, reference] = await Promise.all([
		api.get<Patient>(`/patients/${request.patient_id}`),
		api.get<Prediction[]>(`/requests/${request.id}/predictions`),
		api.get<Proposal[]>(`/requests/${request.id}/proposals`),
		api.get<PlannedCase[]>('/cases', { request_id: request.id }),
		loadReference(api)
	]);

	const open = proposals.filter((p) => p.status === 'proposed').sort((a, b) => a.rank - b.rank);
	const history = proposals.filter((p) => p.status !== 'proposed');
	const currentCase = cases.find((c) => c.status !== 'cancelled') ?? null;
	// Dernière réservation perdue sur un aléa, une urgence ou un déplacement
	const deprogrammed = request.status === 'pending'
		? cases.filter((c) => c.cancel_reason).sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null
		: null;

	// Vacations des propositions ouvertes et de l'intervention programmée
	const vacationIds = new Set([...open.map((p) => p.vacation_id), ...cases.map((c) => c.vacation_id)]);
	// Interventions qu'une date urgente reporterait, pour que le praticien décide en connaissance de cause
	const displacedIds = new Set(open.flatMap((p) => p.displaced_case_ids ?? []));
	const displaced = (
		await Promise.allSettled([...displacedIds].map((id) => api.get<PlannedCase>(`/cases/${id}`)))
	).flatMap((r) => (r.status === 'fulfilled' ? [r.value] : []));
	// Une vacation supprimée depuis ne doit pas empêcher d'afficher la demande
	const vacations = (
		await Promise.allSettled([...vacationIds].map((id) => api.get<Vacation>(`/vacations/${id}`)))
	).flatMap((r) => (r.status === 'fulfilled' ? [r.value] : []));

	return {
		request,
		patient,
		prediction: predictions[0] ?? null,
		open,
		history,
		currentCase,
		deprogrammed,
		vacations,
		displaced,
		...reference
	};
};

async function run(call: () => Promise<unknown>, success: string) {
	try {
		await call();
	} catch (error) {
		return actionFailure(error);
	}
	return { success };
}

/** Le message dit ce qui s'est passé : une liste vide n'est pas un succès. */
async function proposeDates(api: App.Locals['api'], id: string) {
	try {
		const proposals = await api.post<Proposal[]>(`/requests/${id}/proposals`);
		return proposals.length
			? { success: `${proposals.length === 1 ? 'Une date proposée' : `${proposals.length} dates proposées`}.` }
			: { info: 'Aucune date libre dans la fenêtre demandée : élargissez-la ci-dessous.' };
	} catch (error) {
		return actionFailure(error);
	}
}

const field = async (request: Request, key: string) =>
	(await request.formData()).get(key)?.toString() ?? '';

export const actions = {
	propose: ({ locals, params }) => proposeDates(locals.api, params.id),

	/** Repousser la date limite de la demande, puis chercher de nouvelles dates. */
	widen: async ({ request, locals, params }) => {
		const latest = await field(request, 'latest_date');
		try {
			await locals.api.patch(`/requests/${params.id}`, { latest_date: latest || null });
		} catch (error) {
			return actionFailure(error);
		}
		return proposeDates(locals.api, params.id);
	},

	accept: async ({ request, locals }) => {
		const id = await field(request, 'proposalId');
		return run(() => locals.api.post(`/proposals/${id}/accept`), 'Date confirmée : l\'intervention est programmée.');
	},

	reject: async ({ request, locals }) => {
		const id = await field(request, 'proposalId');
		return run(() => locals.api.post(`/proposals/${id}/reject`), 'Proposition écartée.');
	},

	cancelRequest: ({ locals, params }) =>
		run(() => locals.api.post(`/requests/${params.id}/cancel`), 'Demande annulée.'),

	cancelCase: async ({ request, locals }) => {
		const id = await field(request, 'caseId');
		return run(
			() => locals.api.post(`/cases/${id}/cancel`),
			'Intervention annulée : le créneau et le lit sont libérés, la demande est à reprogrammer.'
		);
	},

	reschedule: async ({ request, locals }) => {
		const id = await field(request, 'caseId');
		return run(
			() => locals.api.post(`/cases/${id}/reschedule`),
			'Patient à déplacer : le créneau et le lit sont libérés, choisissez une nouvelle date.'
		);
	},

	outcome: async ({ request, locals }) => {
		const data = await request.formData();
		return run(
			() =>
				locals.api.post(`/cases/${data.get('caseId')}/outcome`, {
					actual_room_minutes: Number(data.get('actual_room_minutes')),
					actual_los_days: Number(data.get('actual_los_days'))
				}),
			'Durées réelles enregistrées.'
		);
	}
} satisfies Actions;
