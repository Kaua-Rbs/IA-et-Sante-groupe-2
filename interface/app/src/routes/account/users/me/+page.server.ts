import { fail, redirect } from '@sveltejs/kit';
import { actionFailure } from '#lib/server/api.ts';
import { clearTokens } from '#lib/server/session.ts';
import type { Surgeon, User } from '#lib/types.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	const [me, surgeons] = await Promise.all([
		locals.api.get<User>('/account/users/me'),
		locals.api.get<Surgeon[]>('/surgeons')
	]);
	return { me, surgeon: surgeons.find((s) => s.user_id === me.id) ?? null };
};

export const actions = {
	updateProfile: async ({ request, locals }) => {
		const data = await request.formData();
		try {
			await locals.api.patch('/account/users/me', { full_name: data.get('full_name')?.toString().trim() });
		} catch (error) {
			return actionFailure(error);
		}
		return { success: 'Profil mis à jour. Le nouveau nom apparaîtra à la prochaine connexion.' };
	},

	changePassword: async ({ request, locals, cookies }) => {
		const data = await request.formData();
		const next = data.get('new_password')?.toString() ?? '';
		if (next !== data.get('new_password_confirmation')?.toString()) {
			return fail(400, { error: 'Les nouveaux mots de passe ne correspondent pas.', reasons: [] });
		}
		try {
			await locals.api.post('/account/change-password', {
				current_password: data.get('current_password')?.toString() ?? '',
				new_password: next
			});
		} catch (error) {
			return actionFailure(error);
		}
		// L'API a révoqué toutes les sessions : on se reconnecte avec le nouveau mot de passe
		clearTokens(cookies);
		redirect(303, '/account/login');
	}
} satisfies Actions;
