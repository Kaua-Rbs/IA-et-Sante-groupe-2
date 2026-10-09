<script lang="ts">
	// Page d'accueil publique de KYST (visiteurs non connectés).
	// Le parcours patient défile dans une scène SVG fixe : chaque « pièce » du monde fait
	// 1000 unités de haut, et la caméra (viewBox) descend d'une pièce à l'autre au scroll.
	import { onMount } from 'svelte';
	import { count, reveal } from '#lib/actions.ts';
	import logo from '#lib/assets/favicon.svg';

	type Pose = 'stand' | 'sit' | 'lie';

	const scenes: { label: string; title: string; lede: string; pose: Pose }[] = [
		{
			label: 'Consultation',
			title: 'Deux dates proposées en consultation',
			lede:
				"En consultation, le chirurgien saisit la demande. KYST estime le temps en salle et la durée du séjour, puis propose deux dates où une vacation de la spécialité et un lit sont libres. Le chirurgien choisit.",
			pose: 'stand'
		},
		{
			label: 'Admission',
			title: 'Le lit est réservé dès la confirmation',
			lede:
				"Le lit est bloqué pour toute la durée de séjour prévue. Si la place a été prise entre la proposition et la confirmation, KYST le détecte et repropose des dates.",
			pose: 'sit'
		},
		{
			label: 'Arrivée au bloc',
			title: 'Une vacation de la bonne spécialité',
			lede:
				"L'intervention est placée dans une vacation compatible avec la spécialité du chirurgien, d'après le temps d'occupation de salle prédit : de l'entrée à la sortie, installation et anesthésie comprises.",
			pose: 'lie'
		},
		{
			label: 'Intervention',
			title: '10 % de chaque vacation reste libre',
			lede:
				"Une part de chaque vacation n'est jamais programmée, pour absorber les urgences et les dépassements. Une date qui l'entamerait n'est pas proposée.",
			pose: 'lie'
		},
		{
			label: 'Réveil — SSPI',
			title: 'Ambulatoire ou hospitalisation',
			lede:
				"La prédiction indique aussi si le patient rentre le soir même. Selon le cas, KYST cherche une place en unité ambulatoire ou un lit d'hospitalisation conventionnelle.",
			pose: 'sit'
		},
		{
			label: 'Sortie & suivi',
			title: 'Les durées réelles reviennent dans KYST',
			lede:
				"Après l'intervention, on saisit le temps réellement passé en salle et la durée effective du séjour. L'écart avec la prédiction est suivi sur le tableau de bord.",
			pose: 'sit'
		}
	];

	const HERO_TITLE = 'La bonne date, pour le bloc et pour les lits';
	const N = scenes.length;
	const pad = (i: number) => String(i + 1).padStart(2, '0');

	// Géométrie du monde SVG (unités du viewBox)
	const WORLD_W = 1600;
	const ROOM_H = 1000;
	const WORLD_H = N * ROOM_H;
	const SPOT_X = 620;
	// Plage de scroll, dans chaque segment, pendant laquelle la caméra se déplace
	const HOLD_A = 0.28;
	const HOLD_B = 0.72;
	// Point d'appui de chaque pose (pieds ou bassin) dans son repère local
	const POSE_ORIGIN: Record<Pose, { ox: number; oy: number }> = {
		stand: { ox: 60, oy: 170 },
		sit: { ox: 0, oy: 0 },
		lie: { ox: 178, oy: 0 }
	};

	let scrolly: HTMLElement;
	let stage: HTMLElement;
	let world: SVGSVGElement;
	let patient: SVGGElement;

	let enhanced = $state(false);
	let staticMode = $state(false);
	let menuOpen = $state(false);
	let progress = $state(0);

	// Scène active (rail, pose) et scène affichée dans le panneau (décalée pour le fondu)
	let active = $state(0);
	let shown = $state(0);
	let switching = $state(false);
	let scene = $derived(scenes[shown]);

	let viewH = 900;
	let maxCam = WORLD_H - viewH;
	let switchTimer: ReturnType<typeof setTimeout> | undefined;

	const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

	function hold(f: number) {
		if (f <= HOLD_A) return 0;
		if (f >= HOLD_B) return 1;
		const x = (f - HOLD_A) / (HOLD_B - HOLD_A);
		return x * x * (3 - 2 * x);
	}

	// Le patient s'efface pendant le trajet de la caméra
	function fade(f: number) {
		if (f <= HOLD_A || f >= HOLD_B) return 1;
		const x = (f - HOLD_A) / (HOLD_B - HOLD_A);
		return 1 - Math.sin(x * Math.PI);
	}

	function setActive(i: number) {
		if (i === active) return;
		active = i;
		switching = true;
		clearTimeout(switchTimer);
		switchTimer = setTimeout(() => {
			shown = i;
			switching = false;
		}, 260);
	}

	function resize() {
		const rect = stage.getBoundingClientRect();
		if (!rect.height || !rect.width) return;
		viewH = clamp(WORLD_W * (rect.height / rect.width), 700, 1000);
		maxCam = Math.max(0, WORLD_H - viewH);
	}

	function update() {
		const rect = scrolly.getBoundingClientRect();
		const total = scrolly.offsetHeight - window.innerHeight;
		const p = total > 0 ? clamp(-rect.top / total, 0, 1) : 0;

		const seg = clamp(p * (N - 1), 0, N - 1);
		let k = Math.floor(seg);
		let f = seg - k;
		if (k >= N - 1) {
			k = N - 2;
			f = 1;
		}
		const pos = k + hold(f);
		const camY = clamp(500 + pos * ROOM_H - viewH / 2, 0, maxCam);
		world.setAttribute('viewBox', `0 ${camY.toFixed(1)} ${WORLD_W} ${viewH.toFixed(0)}`);

		const i = clamp(Math.round(pos), 0, N - 1);
		setActive(i);

		const origin = POSE_ORIGIN[scenes[i].pose];
		const contactY = camY + viewH / 2 + 180;
		patient.setAttribute('transform', `translate(${SPOT_X - origin.ox} ${contactY - origin.oy})`);
		patient.style.opacity = fade(f).toFixed(3);
	}

	function goTo(i: number) {
		const span = scrolly.offsetHeight - window.innerHeight;
		window.scrollTo({ top: scrolly.offsetTop + (i / (N - 1)) * span, behavior: 'smooth' });
	}

	onMount(() => {
		const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		let ticking = false;

		const applyMode = () => {
			staticMode = reduceMotion || window.innerWidth <= 720;
		};

		const onScroll = () => {
			if (ticking) return;
			ticking = true;
			requestAnimationFrame(() => {
				const doc = document.documentElement;
				const max = doc.scrollHeight - doc.clientHeight;
				progress = max > 0 ? doc.scrollTop / max : 0;
				if (!staticMode) update();
				ticking = false;
			});
		};

		const onResize = () => {
			applyMode();
			if (!staticMode) {
				resize();
				update();
			}
			onScroll();
		};

		applyMode();
		enhanced = true;
		// Attendre que la section ait pris sa hauteur de scroll avant de mesurer
		requestAnimationFrame(onResize);

		window.addEventListener('scroll', onScroll, { passive: true });
		window.addEventListener('resize', onResize);
		return () => {
			clearTimeout(switchTimer);
			window.removeEventListener('scroll', onScroll);
			window.removeEventListener('resize', onResize);
		};
	});
</script>

<div class="landing">
	<div class="lnav">
		<nav class="lnav__inner" aria-label="Navigation principale">
			<div class="lnav__side">
				<a href="#parcours">Parcours</a>
				<a href="#methode">Méthode</a>
			</div>

			<a class="lnav__brand" href="/" title="Keep Your Surgeries Timelies">
				<span class="lnav__mark"><img src={logo} alt="" width="26" height="26" />KYST</span>
				<span class="lnav__meta">// keep your surgeries timelies</span>
			</a>

			<div class="lnav__side lnav__side--right">
				<a href="/account/register">Demander un accès</a>
				<a class="lbtn lbtn--outline" href="/account/login">Connexion</a>
			</div>

			<button
				class="lnav__burger"
				type="button"
				aria-label={menuOpen ? 'Fermer le menu' : 'Ouvrir le menu'}
				aria-expanded={menuOpen}
				aria-controls="lnav-mobile"
				onclick={() => (menuOpen = !menuOpen)}
			>
				<span></span><span></span><span></span>
			</button>
		</nav>

		<div class="lnav__mobile" id="lnav-mobile" hidden={!menuOpen}>
			<a href="#parcours" onclick={() => (menuOpen = false)}>Parcours</a>
			<a href="#methode" onclick={() => (menuOpen = false)}>Méthode</a>
			<a href="/account/register">Demander un accès</a>
			<a class="lbtn lbtn--outline" href="/account/login">Connexion</a>
		</div>

		<span class="lnav__progress" style="transform: scaleX({progress})" aria-hidden="true"></span>
	</div>

	<section
		class="scrolly"
		class:is-enhanced={enhanced}
		class:is-static={staticMode}
		id="parcours"
		aria-label="Parcours patient"
		bind:this={scrolly}
	>
		<h2 class="sr-only">Le parcours patient, étape par étape</h2>

		<div class="stage" bind:this={stage}>
			<svg
				class="world"
				viewBox="0 0 1600 900"
				preserveAspectRatio="xMidYMid meet"
				aria-hidden="true"
				bind:this={world}
			>
				<defs>
					<g id="body">
						<circle class="fillg" cx="60" cy="36" r="25" />
						<path class="fillg" d="M20 100 Q60 76 100 100 L100 198 Q60 214 20 198 Z" />
						<path class="strokeg" stroke-width="16" stroke-linecap="round" d="M26 106 Q10 152 20 194" />
						<path class="strokeg" stroke-width="16" stroke-linecap="round" d="M94 106 Q110 152 100 194" />
						<path class="strokeg" stroke-width="19" stroke-linecap="round" d="M47 198 L43 290" />
						<path class="strokeg" stroke-width="19" stroke-linecap="round" d="M73 198 L77 290" />
					</g>
					<g id="cap-beanie"><path class="filli" d="M36 22 A24 22 0 0 1 84 22 Q60 34 36 22 Z" /></g>
					<g id="cap-surgical"><path class="filli" d="M38 26 A23 20 0 0 1 82 26 Q60 36 38 26 Z" /></g>
					<g id="mask"><path class="filli" d="M45 40 Q60 52 75 40 L73 55 Q60 63 47 55 Z" /></g>
					<g id="stetho">
						<path class="strokei" stroke-width="4" fill="none" d="M52 84 Q60 106 68 84" />
						<circle class="filli" cx="68" cy="106" r="4" />
					</g>
					<g id="clipboard">
						<rect class="filli" x="92" y="152" width="26" height="36" rx="3" />
						<rect class="fillacc" x="97" y="160" width="16" height="4" />
						<rect class="fillacc" x="97" y="168" width="16" height="4" />
						<rect class="fillacc" x="97" y="176" width="16" height="4" />
					</g>
					<g id="folder">
						<path class="fillacc" d="M86 158 h24 a4 4 0 0 1 4 4 v30 a4 4 0 0 1 -4 4 h-24 z" />
						<path class="filli" d="M86 158 h10 l5 7 h-15 z" />
					</g>
					<g id="gown"><path class="fillg2" d="M16 102 Q60 78 104 102 L96 212 Q60 226 24 212 Z" /></g>
					<g id="coat">
						<path class="coatfill" d="M18 104 Q60 80 102 104 L94 214 Q60 228 26 214 Z" />
						<path class="coatline" d="M18 104 Q60 80 102 104 L94 214 Q60 228 26 214 Z" />
						<path class="coatline" d="M60 108 L60 222" />
					</g>
				</defs>

				{#each scenes as _, i}
					{#if i > 0}<line class="sep" x1="0" y1={i * 1000} x2="1600" y2={i * 1000} />{/if}
					<line class="floor" x1="0" y1={i * 1000 + 800} x2="1600" y2={i * 1000 + 800} />
					<text class="ghost" x="800" y={i * 1000 + 600}>{pad(i)}</text>
					<text class="room-label" x="1530" y={i * 1000 + 120} text-anchor="end">
						{pad(i)} · {scenes[i].label.toUpperCase()}
					</text>
				{/each}

				<!-- 01 · Consultation : bureau du chirurgien -->
				<rect class="filli" x="1200" y="640" width="200" height="160" rx="6" />
				<rect class="filli" x="1188" y="626" width="224" height="18" rx="5" />
				<rect class="fillacc" x="1252" y="682" width="76" height="7" rx="3" />
				<rect class="fillacc" x="1252" y="700" width="48" height="7" rx="3" />
				<g class="cast" transform="translate(940 510)">
					<use href="#body" /><use href="#coat" /><use href="#stetho" />
				</g>

				<!-- 02 · Admission : lit et perfusion -->
				<rect class="filli" x="340" y="1560" width="26" height="240" rx="8" />
				<rect class="filli" x="340" y="1680" width="300" height="120" rx="10" />
				<rect class="fillacc" x="368" y="1656" width="100" height="18" rx="8" />
				<line class="strokei" stroke-width="4" x1="820" y1="1500" x2="820" y2="1800" />
				<rect class="fillacc" x="802" y="1512" width="36" height="50" rx="7" />
				<g class="cast" transform="translate(1060 1510)">
					<use href="#body" /><use href="#cap-beanie" /><use href="#clipboard" />
				</g>

				<!-- 03 · Arrivée au bloc : brancard -->
				<rect class="filli" x="400" y="2560" width="22" height="240" rx="8" />
				<rect class="filli" x="400" y="2680" width="400" height="120" rx="10" />
				<circle class="strokei" stroke-width="5" fill="none" cx="440" cy="2782" r="18" />
				<circle class="strokei" stroke-width="5" fill="none" cx="760" cy="2782" r="18" />
				<rect class="fillacc" x="428" y="2656" width="110" height="18" rx="8" />
				<g class="cast" transform="translate(940 2510)">
					<use href="#body" /><use href="#cap-surgical" /><use href="#mask" />
				</g>

				<!-- 04 · Intervention : table et scope -->
				<rect class="filli" x="400" y="3680" width="400" height="40" rx="8" />
				<rect class="filli" x="440" y="3720" width="12" height="80" />
				<rect class="filli" x="760" y="3720" width="12" height="80" />
				<rect class="filli" x="1280" y="3560" width="72" height="56" rx="6" />
				<path class="strokeacc" stroke-width="3" fill="none" d="M1288 3596 l10 -16 l8 24 l9 -32 l10 24 h16" />
				<g class="cast" transform="translate(990 3510)">
					<use href="#body" /><use href="#cap-surgical" /><use href="#mask" /><use href="#gown" />
				</g>

				<!-- 05 · Réveil : lit de SSPI et moniteur -->
				<rect class="filli" x="340" y="4560" width="26" height="240" rx="8" />
				<rect class="filli" x="340" y="4680" width="300" height="120" rx="10" />
				<rect class="fillacc" x="368" y="4656" width="100" height="18" rx="8" />
				<rect class="filli" x="1280" y="4560" width="68" height="52" rx="6" />
				<path class="strokeacc" stroke-width="3" fill="none" d="M1286 4592 l9 -14 l7 22 l8 -30 l9 20 h18" />
				<g class="cast" transform="translate(1060 4510)">
					<use href="#body" /><use href="#cap-beanie" /><use href="#clipboard" />
				</g>

				<!-- 06 · Sortie : chaise et bureau -->
				<rect class="filli" x="574" y="5556" width="12" height="124" rx="4" />
				<rect class="filli" x="574" y="5680" width="92" height="16" rx="4" />
				<rect class="filli" x="584" y="5696" width="8" height="104" rx="3" />
				<rect class="filli" x="648" y="5696" width="8" height="104" rx="3" />
				<rect class="filli" x="1200" y="5640" width="200" height="160" rx="6" />
				<rect class="filli" x="1188" y="5626" width="224" height="18" rx="5" />
				<rect class="fillacc" x="1252" y="5682" width="80" height="7" rx="3" />
				<g class="cast" transform="translate(940 5510)">
					<use href="#body" /><use href="#coat" /><use href="#stetho" /><use href="#folder" />
				</g>

				<g class="cast patient" transform="translate(560 510)" bind:this={patient}>
					<g class="pose" class:is-on={scenes[active].pose === 'stand'}>
						<use href="#body" />
					</g>
					<g class="pose" class:is-on={scenes[active].pose === 'sit'}>
						<path class="strokeg" stroke-width="22" stroke-linecap="round" d="M0 -8 L58 -8" />
						<path class="strokeg" stroke-width="20" stroke-linecap="round" d="M58 -8 L58 104" />
						<ellipse class="fillg" cx="58" cy="110" rx="16" ry="9" />
						<path class="fillg" d="M-24 -124 Q0 -136 24 -124 L24 -6 Q0 4 -24 -6 Z" />
						<circle class="fillg" cx="0" cy="-146" r="24" />
					</g>
					<g class="pose" class:is-on={scenes[active].pose === 'lie'}>
						<circle class="fillg" cx="30" cy="-24" r="24" />
						<rect class="fillg" x="54" y="-52" width="130" height="52" rx="24" />
						<rect class="fillg" x="180" y="-44" width="150" height="44" rx="22" />
						<path class="strokeg" stroke-width="14" stroke-linecap="round" d="M120 -40 Q150 -64 180 -44" />
						<ellipse class="fillg" cx="338" cy="-18" rx="13" ry="16" />
					</g>
				</g>
			</svg>

			<div class="overlay">
				<div class="overlay__panel" class:is-hero={shown === 0} class:is-switching={switching}>
					<p class="eyebrow">
						{shown === 0 ? 'KYST · Keep Your Surgeries Timelies' : `${pad(shown)} / ${pad(N - 1)} · ${scene.label}`}
					</p>
					{#if shown === 0}
						<h1 class="overlay__title">{HERO_TITLE}</h1>
					{:else}
						<p class="overlay__title" role="heading" aria-level="3">{scene.title}</p>
					{/if}
					<p class="overlay__lede">{scene.lede}</p>
					{#if shown === 0}
						<div class="overlay__actions">
							<a class="lbtn lbtn--primary" href="/account/login">Se connecter <span aria-hidden="true">→</span></a>
							<a class="lbtn lbtn--ghost" href="#methode">La méthode</a>
						</div>
					{/if}
				</div>
			</div>

			<div class="rail" aria-label="Étapes du parcours">
				{#each scenes as s, i}
					<button
						class="rail__dot"
						class:is-active={i === active}
						type="button"
						aria-label="Étape {i + 1} : {s.label}"
						aria-current={i === active ? 'step' : undefined}
						onclick={() => goTo(i)}
					>
						<i></i><span>{pad(i)}</span>
					</button>
				{/each}
			</div>

			<p class="sr-only" aria-live="polite">{pad(active)}. {scenes[active].label} : {scenes[active].title}.</p>
		</div>

		<div class="scenes-fallback">
			<!-- La scène est masquée en mode statique : l'accroche passe ici -->
			<div class="fallback-intro">
				<p class="eyebrow">KYST · Keep Your Surgeries Timelies</p>
				<h1>{HERO_TITLE}</h1>
				<p>
					KYST propose des dates d'intervention compatibles avec le bloc opératoire et les lits.
					Le chirurgien garde la décision.
				</p>
				<a class="lbtn lbtn--primary" href="/account/login">Se connecter <span aria-hidden="true">→</span></a>
			</div>
			<ol>
				{#each scenes as s, i}
					<li>
						<span>{pad(i)} · {s.label}</span>
						<h3>{s.title}</h3>
						<p>{s.lede}</p>
					</li>
				{/each}
			</ol>
		</div>
	</section>

	<section class="method" id="methode">
		<div class="wrap">
			<div class="section-head" use:reveal>
				<p class="eyebrow">Méthode</p>
				<h2>Flux tiré plutôt que flux poussé</h2>
				<p class="section-head__lede">
					Aujourd'hui, on fixe l'intervention d'après l'agenda du chirurgien, puis on cherche un
					lit. KYST fait l'inverse : il part de la capacité prévue du bloc et des services, et
					en déduit les dates possibles. Optimiser le bloc seul sature les lits, et l'inverse
					laisse des salles vides ; chaque proposition vérifie donc les deux.
				</p>
			</div>

			<div class="facts" use:count use:reveal>
				<div class="fact">
					<span class="fact__key">séjours étudiés</span>
					<span class="fact__val"><span data-count="14649">14&#8239;649</span></span>
					<span class="fact__note">dossiers chirurgicaux anonymisés, base des modèles de durée</span>
				</div>
				<div class="fact">
					<span class="fact__key">dates proposées</span>
					<span class="fact__val"><span data-count="2">2</span></span>
					<span class="fact__note">une date A et une alternative B, chacune avec ses raisons</span>
				</div>
				<div class="fact">
					<span class="fact__key">marge par vacation</span>
					<span class="fact__val"><span data-count="10">10</span><small>%</small></span>
					<span class="fact__note">jamais programmée, gardée pour les urgences et les retards</span>
				</div>
			</div>
		</div>
	</section>

	<section class="cta-band">
		<div class="wrap cta-band__inner" use:reveal>
			<div>
				<h2>Accès réservé aux équipes</h2>
				<p>
					Chirurgiens, secrétariats, cadres de bloc et gestionnaires de lits. Chaque compte est
					validé par un administrateur.
				</p>
			</div>
			<a class="lbtn lbtn--accent" href="/account/register">Demander un accès <span aria-hidden="true">→</span></a>
		</div>
	</section>

	<footer class="footer">
		<div class="wrap">
			<div class="footer__top">
				<div>
					<span class="footer__ghost" aria-hidden="true">KYST</span>
					<p class="footer__tagline">
						Programmation chirurgicale qui tient compte du bloc opératoire et des lits.
					</p>
				</div>
				<div class="footer__cols">
					<div>
						<h4>Application</h4>
						<a href="#parcours">Parcours</a>
						<a href="#methode">Méthode</a>
						<a href="/account/login">Connexion</a>
						<a href="/account/register">Demander un accès</a>
					</div>
					<div>
						<h4>Projet</h4>
						<a href="https://github.com/Kaua-Rbs/IA-et-Sante-groupe-2" rel="noopener">Code source</a>
						<a href="https://centralelille.fr/" rel="noopener">Centrale Lille</a>
					</div>
				</div>
			</div>
			<div class="footer__bottom">
				<p>
					Projet étudiant. Outil d'aide à la décision : il ne remplace pas le jugement clinique.
					Les prédictions actuelles sont des valeurs de démonstration.
				</p>
				<p class="footer__copy">© {new Date().getFullYear()} KYST</p>
			</div>
		</div>
	</footer>
</div>

<style>
	@property --angle {
		syntax: '<angle>';
		inherits: false;
		initial-value: 0deg;
	}

	.landing {
		--nav-h: 68px;
		--fg: var(--fg-on-green);
		--muted: var(--muted-on-green);
		--line-strong: rgba(243, 248, 244, 0.42);
		--line-ink-strong: rgba(6, 51, 31, 0.3);
		--accent-soft: #e4ff7a;
		--lgutter: clamp(1.25rem, 4vw, 4rem);

		background: var(--green-deep);
		color: var(--fg);
		font-size: clamp(15px, 0.4vw + 13px, 17px);
		overflow-x: clip;
	}

	.landing :global(::selection) {
		background: var(--accent);
		color: var(--ink);
	}

	h1,
	h2,
	h3,
	.overlay__title {
		font-family: var(--font-display);
		font-stretch: 78%;
		font-weight: 600;
		text-transform: uppercase;
		line-height: 0.98;
		letter-spacing: -0.02em;
		margin: 0;
	}

	h1 {
		font-weight: 700;
	}

	h2 {
		font-size: clamp(2rem, 4vw, 3.6rem);
	}

	h3 {
		font-size: clamp(1.2rem, 2vw, 1.6rem);
	}

	p {
		margin: 0;
	}

	a {
		color: inherit;
		text-decoration: none;
	}

	ol {
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.wrap {
		width: 100%;
		max-width: var(--max-w);
		margin-inline: auto;
		padding-inline: var(--lgutter);
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
		border: 0;
	}

	.eyebrow {
		font-family: var(--font-mono);
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.14em;
		color: var(--green);
		margin: 0 0 1.1rem;
	}

	/* ── Boutons ───────────────────────────────────────────────────────── */

	.lbtn {
		position: relative;
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.72rem 1.35rem;
		border: 1px solid transparent;
		border-radius: var(--radius-md);
		font-size: 0.78rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		white-space: nowrap;
		cursor: pointer;
		transition: background-color var(--dur) var(--ease), color var(--dur) var(--ease),
			border-color var(--dur) var(--ease);
	}

	.lbtn--primary {
		background: var(--green);
		border-color: var(--green);
		color: #fff;
	}

	.lbtn--primary:hover {
		background: var(--green-hover);
		border-color: var(--green-hover);
	}

	.lbtn--ghost {
		color: var(--ink);
		border-color: var(--line-ink-strong);
	}

	.lbtn--ghost:hover {
		background: rgba(6, 51, 31, 0.06);
	}

	.lbtn--accent {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--ink);
	}

	.lbtn--accent:hover {
		background: var(--accent-soft);
		border-color: var(--accent-soft);
	}

	.lbtn--outline {
		color: var(--fg);
		border-color: var(--line-strong);
	}

	/* Bordure lumineuse rotative au survol */
	.lbtn--outline::before {
		content: '';
		position: absolute;
		inset: 0;
		border-radius: inherit;
		padding: 1px;
		background: conic-gradient(from var(--angle), transparent 0 62%, var(--accent) 78%, transparent 100%);
		-webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
		-webkit-mask-composite: xor;
		mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
		mask-composite: exclude;
		opacity: 0;
		transition: opacity var(--dur) var(--ease);
	}

	.lbtn--outline:hover {
		border-color: transparent;
		color: #fff;
	}

	.lbtn--outline:hover::before {
		opacity: 1;
		animation: spin-border 2.23s linear infinite;
	}

	@keyframes spin-border {
		to {
			--angle: 360deg;
		}
	}

	/* ── Navigation ────────────────────────────────────────────────────── */

	.lnav {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		z-index: 60;
		background: var(--green);
		border-bottom: 0.5px solid var(--line);
	}

	.lnav__inner {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		align-items: center;
		height: var(--nav-h);
		max-width: var(--max-w);
		margin-inline: auto;
		padding-inline: var(--lgutter);
	}

	.lnav__side {
		display: flex;
		align-items: center;
		gap: clamp(1rem, 2vw, 2rem);
	}

	.lnav__side--right {
		justify-content: flex-end;
	}

	.lnav__side a:not(.lbtn) {
		position: relative;
		font-size: 0.82rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--muted);
		transition: color var(--dur) var(--ease);
	}

	.lnav__side a:not(.lbtn):hover {
		color: var(--fg);
	}

	.lnav__side a:not(.lbtn)::after {
		content: '';
		position: absolute;
		left: 0;
		right: 0;
		bottom: -0.35rem;
		height: 1px;
		background: var(--accent);
		transform: scaleX(0);
		transform-origin: left;
		transition: transform var(--dur) var(--ease);
	}

	.lnav__side a:not(.lbtn):hover::after {
		transform: scaleX(1);
	}

	.lnav__brand {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.28rem;
		line-height: 1;
	}

	.lnav__mark {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		font-family: var(--font-display);
		font-stretch: 72%;
		font-weight: 700;
		font-size: 1.5rem;
		color: var(--fg);
	}

	.lnav__mark img {
		border-radius: 6px;
		box-shadow: 0 0 0 1px var(--line-strong);
	}

	.lnav__meta {
		font-family: var(--font-mono);
		font-size: 0.58rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--muted);
	}

	.lnav__progress {
		position: absolute;
		left: 0;
		bottom: -0.5px;
		width: 100%;
		height: 1px;
		background: var(--accent);
		transform-origin: left;
	}

	.lnav__burger {
		display: none;
		justify-self: end;
		position: relative;
		width: 42px;
		height: 42px;
		padding: 0;
		border: 0.5px solid var(--line-strong);
		border-radius: var(--radius-sm);
		background: transparent;
		cursor: pointer;
	}

	.lnav__burger span {
		position: absolute;
		left: 11px;
		right: 11px;
		height: 1.5px;
		background: var(--fg);
		transition: transform var(--dur) var(--ease), opacity var(--dur) var(--ease);
	}

	.lnav__burger span:nth-child(1) {
		top: 15px;
	}

	.lnav__burger span:nth-child(2) {
		top: 20px;
	}

	.lnav__burger span:nth-child(3) {
		top: 25px;
	}

	.lnav__burger[aria-expanded='true'] span:nth-child(1) {
		transform: translateY(5px) rotate(45deg);
	}

	.lnav__burger[aria-expanded='true'] span:nth-child(2) {
		opacity: 0;
	}

	.lnav__burger[aria-expanded='true'] span:nth-child(3) {
		transform: translateY(-5px) rotate(-45deg);
	}

	.lnav__mobile {
		display: none;
		flex-direction: column;
		padding: 0.5rem var(--lgutter) 1.25rem;
		border-bottom: 0.5px solid var(--line);
		background: var(--green);
	}

	.lnav__mobile a {
		padding: 0.85rem 0;
		font-size: 0.95rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--fg);
		border-bottom: 0.5px solid var(--line);
	}

	.lnav__mobile .lbtn {
		justify-content: center;
		margin-top: 0.5rem;
		padding: 0.72rem 1.35rem;
		border-bottom: 1px solid var(--line-strong);
	}

	/* ── Parcours (scrollytelling) ─────────────────────────────────────── */

	.scrolly {
		position: relative;
		background: var(--paper);
	}

	.scrolly.is-enhanced {
		height: 1080vh;
	}

	.stage {
		position: relative;
		height: 100vh;
		overflow: hidden;
		background: var(--paper);
		color: var(--ink);
	}

	.is-enhanced .stage {
		position: sticky;
		top: 0;
	}

	.world {
		display: block;
		width: 100%;
		height: 100%;
	}

	.fillg {
		fill: var(--green);
	}

	.strokeg {
		fill: none;
		stroke: var(--green);
	}

	.filli {
		fill: var(--ink);
	}

	.strokei {
		fill: none;
		stroke: var(--ink);
	}

	.fillacc {
		fill: var(--accent);
	}

	.strokeacc {
		fill: none;
		stroke: var(--accent);
	}

	.fillg2 {
		fill: var(--green-deep);
	}

	.coatfill {
		fill: #e6efe3;
	}

	.coatline {
		fill: none;
		stroke: var(--ink);
		stroke-width: 2.5;
	}

	.floor {
		stroke: var(--line-ink-strong);
		stroke-width: 1.5;
	}

	.sep {
		stroke: var(--line-ink);
		stroke-width: 1;
		stroke-dasharray: 2 7;
	}

	.room-label {
		fill: var(--muted-ink);
		font-family: var(--font-mono);
		font-size: 20px;
		letter-spacing: 2.5px;
	}

	.ghost {
		fill: var(--ink);
		opacity: 0.05;
		font-family: var(--font-display);
		font-weight: 700;
		font-size: 220px;
		text-anchor: middle;
	}

	.patient {
		will-change: transform, opacity;
	}

	.pose {
		opacity: 0;
	}

	.pose.is-on {
		opacity: 1;
	}

	.cast {
		animation: idle 4.8s var(--ease) infinite;
	}

	@keyframes idle {
		50% {
			translate: 0 -4px;
		}
	}

	.overlay {
		position: absolute;
		inset: 0;
		z-index: 2;
		pointer-events: none;
	}

	.overlay__panel {
		position: absolute;
		top: calc(var(--nav-h) + 7vh);
		left: var(--lgutter);
		max-width: min(520px, 40vw);
		pointer-events: auto;
		transition: opacity 0.28s var(--ease), transform 0.28s var(--ease);
	}

	.overlay__panel.is-switching {
		opacity: 0;
		transform: translateY(8px);
	}

	.overlay__title {
		font-size: clamp(1.6rem, 3vw, 2.6rem);
		margin-bottom: 1rem;
	}

	.is-hero .overlay__title {
		font-size: clamp(2rem, 4.6vw, 4.2rem);
	}

	.overlay__lede {
		max-width: 40ch;
		color: var(--muted-ink);
	}

	.is-hero .overlay__lede {
		margin-bottom: 1.7rem;
	}

	.overlay__panel:not(.is-hero) .eyebrow {
		color: var(--muted-ink);
	}

	.overlay__actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.rail {
		position: absolute;
		left: 50%;
		bottom: 5vh;
		z-index: 3;
		display: flex;
		gap: clamp(0.75rem, 3vw, 2.5rem);
		transform: translateX(-50%);
	}

	/* Sans JavaScript, le rail ne peut pas faire défiler : on le masque */
	.scrolly:not(.is-enhanced) .rail {
		display: none;
	}

	.rail__dot {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		padding: 0;
		border: 0;
		background: none;
		cursor: pointer;
		color: var(--muted-ink);
		font-family: var(--font-mono);
		font-size: 0.62rem;
		letter-spacing: 0.08em;
		transition: color var(--dur) var(--ease);
	}

	.rail__dot i {
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: var(--paper);
		border: 1px solid var(--line-ink-strong);
		transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease),
			transform var(--dur) var(--ease);
	}

	.rail__dot:hover,
	.rail__dot.is-active {
		color: var(--ink);
	}

	.rail__dot.is-active i {
		background: var(--accent);
		border-color: var(--green);
		transform: scale(1.5);
	}

	/* Mobile et mouvement réduit : liste statique à la place de la scène */
	.scrolly.is-static {
		height: auto;
	}

	.scrolly.is-static .stage {
		display: none;
	}

	.scenes-fallback {
		display: none;
		flex-direction: column;
		max-width: var(--max-w);
		margin-inline: auto;
		padding: clamp(2rem, 6vw, 5rem) var(--lgutter);
		color: var(--ink);
	}

	.scrolly.is-static .scenes-fallback {
		display: flex;
		padding-top: calc(var(--nav-h) + clamp(1.5rem, 5vw, 4rem));
	}

	/* Sans JavaScript : la liste suit la première scène */
	.scrolly:not(.is-enhanced) .scenes-fallback {
		display: flex;
	}

	.fallback-intro {
		display: none;
		margin-bottom: 2.5rem;
	}

	.scrolly.is-static .fallback-intro {
		display: block;
	}

	.fallback-intro h1 {
		font-size: clamp(2rem, 9vw, 3rem);
		margin-bottom: 1rem;
	}

	.fallback-intro p:not(.eyebrow) {
		margin-bottom: 1.5rem;
		color: var(--muted-ink);
	}

	.scenes-fallback li {
		display: grid;
		gap: 0.5rem;
		max-width: none;
		padding: 1.5rem 0;
		border-bottom: 0.5px solid var(--line-ink);
	}

	.scenes-fallback li:first-child {
		border-top: 0.5px solid var(--line-ink);
	}

	.scenes-fallback li > span {
		font-family: var(--font-mono);
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--green);
	}

	.scenes-fallback li p {
		max-width: 60ch;
		color: var(--muted-ink);
	}

	/* ── Méthode ───────────────────────────────────────────────────────── */

	.method {
		padding-block: clamp(4rem, 8vw, 8rem);
		background: var(--paper);
		color: var(--ink);
		border-top: 0.5px solid var(--line-ink);
	}

	.section-head {
		max-width: 760px;
		margin-bottom: clamp(2.5rem, 5vw, 4rem);
	}

	.section-head h2 {
		margin-bottom: 1rem;
	}

	.section-head__lede {
		max-width: 60ch;
		color: var(--muted-ink);
	}

	.facts {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: clamp(1.5rem, 3vw, 3rem);
		padding-top: clamp(1.5rem, 3vw, 2.5rem);
		border-top: 0.5px solid var(--line-ink);
	}

	.fact {
		padding-left: clamp(1rem, 2vw, 1.75rem);
		border-left: 0.5px solid var(--line-ink);
	}

	.fact__key {
		display: block;
		margin-bottom: 0.6rem;
		font-family: var(--font-mono);
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--muted-ink);
	}

	.fact__val {
		display: flex;
		align-items: baseline;
		margin-bottom: 0.5rem;
		font-family: var(--font-display);
		font-stretch: 72%;
		font-weight: 700;
		font-size: clamp(2.4rem, 5vw, 4rem);
		line-height: 1;
		color: var(--green);
		font-variant-numeric: tabular-nums;
	}

	.fact__val small {
		font-size: 0.5em;
	}

	.fact__note {
		display: block;
		font-size: 0.88rem;
		color: var(--muted-ink);
	}

	/* ── Bandeau d'appel ───────────────────────────────────────────────── */

	.cta-band {
		background: var(--ink);
		color: var(--fg);
	}

	.cta-band__inner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 2rem;
		padding-block: clamp(3.5rem, 7vw, 6rem);
	}

	.cta-band h2 {
		margin-bottom: 0.6rem;
	}

	.cta-band p {
		max-width: 52ch;
		color: var(--muted);
	}

	/* ── Pied de page ──────────────────────────────────────────────────── */

	.footer {
		background: var(--ink);
		color: var(--muted);
		border-top: 0.5px solid var(--line);
	}

	.footer__top {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		gap: clamp(2rem, 6vw, 5rem);
		padding-block: clamp(3rem, 6vw, 5rem);
	}

	.footer__ghost {
		display: block;
		margin-bottom: 1rem;
		font-family: var(--font-display);
		font-stretch: 62%;
		font-weight: 700;
		font-size: clamp(4rem, 13vw, 11rem);
		line-height: 0.8;
		color: transparent;
		-webkit-text-stroke: 0.5px var(--line-strong);
	}

	.footer__tagline {
		max-width: 34ch;
		font-size: 0.92rem;
	}

	.footer__cols {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 2rem;
	}

	.footer__cols h4 {
		margin: 0 0 1rem;
		font-family: var(--font-mono);
		font-size: 0.66rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--fg);
	}

	.footer__cols a {
		display: block;
		padding: 0.3rem 0;
		font-size: 0.88rem;
		color: var(--muted);
	}

	.footer__cols a {
		transition: color var(--dur) var(--ease);
	}

	.footer__cols a:hover {
		color: var(--accent);
	}

	.footer__bottom {
		display: flex;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 1rem;
		padding-block: 1.6rem;
		border-top: 0.5px solid var(--line);
		font-size: 0.78rem;
	}

	.footer__bottom p:first-child {
		max-width: 70ch;
	}

	.footer__copy {
		font-family: var(--font-mono);
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	/* ── Responsive ────────────────────────────────────────────────────── */

	@media (max-width: 1080px) {
		.footer__top {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 900px) {
		.lnav__side {
			display: none;
		}

		.lnav__burger {
			display: block;
		}

		.lnav__inner {
			grid-template-columns: 1fr auto;
		}

		.lnav__brand {
			align-items: flex-start;
		}

		.lnav__mobile:not([hidden]) {
			display: flex;
		}

		.facts {
			grid-template-columns: 1fr;
		}

		.fact {
			padding: 1.25rem 0 0;
			border-left: 0;
			border-top: 0.5px solid var(--line-ink);
		}

		.fact:first-child {
			padding-top: 0;
			border-top: 0;
		}
	}

	@media (max-width: 720px) {
		.overlay__panel {
			max-width: min(560px, 82vw);
		}

		.overlay__lede {
			font-size: 0.92rem;
		}

		.rail {
			gap: 0.6rem;
		}

		.rail__dot span {
			display: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.cast,
		.lbtn--outline:hover::before {
			animation: none;
		}
	}
</style>
