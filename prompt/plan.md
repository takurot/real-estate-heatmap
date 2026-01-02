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
| **PR10** | `summarize_transactions` ツール             | 大規模データ向け集計統計ツール (完了)       | PR4   |
| **PR14** | `fetch_hazard_risks` ツール                 | 災害リスク情報の取得 (完了)                  | PR2   |

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

### Future Expansion (Phase 2+)

#### データ分析系ツール

| PR | タイトル | 概要 | 依存 |
| -- | -- | -- | -- |
| **PR15** | `get_market_trends` ツール | 市場トレンド分析（CAGR、YoY成長率）をサーバー側で実行 (完了) | PR10 |
| **PR17** | `compare_areas` ツール | 複数エリアの価格・取引量比較分析 | PR4 |
| **PR18** | `calculate_unit_price` ツール | 坪単価・㎡単価の計算ツール | PR4 |
| **PR19** | `get_price_distribution` ツール | 価格帯別分布・ヒストグラム生成 | PR10 |
| **PR20** | `detect_outliers` | 異常値・特異取引検出 (IQR/Z-score) | PR10 |
| **PR21** | `fetch_safety_info` | 総合防災情報 (津波・高潮・避難所) (完了) | PR14 |
| **PR22** | `fetch_nearby_amenities` | 周辺施設検索 (病院・教育・公共) | PR2 |
| **PR23** | `fetch_station_stats` | 駅別乗降客数データ | PR2 |
| **PR24** | `fetch_population_trend` | 将来推計人口 (500mメッシュ) | PR2 |
| **PR25** | `search_by_station` | 駅名ベースのエリア検索 | PR2 |
| **PR26** | `compare_market_to_land_price` | 実勢価格 vs 公示地価の乖離分析 | PR4 |
| **PR27** | `generate_area_report` | 総合エリアサマリーレポート生成 | PR15-26 |

#### 詳細仕様

##### PR15: `get_market_trends` ツール
- **目的**: 取引価格データの時系列分析
- **機能**:
  - CAGR (年平均成長率) 計算
  - YoY (前年比) 成長率計算
  - 価格トレンド (上昇/下降/横ばい) 判定
- **出力**: 成長率、トレンド判定、信頼区間

##### PR17: `compare_areas` ツール
- **目的**: 複数エリア間の比較分析
- **機能**:
  - 平均価格比較
  - 取引件数比較
  - 価格推移の相関分析
- **出力**: エリア別統計、ランキング、相関係数

##### PR18: `calculate_unit_price` ツール
- **目的**: 単価計算の標準化
- **機能**:
  - 坪単価 (価格 ÷ 面積 × 3.30578)
  - ㎡単価 (価格 ÷ 面積)
  - 物件タイプ別集計
- **出力**: 平均/中央値/分布

##### PR19: `get_price_distribution` ツール
- **目的**: 価格帯別の分布分析
- **機能**:
  - ヒストグラム用のビン分割
  - パーセンタイル計算
  - 正規分布適合度判定
- **出力**: ビン別件数、累積分布、統計量

##### PR21: `fetch_safety_info` ツール
- **目的**: 洪水・土砂災害以外の高度な防災情報の提供
- **機能**:
  - 津波浸水想定、高潮浸水想定の取得
  - 避難施設（指定緊急避難場所など）の近傍検索
- **出力**: リスクレベル、最寄りの避難施設情報

##### PR22: `fetch_nearby_amenities` ツール
- **目的**: 住環境の利便性評価
- **機能**:
  - 医療機関、保育園、小空学校などの施設種別検索
  - 指定半径内での件数、最寄り施設までの距離計算
- **出力**: 施設一覧、利便性スコア候補

##### PR23: `fetch_station_stats` ツール
- **目的**: 交通アクセスの活気・流動性分析
- **機能**:
  - 駅別の乗降客数（年度別）
  - 前年比増減の計算
- **出力**: 乗降客数推移、利用者数ランキング

##### PR24: `fetch_population_trend` ツール
- **目的**: エリアの将来性分析
- **機能**:
  - 500mメッシュ単位の将来推計人口（2050年まで）
  - 生産年齢人口比率などの属性分析（可能な場合）
- **出力**: 人口増加率、将来人口予測グラフ用データ

##### PR25: `search_by_station` ツール
- **目的**: ユーザーフレンドリーな検索インターフェース
- **機能**:
  - 駅名から代表点（緯度経度）を特定
  - 周辺市区町村コードの自動特定、または半径指定検索
- **出力**: 該当エリアの取引データサマリー

##### PR26: `compare_market_to_land_price` ツール
- **目的**: 市場の適正価格評価
- **機能**:
  - 直近の取引価格平均と公示地価の比率計算（乖離率）
  - 乖離率の過去推移分析
- **出力**: 乖離率、過熱感/割安感の判定

##### PR27: `generate_area_report` ツール
- **目的**: 分散した情報の統合提供
- **機能**:
  - 市場トレンド、防災、利便性、将来人口を1つのレポートに集約
  - LLMが読みやすい構造化Markdown形式で出力
- **出力**: 総合サマリーレポート

#### 運用系ツール

| PR | タイトル | 概要 | 依存 |
| -- | -- | -- | -- |
| **PR16** | `clear_cache` ツール | デバッグ・運用用のキャッシュクリア機能 | PR2 |
