<script lang="ts">
	import { enhance } from '$app/forms';
	import FormErrors from '#lib/components/FormErrors.svelte';
	import { ROLE_LABELS } from '#lib/types.ts';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Mon compte — KYST</title>
</svelte:head>

<div class="page-head">
	<div>
		<p class="eyebrow-ink">Compte</p>
		<h1>{data.me.full_name}</h1>
	</div>
	<form action="/account/logout" method="POST">
		<button type="submit" class="btn btn--danger">Se déconnecter</button>
	</form>
</div>

<FormErrors {form} />

<div class="grid-2">
	<section class="card">
		<h2>Profil</h2>
		<dl class="props">
			<dt>Email</dt>
			<dd>{data.me.email}</dd>
			<dt>Rôles</dt>
			<dd>
				{#if data.me.groups.length}
					{data.me.groups.map((g) => ROLE_LABELS[g.name] ?? g.name).join(', ')}
				{:else}
					<span class="muted">Aucun : demandez un rôle à un administrateur</span>
				{/if}
			</dd>
			{#if data.surgeon}
				<dt>Chirurgien</dt>
				<dd>{data.surgeon.name}</dd>
			{/if}
		</dl>

		<form method="POST" action="?/updateProfile" use:enhance class="profile-form">
			<div class="field">
				<label for="full-name">Nom complet</label>
				<input id="full-name" name="full_name" value={data.me.full_name} required maxlength="200" />
			</div>
			<div class="form-footer">
				<button class="btn btn--ghost" type="submit">Enregistrer</button>
			</div>
		</form>
	</section>

	<section class="card">
		<h2>Mot de passe</h2>
		<form method="POST" action="?/changePassword" use:enhance>
			<div class="stack-fields">
				<div class="field">
					<label for="current-password">Mot de passe actuel</label>
					<input id="current-password" name="current_password" type="password" autocomplete="current-password" required />
				</div>
				<div class="field">
					<label for="new-password">Nouveau mot de passe</label>
					<input id="new-password" name="new_password" type="password" autocomplete="new-password" minlength="8" required />
				</div>
				<div class="field">
					<label for="new-password-2">Confirmation</label>
					<input id="new-password-2" name="new_password_confirmation" type="password" autocomplete="new-password" minlength="8" required />
				</div>
			</div>
			<p class="muted small">Toutes vos sessions seront fermées.</p>
			<div class="form-footer">
				<button class="btn" type="submit">Changer le mot de passe</button>
			</div>
		</form>
	</section>
</div>

<style>
	.profile-form {
		margin-top: var(--s3);
		padding-top: var(--s2);
		border-top: 1px solid var(--border);
	}

	.stack-fields {
		display: flex;
		flex-direction: column;
		gap: var(--s2);
	}
</style>
