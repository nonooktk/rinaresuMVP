// セッション管理（localStorage ベース）
// ログイン/新規登録の入口だけ Google 認証し、ログイン後は従来どおり
// ログイン済みユーザー(User)を localStorage に保存して X-User-Id で API を叩く。

import type { RewardsStatus, User } from "./types";

const STORAGE_KEY = "rinaresu_user";
// アプリ独自セッション通行証（Authorization: Bearer で送る署名付きトークン）の保存キー。
const TOKEN_KEY = "rinaresu_token";
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

// セッション通行証（token）を取得（未ログインなら null）
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

// セッション通行証を保存
export function storeToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

// ログイン確立: ユーザーと通行証をまとめて保存する
export function storeSession(user: User, token: string): void {
  storeUser(user);
  storeToken(token);
}

// ユーザー情報・通行証をクリア（ログアウト／失効時）
export function clearUser(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem(TOKEN_KEY);
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

// ---------- 毎日ログインボーナス: 結果を確認できなかった claim の持ち越し ----------

/**
 * 【QA_Q-6 M-1 対応】「claim を投げたが結果を確認できなかった」ことを次のホーム表示へ持ち越す。
 *
 * claim は冪等なのでオーバーレイ内で再送して復元するが、それでも取りこぼす経路がひとつ残る:
 * リクエストの**送信自体が数秒以上遅延**し、こちらが失敗と判断して再取得したあとに
 * サーバー側で付与が確定するケース。このときページ内の差分比較では拾えず、
 * `rewards_granted[]` は `GET /api/users/{id}` から取れないため、達成告知が永久に失われる。
 *
 * そこで「オーバーレイを開いた時点の特典保有状況・月間pt」を localStorage に残しておき、
 * **次のホーム表示で差分を取って告知する**。持ち越しは次の1回のホーム表示までで終える
 * （それ以上待っても状況は変わらないため）。
 */
const LOGIN_BONUS_PENDING_KEY = "rinaresu_login_bonus_pending";

export interface PendingLoginBonus {
  /** どのユーザーのスナップショットか（別アカウントへ引き継がないための照合用） */
  userId: string;
  /** スナップショット時点の月間pt（増えていれば「実は付与されていた」と判断できる） */
  monthlyPoints: number;
  /** スナップショット時点の特典保有状況（差分検知の基準） */
  rewards: RewardsStatus | null;
}

// 未確認の claim を記録する（オーバーレイを開いたとき／失敗して再取得したあとに更新）
export function storePendingLoginBonus(pending: PendingLoginBonus): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      LOGIN_BONUS_PENDING_KEY,
      JSON.stringify(pending)
    );
  } catch {
    // 容量超過・プライベートモード等。告知は次善の手段なので失敗しても本流は止めない
  }
}

// 未確認の claim を取り出す（無ければ null）
export function getPendingLoginBonus(): PendingLoginBonus | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LOGIN_BONUS_PENDING_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PendingLoginBonus;
  } catch {
    return null;
  }
}

// 未確認の claim を破棄する（結果を確認できたとき／持ち越し分を処理したとき）
export function clearPendingLoginBonus(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(LOGIN_BONUS_PENDING_KEY);
}

/**
 * 持ち越しの**基準だけ**を最新値へ更新する（持ち越し自体は消さない）。
 *
 * 【QA_Q-6 N-1 対応】持ち越しは「ログインボーナスの claim が入ったかどうか」を測るための
 * 基準線。検収（`/history`）など**別ルートで特典が解放され、そこで既に告知した**場合に
 * 基準を古いままにしておくと、次のホーム表示でその特典まで差分で拾って**二重告知**になる。
 * 別ルートで告知を出した側がこの関数で基準を進めることで、
 * 「ログインボーナス由来の変化」だけが差分に残るようにする。
 *
 * 該当ユーザーの持ち越しが無ければ何もしない（新規作成はしない）。
 */
export function rebasePendingLoginBonus(
  userId: string,
  monthlyPoints: number,
  rewards: RewardsStatus | null
): void {
  const pending = getPendingLoginBonus();
  if (!pending || pending.userId !== userId) return;
  storePendingLoginBonus({ userId, monthlyPoints, rewards });
}
