<script lang="ts">
	import { enhance } from '$app/forms';
	import FormErrors from '#lib/components/FormErrors.svelte';
	import { ROLE_LABELS } from '#lib/types.ts';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	let query = $state('');
	let pending = $derived(data.users.filter((u) => !u.validated).length);
	let visible = $derived(
		data.users.filter((u) =>
			`${u.full_name} ${u.email}`.toLowerCase().includes(query.trim().toLowerCase())
		)
	);

	function confirmDelete(event: SubmitEvent, name: string) {
		if (!confirm(`Supprimer définitivement le compte de ${name} ?`)) event.preventDefault();
	}
</script>

<svelte:head>
	<title>Administration — KYST</title>
</svelte:head>

<div class="page-head">
	<div>
		<p class="eyebrow-ink">Administration</p>
		<h1>Utilisateurs</h1>
		<p>
			Validez les nouveaux comptes et attribuez les rôles. Un compte sans rôle ne voit que les
			indicateurs agrégés.
			{#if pending}<strong>{pending} compte{pending > 1 ? 's' : ''} en attente.</strong>{/if}
		</p>
	</div>
	<input class="inline-input search" type="search" placeholder="Rechercher un nom ou un email" bind:value={query} />
</div>

<FormErrors {form} />

<div class="card">
	<div class="table-wrap">
		<table class="table">
			<thead>
				<tr>
					<th>Nom</th>
					<th>Rôles</th>
					<th>Statut</th>
					<th>Actions</th>
				</tr>
			</thead>
			<tbody>
				{#each visible as user (user.id)}
					{@const isMe = user.id === data.currentUserId}
					<tr>
						<td>
							<strong>{user.full_name}</strong>{#if isMe}<span class="muted"> (vous)</span>{/if}
							<div class="muted small">{user.email}</div>
						</td>
						<td>
							<div class="roles">
								{#each data.groups.filter((g) => g.name !== 'user') as group (group.id)}
									{@const enabled = user.groups.some((g) => g.id === group.id)}
									<form method="POST" action="?/setRole" use:enhance>
										<input type="hidden" name="userId" value={user.id} />
										<input type="hidden" name="groupId" value={group.id} />
										<input type="hidden" name="enabled" value={String(!enabled)} />
										<button
											type="submit"
											class="role"
											class:role--on={enabled}
											aria-pressed={enabled}
											disabled={isMe && group.name === 'admin'}
										>
											{enabled ? '✓' : '+'} {ROLE_LABELS[group.name] ?? group.name}
										</button>
									</form>
								{/each}
							</div>
						</td>
						<td>
							{#if !user.validated}
								<span class="badge badge--pending">En attente</span>
							{:else if user.disabled}
								<span class="badge badge--cancelled">Désactivé</span>
							{:else}
								<span class="badge badge--scheduled">Actif</span>
							{/if}
						</td>
						<td>
							{#if !isMe}
								<div class="actions">
									{#if !user.validated}
										<form method="POST" action="?/validate" use:enhance>
											<input type="hidden" name="userId" value={user.id} />
											<button class="btn btn--small" type="submit">Valider</button>
										</form>
									{/if}
									<form method="POST" action="?/toggleStatus" use:enhance>
										<input type="hidden" name="userId" value={user.id} />
										<input type="hidden" name="disabled" value={String(user.disabled)} />
										<button class="btn btn--ghost btn--small" type="submit">
											{user.disabled ? 'Réactiver' : 'Désactiver'}
										</button>
									</form>
									<form
										method="POST"
										action="?/deleteUser"
										use:enhance
										onsubmit={(e) => confirmDelete(e, user.full_name)}
									>
										<input type="hidden" name="userId" value={user.id} />
										<button class="btn btn--danger btn--small" type="submit">Supprimer</button>
									</form>
								</div>
							{/if}
						</td>
					</tr>
				{:else}
					<tr><td colspan="4" class="empty">Aucun utilisateur ne correspond.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<style>
	.search {
		max-width: 320px;
	}

	.roles {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}

	.roles form {
		margin: 0;
	}

	.role {
		padding: 0.15rem 0.55rem;
		border: 1px dashed var(--border-strong);
		border-radius: var(--radius-pill);
		background: transparent;
		color: var(--text-muted);
		font-size: 0.75rem;
		cursor: pointer;
		white-space: nowrap;
	}

	.role:hover {
		border-color: var(--primary);
		color: var(--text);
	}

	.role--on {
		border-style: solid;
		border-color: rgba(15, 138, 77, 0.4);
		background: var(--primary-soft);
		color: var(--green-deep);
	}

	.role:disabled {
		cursor: not-allowed;
		opacity: 0.7;
	}
</style>
