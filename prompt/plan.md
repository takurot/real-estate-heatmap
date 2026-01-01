# 実装計画

本リポジトリは「不動産 API のキャッシュ付き MCP サーバー」を主軸として開発し、その上で「価格成長率分析」などのアプリケーションを実現します。

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

| PR      | タイトル                                     | 概要                                         | 依存  |
| ------- | -------------------------------------------- | -------------------------------------------- | ----- |
| **PR1** | サーバー雛形と設定基盤                       | MCP サーバー骨格、設定ロード (完了済み)      | -     |
| **PR2** | HTTP クライアント＆キャッシュ層              | 共通 HTTP/Retry/LRU/FileCache (完了)         | PR1   |
| **PR3** | `list_municipalities` ツール                 | 市区町村一覧 (XIT002) (完了)                 | PR2   |
| **PR4** | `fetch_transactions` ツール                  | 取引データ (XIT001) + 整形 (完了)            | PR2   |
| **PR5** | `fetch_transaction_points` ツール            | 取引ポイント (XPT001) + resource 化 (完了)   | PR2   |
| **PR6** | `fetch_land_price_points` & `urban_planning` | 地価公示 (XKT001) / 都市計画 (XKT011) (完了) | PR5   |
| **PR7** | `fetch_school_districts` & MVT               | 学区 (XKT004) + MVT base64 (完了)            | PR5   |
| **PR8** | ロギング・監視・キャッシュ運用               | 構造化ログ、Stats、Force Refresh (完了)      | PR2   |
| **PR9** | 統合テストとドキュメント                     | E2E テスト, 負荷テスト, README 完成 (完了)   | PR3-8 |
| **PR10** | `summarize_transactions` ツール             | 大規模データ向け集計統計ツール (実装中)     | PR4   |

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

#### PR7: `fetch_school_districts` ツール - 学区情報

- **API**: MLIT XKT004 データセット（小学校区データ）
- **形式**: タイル座標ベース（z/x/y）の GeoJSON または MVT (PBF)
- **座標変換**:
  - 緯度・経度からタイル座標への変換が必要
  - `gis_helpers.lat_lon_to_tile(lat, lon, zoom)` 関数を実装済み
  - `gis_helpers.bbox_to_tiles(min_lat, min_lon, max_lat, max_lon, zoom)` でエリア全体のタイルリストを取得可能
- **パラメータ**:
  - `z`: Zoom level (11-15)
  - `x`, `y`: Tile coordinates
  - `administrative_area_code`: 5 桁の行政区域コード（オプション、カンマ区切りで複数指定可能）
  - `response_format`: 'geojson' または 'pbf'
- **使用例**:

  ```python
  from mlit_mcp.tools.gis_helpers import lat_lon_to_tile

  # 東京駅の座標からタイル座標を取得
  tile_x, tile_y = lat_lon_to_tile(35.6812, 139.7671, zoom=13)

  # 学区情報を取得
  result = await fetch_school_districts(z=13, x=tile_x, y=tile_y)
  ```

- **注意点**:
  - エリア全体をカバーするには複数のタイルを取得する必要がある
  - 大容量データ（>1MB）は `resource_uri` として返却される
  - クライアント側で座標変換を実装する必要がある

#### PR8: ロギング・監視・キャッシュ運用

- **構造化ログ**: `logging` モジュールによるリクエスト・エラー・キャッシュ状態の記録 (JSON 向けの `extra` フィールド付与)。
- **Stats**: キャッシュヒット率、API エラー数、リクエスト総数を `get_server_stats` ツールで公開。
- **Force Refresh**: 全ツールで `force_refresh=True` によるキャッシュバイパスを検証済み。

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

### PR11: 可視化・レポート生成 (完了)

- **目的**: グラフ (PNG) 生成とランキング出力。
- **実装**:
  - `example/visualize_market.py` スクリプトの実装。
  - `FetchTransactionsTool` を利用したデータ取得。
  - `matplotlib`/`seaborn`/`pandas` を用いたグラフ生成:
    - **価格推移グラフ**: 平均取引価格の年次推移 (Line Chart)。
    - **価格分布**: 最新年の価格ヒストグラム (Histogram)。
    - **特異点分析**: 築年数 vs 価格の相関 (Scatter Plot)。
  - ランキング CSV 出力。

### PR12: Web Map 可視化

- **目的**: Google Maps / OpenLayers 上での可視化。
- **実装**:
  - `fetch_transaction_points` や `fetch_urban_planning_zones` で取得した GeoJSON を表示。
  - 年次スライダーによる時系列変化の可視化。

---

## 将来の拡張

- **ベクトルタイルサーバー化**: MVT をデコードせず、そのままタイルサーバーとして配信する拡張。
- **DB 連携**: 取得データを PostgreSQL/PostGIS に永続化。

### Fixes & Improvements

| PR | タイトル | 概要 | 依存 |
| -- | -- | -- | -- |
| **PR13** | Resource loading fix (cache) | ツールがキャッシュファイルを正しく読み込めない不具合を修正 | - |
