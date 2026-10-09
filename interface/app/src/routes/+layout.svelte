<script lang="ts">
	import { page } from '$app/state';
	import Header from '#lib/components/header.svelte';
	import '#lib/style/variables.css';
	import '#lib/style/main.css';
	import '#lib/style/forms.css';
	import '#lib/style/login.css';
	import '#lib/style/app.css';
	import '#lib/style/responsive.css';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();

	// La page d'accueil publique a sa propre navigation et gère elle-même sa largeur
	let isLanding = $derived(page.route.id === '/' && !data.user);
	let hideHeader = $derived(
		isLanding || ['/account/login', '/account/register'].includes(page.route.id || '')
	);
</script>

<svelte:head>
	<link rel="icon" href="/img/logo-clair.png" />
</svelte:head>

{#if !hideHeader}
	<Header user={data.user} />
{/if}

<main class:no-header={hideHeader} class:bare={hideHeader}>
	{@render children()}
</main>

<style>
	main.no-header {
		/* Si pas de header, le main commence à la première ligne de la grille au lieu de la deuxième */
		grid-area: 1 / 1 / 3 / 2 !important;
	}

	main.bare {
		max-width: none;
		padding: 0;
	}
</style>
