// APIクライアント（バックエンド FastAPI との通信を集約）
// - ベースURL: NEXT_PUBLIC_API_BASE（既定 http://localhost:8000）
// - 認証: X-User-Id ヘッダーを付与
// - API失敗時は ApiError を throw。呼び出し側でトースト表示して壊れないようにする。

import { getStoredUser } from "./session";
import type {
  ClassifyResult,
  Device,
  DeviceType,
  FaqAnswer,
  FaqTopic,
  GoogleAuthResult,
  HistoryResult,
  Idol,
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

// 共通リクエスト関数
async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const user = getStoredUser();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  // ログイン済みなら X-User-Id を付与
  if (user?.id) headers["X-User-Id"] = user.id;

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

  // 1. アイドル一覧
  getIdols: () => request<Idol[]>("/api/idols"),

  // 2. ユーザー一覧
  getUsers: () => request<User[]>("/api/users"),

  // 3. ユーザー作成（Google の credential を添付して本人性を確認）
  createUser: (payload: {
    credential: string;
    temp_id?: string;
    nickname: string;
    idol_id: string;
  }) => request<User>("/api/users", jsonInit(payload)),

  // 4. ユーザー詳細
  getUser: (id: string) => request<User>(`/api/users/${id}`),

  // 4b. ログイン中ユーザーの更新（推し変更。points / rank は引き継ぐ）
  updateMe: (payload: { idol_id: string }) =>
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

  // 11. 伝票PDFのURL（GETで開く用。実データ取得はブラウザに任せる）
  shipmentPdfUrl: (id: string) => `${API_BASE}/api/shipments/${id}/pdf`,

  // 12. 履歴
  getHistory: (id: string) =>
    request<HistoryResult>(`/api/users/${id}/history`),

  // 13. FAQトピック
  getFaqTopics: () => request<FaqTopic[]>("/api/faq/topics"),

  // 14. FAQ質問
  askFaq: (question: string) =>
    request<FaqAnswer>("/api/faq/ask", jsonInit({ question })),
};
