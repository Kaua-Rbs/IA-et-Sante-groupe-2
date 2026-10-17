<script lang="ts">
	import { enhance } from '$app/forms';
	import FormErrors from '#lib/components/FormErrors.svelte';
	import VacationMeter from '#lib/components/VacationMeter.svelte';
	import {
		addDays, formatMinutes, formatPercent, formatShortDay, formatSlot, mondayOf, today
	} from '#lib/format.ts';
	import { nameOf } from '#lib/names.ts';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
	const runLabel: Record<string, string> = {
		running: 'En cours', succeeded: 'Terminé', failed: 'Échec', interrupted: 'Interrompu'
	};

	let days = $derived(Array.from({ length: 7 }, (_, i) => addDays(data.start, i)));
	// Le week-end n'apparaît que s'il porte des vacations
	let shownDays = $derived(
		days.filter((d, i) => i < 5 || data.vacations.some((v) => v.date === d))
	);
	let rooms = $derived(
		data.rooms.filter((r) => r.active || data.vacations.some((v) => v.room_id === r.id))
	);
	const fillOf = (id: number) => data.fills.find((f) => f.vacation_id === id);
	const cellOf = (roomId: number, day: string) =>
		data.vacations
			.filter((v) => v.room_id === roomId && v.date === day)
			.sort((a, b) => a.start_time.localeCompare(b.start_time));

	let margin = $derived(data.health.emergency_margin);
	let totals = $derived.by(() => {
		const capacity = data.fills.reduce((sum, f) => sum + f.duration_min, 0);
		const planned = data.fills.reduce((sum, f) => sum + f.planned_minutes, 0);
		return {
			count: data.fills.length,
			rate: capacity ? planned / capacity : 0,
			// Seules les vacations à venir peuvent encore accueillir des patients
			free: data.fills
				.filter((f) => f.date >= today())
				.reduce((sum, f) => sum + Math.max(0, f.duration_min * (1 - margin) - f.planned_minutes), 0)
		};
	});

	let showForm = $state(false);
	let newRoom = $state<number | null>(null);
	let defaultSpecialty = $derived(data.rooms.find((r) => r.id === newRoom)?.default_specialty_id ?? null);

	function confirmDelete(event: SubmitEvent) {
		if (!confirm('Supprimer cette vacation ?')) event.preventDefault();
	}
</script>

<svelte:head>
	<title>Bloc opératoire — KYST</title>
</svelte:head>

<div class="page-head">
	<div>
		<p class="eyebrow-ink">Bloc opératoire</p>
		<h1>Semaine du {formatShortDay(data.start)}</h1>
		<p>
			Remplissage de chaque vacation. La zone hachurée est la marge de {formatPercent(margin)} gardée
			pour les urgences.
		</p>
	</div>
	<nav class="actions" aria-label="Changer de semaine">
		<a class="btn btn--ghost btn--small" href="?week={addDays(data.start, -7)}">← Précédente</a>
		<a class="btn btn--ghost btn--small" href="?week={mondayOf(today())}">Cette semaine</a>
		<a class="btn btn--ghost btn--small" href="?week={addDays(data.start, 7)}">Suivante →</a>
	</nav>
</div>

<FormErrors {form} />

<div class="kpis">
	<div class="kpi">
		<p class="kpi__label">Vacations</p>
		<p class="kpi__value">{totals.count}</p>
	</div>
	<div class="kpi">
		<p class="kpi__label">Remplissage moyen</p>
		<p class="kpi__value">{formatPercent(totals.rate)}</p>
	</div>
	<div class="kpi">
		<p class="kpi__label">Temps encore disponible</p>
		<p class="kpi__value">{formatMinutes(totals.free)}</p>
		<p class="kpi__note">à partir d'aujourd'hui, hors marge d'urgence</p>
	</div>
</div>

<div class="card board-card">
	<div class="table-wrap">
		<table class="board">
			<thead>
				<tr>
					<th scope="col">Salle</th>
					{#each shownDays as day}
						<th scope="col" class:today={day === today()}>{formatShortDay(day)}</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each rooms as room (room.id)}
					<tr>
						<th scope="row">
							{room.name}
							<span class="muted small">{nameOf(data.specialties, room.default_specialty_id, '')}</span>
						</th>
						{#each shownDays as day}
							<td>
								{#each cellOf(room.id, day) as vacation (vacation.id)}
									{@const fill = fillOf(vacation.id)}
									<div class="vac">
										<div class="vac__head">
											<span class="vac__time">{formatSlot(vacation.start_time, vacation.duration_min)}</span>
											{#if data.user?.canPlan}
												<form method="POST" action="?/deleteVacation" use:enhance onsubmit={confirmDelete}>
													<input type="hidden" name="vacationId" value={vacation.id} />
													<button class="vac__delete" type="submit" aria-label="Supprimer la vacation">×</button>
												</form>
											{/if}
										</div>
										<div class="vac__who">
											{nameOf(data.specialties, vacation.specialty_id)}
											{#if vacation.surgeon_id}· {nameOf(data.surgeons, vacation.surgeon_id)}{/if}
										</div>
										<VacationMeter planned={fill?.planned_minutes ?? 0} duration={vacation.duration_min} {margin} />
										{#if data.user?.isStaff}
											<div class="vac__count muted">
												{data.caseCount[vacation.id] ?? 0} interv. · {formatMinutes(fill?.planned_minutes ?? 0)}
											</div>
										{/if}
									</div>
								{:else}
									<span class="none" aria-label="Pas de vacation">—</span>
								{/each}
							</td>
						{/each}
					</tr>
				{:else}
					<tr><td colspan={shownDays.length + 1} class="empty">Aucune salle configurée.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

{#if data.user?.canPlan}
	{#if data.conflicts.length}
		<section class="card add">
			<h2>Interventions confirmées à revoir</h2>
			<p>Les changements de ressources affectent {data.conflicts.length} interventions confirmées. Leurs réservations restent en place pour organiser leur révision avec les équipes.</p>
			<ul>{#each data.conflicts as conflict}
				<li><a href="/requests/{conflict.request_id}">Intervention du {conflict.admission_date}</a> : {conflict.reasons.join(' ')}</li>
			{/each}</ul>
		</section>
	{/if}
	{#if data.replanning}
		<section class="card add">
			<div class="card-head"><h2>Actualisation des propositions</h2></div>
			<p>{data.replanning.pending_changes} changements en attente · mode {data.replanning.automatic ? 'automatique' : 'manuel'} · {data.replanning.method} sur {data.replanning.horizon_days} jours.</p>
			<p class="muted">Le calcul actualise les propositions des demandes en attente. Les interventions confirmées gardent leurs réservations et les nouvelles dates attendent une confirmation clinique.</p>
			<form method="POST" action="?/refreshProposals" use:enhance><button class="btn" type="submit">Actualiser les propositions</button></form>
			{#if form?.replanRun}
				<p>{form.replanRun.status === 'succeeded' ? `${form.replanRun.proposals_count} propositions actualisées.` : "Le calcul a échoué. Les propositions précédentes sont conservées ; vous pouvez relancer l'actualisation."}</p>
			{:else if form?.refreshQueued}
				<p>Un calcul est déjà en cours ; la demande d'actualisation reste en attente.</p>
			{/if}
			{#if data.replanning.runs.length}
				<div class="table-wrap"><table><thead><tr><th>Calcul</th><th>État</th><th>Changements</th><th>Propositions</th></tr></thead>
					<tbody>{#each data.replanning.runs as run}<tr><td>{run.started_at}</td><td>{runLabel[run.status] ?? run.status}</td><td>{run.event_count}</td><td>{run.proposals_count}</td></tr>{/each}</tbody>
				</table></div>
			{/if}
		</section>
	{/if}
	<section class="card add">
		<div class="card-head"><h2>Simulation Mesa : salles</h2></div>
		<p class="muted">Scénario hypothétique sur les demandes en attente. Les durées d'exécution sont les prédictions multipliées par le facteur choisi. Les lits, les spécialités et les vacations ne sont pas simulés dans cet aperçu.</p>
		<form method="POST" action="?/previewSimulation" use:enhance>
			<div class="fields">
				<div class="field">
					<label for="simulation-date">Date</label>
					<input id="simulation-date" name="date" type="date" min={today()} value={today()} required />
				</div>
				<div class="field">
					<label for="simulation-method">Méthode</label>
					<select id="simulation-method" name="method" required>
						{#each data.simulationMethods as method}
							<option value={method}>{method}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label for="simulation-policy">Politique</label>
					<select id="simulation-policy" name="policy">
						<option value="reactive">Réactive</option>
						<option value="static">Figée</option>
					</select>
				</div>
				<div class="field">
					<label for="simulation-factor">Facteur de durée réalisée</label>
					<input id="simulation-factor" name="realized_factor" type="number" min="1" max="2" step="0.1" value="1.2" required />
				</div>
				<div class="field">
					<label><input name="outage" type="checkbox" checked /> Salle 1 fermée aux nouvelles entrées de 10 h à 12 h</label>
				</div>
			</div>
			<div class="form-footer"><button class="btn" type="submit">Simuler</button></div>
		</form>
		{#if form?.simulation}
			<p><strong>{form.simulation.completed}</strong> interventions terminées sur {form.simulation.cases}, <strong>{form.simulation.unstarted}</strong> non commencées ; dépassement cumulé : <strong>{formatMinutes(form.simulation.overtime_minutes)}</strong>.</p>
			<p class="muted">{form.simulation.replanning_count} replanifications · {form.simulation.failures} échecs · {form.simulation.assumptions.rooms} salles identiques, 08 h–17 h, remise en état de 15 min.</p>
		{/if}
	</section>

	<section class="card add">
		<div class="card-head"><h2>Simulation Mesa : salles et lits</h2></div>
		<p class="muted">Aperçu sur 14 jours au plus. Les réservations existantes réduisent les minutes de vacation et les lits disponibles. Les cas en attente portent au jour suivant. Une durée de séjour réalisée plus longue peut créer un conflit de lits, qui est compté.</p>
		<form method="POST" action="?/previewWard" use:enhance>
			<div class="fields">
				<div class="field"><label for="ward-start">Du</label><input id="ward-start" name="start" type="date" min={today()} value={today()} required /></div>
				<div class="field"><label for="ward-end">Au</label><input id="ward-end" name="end" type="date" min={today()} value={addDays(today(), 6)} required /></div>
				<div class="field"><label for="ward-method">Méthode salle</label><select id="ward-method" name="method">{#each data.simulationMethods as method}<option value={method}>{method}</option>{/each}</select></div>
				<div class="field"><label for="ward-policy">Politique</label><select id="ward-policy" name="policy"><option value="reactive">Réactive</option><option value="static">Figée</option></select></div>
				<div class="field"><label for="ward-room-factor">Facteur temps en salle</label><input id="ward-room-factor" name="realized_factor" type="number" min="1" max="2" step="0.1" value="1.2" required /></div>
				<div class="field"><label for="ward-los-factor">Facteur séjour</label><input id="ward-los-factor" name="los_factor" type="number" min="1" max="2" step="0.1" value="1" required /></div>
				<div class="field"><label><input name="outage" type="checkbox" checked /> Salle 1 fermée aux nouvelles entrées de 10 h à 12 h</label></div>
			</div>
			<div class="form-footer"><button class="btn" type="submit">Simuler salles et lits</button></div>
		</form>
		{#if form?.ward}
			<p><strong>{form.ward.completed}</strong> interventions commencées sur {form.ward.cases} ; <strong>{form.ward.unstarted}</strong> non commencées ; <strong>{form.ward.overcapacity_bed_days}</strong> jours-unité de lits en conflit.</p>
			<p class="muted">Dépassement des salles : {formatMinutes(form.ward.overtime_minutes)} · {form.ward.replanning_count} replanifications · {form.ward.failures} échecs.</p>
			<div class="table-wrap"><table><thead><tr><th>Jour</th><th>Offertes</th><th>Commencées</th><th>En attente</th><th>Lits occupés</th></tr></thead>
				<tbody>{#each form.ward.daily as day}<tr><td>{day.date}</td><td>{day.offered}</td><td>{day.started}</td><td>{day.waiting}</td><td>{day.occupied_beds}</td></tr>{/each}</tbody>
			</table></div>
		{/if}
	</section>

	<section class="card add">
		<div class="card-head">
			<h2>Optimisation de la cohorte</h2>
		</div>
		<p class="muted">L'aperçu ne réserve aucune date. Vous pouvez ensuite publier des propositions recalculées ; les chirurgiens les confirment individuellement.</p>
		<form method="POST" action="?/previewOptimization" use:enhance>
			<div class="fields">
				<div class="field">
					<label for="cohort-start">Du</label>
					<input id="cohort-start" name="start" type="date" min={today()} value={today()} required />
				</div>
				<div class="field">
					<label for="cohort-end">Au</label>
					<input id="cohort-end" name="end" type="date" min={today()} value={addDays(today(), 6)} required />
				</div>
				<div class="field">
					<label for="cohort-method">Méthode</label>
					<select id="cohort-method" name="method" required>
						{#each data.methods as method}
							<option value={method} selected={method === 'Tabou x Recuit'}>{method}</option>
						{/each}
					</select>
				</div>
			</div>
			<div class="form-footer">
				<button class="btn btn--ghost" type="submit">Calculer un aperçu</button>
				<button class="btn" type="submit" formaction="?/publishOptimization">Publier des propositions</button>
			</div>
		</form>
		{#if form?.published}
			<p><strong>{form.published.length}</strong> propositions publiées après un nouveau calcul et un contrôle des capacités. Elles attendent la confirmation clinique.</p>
			{#if form.published.length}
				<ul>
					{#each form.published as proposal}
						<li><a href="/requests/{proposal.request_id}">Demande {proposal.request_id.slice(0, 8)}</a> · {proposal.admission_date}</li>
					{/each}
				</ul>
			{/if}
		{/if}
		{#if form?.preview}
			<p><strong>{form.preview.assignments.length}</strong> demandes placées sur {form.preview.evaluated_cases} · <strong>{form.preview.unassigned.length}</strong> non placées.</p>
			{#if form.preview.assignments.length}
				<div class="table-wrap">
					<table>
						<thead><tr><th>Demande</th><th>Date</th><th>Vacation</th><th>Unité de lits</th><th>Durée prévue</th></tr></thead>
						<tbody>
							{#each form.preview.assignments as assignment}
								<tr>
									<td><a href="/requests/{assignment.request_id}">{assignment.request_id.slice(0, 8)}</a></td>
									<td>{assignment.admission_date}</td>
									<td>#{assignment.vacation_id}</td>
									<td>{nameOf(data.bedUnits, assignment.bed_unit_id)}</td>
									<td>{formatMinutes(assignment.planned_minutes)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		{/if}
	</section>

	<section class="card add">
		<div class="card-head">
			<h2>Ouvrir une vacation</h2>
			<button class="btn btn--ghost btn--small" type="button" onclick={() => (showForm = !showForm)} aria-expanded={showForm}>
				{showForm ? 'Fermer' : 'Ajouter'}
			</button>
		</div>
		{#if showForm}
			<form method="POST" action="?/createVacation" use:enhance={() => async ({ update }) => update({ reset: false })}>
				<div class="fields">
					<div class="field">
						<label for="v-room">Salle</label>
						<select id="v-room" name="room_id" required bind:value={newRoom}>
							{#each data.rooms.filter((r) => r.active) as room (room.id)}
								<option value={room.id}>{room.name}</option>
							{/each}
						</select>
					</div>
					<div class="field">
						<label for="v-specialty">Spécialité</label>
						<select id="v-specialty" name="specialty_id" required>
							{#each data.specialties as s (s.id)}
								<option value={s.id} selected={s.id === defaultSpecialty}>{s.name}</option>
							{/each}
						</select>
					</div>
					<div class="field">
						<label for="v-surgeon">Chirurgien</label>
						<select id="v-surgeon" name="surgeon_id">
							<option value="">Toute l'équipe</option>
							{#each data.surgeons as s (s.id)}
								<option value={s.id}>{s.name}</option>
							{/each}
						</select>
					</div>
					<div class="field">
						<label for="v-date">Date</label>
						<input id="v-date" name="date" type="date" value={data.start} required />
					</div>
					<div class="field">
						<label for="v-start">Début</label>
						<input id="v-start" name="start_time" type="time" value="08:00" required />
					</div>
					<div class="field">
						<label for="v-duration">Durée (min)</label>
						<input id="v-duration" name="duration_min" type="number" min="30" max="720" step="15" value="240" required />
					</div>
				</div>
				<div class="form-footer">
					<button class="btn" type="submit">Ouvrir la vacation</button>
				</div>
			</form>
		{/if}
	</section>
{/if}

<style>
	.kpis {
		margin-bottom: var(--s3);
	}

	.board-card {
		padding: 0;
	}

	.board {
		width: 100%;
		min-width: 760px;
		border-collapse: collapse;
		table-layout: fixed;
	}

	.board th,
	.board td {
		padding: 0.6rem;
		border-bottom: 1px solid var(--border);
		border-right: 1px solid var(--border);
		vertical-align: top;
		text-align: left;
	}

	.board tr > :last-child {
		border-right: none;
	}

	.board thead th {
		font-family: var(--font-mono);
		font-size: 11px;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-muted);
	}

	.board thead th.today {
		color: var(--green-deep);
		box-shadow: inset 0 -2px 0 var(--primary);
	}

	.board tbody th {
		width: 9rem;
		font-weight: 600;
	}

	.board tbody th span {
		display: block;
		font-weight: 400;
	}

	.vac {
		padding: 0.45rem 0.5rem;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--bg);
	}

	.vac + .vac {
		margin-top: 0.4rem;
	}

	.vac__head {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.vac__head form {
		margin: 0;
	}

	.vac__time {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-secondary);
	}

	.vac__delete {
		padding: 0 0.3rem;
		border: none;
		background: transparent;
		color: var(--text-muted);
		font-size: 1rem;
		line-height: 1;
		cursor: pointer;
	}

	.vac__delete:hover {
		color: var(--danger);
	}

	.vac__who {
		margin: 0.1rem 0 0.35rem;
		font-size: 0.82rem;
		font-weight: 500;
	}

	.vac__count {
		margin-top: 0.25rem;
		font-size: 0.75rem;
	}

	.none {
		color: var(--text-muted);
	}

	.add {
		margin-top: var(--s3);
	}
</style>
