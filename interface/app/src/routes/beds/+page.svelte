<script lang="ts">
	import OccupancyChart from '#lib/components/OccupancyChart.svelte';
	import { addDays, formatShortDay, today } from '#lib/format.ts';
	import { sortBedUnits } from '#lib/names.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let units = $derived(sortBedUnits(data.occupancy));
</script>

<svelte:head>
	<title>Lits — KYST</title>
</svelte:head>

<div class="page-head">
	<div>
		<p class="eyebrow-ink">Hébergement</p>
		<h1>Occupation des lits</h1>
		<p>
			Lits et places réservés par les interventions programmées (hors urgences non programmées),
			du {formatShortDay(data.start)} au {formatShortDay(addDays(data.start, data.days - 1))}
		</p>
	</div>
	<form class="actions" method="GET">
		<label class="visually-hidden" for="start">Début</label>
		<input class="inline-input" id="start" type="date" name="start" value={data.start} />
		<label class="visually-hidden" for="days">Durée</label>
		<select class="inline-input" id="days" name="days">
			{#each data.periods as p}
				<option value={p} selected={p === data.days}>{p} jours</option>
			{/each}
		</select>
		<button class="btn btn--ghost btn--small" type="submit">Afficher</button>
		{#if data.start !== today()}
			<a class="btn btn--ghost btn--small" href="?days={data.days}">Aujourd'hui</a>
		{/if}
	</form>
</div>

<div class="grid-2">
	{#each units as unit (unit.bed_unit_id)}
		<section class="card">
			<OccupancyChart {unit} />
		</section>
	{:else}
		<p class="card empty">Aucune unité de lits configurée.</p>
	{/each}
</div>

<style>
	.actions .inline-input {
		width: auto;
	}
</style>
