# MLIT Real Estate MCP Server

日本の国土交通省「不動産情報ライブラリ」API を利用し、不動産取引価格・地価公示・都市計画などの情報を LLM (Large Language Model) エージェントに提供する MCP (Model Context Protocol) サーバーです。

## 特徴

- **MCP 対応**: Cursor, Claude Desktop などの MCP クライアントから直接利用可能。
- **キャッシュ機能**: API レスポンスをキャッシュし、API 制限や待機時間を緩和 (InMemory & File-based)。
- **GeoJSON/MVT 対応**: 大規模な地理データは MCP の `resource://` として効率的に受け渡し。
- **堅牢性**: API エラー時の自動リトライ、レート制限への対応。
- **統計情報**: キャッシュヒット率やエラー数をモニター可能。

## 必要なもの

- Python 3.11 以上
- **国土交通省 API キー**
  - [不動産情報ライブラリ API 利用申請](https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001) から取得してください。

## インストール

1. リポジトリをクローン:
   ```bash
   git clone https://github.com/takurot/real-estate-heatmap.git
   cd real-estate-heatmap
   ```

2. 依存パッケージのインストール:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. 環境変数の設定:
   `.env` ファイルを作成し、API キーを設定します。
   ```bash
   MLIT_API_KEY=your_api_key_here
   ```

## 使い方 (MCP サーバーとして実行)

### 1. Cursor / Claude Desktop での設定

MCP クライアントの設定ファイル (例: `claude_desktop_config.json` や Cursor の MCP 設定) に以下を追加します。

```json
{
  "mcpServers": {
    "mlit": {
      "command": "/absolute/path/to/real-estate-heatmap/.venv/bin/python",
      "args": ["-m", "mlit_mcp"],
      "env": {
        "MLIT_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### 2. コマンドラインでの動作確認

サーバーは標準入出力 (stdio) を使用します。起動チェックは `py test` で行います。

## 利用可能なツール一覧

| ツール名 | 説明 | 引数例 |
| --- | --- | --- |
| `mlit.list_municipalities` | 指定した都道府県の市区町村コード一覧を取得 | `{"prefectureCode": "13"}` |
| `mlit.fetch_transactions` | 不動産取引価格情報の検索・取得 (期間・場所指定) | `{"year_from": 2020, "year_to": 2020, "pref_code": "13", "city_code": "13101"}` |
| `mlit.fetch_transaction_points` | 取引情報のポイントデータを GeoJSON リソースとして取得 | `{"year_from": 2020, ...}` |
| `mlit.fetch_land_price_points` | 地価公示・地価調査ポイントの取得 | `{"zoom": 12, "x": 3639, "y": 1612, "year": 2023}` |
| `mlit.fetch_urban_planning_zones` | 都市計画区域・用途地域などの取得 | `{"zoom": 12, "x": ..., "y": ...}` |
| `mlit.fetch_school_districts` | 学区データの取得 (Vector Tile -> Base64 MVT) | `{"zoom": 12, "x": ..., "y": ...}` |
| `mlit.get_server_stats` | サーバーの統計情報 (リクエスト数, キャッシュヒット率など) を取得 | `{}` |

> **Note**: ポイント系データツール (`fetch_*_points`) はレスポンスが大きいため、MCP の `resource` URI を返却します。クライアントは `read_resource` で別途データを取得できます。

## 開発・テスト

### テスト実行
```bash
# 全テスト
pytest

# カバレッジ
pytest --cov=mlit_mcp
```

### コード品質チェック
```bash
# フォーマット
black .
# Lint
flake8 mlit_mcp tests
# 型チェック
mypy mlit_mcp
```

### ディレクトリ構成
- `mlit_mcp/`: サーバー本体コード
  - `tools/`: 各 MCP ツールの実装
- `tests/`: テストコード
  - `e2e/`: エンドツーエンドテスト

## ライセンス
MIT License
