# app — front SvelteKit de KYST

Pages de KYST, en SvelteKit et Svelte 5, avec du CSS écrit à la main. Le serveur SvelteKit gère la session (cookies HttpOnly) et est le seul à appeler l'API.

```bash
mise install      # version de Node déclarée dans mise.toml
pnpm install
pnpm dev          # http://localhost:5173 (l'API doit tourner)
pnpm check        # types et composants
pnpm build        # build de production, puis pnpm start
```

L'organisation du code, les pages, les variables d'environnement et les principes de mise en page sont décrits dans [docs/Frontend.md](../docs/Frontend.md). L'installation des outils est dans le [guide de contribution](../CONTRIBUTING.md#frontend-svelte-app).
