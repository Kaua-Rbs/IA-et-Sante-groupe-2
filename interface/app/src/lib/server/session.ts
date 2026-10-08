// Session : jetons de l'API dans des cookies HttpOnly, renouvelés automatiquement.

import type { Cookies } from '@sveltejs/kit';
import { dev } from '$app/env';
import { ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS } from '$app/env/private';
import type { Role, SessionUser } from '#lib/types.ts';
import { createApi } from './api.ts';

const ACCESS = 'access_token';
const REFRESH = 'refresh_token';
// Mêmes variables que l'API (kyst.env) : les cookies vivent aussi longtemps que les jetons
const ACCESS_MAX_AGE = 60 * ACCESS_TOKEN_EXPIRE_MINUTES;
const REFRESH_MAX_AGE = 60 * 60 * 24 * REFRESH_TOKEN_EXPIRE_DAYS;

interface Claims {
	sub: string;
	full_name?: string;
	admin?: boolean;
	doctor?: boolean;
	roles?: Role[];
	exp?: number;
}

export interface Tokens {
	access_token: string;
	refresh_token: string;
}

/** Lit le contenu du JWT sans vérifier la signature : l'API la vérifie à chaque appel. */
function decode(token: string): Claims | null {
	try {
		const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
		return JSON.parse(Buffer.from(payload, 'base64').toString('utf8'));
	} catch {
		return null;
	}
}

function isFresh(claims: Claims | null): claims is Claims {
	// Marge de 30 s pour ne pas envoyer un jeton qui expire pendant la requête
	return !!claims?.exp && claims.exp * 1000 > Date.now() + 30_000;
}

export function sessionUser(claims: Claims): SessionUser {
	const roles = claims.roles ?? [];
	const fullName = claims.full_name ?? claims.sub;
	const [first, ...rest] = fullName.split(' ');
	const admin = claims.admin === true;
	const has = (...r: Role[]) => admin || r.some((role) => roles.includes(role));
	return {
		username: claims.sub,
		fullName,
		displayName: rest.length ? `${first.charAt(0).toUpperCase()}. ${rest.join(' ')}` : fullName,
		admin,
		doctor: claims.doctor === true,
		roles,
		canPlan: has('planner'),
		isClinical: has('doctor', 'secretary'),
		isStaff: has('doctor', 'secretary', 'planner')
	};
}

export function storeTokens(cookies: Cookies, tokens: Tokens) {
	const options = { path: '/', httpOnly: true, sameSite: 'lax' as const, secure: !dev };
	cookies.set(ACCESS, tokens.access_token, { ...options, maxAge: ACCESS_MAX_AGE });
	cookies.set(REFRESH, tokens.refresh_token, { ...options, maxAge: REFRESH_MAX_AGE });
}

export function clearTokens(cookies: Cookies) {
	cookies.delete(ACCESS, { path: '/' });
	cookies.delete(REFRESH, { path: '/' });
}

export function refreshToken(cookies: Cookies): string | null {
	return cookies.get(REFRESH) ?? null;
}

/** Jeton d'accès valide pour cette requête, renouvelé si besoin ; null si déconnecté. */
export async function resolveSession(
	cookies: Cookies,
	fetchFn: typeof fetch
): Promise<{ token: string; user: SessionUser } | null> {
	const access = cookies.get(ACCESS);
	const claims = access ? decode(access) : null;
	if (access && isFresh(claims)) {
		return { token: access, user: sessionUser(claims) };
	}

	const refresh = cookies.get(REFRESH);
	if (!refresh) return null;
	try {
		const tokens = await createApi(fetchFn, null).post<Tokens>('/account/token/refresh', {
			refresh_token: refresh
		});
		storeTokens(cookies, tokens);
		const fresh = decode(tokens.access_token);
		return fresh ? { token: tokens.access_token, user: sessionUser(fresh) } : null;
	} catch {
		clearTokens(cookies);
		return null;
	}
}
