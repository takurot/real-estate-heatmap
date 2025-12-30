# 実装計画

本リポジトリは「不動産APIのキャッシュ付きMCPサーバー」を主軸として開発し、その上で「価格成長率分析」などのアプリケーションを実現します。

## 概要

- **Phase 1: MCP サーバーの実装** (旧 PLAN_2)
  - Python/FastAPI/MCP SDK を用いたサーバー構築。
  - MLIT (国土交通省) API のラップ、キャッシュ、GeoJSON 化、MVT (Vector Tile) 対応。
- **Phase 2: 分析・可視化クライアントの実装** (旧 plan.md の適用)
  - MCP サーバーを利用してデータを取得し、価格推移分析や地図可視化を行うクライアント/スクリプト群。

---

## Phase 1: MCP サーバー実装 (Core)

### 前提
- 言語: Python 3.11+, `fastapi`, `mcp` SDK
- HTTP: `httpx.AsyncClient` + `tenacity` (retry) + `cachetools` (LRU) + 一時ファイル (GeoJSON/MVT)
- Auth: `.env` で `MLIT_API_KEY` を管理

### PR 一覧 (Phase 1)
| PR | タイトル | 概要 | 依存 |
| -- | -- | -- | -- |
| **PR1** | サーバー雛形と設定基盤 | MCP サーバー骨格、設定ロード (完了済み) | - |
| **PR2** | HTTP クライアント＆キャッシュ層 | 共通 HTTP/Retry/LRU/FileCache (完了) | PR1 |
| **PR3** | `list_municipalities` ツール | 市区町村一覧 (XIT002) (完了) | PR2 |
| **PR4** | `fetch_transactions` ツール | 取引データ (XIT001) + 整形 (完了) | PR2 |
| **PR5** | `fetch_transaction_points` ツール | 取引ポイント (XIT003) + resource 化 | PR2 |
| **PR6** | `fetch_land_price_points` & `urban_planning` | 地価公示 (XKT001) / 都市計画 (XKT011) | PR5 |
| **PR7** | `fetch_school_districts` & MVT | 学区 (XKT021) + MVT base64 | PR5 |
| **PR8** | ロギング・監視・キャッシュ運用 | 構造化ログ、Stats、Force Refresh | PR2 |
| **PR9** | 統合テストとドキュメント | E2E テスト, 負荷テスト, README 完成 | PR3-8 |

### 詳細仕様

#### PR2: HTTP クライアント＆キャッシュ層
- `httpx.AsyncClient` シングルトン。
- `tenacity`: 429/5xx 時に指数バックオフ。
- キャッシュ:
  - JSON: メモリ LRU (TTL 付き)。
  - GeoJSON/Large Data: 一時ファイル (`tempfile`) + ハッシュキー。
- `force_refresh` フラグ対応。

#### PR4: `fetch_transactions` ツール
- `XIT001` ラッパー。
- 引数: `year_from`, `year_to`, `pref_code`, `city_code`, `classification`。
- 出力: JSON (デフォルト) または `table` (分析用、簡易形式)。

#### PR5, 6, 7: Geo データの Resource 化
- 1MB を超える GeoJSON やバイナリ (MVT) は MCP の `resource://` URI を返却し、メモリ圧迫を回避。
- `fetch_transaction_points` (PR5), `fetch_land_price_points` (PR6), `fetch_school_districts` (PR7) で適用。

---

## Phase 2: 分析クライアント実装 (Application)

Phase 1 完了後、MCP サーバーのクライアントとして分析機能（旧 `evalGrowthRate.py` 相当）を実装・移行します。

### PR10: 分析スクリプトの MCP 対応 (Client)
- **目的**: 旧 `evalGrowthRate.py` のロジックを MCP クライアント経由に移行。
- **実装**:
  - `mcp` クライアントを使用して `fetch_transactions` を呼び出し。
  - 取得データを Pandas DataFrame に変換し、傾き (CAGR/OLS) 計算ロジックを適用。
  - CSV/Parquet 保存機能。
- **メリット**: API 制限管理やキャッシュをサーバー側に委譲できるため、クライアントコードがシンプルになる。

### PR11: 可視化・レポート生成
- **目的**: グラフ (PNG) 生成とランキング出力。
- **実装**:
  - `matplotlib`/`seaborn` を用いた価格推移グラフ。
  - 傾きランキングの CSV 出力。

### PR12: Web Map 可視化
- **目的**: Google Maps / OpenLayers 上での可視化。
- **実装**:
  - `fetch_transaction_points` や `fetch_urban_planning_zones` で取得した GeoJSON を表示。
  - 年次スライダーによる時系列変化の可視化。

---

## 将来の拡張
- **ベクトルタイルサーバー化**: MVT をデコードせず、そのままタイルサーバーとして配信する拡張。
- **DB 連携**: 取得データを PostgreSQL/PostGIS に永続化。
