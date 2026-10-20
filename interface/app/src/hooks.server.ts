import { redirect, type RequestEvent } from '@sveltejs/kit';
import type { Handle, HandleFetch } from '@sveltejs/kit/hooks';
import { KYST_API_URL } from '$app/env/private';
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

// Adresse du navigateur. En production, seul le reverse proxy joint le front (pare-feu) :
// la dernière entrée de X-Forwarded-For est celle qu'il a ajoutée.
function clientAddress(event: RequestEvent): string {
	const forwarded = event.request.headers.get('x-forwarded-for')?.split(',').at(-1)?.trim();
	return forwarded || event.getClientAddress();
}

// Chaque appel à l'API transmet l'adresse du navigateur : elle figure dans la trace d'accès
// de l'API et sert à limiter les tentatives de connexion par navigateur.
export const handleFetch: HandleFetch = async ({ event, request, fetch }) => {
	if (request.url.startsWith(KYST_API_URL)) {
		request.headers.set('x-forwarded-for', clientAddress(event));
	}
	return fetch(request);
};
