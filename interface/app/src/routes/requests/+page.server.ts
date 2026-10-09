import { requireCapability } from '#lib/server/guards.ts';
import type { Patient, RequestStatus, Specialty, Surgeon, SurgicalRequest } from '#lib/types.ts';
import type { PageServerLoad } from './$types';

const STATUSES: RequestStatus[] = ['pending', 'scheduled', 'done', 'cancelled'];

export const load: PageServerLoad = async ({ locals, url }) => {
	requireCapability(locals.user, 'isStaff');
	const param = url.searchParams.get('status');
	const status = param === 'all' ? null : STATUSES.find((s) => s === param) ?? 'pending';

	const [requests, patients, surgeons, specialties] = await Promise.all([
		locals.api.get<SurgicalRequest[]>('/requests', { status, limit: 100 }),
		// TODO : remplacer par une recherche paginée côté API quand le volume augmentera
		locals.api.get<Patient[]>('/patients', { limit: 100 }),
		locals.api.get<Surgeon[]>('/surgeons'),
		locals.api.get<Specialty[]>('/specialties')
	]);
	return { requests, patients, surgeons, specialties, status: status ?? 'all' };
};
