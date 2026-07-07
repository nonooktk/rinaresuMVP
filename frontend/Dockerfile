# りなれす フロントエンド（Next.js 16）用 Dockerfile。
#
# multi-stage 構成。build ステージで next build（standalone 出力）を行い、
# runtime ステージには .next/standalone / .next/static / public のみを配置して軽量化する。
#
# 注意: NEXT_PUBLIC_* はビルド時にバンドルへ埋め込まれるため、
# API 接続先(NEXT_PUBLIC_API_BASE)はビルド引数で渡し、build 前に ENV へ設定する。

# ---------- deps: 依存関係インストール ----------
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---------- build: 本番ビルド ----------
FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# API 接続先をビルド時に埋め込む（build ARG → ENV）
ARG NEXT_PUBLIC_API_BASE
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}

# Google OAuth クライアントID（秘匿値ではない）もビルド時に埋め込む
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID
ENV NEXT_PUBLIC_GOOGLE_CLIENT_ID=${NEXT_PUBLIC_GOOGLE_CLIENT_ID}

RUN npm run build

# ---------- runtime: 実行イメージ ----------
FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

# standalone 出力・静的アセット・public を配置
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
