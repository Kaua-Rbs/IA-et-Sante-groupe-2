import { redirect } from '@sveltejs/kit';
import { clearTokens, refreshToken } from '#lib/server/session.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	redirect(303, '/');
};

export const actions = {
	default: async ({ cookies, locals }) => {
		// Révoque le refresh token côté API, puis efface les cookies quoi qu'il arrive
		const refresh = refreshToken(cookies);
		if (refresh) {
			await locals.api.post('/account/logout', { refresh_token: refresh }).catch(() => {});
		}
		clearTokens(cookies);
		redirect(303, '/');
	}
} satisfies Actions;
