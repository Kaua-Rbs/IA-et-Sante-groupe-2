import { fail, redirect } from '@sveltejs/kit';
import { actionFailure } from '#lib/server/api.ts';
import { requireCapability } from '#lib/server/guards.ts';
import type { Patient, Specialty, Surgeon, SurgicalRequest, User } from '#lib/types.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	requireCapability(locals.user, 'isClinical');
	const [surgeons, specialties, patients, me] = await Promise.all([
		locals.api.get<Surgeon[]>('/surgeons'),
		locals.api.get<Specialty[]>('/specialties'),
		locals.api.get<Patient[]>('/patients', { limit: 100 }),
		locals.api.get<User>('/account/users/me')
	]);
	// Un chirurgien connecté est présélectionné
	const ownSurgeon = surgeons.find((s) => s.user_id === me.id)?.id ?? null;
	return { surgeons, specialties, patients, ownSurgeon };
};

const text = (data: FormData, key: string) => data.get(key)?.toString().trim() ?? '';

export const actions = {
	default: async ({ request, locals }) => {
		const data = await request.formData();
		const values = Object.fromEntries([...data.entries()].map(([k, v]) => [k, v.toString()]));
		const ccam = text(data, 'ccam_codes').toUpperCase().split(/[\s,;]+/).filter(Boolean);
		if (ccam.length === 0 || ccam.length > 4) {
			return fail(400, { values, error: 'Indiquez de 1 à 4 codes CCAM.', reasons: [] });
		}

		let created: SurgicalRequest;
		let patientId = text(data, 'patient_id');
		try {
			if (text(data, 'patient_mode') === 'new') {
				const patient = await locals.api.post<Patient>('/patients', {
					external_ref: text(data, 'external_ref') || null,
					birth_year: Number(text(data, 'birth_year')),
					sex: Number(text(data, 'sex'))
				});
				patientId = patient.id;
			}
			created = await locals.api.post<SurgicalRequest>('/requests', {
				patient_id: patientId,
				surgeon_id: Number(text(data, 'surgeon_id')),
				principal_diagnosis: text(data, 'principal_diagnosis').toUpperCase(),
				ccam_codes: ccam,
				intervention_type: text(data, 'intervention_type') || null,
				earliest_date: text(data, 'earliest_date'),
				latest_date: text(data, 'latest_date') || null
			});
		} catch (error) {
			// Patient déjà créé : on le resélectionne pour ne pas le dupliquer au prochain envoi
			if (patientId) Object.assign(values, { patient_mode: 'existing', patient_id: patientId });
			return actionFailure(error, { values });
		}

		// Les dates sont proposées tout de suite ; un échec reste visible sur la page de la demande
		await locals.api.post(`/requests/${created.id}/proposals`).catch(() => {});
		redirect(303, `/requests/${created.id}`);
	}
} satisfies Actions;
