import { actionFailure } from '#lib/server/api.ts';
import { requireCapability } from '#lib/server/guards.ts';
import type { Group, User } from '#lib/types.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	requireCapability(locals.user, 'admin');
	const [users, groups, me] = await Promise.all([
		locals.api.get<User[]>('/account/users/', { limit: 100 }),
		locals.api.get<Group[]>('/account/groups/'),
		locals.api.get<User>('/account/users/me')
	]);
	// Comptes en attente d'abord, puis ordre alphabétique
	users.sort((a, b) => Number(a.validated) - Number(b.validated) || a.full_name.localeCompare(b.full_name));
	return { users, groups, currentUserId: me.id };
};

/** Exécute un appel d'API pour l'utilisateur du formulaire. */
async function forUser(request: Request, run: (userId: string, data: FormData) => Promise<unknown>) {
	const data = await request.formData();
	try {
		await run(data.get('userId')?.toString() ?? '', data);
	} catch (error) {
		return actionFailure(error);
	}
	return { success: 'Modification enregistrée.' };
}

export const actions = {
	validate: ({ request, locals }) =>
		forUser(request, (id) => locals.api.post(`/account/users/${id}/validate`)),

	toggleStatus: ({ request, locals }) =>
		forUser(request, (id, data) =>
			locals.api.patch(`/account/users/${id}`, { disabled: data.get('disabled') !== 'true' })
		),

	setRole: ({ request, locals }) =>
		forUser(request, (id, data) => {
			const path = `/account/users/${id}/groups/${data.get('groupId')}`;
			return data.get('enabled') === 'true' ? locals.api.post(path) : locals.api.del(path);
		}),

	deleteUser: ({ request, locals }) =>
		forUser(request, (id) => locals.api.del(`/account/users/${id}`))
} satisfies Actions;
