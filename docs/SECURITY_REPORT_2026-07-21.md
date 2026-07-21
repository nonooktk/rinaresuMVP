# セキュリティチェック レポート（りなれす・2026-07-21）

対象: りなれす（frontend=Next.js 16 standalone SSR / backend=FastAPI+SQLAlchemy / Azure Container Apps・PostgreSQL・Azure Files）
実施: **5種すべて実施済み**（① SCA ② SAST=Semgrep ③ CSPM=az 読み取り ④ DAST=ZAP ⑤ 手動 IDOR）。ツールは無料枠のみ。本番へ能動スキャンは撃たない（受動のみ）・az は読み取り専用。
位置づけ: `/security-audit` スキルのドライラン検証を兼ねる。初回（SCA/手動SAST/IDOR）を 2026-07-21 に実施 → F-1/F-2/F-3 修正・v7 デプロイ → 残 3 種（Semgrep・CSPM・DAST）を同日追実施して 5 種を完遂。

> [!success] 修正状況（2026-07-21 追記）
> 本レポートで検出した **F-1・F-2・F-3 は方式B（アプリ独自セッション通行証・HS256・exp7日・fail-closed）で修正し、本番デプロイ済み**（api `rinaresu-api:v7` / rev `ca-rinaresu-api--0000011`・Healthy・Traffic100、web `rinaresu-web:v7`）。
> 本番検証: root 200 / `GET /api/devices`(no auth) 401 / `GET /api/users` 405 / `GET /api/shipments/1/pdf`(no auth) 401。IDOR ハーネス（`backend/tests/test_idor_manual.py`）は「攻撃を弾く」向きに反転して pytest 20 件全 PASS。
> 未対応で次段に残すのは **F-4（依存更新）・F-5（多層防御）・Nice-to-have**。詳細は各節末尾の「対応」を参照。
>
> **2026-07-21 追記**: F-4 は依存更新済み（ブランチ `security/f4-deps-and-ci`）。恒常化として **Snyk CI ゲート＋Dependabot** を導入（`.github/workflows/security.yml`／`.github/dependabot.yml`）。本番反映は deploy CI 初回実行（v8）にて。詳細は F-4 節末尾を参照。

## ■ エグゼクティブサマリー

総合判定（初回・2026-07-21 レビュー時点）は**本番運用不可（要修正）**だった。→ MVP の認証設計（`X-User-Id` ヘッダー）がエンプラ最低ラインを満たさなかった。
**その後 F-1/F-2/F-3 を修正し v7 を本番デプロイ済み。認証・認可のエンプラ最低ラインは充足**（残りは F-4/F-5 の次段対応）。

本丸は2つ。①API は `X-User-Id` 整数ヘッダーを主キーに直結するだけでトークン検証がなく、連番IDの差し替えだけで任意ユーザーになりすませる。②ユーザー系 GET が認証を一切要求せず、ヘッダーすら無しで全ユーザーの email・履歴を一括収集できる。→ いずれも pytest ハーネスで実証済み。

対照的に、`get_current_user` を通す操作系（送付・受領・share-text・端末一覧）は owner スコープが正しく効いており、他人リソースへの越境は 404 で防がれている。→ 穴は「認証の強度」と「認証を掛け忘れた GET 群」の2層に限局する。ここを塞げば最低ラインに乗る。

| 深刻度 | 件数 | 内訳 | 状況 |
| --- | --- | --- | --- |
| Blocker | 2 | F-1 なりすまし / F-2 全ユーザーPII露出・履歴IDOR | ✅ 対応済み・本番デプロイ済み(v7) |
| High | 1 | F-3 伝票PDF 無認証取得 | ✅ 対応済み・本番デプロイ済み(v7) |
| Medium | 1 | F-4 依存の既知脆弱性（backend18・frontend3） | ✅ 依存更新済み・CIゲート導入済み（本番反映は deploy CI 初回実行v8にて） |
| Low | 4 | F-5 多層防御（dev API・CORS）／F-6 セキュリティヘッダ不足／F-7 Storage 最小TLS=TLS1_0／F-8 データストア公開NW露出 | ⏳ 次段・任意 |
| クリア | 0 | — | — |

> [!note] 5種完遂（2026-07-21 追記）
> 初回未実施だった **② SAST（Semgrep）・③ CSPM（az 読み取り）・④ DAST（ZAP）を追実施し 5 種を完遂**。→ いずれも **新規 Blocker/High はゼロ**。Semgrep は 0 件（手動レビューと一致）、CSPM は致命傷なし（SSL強制・匿名BLOB無効を確認）、DAST は 0 FAIL。追加所見は多層防御の Low 3 件（F-6/F-7/F-8）のみ。

## ■ 背景

りなれすは家庭のジャンク端末回収を「推し×ポイント」で促すスマホ Web アプリ。実ユーザーが Google アカウントで登録済みで、DB には **email・Google sub・端末/送付履歴** という PII が載る。本番は Azure Container Apps に公開デプロイ済み。→ 認可の越境（IDOR）と認証の強度が、そのまま実ユーザーの個人情報保護に直結する。

認証は「入口のみ Google 認証」方式。ログイン/登録の入口だけ GIS で本人確認し、以降の API 呼び出しは `X-User-Id` ヘッダーで本人を特定する。メンターからは「抜け道2：ヘッダを差し替えれば通る」と既に指摘されており、本レビューはその成否を実証することを最優先に置いた。

## ■ 目的

①依存の既知脆弱性（SCA）②自作コードの脆弱パターン・秘匿値混入（SAST）③認可の越境と認証の強度（手動 IDOR）を確かめる。特に③で「X-User-Id を差し替えて他人のリソースが取れるか」を実 API と同じ認可ロジックで実証する。

## ■ 手段

| チェック | ツール / 方式 | 対象 |
| --- | --- | --- |
| ① SCA | pip-audit / npm audit | `backend/requirements.txt` / `frontend`（npm） |
| ② SAST | **Semgrep**（`p/security-audit,secrets,python,javascript,typescript`）＋手動コードレビュー＋秘匿値 grep | `backend/app` / `frontend/{app,lib,components}`（node_modules・.next 除外・52ファイル走査） |
| ③ CSPM | **az CLI 読み取り専用クエリ**（storage/postgres/containerapp show・firewall list） | Storage `strinaresua37c` / PostgreSQL `psql-rinaresua37c` / Container Apps `ca-rinaresu-{api,web}` |
| ④ DAST | **OWASP ZAP（Docker）**：本番 web へ受動 baseline ＋ ローカル起動 API へ能動 api-scan | 本番 web（受動）／ローカル backend `:8010` openapi（能動・本番へは撃たない） |
| ⑤ 手動 IDOR | pytest ハーネス（実 API を TestClient で叩く。隔離した一時 SQLite に `get_db` 差し替え） | `backend/tests/test_idor_manual.py` |

手動 IDOR は、被害者 A（id=1・端末/送付あり）と攻撃者 B（id=2）を仕込み、A のリソースに対して「ヘッダー無し」「X-User-Id 差し替え」「B へのなりすまし」で越境を試みる方式。実 dev DB は汚さない。**制約**：本番へ能動スキャンは撃たない（受動のみ）／az はミューテートしない（読み取り専用）／秘匿値（secret 値・接続文字列）は読まない・出力しない。

## ■ 結果

### ① SCA

backend で **18件**（`python-multipart 0.0.9`・`starlette 0.38.6`・`requests 2.32.3`）、frontend で **3件**（`brace-expansion` high / `postcss` moderate / `next` moderate）。

RCE・認可欠陥は無く DoS 中心。→ 見た目の件数ほどの緊急性はない。ただし `python-multipart` は `POST /api/devices/classify`（写真アップロード）の multipart 解析経路で**到達可能**。frontend の postcss はビルド時のみ（配信物には影響しない）。→ 本番前に締める Medium。詳細は F-4。

> [!success] F-4 対応済み（2026-07-21 追記）
> 依存更新済み（ブランチ `security/f4-deps-and-ci`）。backend: python-multipart 0.0.9→0.0.32／requests 2.32.3→2.34.2／PyJWT 2.9.0→2.13.0／python-dotenv 1.0.1→1.2.2／fastapi 0.115.0→0.133.0／starlette 0.38.6→1.3.1（明示ピン）。pip-audit 0件。frontend: `npm audit fix` で brace-expansion（high）を解消。next 同梱 postcss の moderate 2件は dev-only・安定版未提供のため残置（Dependabot が安定版リリース後に PR 化する想定）。pytest 20件全 PASS・ローカルスモークOK（root/idols 200・無認証401・users 405）。
> 恒常化として **Snyk CI ゲート**（`.github/workflows/security.yml`。PR・main push で high 以上をマージブロック）と **Dependabot**（`.github/dependabot.yml`。npm/pip/github-actions を週次スキャン）を導入。Dependabot alerts / automated security fixes はリポジトリ設定で有効化済み。
> **本番反映は deploy CI 初回実行（v8）にて**（統括作業待ち。push・PR・マージ・Azure OIDC secrets 登録・GitHub Environment 保護設定が未了）。実戦知見は [[GitHub Actions による依存脆弱性の CI ゲート（Snyk＋Dependabot）]] を参照。

### ② SAST（Semgrep 実行済み＋手動判定）

**Semgrep を実行**（`p/security-audit` / `p/secrets` / `p/python` / `p/javascript` / `p/typescript`、node_modules・.next 除外、52ファイル走査）。→ **検出 0 件・エラー 0 件**。手動コードレビューの結論（真陽性の脆弱パターン無し）とツールが一致した。良い点を明示する。

- Semgrep: 0 findings / 0 errors（52 files）。→ SQLi・コマンドインジェクション・危険な eval・ハードコード秘密のパターンいずれも不検出。
- 秘匿値: `.env` は `.gitignore` 済み、API キーは環境変数取得、Google クライアントID は非秘匿の埋め込み。→ ハードコード秘密なし（クリア）。
- Google トークン検証: `verify_oauth2_token` で aud/署名/期限を正しく検証（`services/google_auth.py`）。→ 入口認証は健全。
- パストラバーサル: `photo_id` を `[0-9a-f]{32}\.[A-Za-z0-9]{1,8}` の正規表現で厳格検証（`routers/devices.py:92`）。→ 対策済み。
- ORM: SQLAlchemy 経由で生 SQL 文字列連結なし。→ SQLi 面なし。

→ 前回「ツール未実行・手動代替」だった②を **Semgrep 実行済みで埋め戻し**。結論は不変で、本件の本丸は構文の脆弱性ではなく設計（認可）＝F-1〜F-3 だったことを裏づける。Semgrep が認可欠陥を出さないのは想定どおり（IDOR はツール非対象）。

### ③ CSPM（az 読み取り専用で実施）

`az` の読み取り専用クエリで実クラウド資産を確認（ミューテートなし・secret 値は読まない）。→ **致命傷なし**。実データストアは Azure PostgreSQL（`psql-rinaresua37c`）＋写真/PDF は Storage（`strinaresua37c` / Azure Files）。

| 対象 | 実測（読み取り） | 判定 |
| --- | --- | --- |
| Storage `strinaresua37c` | 匿名 BLOB=**無効** / HTTPS強制=**ON** / 最小TLS=**TLS1_0** / publicNW=有効(defaultAction Allow) | 匿名無効・HTTPS強制は良。TLS下限は要引き上げ→**F-7**。公開NW→**F-8** |
| PostgreSQL `psql-rinaresua37c`（v16） | firewall=**全開放ルール無し**（`AllowAllAzureServices` 0.0.0.0-0.0.0.0 のみ）/ SSL強制(`require_secure_transport`)=**ON** / publicNW=有効 | 致命傷なし。公開NW→**F-8**（Low） |
| Container Apps `ca-rinaresu-{api,web}` | external=**true** / allowInsecure=**false**（HTTPS強制）/ targetPort 8000・3000 | HTTPS強制は良。API公開露出は F-1/F-2 増幅要因だったが認証強化(v7)で解消 |

- 良い点: PostgreSQL は「全ネットワーク開放（0.0.0.0-255.255.255.255）」ルールが無く、SSL 強制も ON。Storage は匿名 BLOB アクセス無効＋HTTPS 強制。→ ネットワーク面の致命傷はない。
- 気になる点（多層防御・Low）: Storage 最小 TLS が TLS1_0（F-7）／Storage・PostgreSQL とも publicNetworkAccess 有効（F-8。Private Endpoint 化の余地）。
- **az で読めない項目（ポータル確認）**: Defender for Cloud の推奨事項・セキュアスコアは az 標準クエリでは取得できない。→ **統括がポータルで確認済み（2026-07-21）＝推奨事項 0件**（クリティカル/高/中/低 すべて0・アクティブな攻撃パス0）。集約ビューでも指摘なしで、az 読み取り（致命傷なし）と一致。**課金ガード=「環境設定/Defender プラン」は On にしない**（有料プランの入口）を厳守。既知の残課題（CLAUDE.md）：ACR admin ユーザー方式・DB 接続文字列/`SESSION_SECRET` の Container App secret 直書き（Key Vault 未使用）も次段で。

### ④ DAST（ZAP・本番受動＋ローカル能動）

OWASP ZAP（Docker）で 2 段階実施。→ **両段とも 0 FAIL（実脆弱性ゼロ）**。

- **① 本番 web へ受動 baseline**（非侵襲・攻撃を撃たない）: **0 FAIL / 10 WARN / 57 PASS**。WARN は全てセキュリティヘッダ不足（CSP・HSTS・X-Frame-Options・X-Content-Type-Options・Permissions-Policy・COEP）＋ `X-Powered-By` バナー露出。→ 実脆弱性ではなく多層防御の不足＝**F-6**。curl 実測でも本番 web は HTTP/2 200 で `cache-control` のみ返し、上記ヘッダは不在。
- **② ローカル起動 API へ能動 api-scan**（本番へは撃たない。ローカル `:8010` を dev API 無効・隔離 SQLite で起動し openapi を対象）: **0 FAIL / 2 WARN / 116 PASS**。**injection 系ルールは全 PASS**。WARN は X-Content-Type-Options・Cross-Origin-Resource-Policy の欠落のみ。→ coverage は公開面のみ（認証必須エンドポイントは 401 で未到達＝API 全面ペネテストではない、と正直に注記）。
- 本番へは受動のみ・能動はローカルのみ、を厳守。

**新規所見（DAST/CSPM）はいずれも多層防御の Low（F-6/F-7/F-8）で、Blocker/High はゼロ。**

### ⑤ 手動 IDOR（本丸・実証済み）

pytest 10ケース全 PASS。=「危険な挙動が期待どおり再現した」ことを固定した。

**F-1 [Blocker] `X-User-Id` なりすまし** ✅ **対応済み（2026-07-21・v7 本番デプロイ済み）** — トークン検証がなく、`get_current_user` は `db.get(User, x_user_id)` するだけ（`deps.py:16-38`）だった。
- **対応**: 方式B。`X-User-Id` の信用を撤廃し、ログイン/登録時に発行する HS256 署名付きセッション通行証（`sub`=user id・`exp`=7日）を `deps.py::get_current_user` が `Authorization: Bearer` で毎リクエスト検証。署名鍵は `SESSION_SECRET`（本番は Container App secret、未設定時は非SQLiteで fail-closed）。`backend/app/services/session_token.py` 新設。本番検証で認証なし `/api/devices` は 401。
- 証拠: `X-User-Id: 1` を付けて `GET /api/devices` → **200**（被害者Aとして認証通過）。`PATCH /api/users/me` → **200**（他人の推しを改ざん）。
- 攻撃シナリオ: ID は連番の整数。攻撃者は `1,2,3…` を回すだけで全ユーザーになりすまし、端末登録・送付・**受領（=ポイント/ランク付与）**・推し変更を実行できる。
- 影響: 全アカウントの乗っ取り＋不正なポイント経済の操作。確度: 実証済み（高）。

**F-2 [Blocker] 認証欠如による全ユーザー PII 露出・履歴 IDOR** ✅ **対応済み（2026-07-21・v7 本番デプロイ済み）** — ユーザー系 GET が `get_current_user` に依存していなかった（`routers/users.py`：`list_users`/`get_user`/`get_user_comment`/`get_user_history`）。
- **対応**: `get_user`/`get_user_comment`/`get_user_history` を認証必須＋**本人スコープ**化（`user_id != current_user.id` は 404 で存在秘匿）。全PII列挙だった `GET /api/users`（`list_users`）は**撤廃**（POST のみ残り GET は 405）。本番検証で `GET /api/users` は 405。
- 証拠: `GET /api/users` → **全ユーザー＋email 列挙**。`GET /api/users/1` → **email 露出**（`victim@example.com`）。`GET /api/users/1/history` → **他人の端末・送付履歴 200**。いずれも**認証ヘッダー無し**。
- 攻撃シナリオ: ヘッダーすら不要。連番 id で全ユーザーの email と行動履歴を機械収集できる。→ F-1 より参入障壁が低い。
- 影響: 実ユーザー全員の個人情報漏洩。確度: 実証済み（高）。

**F-3 [High] 伝票PDF 無認証取得** ✅ **対応済み（2026-07-21・v7 本番デプロイ済み）** — `GET /api/shipments/{id}/pdf` が `get_current_user` 非依存だった（`shipments.py:140-151`）。
- **対応**: 認証必須＋owner スコープを追加（他人/不存在は 404）。生 URL の新規タブ表示では Authorization を付けられないため、フロントを Bearer 付き Blob 取得（`api.fetchShipmentPdf`）→ object URL 表示に変更（トークンはクエリに載せない）。本番検証で認証なし PDF は 401。
- 証拠（静的）: shipment を id で引いて `FileResponse` を返すのみ。owner チェックなし。PDF 内容は仮ID・ニックネーム・端末一覧（`slip_pdf.py:95`）。※集荷/宛先は固定住所で、個人宅住所は含まない。
- 攻撃シナリオ: 連番 shipment_id を回して他人の伝票を収集。氏名相当の PII が漏れる。CLAUDE.md にも残課題として既記載。
- 対照: 同じ shipment を扱う `receive`/`share-text` は owner スコープを検証し 404 を返す（**防御 OK**）。→ pdf だけ掛け忘れ。

**対照（防御が効いている＝良い点）**: `POST /api/shipments/1/receive` を B で叩く → **404**、`GET /api/shipments/1/share-text` を B で → **404**、`GET /api/devices` をヘッダー無し → **401**。→ `get_current_user` を通す操作系は owner スコープ・存在秘匿が正しい。

## ■ 考察

穴は「認可越境（IDOR）」ではなく、より上流の **「認証そのものが偽造可能」＋「一部 GET に認証を掛け忘れ」** の2点に集約される。→ オブジェクト単位のスコープ判定（`user_id == current_user.id`）は操作系で正しく書けているため、`X-User-Id` を検証可能な資格情報に置き換え、ユーザー系 GET と PDF に `get_current_user` を必須化すれば、既存の認可ロジックがそのまま効く。修正は `deps.py` の一点差し替え＋各 GET への依存追加で、ルーター本体はほぼ無改変で済む。

ツールの限界も明確に出た。→ SCA（pip-audit/npm audit）は件数を出すが「upload 経路で到達可能か」までは判定しない。SAST（Semgrep）は構文の脆弱性を見るが、本件の本丸である**認可設計の欠陥は 0 件＝検出できない**。IDOR は人＝手動ハーネスでしか実証できない、という [[idor-bugs-require-manual-review-not-tools]] の裏付けが取れた。→ 5 種を回して**新規の Blocker/High が一切出なかった**ことは、本丸が最初から認可設計（F-1〜F-3・修正済み）に集約されていたことを補強する。

追実施で埋めた範囲: CSPM（az 読み取り）・DAST（受動 baseline＋ローカル能動）を実施済み。→ 致命傷なし。**Defender 推奨事項/セキュアスコアは統括がポータルで確認済み＝0件**（集約ビューでも指摘なし）。残るのは **認証済み DAST（Bearer 通行証を持たせた API 全面の能動スキャン）** のみで、認証必須 EP が 401 で未到達のため次段とする。

## ■ ネクストアクション

1. ✅ **［完了・v7］F-1**: `X-User-Id` 直結を撤廃し、ログイン時発行の署名付きセッション通行証（HS256・exp7日）を `get_current_user` で毎リクエスト検証に移行。本番デプロイ済み。
2. ✅ **［完了・v7］F-2**: ユーザー系 GET を認証必須＋本人限定に。`list_users` は削除（GET /api/users は 405）。email は本人のみ返す。本番デプロイ済み。
3. ✅ **［完了・v7］F-3**: `pdf` エンドポイントに認証＋owner スコープを追加（receive/share-text と同じ形）。フロントは Bearer 付き Blob 取得に変更。本番デプロイ済み。
4. ✅ **［完了・2026-07-21］F-4**: backend の python-multipart・requests・PyJWT・python-dotenv・fastapi・starlette を更新（pip-audit 0件）、frontend は `npm audit fix`（brace-expansion high 解消）。回帰確認は pytest 20件全PASS・ローカルスモークOK。恒常化として Snyk CI ゲート＋Dependabot を導入（ブランチ `security/f4-deps-and-ci`）。**本番反映は deploy CI 初回実行（v8）にて**（統括作業待ち）。
5. ⏳ **［次段・任意］F-5**: dev router を本番ビルドから物理除外、CORS `allow_credentials` を false に。
6. ⏳ **［次段・任意］F-6**: web/API に共通セキュリティヘッダ（CSP・HSTS・X-Frame-Options=DENY・X-Content-Type-Options=nosniff・Referrer-Policy・Permissions-Policy）を付与、`poweredByHeader:false`。
7. ⏳ **［次段・任意］F-7**: Storage 最小 TLS を TLS1_2 へ引き上げ（`az storage account update`。既存クライアントは TLS1_2 対応で影響なし）。
8. ⏳ **［次段・任意］F-8**: 本番強化時に Storage/PostgreSQL を Private Endpoint＋VNet 統合し公開ネットワーク無効化。
9. ✅ **［統括が確認済み・2026-07-21］** ポータルの Defender for Cloud 推奨事項＝**0件**（クリティカル/高/中/低 すべて0）。→ CSPM の集約ビューも指摘なしで確定。ACR admin→managed identity 移行、`SESSION_SECRET`/DB 接続文字列の Key Vault 化は次段で検討（**「環境設定/Defender プラン」は On にしない**＝有料課金の入口）。
10. ⏳ **［次段・Nice-to-have］** JWT 検証時に `require=["exp"]` を明示・トークン失効リスト検討・コメント整合の微修正。

## ■ まとめ

残る本丸だった F-1・F-2（＋F-3）は、認証を「検証可能な資格情報（署名付きセッション通行証）」に変え、掛け忘れた GET／PDF に認証＋本人スコープを足すことで**修正・本番デプロイ済み（v7）**。→ エンプラ最低ラインに到達。操作系の認可は元から正しく、土台の良さがそのまま活きた。**F-4（依存更新）も対応済み**（CIゲート導入込み。本番反映は deploy CI 初回実行 v8 にて）。**次段は F-5（多層防御）**。

### 付記（実施範囲・未実施の明示）

- 実施済み（**5種すべて**）: ① SCA（pip-audit/npm audit）・② SAST（**Semgrep** 0件＋手動レビュー＋秘匿値 grep）・③ CSPM（**az 読み取り専用**：storage/postgres/containerapp show・firewall list）・④ DAST（**ZAP** 本番web受動 baseline＋ローカルAPI能動 api-scan）・⑤ 手動 IDOR（pytest）。
- 未実施で次段に残すもの: 認証済み DAST（Bearer 通行証を持たせた API 全面の能動スキャン。現状 coverage は公開面のみ・認証EPは401で未到達）。※Defender 推奨事項・セキュアスコアは**統括がポータルで確認済み＝0件**（2026-07-21）。
- ツール実行環境（メタ）: Semgrep は `python3 -m pip install --user semgrep` で導入・52ファイル走査。CSPM は `az`（読み取りのみ・ミューテートせず）。DAST は Docker Desktop 起動後に `zaproxy/zap-stable`。recalc は `soffice --headless --convert-to`。→ いずれも本タスクで導入・実行済み。
- 検査バージョン記録: `backend/requirements.txt`（fastapi 0.115.0 / starlette 0.38.6 / python-multipart 0.0.9 / requests 2.32.3。修正で `PyJWT 2.9.0`・`python-dotenv 1.0.1` 追加）・`frontend/package-lock.json`。クラウド: Storage `strinaresua37c`・PostgreSQL `psql-rinaresua37c`(v16)・Container Apps `ca-rinaresu-{api,web}`（`rg-001-gen12`/japaneast）。
- 実証ハーネス: `backend/tests/test_idor_manual.py`（隔離 SQLite・実 dev DB 非汚染）。**修正後は「攻撃を弾く」向きに反転して 20 ケース全 PASS**。再実行: `cd backend && venv/bin/python -m pytest tests/test_idor_manual.py -v`。
- **修正・デプロイ状況（2026-07-21 追記）**: F-1/F-2/F-3 を方式B で修正し、統括承認のうえ本番デプロイ済み（api `rinaresu-api:v7`/rev `ca-rinaresu-api--0000011`、web `rinaresu-web:v7`）。`SESSION_SECRET` は Container App secret（`secretref`）で設定（**実値は本レポートに非記載**）。実 Google ログインの疎通は対話が要るため統括の受入確認に委ねる。git commit/push は本タスクでは未実施。
