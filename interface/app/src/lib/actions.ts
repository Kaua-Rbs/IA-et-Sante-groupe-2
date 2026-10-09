/** Actions Svelte partagées : révélation au scroll et compteur animé. */

function prefersReduced(): boolean {
    return (
        typeof window === 'undefined' ||
        window.matchMedia('(prefers-reduced-motion: reduce)').matches
    );
}

export function reveal(node: HTMLElement) {
    if (prefersReduced()) return;
    node.classList.add('reveal');
    const io = new IntersectionObserver(
        (entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    node.classList.add('is-visible');
                    io.unobserve(node);
                }
            }
        },
        { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );
    io.observe(node);
    return { destroy: () => io.disconnect() };
}

const formatCount = new Intl.NumberFormat('fr-FR');

export function count(node: HTMLElement) {
    if (prefersReduced()) return;
    const values = Array.from(node.querySelectorAll<HTMLElement>('[data-count]'));
    const run = () => {
        for (const el of values) {
            const target = Number(el.dataset.count ?? '0');
            const start = performance.now();
            const dur = 900;
            const tick = (now: number) => {
                const t = Math.min(1, (now - start) / dur);
                const eased = 1 - Math.pow(1 - t, 3);
                el.textContent = formatCount.format(Math.round(target * eased));
                if (t < 1) requestAnimationFrame(tick);
                else el.textContent = formatCount.format(target);
            };
            requestAnimationFrame(tick);
        }
    };
    const io = new IntersectionObserver(
        (entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    run();
                    io.disconnect();
                }
            }
        },
        { threshold: 0.4 }
    );
    io.observe(node);
    return { destroy: () => io.disconnect() };
}
