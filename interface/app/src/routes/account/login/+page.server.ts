import { fail, redirect } from '@sveltejs/kit';
import { ApiError, createApi } from '#lib/server/api.ts';
import { storeTokens, type Tokens } from '#lib/server/session.ts';
import type { Actions, PageServerLoad } from './$types';

/** N'accepte qu'un chemin interne, pour ne pas rediriger vers un autre site. */
function safeTarget(value: string | null): string {
	return value && value.startsWith('/') && !value.startsWith('//') ? value : '/';
}

export const load: PageServerLoad = async ({ locals, url }) => {
	if (locals.user) redirect(303, safeTarget(url.searchParams.get('redirectTo')));
	return { registered: url.searchParams.get('registered') };
};

export const actions = {
	default: async ({ request, cookies, fetch, url }) => {
		const data = await request.formData();
		const email = data.get('email')?.toString() ?? '';
		const password = data.get('password')?.toString() ?? '';

		if (!email || !password) {
			return fail(400, { email, error: "L'email et le mot de passe sont requis." });
		}

		try {
			const tokens = await createApi(fetch, null).post<Tokens>(
				'/account/login',
				new URLSearchParams({ username: email, password })
			);
			storeTokens(cookies, tokens);
		} catch (error) {
			if (error instanceof ApiError) return fail(error.status, { email, error: error.message });
			throw error;
		}

		redirect(303, safeTarget(url.searchParams.get('redirectTo')));
	}
} satisfies Actions;
