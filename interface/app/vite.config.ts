import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { existsSync } from 'node:fs';

// Variables d'environnement communes à l'API et au front : interface/kyst.env (référence)
// et interface/kyst.local.env (secrets locaux, non versionné). loadEnvFile n'écrase pas une
// variable déjà définie : l'environnement du processus prime, puis kyst.local.env, puis kyst.env.
for (const file of ['../kyst.local.env', '../kyst.env']) {
	if (existsSync(file)) process.loadEnvFile(file);
}

export default defineConfig(({ command }) => ({
	plugins: [
		sveltekit({
			// Origine publique, figée au build de production (protection CSRF des formulaires).
			// Sans elle, adapter-node la déduit de l'en-tête Host en supposant https.
			// Jamais en développement : le serveur Vite a sa propre origine (localhost:5173).
			paths: { origin: command === 'build' ? process.env.ORIGIN || undefined : undefined },

			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// adapter-auto only supports some environments, see https://svelte.dev/docs/kit/adapter-auto for a list.
			// If your environment is not supported, or you settled on a specific environment, switch out the adapter.
			// See https://svelte.dev/docs/kit/adapters for more information about adapters.
			adapter: adapter()
		})
	]
}));
