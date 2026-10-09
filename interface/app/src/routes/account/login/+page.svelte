<script lang="ts">
	import { enhance } from '$app/forms';
	import logo from '#lib/assets/favicon.svg';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
	let loading = $state(false);
</script>

<svelte:head>
	<title>Connexion — KYST</title>
</svelte:head>

<div class="auth">
	<div class="form">
		<a class="login-title" href="/">
			<img src={logo} alt="" width="56" height="56" />
			<h1>KYST</h1>
			<span class="login-tagline">Keep Your Surgeries Timelies</span>
		</a>

		{#if form?.error}
			<p class="error">{form.error}</p>
		{:else if data.registered === 'pending'}
			<p class="notice">
				Compte créé. Un administrateur doit le valider avant votre première connexion.
			</p>
		{:else if data.registered}
			<p class="notice">Compte créé. Vous pouvez vous connecter.</p>
		{/if}

		<form
			method="POST"
			use:enhance={() => {
				loading = true;
				return async ({ update }) => {
					await update();
					loading = false;
				};
			}}
		>
			<ul>
				<li>
					<label for="signin-email">Adresse email</label>
					<input autocomplete="email" type="email" name="email" id="signin-email" placeholder="nom@hopital.fr" value={form?.email ?? ''} required />
				</li>
				<li>
					<label for="signin-password">Mot de passe</label>
					<input autocomplete="current-password" type="password" name="password" id="signin-password" placeholder="••••••••" minlength="8" required />
				</li>
				<li>
					<button type="submit" disabled={loading}>{loading ? 'Connexion…' : 'Se connecter'}</button>
				</li>
			</ul>
		</form>

		<p class="auth-switch">Pas de compte ? <a href="/account/register">Demander un accès</a></p>
	</div>
</div>
