<script lang="ts">
	// Page d'accueil publique de KYST (visiteurs non connectés).
	import { count, reveal } from '#lib/actions.ts';

	// Ordres de grandeur du cahier des charges, pas des données en temps réel
	const stats = [
		{ value: 45, label: 'lits de chirurgie' },
		{ value: 21, label: 'places ambulatoires' },
		{ value: 4, label: 'heures par vacation' },
		{ value: 2, label: 'dates proposées' }
	];

	const steps = [
		{
			title: 'Patient identifié',
			text: "Âge, sexe, diagnostic et actes prévus, saisis en consultation par le chirurgien ou son secrétariat."
		},
		{
			title: 'Durées prédites',
			text: 'Temps au bloc, durée de séjour et besoin ambulatoire ou conventionnel, appris sur les séjours passés.'
		},
		{
			title: 'Dates proposées',
			text: 'Deux dates compatibles avec les vacations de la spécialité et les lits disponibles, chacune justifiée.'
		},
		{
			title: 'Choix confirmé',
			text: "Le chirurgien choisit. La place au bloc et le lit sont réservés, et le planning se met à jour."
		}
	];
</script>

<div class="landing">
	<section class="hero">
		<div class="wrap hero__grid">
			<div class="hero__copy">
				<p class="eyebrow">KYST · Keep Your Surgeries Timelies</p>
				<h1>La bonne date,<br />pour le bloc et pour les lits.</h1>
				<p class="lede">
					Au lieu de chercher un lit après avoir fixé l'intervention, KYST part de la capacité
					prévue du bloc et des services pour proposer les meilleures dates. Le chirurgien garde
					la décision.
				</p>
				<div class="hero__actions">
					<a class="btn btn--primary" href="/account/login">Se connecter</a>
					<a class="btn btn--ghost" href="#fonctionnement">Comment ça marche</a>
				</div>
			</div>

			<div class="panel" aria-hidden="true">
				<div class="panel__head">Proposition pour une prothèse de genou</div>
				<div class="panel__row"><span class="panel__rule">A</span><span class="panel__label">mar. 14 oct. · Salle 1 · 08h00</span><span class="panel__cf">82 %</span></div>
				<div class="panel__row"><span class="panel__rule">B</span><span class="panel__label">jeu. 16 oct. · Salle 1 · 13h30</span><span class="panel__cf">71 %</span></div>
				<div class="panel__row"><span class="panel__rule">Lits</span><span class="panel__label">au plus 38/45 pendant le séjour</span><span class="panel__cf">4 j</span></div>
				<div class="panel__result">
					<span class="panel__result-name">Date A confirmée</span>
					<span class="panel__result-sev">marge urgences 10 %</span>
				</div>
			</div>
		</div>
	</section>

	<section class="stats-band" use:count>
		<div class="wrap stats">
			{#each stats as s}
				<div>
					<span class="stat-value" data-count={s.value}>{s.value}</span>
					<span class="stat-label">{s.label}</span>
				</div>
			{/each}
		</div>
	</section>

	<section id="fonctionnement" class="section" use:reveal>
		<div class="wrap two-col">
			<div class="col-head">
				<h2>Pourquoi</h2>
			</div>
			<div class="col-body">
				<dl class="facts">
					<div>
						<dt>Flux tiré</dt>
						<dd>la date découle de la capacité disponible, au lieu de chercher un lit après coup.</dd>
					</div>
					<div>
						<dt>Bloc et lits ensemble</dt>
						<dd>optimiser l'un seul sature l'autre : chaque proposition vérifie les deux.</dd>
					</div>
					<div>
						<dt>Marge pour l'imprévu</dt>
						<dd>une part de chaque vacation reste libre pour les urgences et les dépassements.</dd>
					</div>
					<div>
						<dt>Explicable</dt>
						<dd>chaque date proposée affiche ses raisons : remplissage, lits, marge préservée.</dd>
					</div>
				</dl>
			</div>
		</div>
	</section>

	<section class="section section--muted" use:reveal>
		<div class="wrap two-col">
			<div class="col-head">
				<h2>Quatre étapes</h2>
			</div>
			<div class="col-body">
				<ol class="steps">
					{#each steps as step, i}
						<li>
							<span class="num">{i + 1}</span>
							<div>
								<h3>{step.title}</h3>
								<p>{step.text}</p>
							</div>
						</li>
					{/each}
				</ol>
			</div>
		</div>
	</section>

	<section class="cta-band" use:reveal>
		<div class="wrap cta-band__inner">
			<div>
				<h2>Accès réservé aux équipes</h2>
				<p>Chirurgiens, secrétariats, cadres de bloc et gestionnaires de lits.</p>
			</div>
			<a class="btn btn--primary" href="/account/register">Demander un accès</a>
		</div>
	</section>

	<footer class="footer">
		<div class="wrap">
			<p class="disclaimer">
				<strong>Avertissement.</strong> Projet étudiant (Centrale Lille, électif IA &amp; Santé).
				Outil d'aide à la décision : il ne remplace pas le jugement clinique. Les prédictions
				actuelles sont des valeurs de démonstration.
			</p>
			<p class="copyright">KYST · Keep Your Surgeries Timelies</p>
		</div>
	</footer>
</div>

<style>
	.wrap {
		width: 100%;
		max-width: var(--max-w);
		margin: 0 auto;
		padding: 0 5%;
	}

	/* ── Hero ─────────────────────────────────────────────────────────── */
	.hero {
		background: var(--green);
		color: var(--fg-on-green);
		padding: clamp(3rem, 7vw, 5.5rem) 0;
	}

	.hero__grid {
		display: grid;
		grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
		gap: 3rem;
		align-items: center;
	}

	.eyebrow {
		margin: 0 0 1rem;
		font-family: var(--font-mono);
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--accent);
	}

	.hero h1 {
		font-size: clamp(2.2rem, 5.4vw, 4.4rem);
		line-height: 1;
		margin: 0 0 1rem;
	}

	.lede {
		max-width: 50ch;
		margin: 0 0 1.75rem;
		color: var(--muted-on-green);
		font-size: 1.05rem;
	}

	.hero__actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	/* Boutons */
	.btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1.4rem;
		border: 1px solid transparent;
		border-radius: var(--radius);
		font-size: 13px;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		text-decoration: none;
		cursor: pointer;
		transition: background-color var(--dur) var(--ease),
			border-color var(--dur) var(--ease), color var(--dur) var(--ease);
	}

	.hero .btn--primary {
		position: relative;
		overflow: hidden;
		background: var(--paper);
		color: var(--green-deep);
		border-color: var(--paper);
	}

	/* Balayage lumineux au survol */
	.hero .btn--primary::after {
		content: "";
		position: absolute;
		inset: 0 auto 0 -40%;
		width: 40%;
		background: linear-gradient(90deg, transparent, rgba(15, 138, 77, 0.22), transparent);
		transform: skewX(-20deg);
		transition: left var(--dur-slow) var(--ease);
	}

	.hero .btn--primary:hover {
		background: #ffffff;
	}

	.hero .btn--primary:hover::after {
		left: 120%;
	}

	.btn--ghost {
		background: transparent;
		color: var(--fg-on-green);
		border-color: rgba(255, 255, 255, 0.4);
	}

	.btn--ghost:hover {
		background: rgba(255, 255, 255, 0.12);
	}

	/* Panneau « trace » (aperçu produit) */
	.panel {
		overflow: hidden;
		border: 1px solid rgba(255, 255, 255, 0.24);
		border-radius: var(--radius-lg);
		background: var(--green-deep);
	}

	.panel__head {
		padding: 0.7rem 1rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.16);
		font-family: var(--font-mono);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--muted-on-green);
	}

	.panel__row {
		display: grid;
		grid-template-columns: 3rem 1fr auto;
		align-items: center;
		gap: 0.75rem;
		padding: 0.7rem 1rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		font-size: 0.9rem;
	}

	.panel__rule {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--accent);
	}

	.panel__cf {
		font-family: var(--font-mono);
		font-size: 12px;
		color: var(--muted-on-green);
	}

	.panel__result {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem;
	}

	.panel__result-name {
		font-family: var(--font-display);
		font-stretch: 82%;
		font-weight: 600;
		text-transform: uppercase;
	}

	.panel__result-sev {
		font-family: var(--font-mono);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--accent);
	}

	/* Entrée échelonnée des lignes du panneau */
	.panel__row,
	.panel__result {
		animation: row-in var(--dur-slow) var(--ease-out) both;
	}

	.panel__row:nth-child(2) { animation-delay: 80ms; }
	.panel__row:nth-child(3) { animation-delay: 160ms; }
	.panel__row:nth-child(4) { animation-delay: 240ms; }
	.panel__result { animation-delay: 360ms; }

	@keyframes row-in {
		from {
			opacity: 0;
			transform: translateY(6px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}

	/* ── Stats ────────────────────────────────────────────────────────── */
	.stats-band {
		background: var(--paper);
		border-bottom: 1px solid var(--line-ink);
	}

	.stats {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
	}

	.stats > div {
		padding: 1.5rem 1rem;
		border-right: 1px solid var(--line-ink);
	}

	.stats > div:last-child {
		border-right: none;
	}

	.stat-value {
		display: block;
		font-family: var(--font-display);
		font-stretch: 78%;
		font-weight: 600;
		font-size: 2.2rem;
		line-height: 1;
		color: var(--ink);
		font-variant-numeric: tabular-nums;
	}

	.stat-label {
		display: block;
		margin-top: 0.4rem;
		font-family: var(--font-mono);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted-ink);
	}

	/* ── Sections ─────────────────────────────────────────────────────── */
	.section {
		padding: clamp(3rem, 6vw, 5rem) 0;
	}

	.section--muted {
		background: var(--bg-subtle);
		border-top: 1px solid var(--line-ink);
		border-bottom: 1px solid var(--line-ink);
	}

	.two-col {
		display: grid;
		grid-template-columns: minmax(0, 0.75fr) minmax(0, 1.6fr);
		gap: 1.5rem 4rem;
		align-items: start;
	}

	.col-head h2 {
		margin: 0;
	}

	.col-body p {
		max-width: 68ch;
		margin: 0 0 1rem;
		color: var(--text-secondary);
	}

	.facts {
		margin: 0;
	}

	.facts > div {
		display: grid;
		grid-template-columns: 15rem 1fr;
		gap: 1rem;
		padding: 0.9rem 0;
		border-bottom: 1px solid var(--line-ink);
		transition: padding-left var(--dur) var(--ease);
	}

	.facts > div:hover {
		padding-left: 0.4rem;
	}

	.facts > div:first-child {
		border-top: 1px solid var(--line-ink);
	}

	.facts dt {
		font-family: var(--font-mono);
		font-size: 12px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--ink);
	}

	.facts dd {
		margin: 0;
		color: var(--text-secondary);
	}

	.steps {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
	}

	.steps li {
		display: grid;
		grid-template-columns: 2.5rem 1fr;
		gap: 1rem;
		padding: 1rem 0;
		border-bottom: 1px solid var(--line-ink);
	}

	.steps li:first-child {
		border-top: 1px solid var(--line-ink);
	}

	.num {
		font-family: var(--font-display);
		font-stretch: 78%;
		font-weight: 600;
		font-size: 1.4rem;
		color: var(--green);
		line-height: 1;
	}

	.steps h3 {
		margin: 0 0 0.2rem;
		font-size: 1.05rem;
	}

	.steps p {
		margin: 0;
		color: var(--text-secondary);
		font-size: 0.95rem;
	}

	/* ── CTA ──────────────────────────────────────────────────────────── */
	.cta-band {
		background: var(--green-deep);
		color: var(--fg-on-green);
	}

	.cta-band__inner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 2rem;
		padding-top: var(--s6);
		padding-bottom: var(--s6);
	}

	.cta-band h2 {
		margin: 0 0 0.3rem;
		color: var(--fg-on-green);
	}

	.cta-band p {
		margin: 0;
		color: var(--muted-on-green);
	}

	.cta-band .btn--primary {
		background: var(--green);
		color: #ffffff;
		border-color: var(--green);
	}

	.cta-band .btn--primary:hover {
		background: var(--green-hover);
	}

	/* ── Footer ───────────────────────────────────────────────────────── */
	.footer {
		background: var(--ink);
		color: rgba(243, 248, 244, 0.7);
	}

	.footer .wrap {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
		padding-top: 1.75rem;
		padding-bottom: 1.75rem;
	}

	.disclaimer {
		max-width: 720px;
		margin: 0;
		font-size: 0.8rem;
	}

	.disclaimer strong {
		color: var(--fg-on-green);
	}

	.copyright {
		margin: 0;
		font-family: var(--font-mono);
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: rgba(243, 248, 244, 0.55);
	}

	@media (max-width: 860px) {
		.hero__grid,
		.two-col {
			grid-template-columns: 1fr;
			gap: 1.5rem;
		}

		.facts > div {
			grid-template-columns: 1fr;
			gap: 0.2rem;
		}

		.stats {
			grid-template-columns: repeat(2, 1fr);
		}

		.stats > div:nth-child(2) {
			border-right: none;
		}

		.stats > div:nth-child(1),
		.stats > div:nth-child(2) {
			border-bottom: 1px solid var(--line-ink);
		}
	}
</style>
