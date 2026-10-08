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
