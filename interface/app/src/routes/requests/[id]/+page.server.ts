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

	// Vacations des propositions ouvertes et de l'intervention programmée
	const vacationIds = new Set([...open.map((p) => p.vacation_id), ...cases.map((c) => c.vacation_id)]);
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
		vacations,
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

const field = async (request: Request, key: string) =>
	(await request.formData()).get(key)?.toString() ?? '';

export const actions = {
	propose: ({ locals, params }) =>
		run(() => locals.api.post(`/requests/${params.id}/proposals`), 'Nouvelles dates proposées.'),

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
