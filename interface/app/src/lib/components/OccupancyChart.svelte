<script lang="ts">
	// Lits occupés par jour pour une unité : colonnes d'une seule teinte, échelle 0 → capacité.
	// Les jours tendus ou saturés portent un symbole et un libellé (jamais la couleur seule),
	// chaque colonne a son infobulle (survol et focus clavier) et un tableau reprend les valeurs.
	import { CARE_TYPE_LABELS, type UnitOccupancy } from '#lib/types.ts';
	import { formatLongDay, formatPercent, formatShortDay, parseDay } from '#lib/format.ts';

	interface Props {
		unit: UnitOccupancy;
	}

	let { unit }: Props = $props();

	const TENSE = 0.9;

	type Level = 'ok' | 'tense' | 'full';
	const levelOf = (rate: number): Level => (rate >= 1 ? 'full' : rate >= TENSE ? 'tense' : 'ok');
	const LEVEL_LABELS: Record<Level, string> = { ok: '', tense: 'Tendu', full: 'Saturé' };
	const GLYPHS: Record<Level, string> = { ok: '', tense: '▲', full: '■' };

	const DAY_ABBR = ['di', 'lu', 'ma', 'me', 'je', 've', 'sa'];

	let active = $state<number | null>(null);

	let days = $derived(unit.days.map((d) => ({ ...d, level: levelOf(d.rate) })));
	let peak = $derived(
		days.reduce((best, d) => (d.occupied > best.occupied ? d : best), days[0])
	);
	let dense = $derived(days.length > 16);
	let hasTense = $derived(days.some((d) => d.level !== 'ok'));

	/** Repère d'axe : jour abrégé et numéro sur deux lignes ; un repère par lundi si la période est longue. */
	function tick(iso: string, index: number): { day: string; num: string } {
		const date = parseDay(iso);
		if (!dense) return { day: DAY_ABBR[date.getDay()], num: String(date.getDate()) };
		const show = date.getDay() === 1 || index === 0;
		return show ? { day: DAY_ABBR[date.getDay()], num: `${date.getDate()}/${date.getMonth() + 1}` } : { day: '', num: '' };
	}
</script>

<figure class="occ">
	<figcaption class="occ__head">
		<div>
			<h3>{unit.name}</h3>
			<p class="muted small">{CARE_TYPE_LABELS[unit.care_type]} · capacité {unit.capacity}</p>
		</div>
		<p class="occ__peak">
			{#if peak && peak.occupied > 0}
				Pic : <strong>{peak.occupied}/{unit.capacity}</strong>
				<span class="muted">le {formatShortDay(peak.date)}</span>
			{:else}
				<span class="muted">Aucune réservation sur la période</span>
			{/if}
		</p>
	</figcaption>

	<div class="occ__chart">
		<div class="occ__axis" aria-hidden="true">
			<span style="bottom: 100%">{unit.capacity}</span>
			<span style="bottom: 50%">{Math.round(unit.capacity / 2)}</span>
			<span style="bottom: 0%">0</span>
		</div>

		<div class="occ__plot">
			<div class="occ__grid" aria-hidden="true">
				<span style="bottom: 100%"></span>
				<span style="bottom: 50%"></span>
				<span style="bottom: 0%"></span>
			</div>

			<div class="occ__cols">
				{#each days as day, i (day.date)}
					<button
						type="button"
						class="occ__col"
						aria-label="{formatLongDay(day.date)} : {day.occupied} lits occupés sur {unit.capacity}{day.level !== 'ok' ? ', ' + LEVEL_LABELS[day.level] : ''}"
						onpointerenter={() => (active = i)}
						onpointerleave={() => (active = null)}
						onfocus={() => (active = i)}
						onblur={() => (active = null)}
					>
						<span class="occ__bar occ__bar--{day.level}" class:occ__bar--empty={day.occupied === 0} style="height: {Math.min(day.rate, 1) * 100}%">
							{#if day.level !== 'ok'}
								<span class="occ__glyph" aria-hidden="true">{GLYPHS[day.level]}</span>
							{/if}
						</span>
					</button>
				{/each}
			</div>

			{#if active !== null}
				{@const day = days[active]}
				<div class="occ__tip" role="tooltip" style="left: {((active + 0.5) / days.length) * 100}%">
					<strong>{day.occupied} / {unit.capacity}</strong> lits · {formatPercent(day.rate)}
					<span>{formatLongDay(day.date)}</span>
					{#if day.level !== 'ok'}<span>{GLYPHS[day.level]} {LEVEL_LABELS[day.level]}</span>{/if}
				</div>
			{/if}
		</div>

		<div class="occ__ticks" aria-hidden="true">
			{#each days as day, i (day.date)}
				{@const t = tick(day.date, i)}
				<span><span class="occ__tick-day">{t.day}</span>{t.num}</span>
			{/each}
		</div>
	</div>

	{#if hasTense}
		<p class="occ__legend small muted">▲ Tendu : 90 % de la capacité ou plus · ■ Saturé</p>
	{/if}

	<details class="table-view">
		<summary>Voir les valeurs</summary>
		<div class="table-wrap">
			<table class="table">
				<thead>
					<tr><th>Jour</th><th class="num">Lits occupés</th><th class="num">Taux</th><th>État</th></tr>
				</thead>
				<tbody>
					{#each days as day (day.date)}
						<tr>
							<td>{formatLongDay(day.date)}</td>
							<td class="num">{day.occupied} / {unit.capacity}</td>
							<td class="num">{formatPercent(day.rate)}</td>
							<td>{LEVEL_LABELS[day.level]}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</details>
</figure>

<style>
	.occ {
		margin: 0;
	}

	.occ__head {
		margin-bottom: 0.75rem;
	}

	.occ__head h3 {
		margin: 0;
	}

	.occ__head p {
		margin: 0.15rem 0 0;
	}

	.occ__peak {
		margin-top: 0.4rem !important;
		font-size: 0.9rem;
	}

	.occ__chart {
		display: grid;
		grid-template-columns: 2rem 1fr;
		grid-template-rows: 150px auto;
		column-gap: 0.5rem;
		padding-top: 0.75rem;
	}

	.occ__axis {
		position: relative;
		font-family: var(--font-mono);
		font-size: 10px;
		color: var(--text-muted);
		font-variant-numeric: tabular-nums;
	}

	.occ__axis span {
		position: absolute;
		right: 0;
		transform: translateY(50%);
	}

	.occ__plot {
		position: relative;
	}

	.occ__grid span {
		position: absolute;
		left: 0;
		right: 0;
		height: 1px;
		background: var(--border);
	}

	.occ__cols {
		position: absolute;
		inset: 0;
		display: flex;
		gap: 2px;
	}

	.occ__col {
		flex: 1 1 0;
		display: flex;
		align-items: flex-end;
		justify-content: center;
		min-width: 0;
		padding: 0;
		border: none;
		background: transparent;
		cursor: default;
	}

	.occ__col:focus-visible {
		outline: 2px solid var(--primary);
		outline-offset: 1px;
	}

	.occ__col:hover .occ__bar,
	.occ__col:focus-visible .occ__bar {
		filter: brightness(0.88);
	}

	.occ__bar {
		position: relative;
		width: 100%;
		max-width: 24px;
		min-height: 3px;
		border-radius: 4px 4px 0 0;
		background: var(--green);
	}

	/* Jour sans réservation : pas de marque, pour ne pas suggérer une valeur */
	.occ__bar--empty {
		visibility: hidden;
	}

	/* Couleurs de statut (accompagnées d'un symbole et d'un libellé) */
	.occ__bar--tense {
		background: #fab219;
	}

	.occ__bar--full {
		background: #d03b3b;
	}

	.occ__glyph {
		position: absolute;
		bottom: 100%;
		left: 50%;
		transform: translateX(-50%);
		padding-bottom: 2px;
		font-size: 9px;
		line-height: 1;
		color: var(--text);
	}

	.occ__ticks {
		grid-column: 2;
		display: flex;
		gap: 2px;
		margin-top: 0.35rem;
	}

	.occ__ticks > span {
		flex: 1 1 0;
		min-width: 0;
		overflow: visible;
		white-space: nowrap;
		text-align: center;
		font-family: var(--font-mono);
		font-size: 10px;
		line-height: 1.3;
		color: var(--text-muted);
	}

	.occ__tick-day {
		display: block;
	}

	.occ__tip {
		position: absolute;
		top: 0;
		z-index: 2;
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
		padding: 0.45rem 0.65rem;
		border: 1px solid var(--border-strong);
		border-radius: var(--radius);
		background: var(--surface);
		box-shadow: var(--shadow-md);
		font-size: 0.8rem;
		white-space: nowrap;
		pointer-events: none;
		transform: translate(-50%, calc(-100% - 6px));
	}

	.occ__tip span {
		color: var(--text-secondary);
	}

	.occ__legend {
		margin: 0.5rem 0 0;
	}
</style>
