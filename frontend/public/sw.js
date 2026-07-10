/*
 * りなれす Service Worker（PWA 化ステップ1）
 *
 * 保守的キャッシュ方針（本番稼働中アプリのため整合性を最優先）:
 *  - /api/ と /photos/ は一切キャッシュしない（ポイント・判定結果・写真の不整合防止）。
 *    そもそも fetch イベントに介入せずブラウザ既定のネットワーク処理に委ねる。
 *  - HTML ナビゲーションは network-first。オフライン時のみ簡易フォールバック応答を返す
 *    （HTML はキャッシュに保存しない＝常に最新を取得。古い画面の表示を避ける）。
 *  - /_next/static/（ビルド時にハッシュが付き内容不変の静的アセット）のみ cache-first。
 *  - 上記以外・別オリジンへのリクエストは介入しない（Google 認証 iframe やフォント等を壊さない）。
 *
 * キャッシュ名にバージョンを含め、activate 時に旧バージョンのキャッシュを削除する。
 */

// バージョンを上げると、古い静的アセットキャッシュが activate で破棄される
const CACHE_VERSION = "rinaresu-v1";
const STATIC_CACHE = `${CACHE_VERSION}-static`;

// インストール即時、新しい SW を有効化（待機させない）
self.addEventListener("install", () => {
  self.skipWaiting();
});

// 有効化時に、当バージョン以外のキャッシュを削除してからクライアントを掌握
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((key) => key !== STATIC_CACHE).map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // GET 以外（POST 等）は介入しない
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // 別オリジン（Google 認証・外部フォント等）は介入しない
  if (url.origin !== self.location.origin) return;

  // /api/ と /photos/ は絶対にキャッシュしない（介入せずネットワーク直行）
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/photos/")) {
    return;
  }

  // ハッシュ付き静的アセットのみ cache-first
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML ナビゲーションは network-first（オフライン時のみ簡易フォールバック）
  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  // それ以外は介入しない（ブラウザ既定処理に委ねる）
});

// cache-first: キャッシュがあれば即返し、無ければ取得して 200 のみ保存
async function cacheFirst(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.status === 200) {
    cache.put(request, response.clone());
  }
  return response;
}

// network-first（ナビゲーション用）: 常にネットワーク優先。失敗時のみ簡易フォールバック
async function networkFirstNavigation(request) {
  try {
    return await fetch(request);
  } catch {
    // オフライン時の最小フォールバック（HTML は保存しないため固定文言を返す）
    return new Response(
      '<!doctype html><html lang="ja"><head><meta charset="utf-8">' +
        '<meta name="viewport" content="width=device-width, initial-scale=1">' +
        "<title>りなれす</title></head>" +
        '<body style="margin:0;font-family:sans-serif;display:flex;min-height:100vh;' +
        "align-items:center;justify-content:center;background:#ffd9e8;color:#5a3a4a;" +
        'text-align:center;padding:24px;">' +
        "<div><p>オフラインのため、ページを表示できませんでした。</p>" +
        "<p>通信環境を確認して、もう一度お試しください。</p></div></body></html>",
      {
        status: 503,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      },
    );
  }
}
