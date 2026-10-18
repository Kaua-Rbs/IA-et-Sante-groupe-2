# Image du front KYST (SvelteKit, adapter-node). Contexte de build : interface/app
FROM node:24-slim AS builder

WORKDIR /app

RUN npm install --global pnpm@12.9.1

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM node:24-slim

WORKDIR /app
ENV NODE_ENV=production

# Toutes les dépendances sont des devDependencies : adapter-node les intègre au build
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json /app/server.js ./

USER node
# URL publique du site (protection CSRF des formulaires), lue au démarrage par server.js.
# Vide : déduite de l'en-tête Host en supposant https.
ENV HOST=0.0.0.0 PORT=3000 ORIGIN=""
EXPOSE 3000

CMD ["node", "server.js"]
