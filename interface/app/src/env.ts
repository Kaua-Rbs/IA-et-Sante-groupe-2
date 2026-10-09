import { defineEnvVars } from '@sveltejs/kit/env';

// Variables lues par le front ; elles sont documentées dans interface/kyst.env.

/** Entier positif, avec une valeur par défaut si la variable est absente. */
const positiveInt = (fallback: number) => (value: string | undefined) => {
	if (value === undefined || value === '') return fallback;
	const n = Number(value);
	if (!Number.isInteger(n) || n <= 0) throw new Error(`Entier positif attendu, reçu « ${value} »`);
	return n;
};

export const variables = defineEnvVars({
	KYST_API_URL: {
		description: "Adresse de l'API KYST, appelée uniquement depuis le serveur SvelteKit",
		schema: (value: string | undefined) => (value || 'http://127.0.0.1:8000').replace(/\/$/, '')
	},
	ACCESS_TOKEN_EXPIRE_MINUTES: {
		description: "Durée de vie du jeton d'accès, partagée avec l'API (durée du cookie)",
		schema: positiveInt(30)
	},
	REFRESH_TOKEN_EXPIRE_DAYS: {
		description: 'Durée de vie du refresh token, partagée avec l\'API (durée du cookie)',
		schema: positiveInt(7)
	}
});
