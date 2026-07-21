// りなれす 型定義（API契約に対応）

// アイドル情報
export interface Idol {
  id: string;
  name: string;
  theme_color: string; // テーマカラー（例 #ff87b2）
  catchphrase: string;
}

// ユーザー情報（セッションで localStorage に保存する対象）
export interface User {
  id: string;
  temp_id: string;
  nickname: string; // アイドルに呼んでほしいあだ名
  idol_id: string;
  email?: string | null; // Google アカウントのメール（確認用）
  points: number;
  rank: number; // 1〜3
}

// POST /api/auth/google のレスポンス
export interface GoogleAuthResult {
  registered: boolean; // 既存ユーザーかどうか
  user?: User | null; // 既存ユーザーの場合のみ返る
  email?: string | null; // 既存ユーザーの確認用メール
  token?: string | null; // 既存ユーザーの場合のみ返るセッション通行証
}

// ログイン確立レスポンス（新規登録 POST /api/users の返却）
export interface AuthSession {
  user: User;
  token: string; // セッション通行証（Authorization: Bearer で送る）
}

// デバイス種別マスタ
export interface DeviceType {
  code: string;
  label: string;
  weight_g: number;
  points: number;
}

// 撮影判定の候補
export interface ClassifyCandidate {
  device_type: string;
  label: string;
  points: number;
  confidence: number;
}

// 判定APIレスポンス
export interface ClassifyResult {
  photo_id: string;
  photo_url: string; // 相対パス（表示時は API ベースを前置）
  candidates: ClassifyCandidate[];
}

// 登録済みデバイス
export interface Device {
  id: string;
  device_type: string;
  label: string;
  points: number;
  photo_url: string; // 相対パス
  status: string; // registered / shipped / received など
  created_at: string;
}

// 伝票（送付）情報
export interface Shipment {
  id: string;
  pdf_url: string; // 相対パス
  total_points: number;
  device_count: number;
  created_at?: string;
  status?: string;
  received_at?: string | null;
  devices?: Device[];
}

// 履歴レスポンス
export interface HistoryResult {
  devices: Device[];
  shipments: Shipment[];
}

// FAQトピック（質問チップ）
export interface FaqTopic {
  id: string;
  category: string;
  question: string;
}

// FAQ回答
export interface FaqAnswer {
  answer: string;
  matched: boolean;
  generated_by?: string; // "ai" or "keyword"（後方互換の任意フィールド）
}

// 検収完了（受領）結果
export interface ReceiveResult {
  points_added: number;
  new_points: number;
  new_rank: number;
}

// シェア投稿文面
export interface ShareText {
  text: string;
  generated_by: string; // "ai" or "template"
}
