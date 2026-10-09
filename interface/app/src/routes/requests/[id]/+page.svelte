<script lang="ts">
	import { enhance } from '$app/forms';
	import FormErrors from '#lib/components/FormErrors.svelte';
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import {
		formatDateTime, formatDay, formatLongDay, formatMinutes, formatSlot, plural
	} from '#lib/format.ts';
	import { nameOf, patientLabel, sexLabel } from '#lib/names.ts';
	import {
		CARE_TYPE_LABELS, CASE_STATUS_LABELS, PROPOSAL_STATUS_LABELS, REQUEST_STATUS_LABELS,
		type Vacation
	} from '#lib/types.ts';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	let busy = $state(false);
	const submit = () => {
		busy = true;
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
			busy = false;
		};
	};

	const letter = (rank: number) => String.fromCharCode(64 + rank);
	const vacationOf = (id: number) => data.vacations.find((v) => v.id === id);
	function slot(v: Vacation | undefined): string {
		if (!v) return 'Vacation supprimée';
		return `${nameOf(data.rooms, v.room_id)}, ${formatSlot(v.start_time, v.duration_min)}`;
	}

	let req = $derived(data.request);
	let pred = $derived(data.prediction);
	let canAct = $derived(data.user?.isClinical ?? false);
	let age = $derived(Number(req.earliest_date.slice(0, 4)) - data.patient.birth_year);

	function confirmSubmit(event: SubmitEvent, message: string) {
		if (!confirm(message)) event.preventDefault();
	}
</script>

<svelte:head>
	<title>{patientLabel(data.patient)} — Demande — KYST</title>
</svelte:head>

<div class="page-head">
	<div>
		<p class="eyebrow-ink"><a href="/requests">Demandes</a> / {patientLabel(data.patient)}</p>
		<h1>{nameOf(data.specialties, req.specialty_id)} · {req.principal_diagnosis}</h1>
		<p>
			{sexLabel(data.patient.sex)}, {age} ans · {nameOf(data.surgeons, req.surgeon_id)}
			· <StatusBadge status={req.status} labels={REQUEST_STATUS_LABELS} />
		</p>
	</div>
	{#if canAct && req.status === 'pending'}
		<div class="actions">
			<form method="POST" action="?/propose" use:enhance={submit}>
				<button class="btn btn--ghost" type="submit" disabled={busy}>Proposer de nouvelles dates</button>
			</form>
			<form method="POST" action="?/cancelRequest" use:enhance={submit} onsubmit={(e) => confirmSubmit(e, 'Annuler cette demande ?')}>
				<button class="btn btn--danger" type="submit" disabled={busy}>Annuler la demande</button>
			</form>
		</div>
	{/if}
</div>

<FormErrors {form} />

<div class="layout">
	<div class="stack">
		{#if req.status === 'pending'}
			<section>
				<div class="card-head">
					<h2>Dates proposées</h2>
					{#if data.open.length}
						<span class="muted small">calculées le {formatDateTime(data.open[0].created_at)}</span>
					{/if}
				</div>

				{#if data.open.length}
					<div class="proposals">
						{#each data.open as proposal (proposal.id)}
							{@const vacation = vacationOf(proposal.vacation_id)}
							<article class="proposal card" class:proposal--best={proposal.rank === 1}>
								<div class="proposal__head">
									<span class="proposal__letter" aria-label="Date {letter(proposal.rank)}">{letter(proposal.rank)}</span>
									<div>
										<p class="proposal__kicker">{proposal.rank === 1 ? 'Meilleure option' : 'Alternative'}</p>
										<h3 class="proposal__date">{formatLongDay(proposal.admission_date)}</h3>
									</div>
								</div>
								<dl class="props">
									<dt>Bloc</dt>
									<dd>{slot(vacation)}</dd>
									<dt>Temps prévu</dt>
									<dd>{formatMinutes(proposal.planned_minutes)}</dd>
									<dt>Hébergement</dt>
									<dd>{nameOf(data.bedUnits, proposal.bed_unit_id)}</dd>
									<dt>Sortie prévue</dt>
									<dd>{formatLongDay(proposal.discharge_date)}</dd>
								</dl>
								<div class="reasons">
									<p class="label">Pourquoi cette date</p>
									<ul>
										{#each proposal.reasons as reason}
											<li>{reason}</li>
										{/each}
									</ul>
								</div>
								{#if canAct}
									<div class="actions">
										<form method="POST" action="?/accept" use:enhance={submit}>
											<input type="hidden" name="proposalId" value={proposal.id} />
											<button class="btn" type="submit" disabled={busy}>Confirmer cette date</button>
										</form>
										<form method="POST" action="?/reject" use:enhance={submit}>
											<input type="hidden" name="proposalId" value={proposal.id} />
											<button class="btn btn--ghost" type="submit" disabled={busy}>Écarter</button>
										</form>
									</div>
								{/if}
							</article>
						{/each}
					</div>
				{:else}
					<div class="card empty-state">
						<p><strong>Aucune date à proposer pour l'instant.</strong></p>
						<p class="muted">
							Aucune vacation de la spécialité n'a assez de temps libre avec un lit disponible
							dans la fenêtre demandée. Élargissez la date limite, ou demandez au cadre de bloc
							d'ouvrir des vacations, puis proposez de nouvelles dates.
						</p>
					</div>
				{/if}
			</section>
		{/if}

		{#if data.currentCase}
			{@const c = data.currentCase}
			<section class="card">
				<div class="card-head">
					<h2>Intervention</h2>
					<StatusBadge status={c.status} labels={CASE_STATUS_LABELS} />
				</div>
				<dl class="props">
					<dt>Admission</dt>
					<dd>{formatLongDay(c.admission_date)}</dd>
					<dt>Bloc</dt>
					<dd>{slot(vacationOf(c.vacation_id))}</dd>
					<dt>Temps prévu</dt>
					<dd>{formatMinutes(c.planned_minutes)}</dd>
					<dt>Hébergement</dt>
					<dd>{nameOf(data.bedUnits, c.bed_unit_id)}</dd>
					<dt>Sortie prévue</dt>
					<dd>{formatLongDay(c.discharge_date)}</dd>
					{#if c.status === 'done'}
						<dt>Temps réel</dt>
						<dd>{formatMinutes(c.actual_room_minutes ?? 0)}</dd>
						<dt>Séjour réel</dt>
						<dd>{plural(c.actual_los_days ?? 0, 'jour')}</dd>
					{/if}
				</dl>

				{#if c.status === 'planned' && data.user?.isStaff}
					<form method="POST" action="?/outcome" use:enhance={submit} class="outcome">
						<input type="hidden" name="caseId" value={c.id} />
						<p class="label">Après l'intervention : durées observées</p>
						<div class="fields">
							<div class="field">
								<label for="actual-room">Temps en salle (min)</label>
								<input id="actual-room" name="actual_room_minutes" type="number" min="1" max="1440" required />
							</div>
							<div class="field">
								<label for="actual-los">Séjour (jours, ambulatoire = 1)</label>
								<input id="actual-los" name="actual_los_days" type="number" min="1" required />
							</div>
						</div>
						<div class="actions outcome__actions">
							<button class="btn" type="submit" disabled={busy}>Enregistrer</button>
						</div>
					</form>
					{#if canAct}
						<form method="POST" action="?/cancelCase" use:enhance={submit} onsubmit={(e) => confirmSubmit(e, "Annuler l'intervention et libérer le créneau ?")}>
							<input type="hidden" name="caseId" value={c.id} />
							<button class="btn btn--danger btn--small" type="submit" disabled={busy}>Annuler l'intervention</button>
						</form>
					{/if}
				{/if}
			</section>
		{/if}

		{#if data.history.length}
			<details class="card history">
				<summary>Propositions précédentes ({data.history.length})</summary>
				<div class="table-wrap">
					<table class="table">
						<thead>
							<tr><th>Date</th><th>Rang</th><th>Statut</th><th>Décision</th></tr>
						</thead>
						<tbody>
							{#each data.history as p (p.id)}
								<tr>
									<td>{formatDay(p.admission_date)}</td>
									<td>{letter(p.rank)}</td>
									<td><StatusBadge status={p.status} labels={PROPOSAL_STATUS_LABELS} /></td>
									<td class="muted small">{p.decided_at ? formatDateTime(p.decided_at) : '—'}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</details>
		{/if}
	</div>

	<aside class="stack">
		<section class="card">
			<h2>Prédiction</h2>
			{#if pred}
				<div class="figures">
					<div>
						<p class="label">Temps au bloc</p>
						<p class="figure">{formatMinutes(pred.room_minutes)}</p>
						{#if pred.room_minutes_low !== null && pred.room_minutes_high !== null}
							<p class="muted small">entre {formatMinutes(pred.room_minutes_low)} et {formatMinutes(pred.room_minutes_high)}</p>
						{/if}
					</div>
					<div>
						<p class="label">Séjour</p>
						<p class="figure">{plural(pred.los_days, 'jour')}</p>
						{#if pred.los_days_low !== null && pred.los_days_high !== null}
							<p class="muted small">entre {pred.los_days_low} et {pred.los_days_high} j</p>
						{/if}
					</div>
				</div>
				<p>{CARE_TYPE_LABELS[pred.care_type]}</p>
				<p class="muted small">Modèle {pred.model_version} · {formatDateTime(pred.created_at)}</p>
				{#if pred.source === 'fixtures'}
					<p class="alert alert--info small">
						Valeurs de démonstration : les modèles entraînés ne sont pas encore branchés.
					</p>
				{/if}
			{:else}
				<p class="muted">Pas encore de prédiction : elle est faite en proposant des dates.</p>
			{/if}
		</section>

		<section class="card">
			<h2>Demande</h2>
			<dl class="props">
				<dt>Patient</dt>
				<dd>{patientLabel(data.patient)}</dd>
				<dt>Diagnostic</dt>
				<dd class="mono">{req.principal_diagnosis}</dd>
				<dt>Actes CCAM</dt>
				<dd class="mono">{req.ccam_codes.join(', ')}</dd>
				{#if req.intervention_type}
					<dt>Type</dt>
					<dd>{req.intervention_type}</dd>
				{/if}
				<dt>Fenêtre</dt>
				<dd>
					à partir du {formatDay(req.earliest_date)}{#if req.latest_date}, avant le {formatDay(req.latest_date)}{/if}
				</dd>
				<dt>Créée le</dt>
				<dd>{formatDateTime(req.created_at)}</dd>
			</dl>
		</section>
	</aside>
</div>

<style>
	.layout {
		display: grid;
		grid-template-columns: minmax(0, 1fr) clamp(260px, 24%, 460px);
		gap: var(--s3);
		align-items: start;
	}

	.eyebrow-ink a {
		color: inherit;
	}

	.page-head p :global(.badge) {
		vertical-align: middle;
	}

	.proposals {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
		gap: var(--s2);
	}

	.proposal {
		display: flex;
		flex-direction: column;
		gap: var(--s2);
	}

	.proposal--best {
		border-color: var(--primary);
		box-shadow: 0 0 0 1px var(--primary);
	}

	.proposal__head {
		display: flex;
		align-items: center;
		gap: 0.9rem;
	}

	.proposal__letter {
		display: grid;
		place-items: center;
		flex-shrink: 0;
		width: 2.6rem;
		height: 2.6rem;
		border-radius: var(--radius-lg);
		background: var(--primary-soft);
		color: var(--green-deep);
		font-family: var(--font-display);
		font-stretch: 80%;
		font-weight: 600;
		font-size: 1.5rem;
	}

	.proposal--best .proposal__letter {
		background: var(--primary);
		color: var(--on-primary);
	}

	.proposal__kicker {
		margin: 0;
		font-family: var(--font-mono);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-muted);
	}

	.proposal__date {
		margin: 0.1rem 0 0;
		font-size: 1.15rem;
	}

	.label {
		margin: 0 0 0.35rem;
		font-family: var(--font-mono);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-muted);
	}

	.reasons ul {
		max-width: 70ch;
		margin: 0;
		padding-left: 1.1rem;
		color: var(--text-secondary);
		font-size: 0.9rem;
	}

	.reasons li + li {
		margin-top: 0.25rem;
	}

	.proposal .actions {
		margin-top: auto;
	}

	.empty-state p {
		margin: 0 0 0.4rem;
	}

	.outcome {
		margin: var(--s3) 0 var(--s2);
		padding-top: var(--s2);
		border-top: 1px solid var(--border);
	}

	.outcome__actions {
		margin-top: var(--s2);
	}

	.figures {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--s2);
		margin-bottom: var(--s2);
	}

	.figures p {
		margin: 0;
	}

	.figure {
		font-size: 1.6rem;
		font-weight: 600;
		line-height: 1.15;
	}

	aside p {
		margin: 0 0 0.4rem;
	}

	.history summary {
		cursor: pointer;
		font-weight: 500;
	}

	.history .table-wrap {
		margin-top: var(--s2);
	}

	@media (max-width: 900px) {
		.layout {
			grid-template-columns: 1fr;
		}
	}
</style>
