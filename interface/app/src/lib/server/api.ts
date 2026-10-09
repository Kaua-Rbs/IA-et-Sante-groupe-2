// Client de l'API KYST, utilisé uniquement côté serveur : le jeton ne quitte jamais
// les cookies HttpOnly et le navigateur ne parle qu'à SvelteKit (pas de CORS).

import { error, fail, redirect, type ActionFailure } from '@sveltejs/kit';
import { KYST_API_URL } from '$app/env/private';

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string,
		public reasons: string[] = []
	) {
		super(message);
	}
}

// Messages de l'API traduits pour l'interface
const MESSAGES: Record<string, string> = {
	'Incorrect username or password': 'Adresse email ou mot de passe incorrect.',
	'Inactive user': 'Ce compte a été désactivé.',
	'Account pending validation': "Ce compte attend la validation d'un administrateur.",
	'Username or email already exists': 'Cet email est déjà utilisé.',
	'Insufficient role': "Votre rôle ne permet pas cette action.",
	'Admin access required': 'Accès administrateur requis.',
	'Conflicts with existing data': 'Cet élément existe déjà.',
	'Still referenced by other data': 'Cet élément est encore utilisé ailleurs.',
	'Current password is incorrect': 'Mot de passe actuel incorrect.',
	'Cannot delete your own account': 'Vous ne pouvez pas supprimer votre propre compte.',
	'Cannot remove your own admin role': 'Vous ne pouvez pas retirer votre propre rôle administrateur.',
	'Proposal is no longer feasible; generate new proposals':
		"Ce créneau n'est plus disponible : générez de nouvelles propositions."
};

function translate(detail: unknown, status: number): { message: string; reasons: string[] } {
	if (typeof detail === 'string') {
		if (detail.startsWith('Overlaps vacation')) {
			return { message: 'Cette vacation chevauche une autre vacation de la salle.', reasons: [] };
		}
		return { message: MESSAGES[detail] ?? detail, reasons: [] };
	}
	if (Array.isArray(detail)) {
		// Erreurs de validation FastAPI : [{ loc, msg }, ...]
		const reasons = detail.map((d) => `${(d.loc ?? []).slice(1).join('.')} : ${d.msg}`);
		return { message: 'Certaines informations saisies sont invalides.', reasons };
	}
	if (detail && typeof detail === 'object' && 'message' in detail) {
		const d = detail as { message: string; reasons?: string[] };
		return { message: MESSAGES[d.message] ?? d.message, reasons: d.reasons ?? [] };
	}
	if (status === 429) return { message: 'Trop de tentatives. Réessayez dans une minute.', reasons: [] };
	return { message: `Erreur de l'API (${status}).`, reasons: [] };
}

type Fetch = typeof fetch;
type Query = Record<string, string | number | boolean | null | undefined>;

export function createApi(fetchFn: Fetch, token: string | null) {
	async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
		const url = new URL(KYST_API_URL + path);
		for (const [key, value] of Object.entries(query ?? {})) {
			if (value !== null && value !== undefined && value !== '') url.searchParams.set(key, String(value));
		}
		const headers: Record<string, string> = {};
		if (token) headers.Authorization = `Bearer ${token}`;
		let payload: BodyInit | undefined;
		if (body instanceof URLSearchParams) {
			payload = body;
		} else if (body !== undefined) {
			headers['Content-Type'] = 'application/json';
			payload = JSON.stringify(body);
		}

		let response: Response;
		try {
			response = await fetchFn(url, { method, headers, body: payload });
		} catch {
			throw new ApiError(503, "Impossible de joindre l'API KYST.");
		}
		if (!response.ok) {
			const data = await response.json().catch(() => ({}));
			const { message, reasons } = translate(data.detail, response.status);
			throw new ApiError(response.status, message, reasons);
		}
		return (await response.json()) as T;
	}

	/** Lecture pour une fonction `load` : les erreurs deviennent des pages d'erreur SvelteKit. */
	async function get<T>(path: string, query?: Query): Promise<T> {
		try {
			return await request<T>('GET', path, undefined, query);
		} catch (e) {
			if (!(e instanceof ApiError)) throw e;
			if (e.status === 401) redirect(303, '/account/login');
			error(e.status, e.message);
		}
	}

	return {
		get,
		post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
		patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
		del: <T>(path: string) => request<T>('DELETE', path)
	};
}

export type Api = ReturnType<typeof createApi>;

/** Transforme une erreur d'API en échec d'action de formulaire ; relance le reste. */
export function actionFailure<Extra extends Record<string, unknown> = Record<never, never>>(
	error: unknown,
	extra: Extra = {} as Extra
): ActionFailure<Extra & { error: string; reasons: string[] }> {
	if (error instanceof ApiError) {
		return fail(error.status, { ...extra, error: error.message, reasons: error.reasons });
	}
	throw error;
}
