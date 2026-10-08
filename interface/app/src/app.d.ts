// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
import type { Api } from '#lib/server/api.ts';
import type { SessionUser } from '#lib/types.ts';

declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			user: SessionUser | null;
			/** Client de l'API KYST authentifié avec le jeton de la session */
			api: Api;
		}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
