// APIクライアント（バックエンド FastAPI との通信を集約）
// - ベースURL: NEXT_PUBLIC_API_BASE（既定 http://localhost:8000）
// - 認証: アプリ独自セッション通行証を Authorization: Bearer で付与（X-User-Id は廃止）
// - API失敗時は ApiError を throw。呼び出し側でトースト表示して壊れないようにする。
// - 401（通行証の失効・不正）受信時は通行証を破棄して /login へ誘導する。

import { clearUser, getToken } from "./session";
import type {
  AuthSession,
  ClassifyResult,
  Device,
  DeviceType,
  FaqAnswer,
  FaqTopic,
  GoogleAuthResult,
  HistoryResult,
  Idol,
  ReceiveResult,
  ShareText,
  Shipment,
  User,
} from "./types";

// APIベースURL（末尾スラッシュを除去）
export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000"
).replace(/\/$/, "");

// API通信エラー
export class ApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// 相対的な photo_url / pdf_url に APIベースを前置してフルURLにする
export function mediaUrl(path: string | undefined | null): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path; // 既に絶対URLならそのまま
  return `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}

// 401 受信時: 通行証を破棄してログイン画面へ誘導する。
// ただしログイン処理そのもの（通行証を持たない状態での /api/auth/* や登録）で
// リダイレクトループに陥らないよう、「通行証を持っていた場合」のみ実施する。
function handleUnauthorized(hadToken: boolean): void {
  if (typeof window === "undefined") return;
  clearUser();
  if (hadToken && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

// 認証ヘッダー（通行証があれば Authorization: Bearer を付与）
function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// 共通リクエスト関数
async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...authHeaders(),
    ...(options.headers as Record<string, string> | undefined),
  };

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
  } catch {
    // ネットワーク到達不可（バックエンド未起動など）
    throw new ApiError("サーバーに接続できませんでした", 0);
  }

  if (!res.ok) {
    if (res.status === 401) handleUnauthorized(!!token);
    let detail = `エラーが発生しました (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* JSONでない場合は無視 */
    }
    throw new ApiError(detail, res.status);
  }

  // 204 No Content 等
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// JSON POST 用ヘルパー
function jsonInit(body: unknown, method = "POST"): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

// ===== エンドポイント =====

export const api = {
  // 0. Google 認証（ログイン入口）。credential を検証し、既存ユーザーかどうかを返す
  googleAuth: (credential: string) =>
    request<GoogleAuthResult>("/api/auth/google", jsonInit({ credential })),

  // 1. アイドル一覧（通常6人。期間限定推しは含まない）
  getIdols: () => request<Idol[]>("/api/idols"),

  // 1b. 当月の期間限定推し（T1特典。獲得済みユーザーの /oshi 表示用）
  getLimitedIdol: () => request<Idol>("/api/idols/limited"),

  // 2. （旧）ユーザー一覧 GET /api/users は F-2 対応で撤廃した（全 PII 列挙の穴だったため）。

  // 3. ユーザー作成（Google の credential を添付して本人性を確認）。
  //    登録完了はログイン確立とみなし、user と通行証(token)を返す。
  createUser: (payload: {
    credential: string;
    temp_id?: string;
    nickname: string;
    idol_id: string;
  }) => request<AuthSession>("/api/users", jsonInit(payload)),

  // 4. ユーザー詳細
  getUser: (id: string) => request<User>(`/api/users/${id}`),

  // 4b. ログイン中ユーザーの更新（推し変更 idol_id ／ 特殊ビジュアル切替 active_visual）。
  //     いずれも任意。points / rank は引き継ぐ。
  updateMe: (payload: { idol_id?: string; active_visual?: string }) =>
    request<User>("/api/users/me", jsonInit(payload, "PATCH")),

  // 5. 推しコメント取得
  getComment: (id: string) =>
    request<{ comment: string }>(`/api/users/${id}/comment`),

  // 6. デバイス種別マスタ
  getDeviceTypes: () => request<DeviceType[]>("/api/device-types"),

  // 7. 撮影画像の判定（multipart）
  classifyDevice: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ClassifyResult>("/api/devices/classify", {
      method: "POST",
      body: form,
    });
  },

  // 8. デバイス登録
  createDevice: (payload: { device_type: string; photo_id?: string }) =>
    request<Device>("/api/devices", jsonInit(payload)),

  // 9. 登録済みデバイス一覧
  getDevices: (status = "registered") =>
    request<Device[]>(`/api/devices?status=${encodeURIComponent(status)}`),

  // 10. 伝票発行（送付）
  createShipment: (device_ids: string[]) =>
    request<Shipment>("/api/shipments", jsonInit({ device_ids })),

  // 11. 伝票PDFを取得する（F-3 対応で認証必須になったため、Bearer 付きで fetch し Blob を返す）。
  //     生 URL を新規タブで直接開くと Authorization を付与できないため、呼び出し側で
  //     Blob → object URL 化して開く。
  fetchShipmentPdf: async (id: string): Promise<Blob> => {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/shipments/${id}/pdf`, {
        headers: authHeaders(),
      });
    } catch {
      throw new ApiError("サーバーに接続できませんでした", 0);
    }
    if (!res.ok) {
      if (res.status === 401) handleUnauthorized(!!getToken());
      throw new ApiError(`伝票PDFの取得に失敗しました (${res.status})`, res.status);
    }
    return res.blob();
  },

  // 11b. 検収完了（自分の送付を受領扱いにしポイント付与・ランク再計算）
  receiveShipment: (id: string) =>
    request<ReceiveResult>(`/api/shipments/${id}/receive`, { method: "POST" }),

  // 11c. シェア投稿文面の取得（受領済みのみ。AI生成 or テンプレ）
  getShareText: (id: string) =>
    request<ShareText>(`/api/shipments/${id}/share-text`),

  // 12. 履歴
  getHistory: (id: string) =>
    request<HistoryResult>(`/api/users/${id}/history`),

  // 13. FAQトピック
  getFaqTopics: () => request<FaqTopic[]>("/api/faq/topics"),

  // 14. FAQ質問
  askFaq: (question: string) =>
    request<FaqAnswer>("/api/faq/ask", jsonInit({ question })),
};
