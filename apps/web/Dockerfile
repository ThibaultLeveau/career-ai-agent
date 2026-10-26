FROM node:24.22.1-bookworm-slim AS dependencies
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM dependencies AS development
COPY --chown=node:node . .
RUN chown node:node /app
USER node
CMD ["npm", "run", "dev"]

FROM dependencies AS test
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
RUN npx playwright install --with-deps chromium
COPY --chown=node:node . .
RUN chown node:node /app
USER node
CMD ["npm", "run", "test:e2e"]

FROM dependencies AS build
COPY . .
RUN npm run build

FROM node:24.22.1-bookworm-slim AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
