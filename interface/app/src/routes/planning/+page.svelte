<script lang="ts">
	import { enhance } from '$app/forms';
	import FormErrors from '#lib/components/FormErrors.svelte';
	import VacationMeter from '#lib/components/VacationMeter.svelte';
	import {
		addDays, formatDateTime, formatLongDay, formatMinutes, formatPercent, formatShortDay, formatSlot,
		mondayOf, plural, today
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
		<p>Remplissage de chaque vacation, réserve pour les urgences comprise.</p>
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
		<p class="kpi__note">à partir d'aujourd'hui, hors réserve urgences</p>
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
		{@const replan = data.replanning}
		<section class="card add">
			<div class="card-head">
				<h2>Actualiser les propositions après un changement</h2>
				<span class="badge">{replan.automatic ? 'Automatique' : 'Manuel'}</span>
			</div>
			<p class="lead">
				Une vacation ajoutée ou supprimée, une salle fermée, une intervention annulée ou une date
				refusée peut rendre caduques les dates proposées. KYST recalcule alors celles de toutes les
				demandes en attente sur les {replan.horizon_days} prochains jours.
			</p>
			<p class="lead">
				Les dates proposées sont remplacées, ou retirées si elles deviennent impossibles ; les
				interventions confirmées gardent leur créneau et leur lit ; le chirurgien confirme chaque
				nouvelle date.
			</p>
			<p class="status">
				{#if replan.pending_changes}
					<strong>{plural(replan.pending_changes, 'changement')}</strong> depuis le dernier calcul.
				{:else}
					Aucun changement depuis le dernier calcul : les propositions sont à jour.
				{/if}
				{#if replan.automatic}
					L'actualisation est automatique : le calcul part tout seul dans les secondes qui suivent un changement.
				{/if}
			</p>
			<form method="POST" action="?/refreshProposals" use:enhance>
				<button class="btn" type="submit">Actualiser maintenant</button>
			</form>
			{#if form?.replanRun}
				<p class="result">
					{form.replanRun.status === 'succeeded'
						? `${plural(form.replanRun.proposals_count, 'date proposée')} après actualisation.`
						: "Le calcul a échoué. Les propositions précédentes sont conservées ; vous pouvez relancer l'actualisation."}
				</p>
			{:else if form?.refreshQueued}
				<p class="result">Un calcul est déjà en cours ; votre demande sera prise en compte au suivant.</p>
			{/if}
			{#if replan.runs.length}
				<details class="history">
					<summary>Derniers calculs ({replan.runs.length})</summary>
					<div class="table-wrap">
						<table class="table">
							<thead><tr><th>Lancé le</th><th>État</th><th>Changements pris en compte</th><th>Dates proposées</th></tr></thead>
							<tbody>
								{#each replan.runs as run (run.id)}
									<tr>
										<td>{formatDateTime(run.started_at)}</td>
										<td>{runLabel[run.status] ?? run.status}</td>
										<td>{run.event_count}</td>
										<td>{run.proposals_count}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</details>
			{/if}
		</section>
	{/if}

	<section class="card add">
		<div class="card-head">
			<h2>Optimiser une période au choix</h2>
			<span class="badge">Avec aperçu</span>
		</div>
		<p class="lead">
			Même calcul que l'actualisation ci-dessus, mais sur la période de votre choix (60 jours au
			plus) et avec un aperçu avant publication. Toutes les demandes en attente de la période
			(50 au plus) sont placées <strong>ensemble</strong>, pour mieux remplir les vacations et
			étaler l'occupation des lits.
		</p>
		<ol class="points steps">
			<li class="point">
				<strong>Choisir la période</strong>
				<span>Elle dure 4 semaines par défaut. Plus elle est longue, plus KYST trouve de créneaux libres.</span>
			</li>
			<li class="point">
				<strong>Voir le résultat</strong>
				<span>KYST affiche le placement proposé, sans rien réserver ni envoyer.</span>
			</li>
			<li class="point">
				<strong>Publier les dates</strong>
				<span>Chaque demande placée reçoit sa nouvelle date, que le chirurgien confirme ou écarte.</span>
			</li>
		</ol>
		<p class="muted small">
			Méthode : recuit simulé, la plus performante des dix métaheuristiques comparées. Chaque date
			respecte la spécialité, le chirurgien, la fenêtre de la demande, les lits et la réserve
			pour les urgences.
		</p>
		<form method="POST" action="?/previewOptimization" use:enhance={() => async ({ update }) => update({ reset: false })}>
			<div class="fields">
				<div class="field">
					<label for="cohort-start">Du</label>
					<input id="cohort-start" name="start" type="date" min={today()} value={today()} required />
				</div>
				<div class="field">
					<label for="cohort-end">Au</label>
					<input id="cohort-end" name="end" type="date" min={today()} max={addDays(today(), 60)} value={addDays(today(), 27)} required />
				</div>
			</div>
			<div class="form-footer">
				<button class="btn btn--ghost" type="submit">Voir le résultat</button>
				<button class="btn" type="submit" formaction="?/publishOptimization">Publier les dates</button>
			</div>
		</form>
		{#if form?.published}
			<p class="result">
				<strong>{plural(form.published.length, 'date publiée', 'dates publiées')}</strong>, à confirmer par les chirurgiens.
			</p>
			{#if form.published.length}
				<ul>
					{#each form.published as proposal (proposal.id)}
						<li><a href="/requests/{proposal.request_id}">Demande du {formatLongDay(proposal.admission_date)}</a></li>
					{/each}
				</ul>
			{/if}
		{/if}
		{#if form?.preview}
			{@const preview = form.preview}
			<p class="result">
				<strong>{preview.assignments.length}</strong> demandes placées sur {preview.evaluated_cases}.
				{#if preview.unassigned.length}
					{plural(preview.unassigned.length, 'demande reste', 'demandes restent')} sans date : aucun créneau
					compatible dans la période, élargissez-la ou ouvrez des vacations.
				{/if}
				Rien n'est encore réservé.
			</p>
			{#if preview.assignments.length}
				<div class="table-wrap">
					<table class="table">
						<thead><tr><th>Demande</th><th>Admission</th><th>Sortie prévue</th><th>Hébergement</th><th>Temps au bloc</th></tr></thead>
						<tbody>
							{#each preview.assignments as assignment (assignment.request_id)}
								<tr>
									<td><a href="/requests/{assignment.request_id}">Voir la demande</a></td>
									<td>{formatLongDay(assignment.admission_date)}</td>
									<td>{formatLongDay(assignment.discharge_date)}</td>
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

	.badge {
		padding: 0.15rem 0.5rem;
		border: 1px solid var(--border-strong);
		border-radius: var(--radius-pill);
		font-family: var(--font-mono);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-secondary);
	}

	.lead {
		max-width: none;
		margin: 0 0 var(--s2);
	}

	.points {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
		gap: var(--s2);
		margin: 0 0 var(--s2);
		padding: 0;
		list-style: none;
	}

	.point {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		max-width: none;
		padding: var(--s1) var(--s2);
		border-left: 3px solid var(--primary);
		border-radius: var(--radius);
		background: var(--bg);
	}

	.point strong {
		font-weight: 600;
	}

	.point span {
		color: var(--text-secondary);
	}

	.steps {
		counter-reset: step;
	}

	.steps .point strong::before {
		counter-increment: step;
		content: counter(step) '. ';
		color: var(--primary);
	}

	.status {
		max-width: none;
		padding: var(--s1) var(--s2);
		border-radius: var(--radius);
		background: var(--surface-muted);
	}

	.result {
		margin-top: var(--s2);
	}

	.history {
		margin-top: var(--s2);
	}

	.history summary {
		cursor: pointer;
		color: var(--text-secondary);
	}
</style>
