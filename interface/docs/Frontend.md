# KYST — interface web

Front de KYST (*Keep Your Surgeries Timelies*), en [SvelteKit 3](https://svelte.dev/docs/kit) et Svelte 5 (runes), avec du CSS écrit à la main. Le code est dans `interface/app` ; il parle à l'API FastAPI de `interface/api`.

## Lancer en local

L'API doit tourner (voir le [guide de contribution](../CONTRIBUTING.md)). Ensuite, depuis `interface/app` :

```bash
mise install
pnpm install
pnpm dev          # http://localhost:5173
```

Autres commandes : `pnpm check` (types et composants), `pnpm build` puis `pnpm start` (serveur Node de production), et le `Dockerfile` pour l'image. Pour lancer l'API et le front ensemble en production, utilisez `just prod` depuis `interface/` (voir le guide de contribution).

## Variables d'environnement

Le front lit les mêmes fichiers que l'API, décrits dans [`interface/kyst.env`](../kyst.env). Par ordre de priorité, on trouve l'environnement du processus, puis `kyst.local.env`, puis `kyst.env`. En développement, `vite.config.ts` charge ces fichiers ; en production, `pnpm start` les passe à Node avec `--env-file`. Dans l'image Docker, les variables viennent de l'environnement du conteneur.

| Variable | Rôle |
| :--- | :--- |
| `KYST_API_URL` | Adresse de l'API, appelée uniquement par le serveur SvelteKit |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | Partagées avec l'API : durée de vie des cookies de session |
| `HOST`, `PORT` | Adresse et port du serveur Node de production (adapter-node) |
| `ORIGIN` | URL publique du site, **figée au build** (`paths.origin` dans `vite.config.ts`) pour la protection CSRF des formulaires. Vide : origine déduite de l'en-tête Host, en supposant HTTPS |

Les variables lues par le code sont déclarées et validées dans `src/env.ts`, puis importées depuis `$app/env/private`.

## Principes

- **L'API n'est appelée que par le serveur SvelteKit.** Les jetons restent dans des cookies HttpOnly, et le navigateur ne parle qu'au front : pas de CORS, pas de jeton en JavaScript.
- **La session est gérée dans `src/hooks.server.ts`.** Le hook lit les cookies et renouvelle le jeton d'accès avec le refresh token quand il expire. Il expose ensuite `locals.user` (rôles tirés du jeton) et `locals.api` (client authentifié). Les pages non publiques redirigent vers la connexion.
- **Les lectures se font dans les `load`** (`locals.api.get` : une erreur d'API devient une page d'erreur). **Les écritures passent par des actions de formulaire** (`actionFailure` transforme l'erreur en message affiché). Les formulaires fonctionnent aussi sans JavaScript.
- **Les droits** reflètent ceux de l'API (`requireCapability`) : l'API reste la seule autorité, le front masque seulement ce qui n'est pas permis.

## Organisation

```text
src/
├── env.ts                 # Déclaration et validation des variables lues (voir kyst.env)
├── hooks.server.ts        # Session, renouvellement du jeton, garde des pages
├── lib/
│   ├── server/            # Code serveur uniquement : client d'API, session, droits, données de référence
│   ├── components/        # En-tête, landing, graphiques (occupation, jauge de vacation), badges
│   ├── style/             # Variables, base, formulaires, composants des pages outil
│   ├── types.ts           # Types des réponses de l'API et libellés français
│   ├── format.ts          # Dates, heures, durées
│   └── names.ts           # Identifiants -> libellés
└── routes/                # Une page par dossier (voir ci-dessous)
```

## Pages

| Route | Rôle requis | Contenu |
| :--- | :--- | :--- |
| `/` | public / connecté | Présentation de KYST ; une fois connecté, tableau de bord (lits du jour, remplissage du bloc, demandes en attente, occupation sur 14 jours) |
| `/requests` | chirurgien, secrétariat, cadre | Demandes d'intervention par statut |
| `/requests/new` | chirurgien, secrétariat | Saisie en consultation : patient pseudonymisé, intervention, fenêtre ; les dates sont proposées dans la foulée |
| `/requests/[id]` | chirurgien, secrétariat, cadre | Prédiction, dates A/B avec leurs raisons, confirmation, puis suivi de l'intervention (annulation, durées réelles) |
| `/planning` | connecté | Semaine du bloc : vacations par salle et par jour avec leur remplissage ; le cadre ouvre ou supprime des vacations |
| `/beds` | connecté | Occupation prévue de chaque unité de lits sur 7, 14 ou 28 jours |
| `/resources` | cadre, admin | Unités de lits, salles, chirurgiens (et lien avec un compte), spécialités |
| `/account/users` | admin | Validation des comptes, rôles, activation |
| `/account/users/me` | connecté | Profil et mot de passe |
| `/account/login`, `/account/register` | public | Connexion, demande d'accès |

## Graphiques

Les graphiques d'occupation sont faits en HTML/CSS, sans bibliothèque :
- **une seule teinte** sur une échelle de 0 à la capacité ;
- **statut doublé d'un symbole** : les jours tendus (▲, 90 % ou plus) ou saturés (■) ne sont jamais signalés par la couleur seule ;
- **une infobulle** par colonne, au survol comme au clavier ;
- **un tableau des valeurs** sous chaque graphique.
