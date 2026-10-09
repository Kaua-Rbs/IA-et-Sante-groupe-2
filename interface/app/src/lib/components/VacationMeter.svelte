<script lang="ts">
	// Jauge de remplissage d'une vacation. La zone hachurée en fin de piste est la marge
	// gardée pour les urgences ; l'ordonnanceur n'y place pas de patient.
	import { formatMinutes, formatPercent } from '#lib/format.ts';

	interface Props {
		planned: number;
		duration: number;
		margin: number;
	}

	let { planned, duration, margin }: Props = $props();

	let rate = $derived(duration > 0 ? planned / duration : 0);
	let usable = $derived(1 - margin);
	let overMargin = $derived(rate > usable + 1e-9);
</script>

<div class="meter" title="{formatMinutes(planned)} prévues sur {formatMinutes(duration)}">
	<div
		class="meter__track"
		role="meter"
		aria-valuemin={0}
		aria-valuemax={duration}
		aria-valuenow={planned}
		aria-label="Remplissage de la vacation"
	>
		<span class="meter__margin" style="left: {usable * 100}%"></span>
		<span class="meter__fill" class:meter__fill--over={overMargin} style="width: {Math.min(rate, 1) * 100}%"></span>
	</div>
	<span class="meter__value">
		{formatPercent(rate)}
		{#if overMargin}<span class="meter__flag">▲ marge entamée</span>{/if}
	</span>
</div>

<style>
	.meter {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.meter__track {
		position: relative;
		flex: 1;
		height: 8px;
		min-width: 3rem;
		border-radius: 4px;
		background: var(--primary-soft);
		overflow: hidden;
	}

	.meter__margin {
		position: absolute;
		top: 0;
		bottom: 0;
		right: 0;
		background: repeating-linear-gradient(
			135deg,
			transparent 0 3px,
			rgba(6, 51, 31, 0.18) 3px 4px
		);
	}

	.meter__fill {
		position: absolute;
		top: 0;
		bottom: 0;
		left: 0;
		border-radius: 4px;
		background: var(--green);
	}

	.meter__fill--over {
		background: #fab219;
	}

	.meter__value {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-secondary);
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}

	.meter__flag {
		margin-left: 0.25rem;
		color: var(--warning);
	}
</style>
