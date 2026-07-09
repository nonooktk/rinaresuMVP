"use client";

import { useEffect } from "react";

/**
 * Service Worker 登録コンポーネント（PWA 化ステップ1）
 *
 * - navigator.serviceWorker 対応時のみ登録する。
 * - 本番ビルドでのみ有効（開発時のキャッシュ挙動による混乱を防ぐため
 *   process.env.NODE_ENV === "production" でガードする）。
 * - UI は描画しない（副作用のみ）。
 */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    // 本番ビルドのみ（開発時は登録しない）
    if (process.env.NODE_ENV !== "production") return;
    // Service Worker 非対応環境では何もしない
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      return;
    }

    // 初期描画を妨げないよう、load 完了後に登録する
    const register = () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch((err) => {
        // 登録失敗はアプリ本体の動作に影響させない（ログのみ）
        console.error("Service Worker 登録に失敗しました", err);
      });
    };

    if (document.readyState === "complete") {
      register();
      return;
    }
    window.addEventListener("load", register);
    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}
