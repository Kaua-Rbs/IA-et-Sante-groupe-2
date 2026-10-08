import { redirect } from '@sveltejs/kit';
import type { Handle } from '@sveltejs/kit/hooks';
import { createApi } from '#lib/server/api.ts';
import { resolveSession } from '#lib/server/session.ts';

// Pages accessibles sans être connecté
const PUBLIC_ROUTES = new Set(['/', '/account/login', '/account/register']);

export const handle: Handle = async ({ event, resolve }) => {
	const session = await resolveSession(event.cookies, event.fetch);
	event.locals.user = session?.user ?? null;
	event.locals.api = createApi(event.fetch, session?.token ?? null);

	const routeId = event.route.id;
	if (!session && routeId && !PUBLIC_ROUTES.has(routeId)) {
		const target = event.url.pathname + event.url.search;
		redirect(303, `/account/login?redirectTo=${encodeURIComponent(target)}`);
	}

	return resolve(event);
};
