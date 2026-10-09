<script lang="ts">
	import { page } from '$app/state';

	const TITLES: Record<number, string> = {
		403: 'Accès refusé',
		404: 'Page introuvable',
		503: 'Service indisponible'
	};
</script>

<svelte:head>
	<title>{TITLES[page.status] ?? 'Erreur'} — KYST</title>
</svelte:head>

<div class="card error-page">
	<p class="eyebrow-ink">Erreur {page.status}</p>
	<h1>{TITLES[page.status] ?? 'Une erreur est survenue'}</h1>
	<p>{page.error?.message}</p>
	<a class="btn btn--ghost" href="/">Retour au tableau de bord</a>
</div>

<style>
	.error-page {
		max-width: 560px;
		margin: var(--s5) auto;
	}

	.error-page p {
		color: var(--text-secondary);
	}
</style>
