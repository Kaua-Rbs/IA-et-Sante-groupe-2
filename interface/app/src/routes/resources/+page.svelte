<script lang="ts">
	import { enhance } from '$app/forms';
	import FormErrors from '#lib/components/FormErrors.svelte';
	import { nameOf, sortBedUnits } from '#lib/names.ts';
	import { CARE_TYPE_LABELS } from '#lib/types.ts';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	function confirmDelete(event: SubmitEvent, what: string) {
		if (!confirm(`Supprimer ${what} ? Préférez la désactivation si des données y font référence.`)) {
			event.preventDefault();
		}
	}

	const sectionForm = (section: string) => (form?.section === section ? form : null);
</script>

<svelte:head>
	<title>Ressources — KYST</title>
</svelte:head>

<div class="page-head">
	<div>
		<p class="eyebrow-ink">Configuration</p>
		<h1>Ressources</h1>
		<p>
			Spécialités, salles, unités de lits et chirurgiens utilisés pour proposer les dates. Les
			vacations s'ouvrent depuis la page <a href="/planning">Bloc</a>.
		</p>
	</div>
</div>

<div class="resources">
	<!-- Unités de lits -->
	<section class="card" id="beds">
		<h2>Unités de lits</h2>
		<FormErrors form={sectionForm('beds')} />
		<div class="table-wrap">
			<table class="table">
				<thead><tr><th>Unité</th><th>Capacité</th><th>Statut</th></tr></thead>
				<tbody>
					{#each sortBedUnits(data.bedUnits) as unit (unit.id)}
						<tr class:inactive={!unit.active}>
							<td>{unit.name}<div class="muted small">{CARE_TYPE_LABELS[unit.care_type]}</div></td>
							<td>
								<form method="POST" action="?/updateCapacity" use:enhance class="inline">
									<input type="hidden" name="section" value="beds" />
									<input type="hidden" name="id" value={unit.id} />
									<input class="inline-input capacity" name="capacity" type="number" min="1" value={unit.capacity} aria-label="Capacité de {unit.name}" />
									<button class="btn btn--ghost btn--small" type="submit">OK</button>
								</form>
							</td>
							<td>
								<form method="POST" action="?/toggleBedUnit" use:enhance>
									<input type="hidden" name="section" value="beds" />
									<input type="hidden" name="id" value={unit.id} />
									<input type="hidden" name="active" value={String(unit.active)} />
									<button class="btn btn--ghost btn--small" type="submit">{unit.active ? 'Désactiver' : 'Activer'}</button>
								</form>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<form method="POST" action="?/createBedUnit" use:enhance class="add">
			<input type="hidden" name="section" value="beds" />
			<div class="fields">
				<div class="field"><label for="b-name">Nom</label><input id="b-name" name="name" required maxlength="100" /></div>
				<div class="field">
					<label for="b-type">Type</label>
					<select id="b-type" name="care_type">
						<option value="conventional">{CARE_TYPE_LABELS.conventional}</option>
						<option value="ambulatory">{CARE_TYPE_LABELS.ambulatory}</option>
					</select>
				</div>
				<div class="field"><label for="b-cap">Capacité</label><input id="b-cap" name="capacity" type="number" min="1" required /></div>
			</div>
			<div class="form-footer"><button class="btn btn--small" type="submit">Ajouter l'unité</button></div>
		</form>
	</section>

	<!-- Salles -->
	<section class="card" id="rooms">
		<h2>Salles d'opération</h2>
		<FormErrors form={sectionForm('rooms')} />
		<div class="table-wrap">
			<table class="table">
				<thead><tr><th>Salle</th><th>Spécialité habituelle</th><th>Statut</th></tr></thead>
				<tbody>
					{#each data.rooms as room (room.id)}
						<tr class:inactive={!room.active}>
							<td>{room.name}</td>
							<td>{nameOf(data.specialties, room.default_specialty_id)}</td>
							<td>
								<form method="POST" action="?/toggleRoom" use:enhance>
									<input type="hidden" name="section" value="rooms" />
									<input type="hidden" name="id" value={room.id} />
									<input type="hidden" name="active" value={String(room.active)} />
									<button class="btn btn--ghost btn--small" type="submit">{room.active ? 'Désactiver' : 'Activer'}</button>
								</form>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<form method="POST" action="?/createRoom" use:enhance class="add">
			<input type="hidden" name="section" value="rooms" />
			<div class="fields">
				<div class="field"><label for="r-name">Nom</label><input id="r-name" name="name" required maxlength="100" /></div>
				<div class="field">
					<label for="r-spec">Spécialité habituelle</label>
					<select id="r-spec" name="default_specialty_id">
						<option value="">Aucune</option>
						{#each data.specialties as s (s.id)}<option value={s.id}>{s.name}</option>{/each}
					</select>
				</div>
			</div>
			<div class="form-footer"><button class="btn btn--small" type="submit">Ajouter la salle</button></div>
		</form>
	</section>

	<!-- Chirurgiens -->
	<section class="card" id="surgeons">
		<h2>Chirurgiens</h2>
		<FormErrors form={sectionForm('surgeons')} />
		<div class="table-wrap">
			<table class="table">
				<thead><tr><th>Nom</th><th>Spécialité</th>{#if data.user?.admin}<th>Compte</th>{/if}<th></th></tr></thead>
				<tbody>
					{#each data.surgeons as surgeon (surgeon.id)}
						<tr>
							<td>{surgeon.name}</td>
							<td>{nameOf(data.specialties, surgeon.specialty_id)}</td>
							{#if data.user?.admin}
								<td>
									<form method="POST" action="?/linkSurgeon" use:enhance class="inline">
										<input type="hidden" name="section" value="surgeons" />
										<input type="hidden" name="id" value={surgeon.id} />
										<select class="inline-input" name="user_id" aria-label="Compte de {surgeon.name}" onchange={(e) => e.currentTarget.form?.requestSubmit()}>
											<option value="">Aucun</option>
											{#each data.users as u (u.id)}
												<option value={u.id} selected={u.id === surgeon.user_id}>{u.full_name}</option>
											{/each}
										</select>
									</form>
								</td>
							{/if}
							<td>
								<form method="POST" action="?/deleteSurgeon" use:enhance onsubmit={(e) => confirmDelete(e, surgeon.name)}>
									<input type="hidden" name="section" value="surgeons" />
									<input type="hidden" name="id" value={surgeon.id} />
									<button class="btn btn--danger btn--small" type="submit">Supprimer</button>
								</form>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<form method="POST" action="?/createSurgeon" use:enhance class="add">
			<input type="hidden" name="section" value="surgeons" />
			<div class="fields">
				<div class="field"><label for="s-name">Nom affiché</label><input id="s-name" name="name" required maxlength="100" placeholder="Dr Martin" /></div>
				<div class="field">
					<label for="s-spec">Spécialité</label>
					<select id="s-spec" name="specialty_id" required>
						{#each data.specialties as s (s.id)}<option value={s.id}>{s.name}</option>{/each}
					</select>
				</div>
			</div>
			<div class="form-footer"><button class="btn btn--small" type="submit" disabled={!data.specialties.length}>Ajouter le chirurgien</button></div>
		</form>
	</section>

	<!-- Spécialités -->
	<section class="card" id="specialties">
		<h2>Spécialités</h2>
		<FormErrors form={sectionForm('specialties')} />
		<ul class="chips">
			{#each data.specialties as s (s.id)}
				<li>
					{s.name}
					<form method="POST" action="?/deleteSpecialty" use:enhance onsubmit={(e) => confirmDelete(e, s.name)}>
						<input type="hidden" name="section" value="specialties" />
						<input type="hidden" name="id" value={s.id} />
						<button type="submit" aria-label="Supprimer {s.name}">×</button>
					</form>
				</li>
			{:else}
				<li class="muted">Aucune spécialité.</li>
			{/each}
		</ul>
		<form method="POST" action="?/createSpecialty" use:enhance class="add">
			<input type="hidden" name="section" value="specialties" />
			<div class="fields">
				<div class="field"><label for="sp-name">Nouvelle spécialité</label><input id="sp-name" name="name" required maxlength="100" /></div>
			</div>
			<div class="form-footer"><button class="btn btn--small" type="submit">Ajouter</button></div>
		</form>
	</section>
</div>

<style>
	.resources {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 500px), 1fr));
		gap: var(--s3);
		align-items: start;
	}

	.add {
		margin-top: var(--s2);
		padding-top: var(--s2);
		border-top: 1px solid var(--border);
	}

	.inline {
		display: flex;
		gap: 0.4rem;
		align-items: center;
		margin: 0;
	}

	.capacity {
		width: 5rem;
	}

	tr.inactive td {
		color: var(--text-muted);
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.chips li {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.2rem 0.3rem 0.2rem 0.7rem;
		border: 1px solid var(--border-strong);
		border-radius: var(--radius-pill);
		font-size: 0.9rem;
	}

	.chips form {
		margin: 0;
	}

	.chips button {
		border: none;
		background: transparent;
		color: var(--text-muted);
		cursor: pointer;
		font-size: 1rem;
		line-height: 1;
	}

	.chips button:hover {
		color: var(--danger);
	}
</style>
