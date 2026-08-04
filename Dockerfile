# syntax=docker/dockerfile:1
#
# Multi-stage: se compila con node y se sirve con nginx.
# La imagen final es nginx-unprivileged, que corre como uid 101 y escucha en
# 8080. Nunca root: es invariante de este servidor EasyPanel (incidente de
# abril de 2026, cryptominer en un contenedor que corria como root).

# ---------- 1. Build ----------
FROM node:22-alpine AS build

WORKDIR /app

# Capa de dependencias aparte para que un cambio en el codigo no reinstale todo.
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
COPY public ./public

RUN npm run build

# ---------- 2. Runtime ----------
FROM nginxinc/nginx-unprivileged:1.30-alpine

# htpasswd, para generar el fichero de autenticacion desde las variables de
# entorno en cada arranque. Es lo unico que se instala como root.
USER root
RUN apk add --no-cache apache2-utils
USER 101

COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --chmod=755 docker/10-runtime-config.sh /docker-entrypoint.d/10-runtime-config.sh

# El GEDCOM se monta aqui como volumen. El directorio existe en la imagen para
# que un arranque sin volumen de un 404 claro en vez de un error de nginx.
VOLUME ["/data"]

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO /dev/null http://127.0.0.1:8080/healthz || exit 1
