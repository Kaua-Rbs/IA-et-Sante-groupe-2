import { actionFailure } from '#lib/server/api.ts';
import { requireCapability } from '#lib/server/guards.ts';
import { loadReference } from '#lib/server/reference.ts';
import type { User } from '#lib/types.ts';
import type { Actions, PageServerLoad, RequestEvent } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	const user = requireCapability(locals.user, 'canPlan');
	const [reference, users] = await Promise.all([
		loadReference(locals.api),
		// Seul un admin peut lister les comptes pour les lier à un chirurgien
		user.admin ? locals.api.get<User[]>('/account/users/', { limit: 100 }) : Promise.resolve([] as User[])
	]);
	return { ...reference, users };
};

const str = (data: FormData, key: string) => data.get(key)?.toString().trim() ?? '';
const num = (data: FormData, key: string) => Number(str(data, key));
const optionalNum = (data: FormData, key: string) => (str(data, key) ? num(data, key) : null);

/** Action de formulaire : vérifie le rôle, appelle l'API, renvoie un message. */
function action(success: string, call: (event: RequestEvent, data: FormData) => Promise<unknown>) {
	return async (event: RequestEvent) => {
		requireCapability(event.locals.user, 'canPlan');
		const data = await event.request.formData();
		try {
			await call(event, data);
		} catch (error) {
			return actionFailure(error, { section: str(data, 'section') });
		}
		return { success, section: str(data, 'section') };
	};
}

export const actions = {
	createSpecialty: action('Spécialité ajoutée.', ({ locals }, d) =>
		locals.api.post('/specialties', { name: str(d, 'name') })
	),
	deleteSpecialty: action('Spécialité supprimée.', ({ locals }, d) =>
		locals.api.del(`/specialties/${num(d, 'id')}`)
	),

	createRoom: action('Salle ajoutée.', ({ locals }, d) =>
		locals.api.post('/rooms', {
			name: str(d, 'name'),
			default_specialty_id: optionalNum(d, 'default_specialty_id')
		})
	),
	toggleRoom: action('Salle mise à jour.', ({ locals }, d) =>
		locals.api.patch(`/rooms/${num(d, 'id')}`, { active: str(d, 'active') !== 'true' })
	),

	createBedUnit: action('Unité ajoutée.', ({ locals }, d) =>
		locals.api.post('/bed-units', {
			name: str(d, 'name'),
			care_type: str(d, 'care_type'),
			capacity: num(d, 'capacity')
		})
	),
	updateCapacity: action('Capacité mise à jour.', ({ locals }, d) =>
		locals.api.patch(`/bed-units/${num(d, 'id')}`, { capacity: num(d, 'capacity') })
	),
	toggleBedUnit: action('Unité mise à jour.', ({ locals }, d) =>
		locals.api.patch(`/bed-units/${num(d, 'id')}`, { active: str(d, 'active') !== 'true' })
	),

	createSurgeon: action('Chirurgien ajouté.', ({ locals }, d) =>
		locals.api.post('/surgeons', {
			name: str(d, 'name'),
			specialty_id: num(d, 'specialty_id'),
			user_id: str(d, 'user_id') || null
		})
	),
	linkSurgeon: action('Compte lié.', ({ locals }, d) =>
		locals.api.patch(`/surgeons/${num(d, 'id')}`, { user_id: str(d, 'user_id') || null })
	),
	deleteSurgeon: action('Chirurgien supprimé.', ({ locals }, d) =>
		locals.api.del(`/surgeons/${num(d, 'id')}`)
	)
} satisfies Actions;
