# Single-service deploy: build the SPA + backend, the Hono server serves both
# (API under /api/*, the built SPA + assets for everything else) on $PORT.
FROM node:20-slim
WORKDIR /app

# Install workspace deps first (layer cache on lockfile).
COPY package.json package-lock.json ./
COPY backend/package.json ./backend/
COPY frontend/package.json ./frontend/
RUN npm ci

# App source (see .dockerignore for what's excluded).
COPY . .

# Build: backend (tsc) + frontend (vite). Same-origin API (relative /api) and
# dev tools on for the pilot demo (skip-login + the seeded demo account).
ENV VITE_API_URL=""
ENV VITE_DEV_TOOLS="1"
RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000

# On boot: apply migrations, seed the catalog+demo account ONCE if empty, serve.
CMD ["sh", "-c", "npx tsx backend/src/db/migrate.ts && SEED_IF_EMPTY=1 npx tsx scripts/seed-dev-user.ts && node backend/dist/index.js"]
