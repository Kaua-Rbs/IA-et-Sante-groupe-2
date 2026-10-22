<script lang="ts">
	import { enhance } from '$app/forms';
	import FormErrors from '#lib/components/FormErrors.svelte';
	import VacationMeter from '#lib/components/VacationMeter.svelte';
	import {
		addDays, formatDateTime, formatDay, formatLongDay, formatMinutes, formatNumber, formatPercent,
		formatShortDay, formatSlot, formatTime, mondayOf, parseDay, plural, today
	} from '#lib/format.ts';
	import { nameOf, patientLabel } from '#lib/names.ts';
	import type { CohortMetrics, CohortPreview, Proposal, Unavailability, Vacation } from '#lib/types.ts';
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

	const minutesOf = (time: string) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5));

	/** Fermetures de la salle et absences du chirurgien de la vacation qui la chevauchent. */
	function closuresOf(vacation: Vacation): { label: string; whole: boolean }[] {
		const start = minutesOf(vacation.start_time);
		const end = start + vacation.duration_min;
		return data.weekClosures.flatMap((u) => {
			const concerned = u.room_id === vacation.room_id
				|| (u.surgeon_id !== null && u.surgeon_id === vacation.surgeon_id);
			if (!concerned || vacation.date < u.start_date || vacation.date > u.end_date) return [];
			const from = u.start_time ? Math.max(start, minutesOf(u.start_time)) : start;
			const to = u.end_time ? Math.min(end, minutesOf(u.end_time)) : end;
			if (from >= to) return [];
			const what = u.room_id !== null ? 'Fermée' : `${nameOf(data.surgeons, u.surgeon_id)} absent`;
			const hours = u.start_time && u.end_time ? ` ${formatTime(u.start_time)}–${formatTime(u.end_time)}` : '';
			return [{ label: `${what}${hours}`, whole: from === start && to === end }];
		});
	}

	function describeClosure(u: Unavailability): string {
		const who = u.room_id !== null
			? `${nameOf(data.rooms, u.room_id)} fermée`
			: `${nameOf(data.surgeons, u.surgeon_id)} absent`;
		const days = u.start_date === u.end_date
			? `le ${formatDay(u.start_date)}`
			: `du ${formatDay(u.start_date)} au ${formatDay(u.end_date)}`;
		const hours = u.start_time && u.end_time ? `, de ${formatTime(u.start_time)} à ${formatTime(u.end_time)}` : '';
		return `${who} ${days}${hours}`;
	}

	let closureStart = $state(today());

	/** Motif court gardé sur l'intervention déprogrammée : l'aléa, sans la conséquence. */
	const reasonOf = (reasons: string[]) => reasons[0]?.split(' : ')[0].replace(/\.$/, '') ?? '';
	const withoutPrefix = (reason: string) => reason.replace(/^Déprogrammée : /, '');

	// Interventions du jour : à reprogrammer (conflit), puis à confirmer (dates A/B), au même
	// endroit. L'ordre ne dépend que du créneau et du patient : une ligne ne bouge pas au clic.
	let todayRows = $derived.by(() => {
		const pending = data.conflicts.map((c) => ({
			caseId: c.case_id, requestId: c.request_id, patient: c.patient, day: c.admission_date,
			room: c.room_name, start: c.start_time, minutes: c.planned_minutes,
			reason: reasonOf(c.reasons), reasonText: c.reasons.join(' '), proposals: null
		}));
		const chosen = data.user?.canPlan
			? data.deprogrammed.filter((d) => d.former_date === today()).map((d) => ({
				caseId: d.case_id, requestId: d.request_id, patient: d.patient, day: d.former_date,
				room: d.room_name, start: d.start_time, minutes: d.planned_minutes,
				reason: withoutPrefix(d.reason), reasonText: withoutPrefix(d.reason), proposals: d.proposals
			}))
			: [];
		const key = (r: (typeof pending)[number] | (typeof chosen)[number]) =>
			`${r.day} ${r.start} ${r.room} ${patientLabel(r.patient)} ${r.caseId}`;
		return [...pending, ...chosen].sort((a, b) => key(a).localeCompare(key(b)));
	});
	let pendingToday = $derived(todayRows.filter((r) => r.proposals === null));
	// Celles du jour sont traitées dans leur section, sur place
	let topDeprogrammed = $derived(
		data.user?.canPlan ? data.deprogrammed.filter((d) => d.former_date !== today()) : data.deprogrammed
	);

	// Comparaison de l'aperçu : « mieux » dépend du sens de l'indicateur
	type Effect = 'better' | 'same' | 'worse';
	const effectLabel: Record<Effect, string> = { better: 'Mieux', same: 'Identique', worse: 'Moins bien' };
	const effectOf = (before: number, after: number, higherIsBetter: boolean, tolerance = 0.005): Effect =>
		Math.abs(after - before) <= tolerance ? 'same' : (after > before) === higherIsBetter ? 'better' : 'worse';
	const inDays = (value: number) => `${formatNumber(value)} j`;

	function indicators(before: CohortMetrics, after: CohortMetrics) {
		return [
			{ label: 'Demandes placées', hint: '', before: String(before.placed), after: String(after.placed),
				effect: effectOf(before.placed, after.placed, true) },
			{ label: 'Attente moyenne', hint: ' après la date au plus tôt', before: inDays(before.mean_wait_days),
				after: inDays(after.mean_wait_days), effect: effectOf(before.mean_wait_days, after.mean_wait_days, false, 0.05) },
			{ label: 'Vacation la plus remplie', hint: ' (réserve urgences comprise)', before: formatPercent(before.max_fill),
				after: formatPercent(after.max_fill), effect: effectOf(before.max_fill, after.max_fill, false) },
			{ label: 'Écart de remplissage', hint: ' entre vacations occupées', before: `${Math.round(before.fill_spread * 100)} pts`,
				after: `${Math.round(after.fill_spread * 100)} pts`, effect: effectOf(before.fill_spread, after.fill_spread, false) },
			{ label: 'Pic d’occupation des lits', hint: ' unité la plus chargée', before: formatPercent(before.bed_peak),
				after: formatPercent(after.bed_peak), effect: effectOf(before.bed_peak, after.bed_peak, false) }
		];
	}

	function gapOf(before: string | null, after: string | null) {
		if (before === after) return { changed: false, label: '—' };
		if (!before) return { changed: true, label: 'placée grâce à l’optimisation' };
		if (!after) return { changed: true, label: 'non placée' };
		const shift = Math.round((parseDay(after).getTime() - parseDay(before).getTime()) / 86_400_000);
		return { changed: true, label: shift > 0 ? `${shift} j plus tard` : `${-shift} j plus tôt` };
	}

	// Les demandes déplacées d'abord, puis par date retenue
	const sortedRows = (rows: CohortPreview['rows']) =>
		[...rows].sort((a, b) =>
			Number(gapOf(b.baseline_date, b.optimized_date).changed) - Number(gapOf(a.baseline_date, a.optimized_date).changed)
			|| (a.optimized_date ?? '9').localeCompare(b.optimized_date ?? '9'));

	function confirmDelete(event: SubmitEvent) {
		const message = 'Supprimer cette vacation ? Ses interventions futures seront déprogrammées et recevront des dates A/B à confirmer.';
		if (!confirm(message)) event.preventDefault();
	}

</script>

{#snippet plan(requestId: string, proposals: Proposal[])}
	<div class="plan">
		<span class="muted">
			{#if proposals.length}
				{proposals.length === 1 ? '1 date proposée' : `${proposals.length} dates proposées`},
				dès le {formatLongDay(proposals.map((p) => p.admission_date).sort()[0])}
			{:else}
				Aucune date libre dans la fenêtre
			{/if}
		</span>
		<a class="btn btn--small" href="/requests/{requestId}">Planifier →</a>
	</div>
{/snippet}

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

{#if topDeprogrammed.length}
	<section class="card add deprogrammed">
		<div class="card-head">
			<h2>Interventions déprogrammées : à replanifier</h2>
			<span class="badge badge--urgent">{topDeprogrammed.length}</span>
		</div>
		<p class="lead">
			Le créneau de ces interventions a été fermé ou réduit (voir le motif) : salle
			fermée, chirurgien absent, vacation supprimée, ou place cédée à une urgence. KYST a
			déjà cherché jusqu'à deux nouvelles dates pour chaque patient : « Planifier » ouvre la
			fiche du patient pour les comparer et confirmer celle qui convient.
		</p>
		<div class="table-wrap">
			<table class="table spaced">
				<thead><tr><th>Patient</th><th>Créneau initial</th><th>Motif</th><th>Nouvelle date</th></tr></thead>
				<tbody>
					{#each topDeprogrammed as row (row.case_id)}
						<tr>
							<td><a href="/requests/{row.request_id}">{patientLabel(row.patient)}</a></td>
							<td>{formatShortDay(row.former_date)}, {row.room_name} {formatTime(row.start_time)}</td>
							<td>{withoutPrefix(row.reason)}</td>
							<td>{@render plan(row.request_id, row.proposals)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>
{/if}

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
							{#if !room.active}<span class="badge badge--urgent">Salle fermée</span>{/if}
						</th>
						{#each shownDays as day}
							<td>
								{#each cellOf(room.id, day) as vacation (vacation.id)}
									{@const fill = fillOf(vacation.id)}
									{@const closures = closuresOf(vacation)}
									<div class="vac" class:vac--closed={!room.active || closures.some((c) => c.whole)}>
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
										{#if !room.active}
											<div class="vac__closure">Salle fermée</div>
										{/if}
										{#each closures as closure}
											<div class="vac__closure">{closure.label}</div>
										{/each}
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
	{#if todayRows.length}
		<section class="card add">
			<div class="card-head">
				<h2>Interventions du jour à reprogrammer</h2>
				{#if data.user?.isClinical && pendingToday.length > 1}
					<form method="POST" action="?/reprogram" use:enhance
						onsubmit={(e) => { if (!confirm(`Reprogrammer les ${pendingToday.length} interventions restantes ? Chacune reçoit des dates A/B à confirmer.`)) e.preventDefault(); }}>
						{#each pendingToday as row (row.caseId)}
							<input type="hidden" name="caseId" value={row.caseId} />
							<input type="hidden" name="reason" value={row.reason} />
						{/each}
						<button class="btn btn--small" type="submit">Tout reprogrammer ({pendingToday.length})</button>
					</form>
				{/if}
			</div>
			<p>
				Le jour même, KYST ne déprogramme rien seul. « Reprogrammer » libère la réservation et
				calcule des dates A/B ; « Planifier » ouvre ensuite la fiche du patient pour choisir.
			</p>
			<div class="table-wrap">
				<table class="table conflicts spaced">
					<thead><tr><th>Patient</th><th>Créneau initial</th><th>Motif</th><th>Nouvelle date</th></tr></thead>
					<tbody>
						{#each todayRows as row (row.caseId)}
							<tr>
								<td><a href="/requests/{row.requestId}">{patientLabel(row.patient)}</a></td>
								<td>{formatShortDay(row.day)}, {row.room} {formatTime(row.start)} · {formatMinutes(row.minutes)}</td>
								<td>{row.reasonText}</td>
								<td>
									{#if row.proposals === null}
										{#if data.user?.isClinical}
											<form method="POST" action="?/reprogram" use:enhance>
												<input type="hidden" name="caseId" value={row.caseId} />
												<input type="hidden" name="reason" value={row.reason} />
												<button class="chip" type="submit">Reprogrammer</button>
											</form>
										{:else}
											<a href="/requests/{row.requestId}">Ouvrir</a>
										{/if}
									{:else}
										{@render plan(row.requestId, row.proposals)}
									{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}
	<section class="card add">
		<div class="card-head">
			<h2>Fermetures et absences</h2>
			<span class="badge">Aléas</span>
		</div>
		<p class="lead">
			Salle fermée (toute la journée ou sur un créneau, par exemple 10h–12h) ou chirurgien absent.
			KYST retire aussitôt le temps perdu des vacations. Les interventions futures qui n'ont plus
			leur place sont déprogrammées et reçoivent des dates A/B (en haut de page) ; les premières
			réservées gardent la leur. Celles du jour se reprogramment d'un clic, ligne par ligne.
		</p>
		<form method="POST" action="?/createUnavailability" use:enhance>
			<div class="fields">
				<div class="field">
					<label for="u-target">Concerne</label>
					<select id="u-target" name="target" required>
						<optgroup label="Salles">
							{#each data.rooms.filter((r) => r.active) as room (room.id)}
								<option value="room:{room.id}">{room.name}</option>
							{/each}
						</optgroup>
						<optgroup label="Chirurgiens">
							{#each data.surgeons as surgeon (surgeon.id)}
								<option value="surgeon:{surgeon.id}">{surgeon.name}</option>
							{/each}
						</optgroup>
					</select>
				</div>
				<div class="field">
					<label for="u-start">Du</label>
					<input id="u-start" name="start_date" type="date" min={today()} bind:value={closureStart} required />
				</div>
				<div class="field">
					<label for="u-end">Au</label>
					<input id="u-end" name="end_date" type="date" min={closureStart} value={closureStart} />
				</div>
				<div class="field">
					<label for="u-from">De</label>
					<input id="u-from" name="start_time" type="time" step="900" />
				</div>
				<div class="field">
					<label for="u-to">À</label>
					<input id="u-to" name="end_time" type="time" step="900" />
				</div>
				<div class="field">
					<label for="u-reason">Motif</label>
					<input id="u-reason" name="reason" maxlength="200" placeholder="ex. maintenance, arrêt de travail" />
				</div>
			</div>
			<p class="muted small">Sans heures, toute la journée est concernée.</p>
			<div class="form-footer">
				<button class="btn" type="submit">Enregistrer l'aléa</button>
			</div>
		</form>
		{#if data.upcomingClosures.length}
			<ul class="closures">
				{#each data.upcomingClosures as u (u.id)}
					<li>
						<span>{describeClosure(u)}{u.reason ? ` — ${u.reason}` : ''}</span>
						<form method="POST" action="?/deleteUnavailability" use:enhance>
							<input type="hidden" name="id" value={u.id} />
							<button class="btn btn--ghost btn--small" type="submit">Lever</button>
						</form>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

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
			{#if preview.evaluated_cases}
				<h3 class="compare-title">Ce que l'optimisation change</h3>
				<p class="muted small">
					Comparaison sur les mêmes demandes et les mêmes vacations avec la méthode habituelle,
					où chaque demande prend tour à tour sa meilleure date A sans tenir compte des suivantes.
				</p>
				<div class="table-wrap">
					<table class="table spaced compare">
						<thead><tr><th>Indicateur</th><th class="num">Une par une</th><th class="num">Optimisé ensemble</th><th>Effet</th></tr></thead>
						<tbody>
							{#each indicators(preview.baseline, preview.optimized) as row (row.label)}
								<tr>
									<td>{row.label}<span class="muted small">{row.hint}</span></td>
									<td class="num">{row.before}</td>
									<td class="num"><strong>{row.after}</strong></td>
									<td><span class="effect effect--{row.effect}">{effectLabel[row.effect]}</span></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<div class="table-wrap">
					<table class="table">
						<thead><tr><th>Patient</th><th>Au plus tôt</th><th>Une par une</th><th>Optimisé ensemble</th><th>Écart</th></tr></thead>
						<tbody>
							{#each sortedRows(preview.rows) as row (row.request_id)}
								{@const gap = gapOf(row.baseline_date, row.optimized_date)}
								<tr class:moved={gap.changed}>
									<td><a href="/requests/{row.request_id}">{patientLabel(row.patient ?? undefined)}</a></td>
									<td>{formatShortDay(row.earliest_date)}</td>
									<td>{row.baseline_date ? formatShortDay(row.baseline_date) : 'sans date'}</td>
									<td>{row.optimized_date ? formatShortDay(row.optimized_date) : 'sans date'}</td>
									<td>{gap.label}</td>
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

	.vac--closed {
		background: repeating-linear-gradient(135deg, var(--emergency-soft) 0 6px, transparent 6px 12px);
		opacity: 0.85;
	}

	.vac__closure {
		margin: 0.15rem 0;
		color: var(--emergency);
		font-size: 0.75rem;
		font-weight: 600;
	}

	.plan {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: var(--s1) var(--s2);
	}

	.plan .btn {
		white-space: nowrap;
	}

	.lead,
	.card-head + p {
		margin: var(--s1) 0 var(--s2);
	}

	.spaced td {
		padding-block: var(--s2);
	}

	.compare-title {
		margin: var(--s3) 0 var(--s1);
	}

	.compare {
		margin-bottom: var(--s3);
	}

	.compare td span {
		display: block;
	}

	.effect {
		padding: 0.1rem 0.5rem;
		border-radius: var(--radius-pill);
		font-size: 0.8rem;
		font-weight: 600;
		white-space: nowrap;
	}

	.effect--better {
		background: var(--primary-soft);
		color: var(--green-deep);
	}

	.effect--same {
		color: var(--text-muted);
	}

	.effect--worse {
		background: var(--emergency-soft);
		color: var(--emergency);
	}

	tr.moved td {
		background: var(--bg);
	}

	.deprogrammed {
		margin-bottom: var(--s3);
		border-color: var(--emergency);
	}

	.chip {
		padding: 0.15rem 0.55rem;
		border: 1px solid var(--primary);
		border-radius: var(--radius-pill);
		background: var(--surface);
		color: var(--green-deep);
		font: inherit;
		font-size: 0.85rem;
		cursor: pointer;
	}

	.chip:hover {
		background: var(--primary-soft);
	}

	.conflicts a {
		white-space: nowrap;
	}

	.closures {
		margin: var(--s2) 0 0;
		padding: 0;
		list-style: none;
	}

	.closures li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.4rem 0;
		border-top: 1px solid var(--border);
	}

	th :global(.badge) {
		margin-top: 0.3rem;
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
