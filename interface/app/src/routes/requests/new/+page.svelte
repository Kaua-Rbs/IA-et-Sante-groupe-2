<script lang="ts">
	import { enhance } from '$app/forms';
	import FormErrors from '#lib/components/FormErrors.svelte';
	import { today } from '#lib/format.ts';
	import { nameOf, patientLabel, sexLabel } from '#lib/names.ts';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	// Valeurs saisies, conservées si l'API refuse le formulaire
	const v = (key: string, fallback = '') => form?.values?.[key] ?? fallback;

	let patientMode = $state(v('patient_mode', 'new'));
	$effect(() => {
		// Après un échec, le serveur peut basculer sur le patient qu'il vient de créer
		if (form?.values?.patient_mode) patientMode = form.values.patient_mode;
	});
	let submitting = $state(false);
	const currentYear = new Date().getFullYear();
</script>

<svelte:head>
	<title>Nouvelle demande — KYST</title>
</svelte:head>

<div class="page-head">
	<div>
		<p class="eyebrow-ink"><a href="/requests">Demandes</a> / Nouvelle</p>
		<h1>Nouvelle demande d'intervention</h1>
		<p>
			Les informations de la consultation suffisent : KYST prédit la durée au bloc et le séjour,
			puis propose des dates compatibles avec les vacations et les lits.
		</p>
	</div>
</div>

<FormErrors {form} />

<form
	method="POST"
	use:enhance={() => {
		submitting = true;
		return async ({ update }) => {
			await update({ reset: false });
			submitting = false;
		};
	}}
>
	<div class="request-sections">
		<section class="card">
			<h2>Patient</h2>
			<fieldset class="choice">
				<legend class="visually-hidden">Patient</legend>
				<label><input type="radio" name="patient_mode" value="new" bind:group={patientMode} /> Nouveau patient</label>
				<label>
					<input type="radio" name="patient_mode" value="existing" bind:group={patientMode} disabled={!data.patients.length} />
					Patient déjà enregistré
				</label>
			</fieldset>

			{#if patientMode === 'new'}
				<div class="fields">
					<div class="field">
						<label for="external_ref">Identifiant pseudonyme</label>
						<input id="external_ref" name="external_ref" maxlength="64" value={v('external_ref')} placeholder="ex. IPP pseudonymisé" />
						<span class="hint">Facultatif. Jamais de nom.</span>
					</div>
					<div class="field">
						<label for="birth_year">Année de naissance</label>
						<input id="birth_year" name="birth_year" type="number" min="1900" max={currentYear} value={v('birth_year')} required />
					</div>
					<div class="field">
						<label for="sex">Sexe</label>
						<select id="sex" name="sex" required>
							<option value="2" selected={v('sex') === '2'}>Femme</option>
							<option value="1" selected={v('sex') === '1'}>Homme</option>
						</select>
					</div>
				</div>
			{:else}
				<div class="field">
					<label for="patient_id">Patient</label>
					<select id="patient_id" name="patient_id" required>
						{#each data.patients as patient (patient.id)}
							<option value={patient.id} selected={v('patient_id') === patient.id}>
								{patientLabel(patient)} — {sexLabel(patient.sex)}, né·e en {patient.birth_year}
							</option>
						{/each}
					</select>
				</div>
			{/if}
		</section>

		<section class="card">
			<h2>Intervention</h2>
			<div class="fields">
				<div class="field">
					<label for="surgeon_id">Chirurgien</label>
					<select id="surgeon_id" name="surgeon_id" required>
						{#each data.surgeons as surgeon (surgeon.id)}
							<option
								value={surgeon.id}
								selected={v('surgeon_id') ? v('surgeon_id') === String(surgeon.id) : data.ownSurgeon === surgeon.id}
							>
								{surgeon.name} — {nameOf(data.specialties, surgeon.specialty_id)}
							</option>
						{/each}
					</select>
					<span class="hint">La spécialité du chirurgien détermine les vacations possibles.</span>
				</div>
				<div class="field">
					<label for="principal_diagnosis">Diagnostic principal (CIM-10)</label>
					<input id="principal_diagnosis" name="principal_diagnosis" maxlength="16" value={v('principal_diagnosis')} placeholder="M17.1" required />
				</div>
				<div class="field">
					<label for="ccam_codes">Actes prévus (CCAM)</label>
					<input id="ccam_codes" name="ccam_codes" value={v('ccam_codes')} placeholder="NFKA008" required />
					<span class="hint">1 à 4 codes, séparés par des espaces ou des virgules.</span>
				</div>
				<div class="field">
					<label for="intervention_type">Type d'intervention</label>
					<input id="intervention_type" name="intervention_type" maxlength="100" value={v('intervention_type')} placeholder="ex. Varices" />
					<span class="hint">Facultatif.</span>
				</div>
			</div>
		</section>

		<section class="card">
			<h2>Fenêtre souhaitée</h2>
			<div class="fields">
				<div class="field">
					<label for="earliest_date">Pas d'admission avant le</label>
					<input id="earliest_date" name="earliest_date" type="date" value={v('earliest_date', today())} required />
				</div>
				<div class="field">
					<label for="latest_date">Date limite souhaitée</label>
					<input id="latest_date" name="latest_date" type="date" value={v('latest_date')} />
					<span class="hint">Facultatif. Sans limite, KYST cherche sur les semaines suivantes.</span>
				</div>
			</div>
		</section>

	</div>

	<div class="form-footer">
		<a class="btn btn--ghost" href="/requests">Annuler</a>
		<button class="btn" type="submit" disabled={submitting}>
			{submitting ? 'Recherche des dates…' : 'Créer et proposer des dates'}
		</button>
	</div>
</form>

<style>
	/* Patient, intervention et fenêtre : empilés, puis côte à côte (jamais 2 + 1) */
	.request-sections {
		display: grid;
		gap: var(--s3);
	}

	@media (min-width: 1400px) {
		.request-sections {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.choice {
		display: flex;
		flex-wrap: wrap;
		gap: 1.25rem;
		margin: 0 0 var(--s2);
		padding: 0;
		border: none;
	}

	.choice label {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		cursor: pointer;
	}

	.eyebrow-ink a {
		color: inherit;
	}
</style>
