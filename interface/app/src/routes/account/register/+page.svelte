<script lang="ts">
	import { enhance } from '$app/forms';
	import type { PageProps } from './$types';

	let { form }: PageProps = $props();
	let loading = $state(false);
</script>

<svelte:head>
	<title>Demande d'accès — KYST</title>
</svelte:head>

<div class="auth">
	<div class="form">
		<a class="login-title" href="/">
			<img src="/img/logo-clair.png" alt="" width="56" height="56" />
			<h1>KYST</h1>
			<span class="login-tagline">Demande d'accès</span>
		</a>

		{#if form?.error}
			<div class="error">
				{form.error}
				{#each form.reasons ?? [] as reason}<br />{reason}{/each}
			</div>
		{/if}

		<form
			method="POST"
			use:enhance={() => {
				loading = true;
				return async ({ update }) => {
					await update({ reset: false });
					loading = false;
				};
			}}
		>
			<ul>
				<li>
					<label for="signup-last-name">Nom</label>
					<input autocomplete="family-name" type="text" name="last_name" id="signup-last-name" placeholder="Dupont" value={form?.lastName ?? ''} required />
				</li>
				<li>
					<label for="signup-first-name">Prénom</label>
					<input autocomplete="given-name" type="text" name="first_name" id="signup-first-name" placeholder="Jeanne" value={form?.firstName ?? ''} required />
				</li>
				<li>
					<label for="signup-email">Adresse email</label>
					<input autocomplete="email" type="email" name="email" id="signup-email" placeholder="nom@hopital.fr" value={form?.email ?? ''} required />
				</li>
				<li>
					<label for="signup-password">Mot de passe</label>
					<input autocomplete="new-password" type="password" name="password" id="signup-password" placeholder="••••••••" minlength="8" required />
				</li>
				<li>
					<label for="signup-password-confirmation">Confirmation du mot de passe</label>
					<input autocomplete="new-password" type="password" name="password_confirmation" id="signup-password-confirmation" placeholder="••••••••" minlength="8" required />
				</li>
				<li>
					<button type="submit" disabled={loading}>{loading ? 'Envoi…' : 'Demander un accès'}</button>
				</li>
			</ul>
		</form>

		<p class="auth-switch">
			Un administrateur valide chaque compte et lui attribue un rôle.<br />
			Déjà un compte ? <a href="/account/login">Se connecter</a>
		</p>
	</div>
</div>
