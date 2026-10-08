FROM node:24-bookworm-slim
WORKDIR /app
RUN npm exec --yes --package=@playwright/test@1.64.0 -- playwright install --with-deps chromium
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
ENV API_INTERNAL_URL=http://api:8000
COPY apps/web ./
RUN npm run build
ENV NODE_ENV=production
CMD ["npm", "run", "start"]
