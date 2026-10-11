# The React app, built then served as static files by nginx (phase 8, compose `web`).
#
# Build context is frontend/ alone: `npm run build` (tsc --noEmit && vite build) reads only
# what is in here. The generated client src/api/schema.d.ts is committed, so openapi.yaml
# (one level up) is not needed to build -- only `npm run gen:api` reads it.

# Node pinned to frontend/.nvmrc and package.json `engines` (engine-strict=true in .npmrc).
FROM node:24.19.0-alpine AS build

WORKDIR /app

# Locked install first, so the layer is reused while only sources change.
COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .

# Baked into the bundle at build time (see src/api/client.ts). Compose passes the URL of
# its own API; the default is the same as `make api`.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:1.27.5-alpine

# The default nginx site serves /usr/share/nginx/html. The app has no client-side router
# (two screens switched by local state, one URL), so no try_files fallback is needed.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
