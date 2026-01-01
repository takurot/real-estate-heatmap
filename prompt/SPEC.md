## MLIT 不動産情報ライブラリ MCP サーバー仕様

### 1. 背景と目的
- 国土交通省「不動産情報ライブラリ」の公開 API 群（取引価格、地価公示、都市計画など）を MCP (Model Context Protocol) 経由で利用可能にする。
- LLM クライアント（Cursor など）から自然言語で「東京都の取引データを取得して」といった指示が可能になる。
- キャッシュ機構とレート制限ハンドリングをサーバー側で実装し、API 利用の効率化とコンプライアンス遵守を担保する。

### 2. システム構成
- **言語**: Python 3.11+
- **フレームワーク**: `fastapi`, `mcp` SDK
- **HTTP クライアント**: `httpx` + `tenacity` (Retry)
- **キャッシュ**: In-memory LRU (JSON) + File Cache (GeoJSON/MVT)
- **認証**: `.env` による `MLIT_API_KEY` 管理

### 3. 提供ツール (Tools)

各ツールは `mlit.` プレフィックスを持ち、snake_case で命名される。
パラメータ入力は JSON 上では **camelCase** を推奨（Pydantic alias 対応）。

| Tool 名 | 説明 | 必須パラメータ | オプション |
| --- | --- | --- | --- |
| `mlit.list_municipalities` | 都道府県内の市区町村一覧を取得する (XIT002) | `prefectureCode` | `lang`, `forceRefresh` |
| `mlit.fetch_transactions` | 不動産取引価格データを取得する (XIT001) | `yearFrom`, `yearTo`, `area` | `classification`, `format`, `forceRefresh` |
| `mlit.summarize_transactions` | 取引データの集計統計を取得 (XIT001) | `yearFrom`, `yearTo`, `area` | `classification`, `forceRefresh` |
| `mlit.fetch_transaction_points` | 取引データ (ポイント) を GeoJSON で取得 (XIT003) | `area`, `yearFrom`, `yearTo` | `bbox`, `forceRefresh` |
| `mlit.fetch_land_price_points` | 地価公示・都道府県地価調査を取得 (XKT001) | `area`, `year` | `responseFormat`, `forceRefresh` |
| `mlit.fetch_urban_planning_zones` | 都市計画区域などを取得 (XKT011想定) | `area` | `bbox`, `responseFormat`, `forceRefresh` |
| `mlit.fetch_school_districts` | 小学校区などのタイルデータを取得 (XKT021想定) | `area`, `z`, `x`, `y` | `crs`, `forceRefresh` |
| `mlit.fetch_hazard_risks` | 洪水・土砂災害リスク情報を取得 | `latitude`, `longitude` | `riskTypes`, `forceRefresh` |
| `mlit.get_server_stats` | サーバーの内部統計（キャッシュヒット率など）を取得 | - | - |

#### 共通仕様
- **forceRefresh**: `true` を指定するとキャッシュを無視して API を叩き直す。
- **area**: 都道府県コード (2桁) または 市区町村コード (5桁)。

### 4. レスポンス仕様 ("meta" フィールド)
全てのツールレスポンスは `meta` オブジェクトを含み、データの出典とキャッシュ状況を示す。

```json
{
  "data": [...],
  "meta": {
    "source": "reinfolib.mlit.go.jp",
    "dataset": "XIT001",
    "cacheHit": true,
    "fetchedAt": "2024-01-01T12:00:00Z"
  }
}
```

- **Large Response**: GeoJSON などサイズが大きい場合、`resource://` URI を返す場合がある（クライアントは `read_resource` で取得）。

### 5. エラーハンドリング
- **401 Unauthorized**: API キー未設定または無効。
- **429 Too Many Requests**: 指数バックオフでリトライ後、失敗すればエラー返却。
- **404 Not Found**: 引数に対応するデータが存在しない場合。
- **Validation Error**: 引数が不正（例: 存在しない都道府県コード）。

### 6. 開発・運用
- **環境変数**: `MLIT_API_KEY` 必須。
- **ログ**: 構造化ログを出力 (JSON)。API キーはマスクする。
- **テスト**: `pytest` による単体テストおよび統合テスト。

### 7. 今後の拡張案 (Proposed)

#### データ分析系ツール

| Tool 名 | 説明 | 必須パラメータ | オプション |
| --- | --- | --- | --- |
| `mlit.compare_areas` | 複数エリア間の価格・取引量を比較分析 | `areas` (配列), `yearFrom`, `yearTo` | `metrics`, `classification` |
| `mlit.calculate_unit_price` | 坪単価・㎡単価を計算して返却 | `area`, `yearFrom`, `yearTo` | `priceType` (tsubo/sqm), `classification` |
| `mlit.get_market_trends` | 価格推移・成長率 (CAGR, YoY) を計算 | `area`, `yearFrom`, `yearTo` | `trendType`, `classification` |
| `mlit.get_price_distribution` | 価格帯別の分布統計を取得 | `area`, `yearFrom`, `yearTo` | `binSize`, `classification` |
| `mlit.detect_outliers` | 異常値・特異取引を検出 | `area`, `yearFrom`, `yearTo` | `method` (iqr/zscore), `threshold` |

#### 運用系ツール
- **`mlit.clear_cache`**: キャッシュを手動でクリアする管理用ツール。
