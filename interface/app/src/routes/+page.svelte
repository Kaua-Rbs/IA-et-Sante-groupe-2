<script lang="ts">
	import Landing from '#lib/components/Landing.svelte';
	import OccupancyChart from '#lib/components/OccupancyChart.svelte';
	import { formatMinutes, formatPercent } from '#lib/format.ts';
	import { sortBedUnits } from '#lib/names.ts';
	import type { CareType } from '#lib/types.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let dash = $derived(data.dashboard);

	/** Occupation du jour, toutes unités d'un même type confondues. */
	function todayLoad(careType: CareType) {
		const units = dash?.occupancy.filter((u) => u.care_type === careType) ?? [];
		return {
			occupied: units.reduce((sum, u) => sum + (u.days[0]?.occupied ?? 0), 0),
			capacity: units.reduce((sum, u) => sum + u.capacity, 0)
		};
	}

	let conventional = $derived(todayLoad('conventional'));
	let ambulatory = $derived(todayLoad('ambulatory'));
	let blocRate = $derived.by(() => {
		const capacity = dash?.fills.reduce((s, f) => s + f.duration_min, 0) ?? 0;
		const planned = dash?.fills.reduce((s, f) => s + f.planned_minutes, 0) ?? 0;
		return capacity ? planned / capacity : null;
	});
</script>

<svelte:head>
	<title>KYST — Keep Your Surgeries Timelies</title>
	<meta
		name="description"
		content="KYST propose des dates d'intervention compatibles avec le bloc opératoire et les lits, à partir de durées prédites."
	/>
</svelte:head>

{#if !dash}
	<Landing />
{:else}
	<div class="page-head">
		<div>
			<p class="eyebrow-ink">Tableau de bord</p>
			<h1>Bonjour {data.user?.fullName}</h1>
			<p>Charge prévue du bloc et des lits, à partir des interventions programmées.</p>
		</div>
		{#if data.user?.isClinical}
			<a class="btn" href="/requests/new">Nouvelle demande</a>
		{/if}
	</div>

	{#if dash.health.ai_backend === 'fixtures'}
		<p class="alert alert--info small">
			Mode démonstration : les durées prédites et les dates proposées viennent de valeurs fixes, en
			attendant les modèles entraînés et le solveur d'optimisation.
		</p>
	{/if}

	{#if !data.user?.roles.length && !data.user?.admin}
		<p class="alert alert--info small">
			Votre compte n'a pas encore de rôle : demandez à un administrateur de vous en attribuer un
			pour saisir des demandes ou gérer le planning.
		</p>
	{/if}

	<div class="kpis">
		<div class="kpi">
			<p class="kpi__label">Lits conventionnels aujourd'hui</p>
			<p class="kpi__value">{conventional.occupied}&nbsp;<small>/ {conventional.capacity}</small></p>
		</div>
		<div class="kpi">
			<p class="kpi__label">Places ambulatoires aujourd'hui</p>
			<p class="kpi__value">{ambulatory.occupied}&nbsp;<small>/ {ambulatory.capacity}</small></p>
		</div>
		<div class="kpi">
			<p class="kpi__label">Remplissage du bloc, 7 jours</p>
			<p class="kpi__value">{blocRate === null ? '—' : formatPercent(blocRate)}</p>
			<p class="kpi__note"><a href="/planning">Voir le planning</a></p>
		</div>
		{#if dash.pending}
			<div class="kpi">
				<p class="kpi__label">Demandes à programmer</p>
				<p class="kpi__value">{dash.pending.length >= 100 ? '100+' : dash.pending.length}</p>
				<p class="kpi__note"><a href="/requests">Voir les demandes</a></p>
			</div>
		{/if}
	</div>

	<div class="section-head">
		<h2>Lits, 14 prochains jours</h2>
		<a href="/beds">Détail</a>
	</div>
	<div class="grid-2">
		{#each sortBedUnits(dash.occupancy) as unit (unit.bed_unit_id)}
			<section class="card"><OccupancyChart {unit} /></section>
		{:else}
			<p class="card empty">Aucune unité de lits configurée.</p>
		{/each}
	</div>

	{#if dash.accuracy && dash.accuracy.evaluated_cases > 0}
		<section class="card accuracy">
			<h2>Précision des prédictions</h2>
			<p class="muted small">Sur {dash.accuracy.evaluated_cases} interventions réalisées.</p>
			<dl class="props">
				<dt>Temps au bloc</dt>
				<dd>
					écart moyen de {formatMinutes(dash.accuracy.room_minutes_mae ?? 0)} ·
					{dash.accuracy.room_minutes_underestimated} sous-estimés, {dash.accuracy.room_minutes_overestimated} surestimés
				</dd>
				<dt>Séjour</dt>
				<dd>écart moyen de {dash.accuracy.los_days_mae} jour(s)</dd>
			</dl>
		</section>
	{/if}
{/if}

<style>
	.kpis {
		margin-bottom: var(--s4);
	}

	.section-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		margin-bottom: var(--s2);
	}

	.section-head h2 {
		margin: 0;
	}

	.accuracy {
		margin-top: var(--s3);
	}
</style>
