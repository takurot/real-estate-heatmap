# 不動産価格成長率分析ツール

国交省「不動産取引価格情報」APIを使用して、都道府県ごとの市区町村単位での不動産価格の時系列変化（傾き）を分析し、成長率が高い市区町村を可視化するツールです。

## 機能

- 都道府県ごとの市区町村単位データを年度別に取得
- 価格の時間変化（傾き）を計算し、成長率が高い市区町村を抽出
- グラフ（PNG）とCSVデータの出力
- CLI インターフェースによる柔軟な設定

## セットアップ

### 前提条件

- Python 3.11 以上
- 国交省 API キー（[申請ページ](https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001)）

### インストール

1. リポジトリをクローン
```bash
git clone https://github.com/takurot/real-estate-heatmap.git
cd real-estate-heatmap
```

2. 仮想環境を作成・有効化
```bash
python3 -m venv env
source env/bin/activate  # macOS/Linux
# または
env\Scripts\activate  # Windows
```

3. 依存パッケージをインストール
```bash
pip install -r requirements.txt
```

4. 環境変数の設定
```bash
# .env ファイルを作成
cp .env.example .env

# .env ファイルを編集してAPIキーを設定
# HUDOUSAN_API_KEY=your_api_key_here
```

## 使い方

### 基本的な使い方

```bash
# デフォルト設定（全47都道府県、2015-2024年、上位5件）
python evalGrowthRate.py

# 特定の都道府県のみ（東京都と神奈川県）
python evalGrowthRate.py --prefectures 13 14

# 年度範囲と上位件数を指定
python evalGrowthRate.py --start-year 2020 --end-year 2024 --top-n 10

# 出力先を変更
python evalGrowthRate.py --output-dir my_output
```

### コマンドラインオプション

- `--start-year`: 開始年（デフォルト: 2015）
- `--end-year`: 終了年（デフォルト: 2024）
- `--top-n`: 上位何件を表示するか（デフォルト: 5）
- `--prefectures`: 対象都道府県コード（例: 13 14）。指定しない場合は全47都道府県
- `--output-dir`: 出力ディレクトリ（デフォルト: output）
- `--help`: ヘルプメッセージを表示

### 都道府県コード一覧

| コード | 都道府県 | コード | 都道府県 |
|--------|----------|--------|----------|
| 01 | 北海道 | 25 | 滋賀県 |
| 02 | 青森県 | 26 | 京都府 |
| 03 | 岩手県 | 27 | 大阪府 |
| 04 | 宮城県 | 28 | 兵庫県 |
| 05 | 秋田県 | 29 | 奈良県 |
| 06 | 山形県 | 30 | 和歌山県 |
| 07 | 福島県 | 31 | 鳥取県 |
| 08 | 茨城県 | 32 | 島根県 |
| 09 | 栃木県 | 33 | 岡山県 |
| 10 | 群馬県 | 34 | 広島県 |
| 11 | 埼玉県 | 35 | 山口県 |
| 12 | 千葉県 | 36 | 徳島県 |
| 13 | 東京都 | 37 | 香川県 |
| 14 | 神奈川県 | 38 | 愛媛県 |
| 15 | 新潟県 | 39 | 高知県 |
| 16 | 富山県 | 40 | 福岡県 |
| 17 | 石川県 | 41 | 佐賀県 |
| 18 | 福井県 | 42 | 長崎県 |
| 19 | 山梨県 | 43 | 熊本県 |
| 20 | 長野県 | 44 | 大分県 |
| 21 | 岐阜県 | 45 | 宮崎県 |
| 22 | 静岡県 | 46 | 鹿児島県 |
| 23 | 愛知県 | 47 | 沖縄県 |
| 24 | 三重県 | | |

## 出力構造

```
output/
├── 13/  # 東京都
│   ├── plots/
│   │   ├── growth_with_price_13.png
│   │   └── growth_with_price_per_unit_13.png
│   └── tables/
│       └── df_grouped.csv
├── 14/  # 神奈川県
│   └── ...
└── ...
```

- **plots/**: グラフ画像（PNG形式、DPI 150）
  - `growth_with_price_{pref}.png`: 平均価格の推移
  - `growth_with_price_per_unit_{pref}.png`: 平均坪単価の推移
- **tables/**: 集計データ（CSV形式）
  - `df_grouped.csv`: 市区町村 × 年度の集計データ

### CSVファイルの列

| 列名           | 型    | 説明                              |
| -------------- | ----- | --------------------------------- |
| `CityCode`     | str   | 5 桁市区町村コード（例: "13101"） |
| `CityName`     | str   | 市区町村名（例: "千代田区"）      |
| `Year`         | int   | 年度（例: 2024）                  |
| `Price`        | float | 平均取引価格（万円）              |
| `PricePerUnit` | float | 平均坪単価（万円/坪）             |

## Cursor IDE からの MCP アクセス

このプロジェクトには MCP（Model Context Protocol）サーバーが含まれており、Cursor IDE から直接アクセスできます。

### MCP サーバーの設定

1. **環境変数の設定**
   - `.env` ファイルに `MLIT_API_KEY` を設定してください（`HUDOUSAN_API_KEY` と同じ値を使用可能）

2. **Cursor の MCP 設定**
   - Cursor の設定ファイルに MCP サーバーを追加します
   - 設定ファイルの場所：
     - **macOS**: `~/Library/Application Support/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`
     - **Windows**: `%APPDATA%\Cursor\User\globalStorage\rooveterinaryinc.roo-cline\settings\cline_mcp_settings.json`
     - **Linux**: `~/.config/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`

3. **設定例**（仮想環境を使用する場合）:
   ```json
   {
     "mcpServers": {
       "mlit-mcp": {
         "command": "/path/to/real-estate/env/bin/python",
         "args": ["-m", "mlit_mcp"],
         "env": {
           "MLIT_API_KEY": "your-api-key-here"
         }
       }
     }
   }
   ```

   仮想環境を使わない場合:
   ```json
   {
     "mcpServers": {
       "mlit-mcp": {
         "command": "python",
         "args": ["-m", "mlit_mcp"],
         "env": {
           "MLIT_API_KEY": "your-api-key-here"
         }
       }
     }
   }
   ```

4. **Cursor の再起動**
   - 設定を反映させるため、Cursor を再起動してください

5. **MCP ツールの使用**
   - Cursor のチャットで、以下のように自然言語で指示できます：
     - 「mlit-mcp の list_municipalities ツールを使って東京（都道府県コード13）の市区町村一覧を取得して」
     - 「東京都の市区町村データを取得して」

### 利用可能な MCP ツール

- **`list_municipalities`**: 指定された都道府県内の市区町村一覧を取得
  - パラメータ:
    - `prefecture_code`: 2桁の都道府県コード（例: "13" は東京都）
    - `lang`: 言語（"ja" または "en"、デフォルト: "ja"）

### 設定例ファイル

プロジェクトルートの `.cursor/mcp-config.json.example` を参考にしてください。

## テスト

E2Eテストスイートを実行：

```bash
python test_e2e.py
```

テスト項目：
- CLIヘルプの表示
- 単一都道府県の実行
- 複数都道府県の実行
- 無効な引数のエラーハンドリング
- 出力ディレクトリ構造の確認

## トラブルシューティング

### APIキーが設定されていない

```
ValueError: APIキーが設定されていません。環境変数 'HUDOUSAN_API_KEY' にAPIキーを設定してください。
```

**解決方法**: `.env` ファイルに `HUDOUSAN_API_KEY` を設定してください。

### タイムアウトエラー

API の応答が遅い場合、タイムアウトが発生する可能性があります。現在は実装されていませんが、PR2でタイムアウト設定を追加予定です。

### データが取得できない

特定の年度・都道府県でデータが取得できない場合、以下のメッセージが表示されます：

```
No valid data available for {都道府県名}.
```

この場合、グラフは生成されませんが、処理は継続されます。

### フォントの警告

macOS以外の環境では、日本語フォントが見つからない場合に警告が表示されることがあります。フォントは自動的にフォールバックされます。

## 開発計画

現在は **PR1（クリーニングとCLI化）** が完了しています。

今後の予定：
- **PR2**: ネットワーク堅牢化（Session/Timeout/Retry）
- **PR3**: データ整形と永続化（CSV/Parquet）
- **PR4**: パフォーマンス向上（並列化・簡易キャッシュ）
- **PR5**: 可視化の整備（PNG出力の品質・一貫性）
- **PR6**: GeoJSONメトリクス生成（マップ用データ）
- **PR7-8**: Webマップ基盤と傾きの発散色コロプレス
- **PR9**: ドキュメント・パッケージング
- **PR10**: 解析品質向上（テスト追加）

詳細は `prompt/plan.md` を参照してください。

## データ利用規約

- **国交省API**: [利用規約](https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001)に従って使用してください
- データの二次配布・商用利用については、各APIの利用規約を確認してください

## ライセンス

このプロジェクトのライセンスは未定です。

## 貢献

プルリクエストやイシューの報告を歓迎します。

## 作者

- GitHub: [@takurot](https://github.com/takurot)

