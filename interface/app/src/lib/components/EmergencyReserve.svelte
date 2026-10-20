<script lang="ts">
	// Encart qui explique la réserve gardée pour les urgences et en donne l'état.
	// Sa pastille hachurée reprend le motif de la jauge de vacation (VacationMeter).
	import type { EmergencyReserve } from '#lib/emergency.ts';
	import { formatMinutes, formatPercent, plural } from '#lib/format.ts';

	interface Props {
		margin: number;
		reserve: EmergencyReserve;
	}

	let { margin, reserve }: Props = $props();
</script>

<section class="reserve" aria-labelledby="reserve-title">
	<span class="reserve__icon" aria-hidden="true">+</span>
	<div class="reserve__body">
		<h2 id="reserve-title" class="reserve__title">Réserve pour les urgences : {formatPercent(margin)} de chaque vacation</h2>
		<p class="reserve__text">
			<span class="reserve__swatch" aria-hidden="true"></span>
			La zone hachurée en fin de jauge reste libre pour les urgences et les dépassements :
			l'ordonnanceur n'y place jamais de patient programmé.
		</p>
	</div>
	{#if reserve.vacations}
		<dl class="reserve__figures">
			<div>
				<dt>Gardé libre</dt>
				<dd>{formatMinutes(reserve.reserved)}</dd>
			</div>
			<div>
				<dt>État</dt>
				<dd class:reserve__breach={reserve.breached > 0}>
					{reserve.breached ? `${plural(reserve.breached, 'vacation')} entamée${reserve.breached > 1 ? 's' : ''}` : 'Intacte'}
				</dd>
			</div>
		</dl>
	{/if}
</section>

<style>
	.reserve {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s2);
		margin-bottom: var(--s3);
		padding: var(--s2) var(--s3);
		border: 1px solid var(--emergency);
		border-left-width: 4px;
		border-radius: var(--radius-lg);
		background: var(--emergency-soft);
	}

	.reserve__icon {
		display: grid;
		place-items: center;
		flex: none;
		width: 2rem;
		height: 2rem;
		border-radius: var(--radius);
		background: var(--emergency);
		color: #fff;
		font-size: 1.4rem;
		font-weight: 700;
		line-height: 1;
	}

	.reserve__body {
		flex: 1 1 22rem;
	}

	.reserve__title {
		margin: 0;
		font-family: var(--font-body);
		font-size: 1rem;
		font-weight: 600;
		text-transform: none;
		letter-spacing: 0;
		color: var(--emergency);
	}

	.reserve__text {
		margin: 0.2rem 0 0;
		font-size: 0.88rem;
		color: var(--text-secondary);
	}

	.reserve__swatch {
		display: inline-block;
		width: 1.6rem;
		height: 0.6rem;
		margin-right: 0.3rem;
		vertical-align: middle;
		border: 1px solid var(--emergency);
		border-radius: 2px;
		background: repeating-linear-gradient(135deg, transparent 0 3px, var(--emergency) 3px 5px);
	}

	.reserve__figures {
		display: flex;
		gap: var(--s3);
		margin: 0;
	}

	.reserve__figures dt {
		font-family: var(--font-mono);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-muted);
	}

	.reserve__figures dd {
		margin: 0;
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--text);
	}

	.reserve__figures dd.reserve__breach {
		color: var(--emergency);
	}
</style>
