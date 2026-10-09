<script lang="ts">
    import { page } from '$app/state';
    import { goto } from '$app/navigation';
    import './header.css';

    import type { SessionUser } from '#lib/types.ts';

    interface Props {
        user?: SessionUser | null;
        /** Aligner sur la colonne de la landing (--max-w) plutôt que sur celle des pages outil */
        narrow?: boolean;
    }

    let { user = null, narrow = false }: Props = $props();

    // Fonction pour déterminer la page active (ajoute la classe "active")
    const actif = (path: string) =>
        (path === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(path)) ? "active" : "";

    let menuOpen = $state(false);
    let dropdownOpen = $state(false);

    function toggleMenu() {
        menuOpen = !menuOpen;
    }

    function toggleDropdown(e: Event) {
        const target = e.target as HTMLElement;
        if (target.closest('#btn-login')) {
            return; // Laisse le lien naviguer
        }
        dropdownOpen = !dropdownOpen;
    }

    $effect(() => {
        // Fermer les menus lors d'un changement de page
        page.url.href;
        menuOpen = false;
        dropdownOpen = false;
    });

    // Barre de progression du défilement, en bas de l'en-tête.
    let progress = $state(0);

    $effect(() => {
        const measure = () => {
            const el = document.documentElement;
            const max = el.scrollHeight - el.clientHeight;
            progress = max > 0 ? el.scrollTop / max : 0;
        };
        measure();
        window.addEventListener('scroll', measure, { passive: true });
        window.addEventListener('resize', measure);
        return () => {
            window.removeEventListener('scroll', measure);
            window.removeEventListener('resize', measure);
        };
    });
</script>

<header class:header--narrow={narrow}>
    <div class="title">
        <a class="brand" href="/" title="Keep Your Surgeries Timelies">
            <img src="/img/logo-clair.png" alt="" width="28" height="28" />
            KYST
        </a>
    </div>
    <div class="header-right" aria-label="Toggle menu">
        <button id="hamburger" aria-label="Ouvrir le menu" aria-expanded={menuOpen} onclick={toggleMenu} class:active={menuOpen}>
            <span></span>
            <span></span>
            <span></span>
        </button>

        <nav>
            <ul id="tabs" class:open={menuOpen}>
                <li><a href="/" class={actif('/')}>{user ? 'Tableau de bord' : 'Accueil'}</a></li>
                {#if user?.isStaff}
                    <li><a href="/requests" class={actif('/requests')}>Demandes</a></li>
                {/if}
                {#if user}
                    <li><a href="/planning" class={actif('/planning')}>Bloc</a></li>
                    <li><a href="/beds" class={actif('/beds')}>Lits</a></li>
                {/if}
                {#if user?.canPlan}
                    <li><a href="/resources" class={actif('/resources')}>Ressources</a></li>
                {/if}
            </ul>
        </nav>

        {#if user}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div class="button_with_icon" class:open={dropdownOpen} onclick={toggleDropdown}>
                <button type="button" id="btn-login" onclick={() => goto('/account/users/me')}>{user.displayName}</button>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" style="cursor:pointer;"><!--!Font Awesome Free v7.2.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M297.4 438.6C309.9 451.1 330.2 451.1 342.7 438.6L502.7 278.6C515.2 266.1 515.2 245.8 502.7 233.3C490.2 220.8 469.9 220.8 457.4 233.3L320 370.7L182.6 233.4C170.1 220.9 149.8 220.9 137.3 233.4C124.8 245.9 124.8 266.2 137.3 278.7L297.3 438.7z"/></svg>
                <ul>
                    <li>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.2.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M320 312C386.3 312 440 258.3 440 192C440 125.7 386.3 72 320 72C253.7 72 200 125.7 200 192C200 258.3 253.7 312 320 312zM290.3 368C191.8 368 112 447.8 112 546.3C112 562.7 125.3 576 141.7 576L498.3 576C514.7 576 528 562.7 528 546.3C528 447.8 448.2 368 349.7 368L290.3 368z"/></svg>
                        <a href="/account/users/me">Compte</a>
                    </li>
                    {#if user.admin}
                    <li>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.2.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M259.1 73.5C262.1 58.7 275.2 48 290.4 48L350.2 48C365.4 48 378.5 58.7 381.5 73.5L396 143.5C410.1 149.5 423.3 157.2 435.3 166.3L503.1 143.8C517.5 139 533.3 145 540.9 158.2L570.8 210C578.4 223.2 575.7 239.8 564.3 249.9L511 297.3C511.9 304.7 512.3 312.3 512.3 320C512.3 327.7 511.8 335.3 511 342.7L564.4 390.2C575.8 400.3 578.4 417 570.9 430.1L541 481.9C533.4 495 517.6 501.1 503.2 496.3L435.4 473.8C423.3 482.9 410.1 490.5 396.1 496.6L381.7 566.5C378.6 581.4 365.5 592 350.4 592L290.6 592C275.4 592 262.3 581.3 259.3 566.5L244.9 496.6C230.8 490.6 217.7 482.9 205.6 473.8L137.5 496.3C123.1 501.1 107.3 495.1 99.7 481.9L69.8 430.1C62.2 416.9 64.9 400.3 76.3 390.2L129.7 342.7C128.8 335.3 128.4 327.7 128.4 320C128.4 312.3 128.9 304.7 129.7 297.3L76.3 249.8C64.9 239.7 62.3 223 69.8 209.9L99.7 158.1C107.3 144.9 123.1 138.9 137.5 143.7L205.3 166.2C217.4 157.1 230.6 149.5 244.6 143.4L259.1 73.5zM320.3 400C364.5 399.8 400.2 363.9 400 319.7C399.8 275.5 363.9 239.8 319.7 240C275.5 240.2 239.8 276.1 240 320.3C240.2 364.5 276.1 400.2 320.3 400z"/></svg>
                        <a href="/account/users">Administration</a>
                    </li>
                    {/if}

                    <li>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640"><!--!Font Awesome Free v7.2.0 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2026 Fonticons, Inc.--><path d="M384 128L448 128L448 544C448 561.7 462.3 576 480 576L512 576C529.7 576 544 561.7 544 544C544 526.3 529.7 512 512 512L512 128C512 92.7 483.3 64 448 64L352 64L352 64L192 64C156.7 64 128 92.7 128 128L128 512C110.3 512 96 526.3 96 544C96 561.7 110.3 576 128 576L352 576C369.7 576 384 561.7 384 544L384 128zM256 320C256 302.3 270.3 288 288 288C305.7 288 320 302.3 320 320C320 337.7 305.7 352 288 352C270.3 352 256 337.7 256 320z"/></svg>
                        <!-- Formulaire de déconnexion utilisant les actions de SvelteKit -->
                        <form action="/account/logout" method="POST">
                            <button type="submit" class="logout-btn">Se déconnecter</button>
                        </form>
                    </li>
                </ul>
            </div>
        {:else}
            <a href="/account/login">
                <button type="button" id="btn-login">Se connecter</button>
            </a>
        {/if}
    </div>
    <span class="progress" style="transform: scaleX({progress})"></span>
</header>


