<script lang="ts">
	// Jauge de remplissage d'une vacation. La zone hachurée orange en fin de piste est la
	// réserve gardée pour les urgences ; l'ordonnanceur n'y place pas de patient.
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

<div
	class="meter"
	title="{formatMinutes(planned)} prévues sur {formatMinutes(duration)}, dont {formatMinutes(duration * margin)} réservées aux urgences"
>
	<div
		class="meter__track"
		role="meter"
		aria-valuemin={0}
		aria-valuemax={duration}
		aria-valuenow={planned}
		aria-label="Remplissage de la vacation, {formatPercent(margin)} réservés aux urgences"
	>
		<span class="meter__margin" style="left: {usable * 100}%"></span>
		<span class="meter__fill" class:meter__fill--over={overMargin} style="width: {Math.min(rate, 1) * 100}%"></span>
	</div>
	<span class="meter__value">
		{formatPercent(rate)}
		{#if overMargin}<span class="meter__flag">▲ réserve urgences entamée</span>{/if}
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
		border-left: 1px solid var(--emergency);
		background: repeating-linear-gradient(
			135deg,
			var(--emergency-soft) 0 3px,
			var(--emergency) 3px 5px
		);
	}

	.meter__fill {
		position: absolute;
		z-index: 1;
		top: 0;
		bottom: 0;
		left: 0;
		border-radius: 4px;
		background: var(--green);
	}

	/* Le remplissage passe en orange quand il déborde sur la réserve */
	.meter__fill--over {
		background: var(--emergency);
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
		font-weight: 600;
		color: var(--emergency);
	}
</style>
