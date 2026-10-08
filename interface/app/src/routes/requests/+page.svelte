<script lang="ts">
	import StatusBadge from '#lib/components/StatusBadge.svelte';
	import { formatDay } from '#lib/format.ts';
	import { nameOf, patientLabel } from '#lib/names.ts';
	import { REQUEST_STATUS_LABELS } from '#lib/types.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const TABS = [
		{ value: 'pending', label: 'À programmer' },
		{ value: 'scheduled', label: 'Programmées' },
		{ value: 'done', label: 'Réalisées' },
		{ value: 'cancelled', label: 'Annulées' },
		{ value: 'all', label: 'Toutes' }
	];
</script>

<svelte:head>
	<title>Demandes d'intervention — KYST</title>
</svelte:head>

<div class="page-head">
	<div>
		<p class="eyebrow-ink">Consultation</p>
		<h1>Demandes d'intervention</h1>
		<p>Chaque demande reçoit des dates proposées selon le bloc et les lits ; vous choisissez.</p>
	</div>
	{#if data.user?.isClinical}
		<a class="btn" href="/requests/new">Nouvelle demande</a>
	{/if}
</div>

<nav class="tabs" aria-label="Filtrer par statut">
	{#each TABS as tab}
		<a href="?status={tab.value}" aria-current={data.status === tab.value ? 'page' : undefined}>{tab.label}</a>
	{/each}
</nav>

<div class="card">
	<div class="table-wrap">
		<table class="table">
			<thead>
				<tr>
					<th>Patient</th>
					<th>Chirurgien</th>
					<th>Spécialité</th>
					<th>Diagnostic</th>
					<th>Fenêtre souhaitée</th>
					<th>Statut</th>
					<th><span class="visually-hidden">Ouvrir</span></th>
				</tr>
			</thead>
			<tbody>
				{#each data.requests as request (request.id)}
					<tr>
						<td>{patientLabel(data.patients.find((p) => p.id === request.patient_id))}</td>
						<td>{nameOf(data.surgeons, request.surgeon_id)}</td>
						<td>{nameOf(data.specialties, request.specialty_id)}</td>
						<td class="mono">{request.principal_diagnosis}</td>
						<td>
							à partir du {formatDay(request.earliest_date)}
							{#if request.latest_date}<div class="muted small">avant le {formatDay(request.latest_date)}</div>{/if}
						</td>
						<td><StatusBadge status={request.status} labels={REQUEST_STATUS_LABELS} /></td>
						<td><a href="/requests/{request.id}">Ouvrir</a></td>
					</tr>
				{:else}
					<tr><td colspan="7" class="empty">Aucune demande dans cette catégorie.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

