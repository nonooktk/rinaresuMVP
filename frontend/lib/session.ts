// セッション管理（localStorage ベース）
// ログイン/新規登録の入口だけ Google 認証し、ログイン後は従来どおり
// ログイン済みユーザー(User)を localStorage に保存して X-User-Id で API を叩く。

import type { User } from "./types";

const STORAGE_KEY = "rinaresu_user";
// /login で受け取った Google の credential を /register まで一時的に持ち越すキー。
// タブを閉じると消える sessionStorage を使う（localStorage には残さない）。
const PENDING_CREDENTIAL_KEY = "rinaresu_pending_credential";

// 保存されているユーザーを取得（未ログインなら null）
export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

// ユーザーを保存
export function storeUser(user: User): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
}

// ユーザー情報をクリア（ログアウト）
export function clearUser(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}

// 未登録ユーザーの Google credential を一時保存（/login → /register の受け渡し用）
export function storePendingCredential(credential: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(PENDING_CREDENTIAL_KEY, credential);
}

// 一時保存した Google credential を取得（無ければ null）
export function getPendingCredential(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(PENDING_CREDENTIAL_KEY);
}

// 一時保存した Google credential を破棄（登録完了時・ログイン戻り時）
export function clearPendingCredential(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(PENDING_CREDENTIAL_KEY);
}
