import { fail, redirect } from '@sveltejs/kit';
import { actionFailure, createApi } from '#lib/server/api.ts';
import type { User } from '#lib/types.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	if (locals.user) redirect(303, '/');
};

export const actions = {
	default: async ({ request, fetch }) => {
		const data = await request.formData();
		const values = {
			lastName: data.get('last_name')?.toString().trim() ?? '',
			firstName: data.get('first_name')?.toString().trim() ?? '',
			email: data.get('email')?.toString().trim() ?? ''
		};
		const password = data.get('password')?.toString() ?? '';

		if (password !== data.get('password_confirmation')?.toString()) {
			return fail(400, { ...values, error: 'Les mots de passe ne correspondent pas.', reasons: [] });
		}

		let user: User;
		try {
			user = await createApi(fetch, null).post<User>('/account/users/create', {
				username: values.email,
				email: values.email,
				full_name: `${values.firstName} ${values.lastName}`.trim(),
				password
			});
		} catch (error) {
			return actionFailure(error, values);
		}

		redirect(303, `/account/login?registered=${user.validated ? 'ok' : 'pending'}`);
	}
} satisfies Actions;
