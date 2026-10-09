# Image du front KYST (SvelteKit, adapter-node). Contexte de build : interface/app
FROM node:24-slim AS builder

WORKDIR /app

RUN npm install --global pnpm@12.9.1

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
RUN pnpm install --frozen-lockfile

COPY . .
# URL publique du site, figée au build (protection CSRF des formulaires, voir vite.config.ts).
# Vide : déduite de l'en-tête Host en supposant https.
ARG ORIGIN=""
RUN ORIGIN="$ORIGIN" pnpm build

FROM node:24-slim

WORKDIR /app
ENV NODE_ENV=production

# Toutes les dépendances sont des devDependencies : adapter-node les intègre au build
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./

USER node
ENV HOST=0.0.0.0 PORT=3000
EXPOSE 3000

CMD ["node", "build/index.js"]
