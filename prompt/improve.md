## evalGrowthRate.py 改善提案・機能拡張案

### 評価サマリー

現状の提案は**良好な基盤**を持っていますが、以下の観点で補強が必要です：

1. **具体性の不足**: API レート制限、市区町村境界データの入手方法、Google Maps API キーのセキュリティ扱いなど、運用上の制約が不明確。
2. **データ構造の曖昧さ**: `df_grouped` の列定義、GeoJSON の `CityCode` と API の `MunicipalityCode` の対応関係が未整備。
3. **テスト戦略の欠如**: 単体テスト、統合テスト、欠損・外れ値のエッジケースへの対処が言及されていない。
4. **セキュリティ考慮**: API キー、地図キーの管理、公開リポジトリでの扱いが不十分。
5. **パフォーマンス指標**: 並列化の効果測定、キャッシュヒット率、想定実行時間が不明。

以下、修正版を示します。

---

### 現状の把握（スクリプトの概要）

- **目的**: 国交省「不動産取引価格情報」API（`https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001`）から、都道府県ごとの市区町村単位データを年度別に取得し、価格の時間変化（傾き）上位の市区町村を可視化。
- **入力**: 環境変数 `HUDOUSAN_API_KEY`、年度範囲（2015–2024 固定）、都道府県（47 都道府県固定）、`priceClassification = "01"`。
- **処理**:
  - 各年度 × 各都道府県で API を逐次呼び出し、`MunicipalityCode`/`Municipality`/`TradePrice`/`PricePerUnit` を収集。
  - 市区町村 × 年に集計（平均）し、回帰の傾きが大きい市区町村を上位 5 件抽出。
  - 価格（`Price`）と坪単価（`PricePerUnit`）の推移を線グラフで保存（都道府県ごとに 2 枚）。
- **出力**: `growth_with_price_{pref}.png`, `growth_with_price_per_unit_{pref}.png` をカレント直下に保存。
- **API 仕様（要確認）**:
  - レート制限: 要確認（未公開の場合、保守的に 1 req/sec 想定）
  - 応答サイズ: 1 都道府県 ×1 年で数 KB ～数 MB（市区町村数・取引件数に依存）
  - タイムアウト推奨: 10–30 秒

### 気づいた問題点 / バグの可能性

#### 致命的（動作に影響）

- **傾き算出に未集約のデータを使用**（重大度: 高）
  - `df_grouped` を作成しているが未使用のまま、傾きは生データ `df` で計算しているため、同一年に複数行があると回帰が歪む可能性。
  - → **修正**: 傾き計算は `df_grouped`（市区町村 × 年で平均済み）を用いるべき。
  - 影響範囲: 傾き上位の市区町村ランキングが誤る可能性。

#### 機能的問題（運用に影響）

- **ネットワーク耐障害性の不足**（重大度: 中）
  - `requests.get` に `timeout` が無く、リトライや指数バックオフ、429/5xx ハンドリングも未実装。
  - → **修正**: `Session` + `timeout=10` + `urllib3.Retry` (max_retries=3, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])。
- **逐次実行で遅い**（重大度: 中）
  - 年 × 都道府県の全組み合わせ（10 年 × 47 県 = 470 リクエスト）を直列で呼び出し。1 req/sec 制限なら約 8 分。
  - → **修正**: `ThreadPoolExecutor` (max_workers=4~8、API 規約次第) で並列化、キャッシュ導入で 2 回目実行は数秒。

#### 可読性・保守性の問題

- **変数名の不整合**（重大度: 低）
  - `top_num = 5` に対し、変数名が `top_10_cities`/`top_10_city_names` となっており可読性が低い。
  - → **修正**: `top_n` へ統一。
- **可視化の固定的設定**（重大度: 低）
  - 上位件数、年度範囲、対象指標（価格/坪単価）等がハードコード。
  - → **修正**: `argparse` で引数化。
- **出力先の管理**（重大度: 低）
  - 画像が作業ディレクトリ直下に多数生成（47×2=94 枚）。`output/` 等の明示的な保存先や命名規約、DPI 指定が無い。
  - → **修正**: `output/{pref}/plots/`, `output/{pref}/tables/` で階層化。
- **データ出力が無い**（重大度: 中）
  - 集計済みテーブル（CSV/Parquet）の保存が無く、再分析・再可視化がしづらい。
  - → **修正**: `df_grouped.csv` と全県結合版を保存。
- **ログ/進捗が粗い**（重大度: 低）
  - `print` ベースで情報が散発的。ログレベルや進捗バーが無い。
  - → **修正**: `logging` (INFO/DEBUG) + `tqdm`。
- **フォント依存**（重大度: 低）
  - `Hiragino Sans` 固定で他環境だと文字化け・フォールバック不在。
  - → **修正**: フォールバックチェーン設定（`['Hiragino Sans', 'Noto Sans CJK JP', 'MS Gothic', 'DejaVu Sans']`）。

### 改善提案（実装しやすい順）

1. **構造化・引数化**

   - `argparse` を導入し、以下を引数化:
     - 年度範囲、上位件数、対象都道府県（複数指定）、指標（価格/坪単価/両方）、出力先、DPI、線形回帰の対象列、最小年数など。
   - `main()` を設け、`fetch → transform → analyze → plot → export` の関数分割。

2. **傾き計算の是正**

   - `df_grouped`（市区町村 × 年の平均）を用いて `np.polyfit`。`Year` が 2 未満は除外。
   - 価格と坪単価の双方で傾きを算出できるように `target_col` を引数化。

3. **ネットワーク堅牢化**

   - `requests.Session()` の再利用、`timeout`（例: 10 秒）、`Retry`（`urllib3.util.retry`）や指数バックオフの実装。
   - 429/5xx に対するリトライ、最大試行回数と待機の上限設定。

4. **パフォーマンス**

   - `concurrent.futures.ThreadPoolExecutor` による年 × 都道府県の並列化（同時接続数を制御）。
   - 簡易キャッシュ（`cache/{year}_{pref}.json`）で再取得を回避。

5. **出力の整理**

   - `output/{pref}/plots/` に PNG、`output/{pref}/tables/` に CSV を保存。
   - 集約済みデータのマージ版（全都道府県横断）も保存。
   - 画像は `dpi` 指定、凡例の列数・位置調整、色パレット統一。

6. **品質向上（解析面）**

   - 外れ値の影響を低減（中央値・分位点、ロバスト回帰 Theil–Sen など）。
   - サンプル数しきい値（例: 年 × 市区町村で観測 N≥K）を導入。
   - CAGR、前年度比、移動平均など補助指標の算出。

7. **UX/運用**

   - `tqdm` による進捗バー、`logging` による INFO/DEBUG ログ出力。
   - `.env`（`python-dotenv`）対応、`requirements.txt`/`pyproject.toml` 整備、README 追記。
   - 例外時も中間生成物は保存し、再実行でスキップ可能に（チェックポイント）。

8. **フォントと国際化**
   - `Hiragino Sans` → `Noto Sans CJK JP` などのフォールバック設定を追加。

### 機能拡張案

- **指標の拡充**: 価格と坪単価の双方で傾き上位/下位、市区町村ランキング表（CSV/Markdown/PNG テーブル）。
- **地図可視化**: 県内の市区町村を色分けしたコロプレス（`geopandas`/`folium`/`plotly`）。
- **対話的ダッシュボード**: `Plotly Dash` / `Streamlit` で年度・県・上位件数を操作可能に。
- **レポート自動生成**: 県ごとに Markdown/HTML レポートを出力（グラフ埋め込み、要約統計、上位市区町村リスト）。
- **比較分析**: 期間 A vs 期間 B の傾き差分、パンデミック前後比較など。
- **データ管理**: 取得データを Parquet 化してバージョン管理、メタ情報（取得日時・API レスポンスヘッダ）付与。

### リファクタリング方針（モジュール分割の一例）

- `client.py`: API クライアント（セッション、リトライ、キャッシュ）。
- `transform.py`: 型変換、クリーニング、集計（市区町村 × 年の平均など）。
- `analyze.py`: 傾き・CAGR・前年度比などの指標計算。
- `plot.py`: 折れ線、ランキングバー、ヒートマップ、地図描画。
- `cli.py`: 引数パースとサブルーチン起動（fetch/analyze/plot/report）。

### コード断片（イメージ）

傾き計算（集計済みデータを使用）:

```python
def compute_slopes(df_grouped: pd.DataFrame, target_col: str = "Price") -> dict[tuple[str, str], float]:
    slopes: dict[tuple[str, str], float] = {}
    for (city_code, city_name), g in df_grouped.groupby(["CityCode", "CityName"]):
        gg = g.sort_values("Year")
        if gg["Year"].nunique() < 2:
            continue
        x = gg["Year"].to_numpy()
        y = gg[target_col].to_numpy()
        slope, _ = np.polyfit(x, y, 1)
        slopes[(city_code, city_name)] = slope
    return slopes
```

並列取得（簡易例・同時数は API 規約に応じて調整）:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

def fetch_one(session: requests.Session, year: int, pref: str, key: str) -> list[dict]:
    params = {"year": year, "area": pref, "priceClassification": "01"}
    headers = {"Ocp-Apim-Subscription-Key": key}
    resp = session.get(API_URL, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", []) if data.get("status") == "OK" else []

with requests.Session() as s, ThreadPoolExecutor(max_workers=8) as ex:
    futures = [ex.submit(fetch_one, s, y, pref, API_KEY) for y in years]
    for fut in tqdm(as_completed(futures), total=len(futures)):
        rows = fut.result()
        # ここで整形・蓄積
```

### 最初に取り組むと効果が大きい変更（優先度案）

1. 傾き計算の是正（`df_grouped` を利用）と変数名整理（`top_n` へ統一）。
2. 引数化＋出力ディレクトリ整備＋ CSV 併走出力。
3. セッション＋タイムアウト＋リトライ導入。
4. 並列化＋進捗バー導入。
5. 解析の強化（サンプル数しきい値、CAGR 等）。

### 付録：運用・環境

#### 依存パッケージ（`requirements.txt`）

```
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
seaborn>=0.13.0
requests>=2.31.0
tqdm>=4.66.0
python-dotenv>=1.0.0
urllib3>=2.0.0
```

#### 環境設定（`.env`）

```bash
# 国交省 API キー（要申請: https://www.reinfolib.mlit.go.jp/）
HUDOUSAN_API_KEY=your_api_key_here

# Google Maps API キー（任意、Web マップ表示時のみ）
GOOGLE_MAPS_API_KEY=your_google_maps_key_here
```

**重要**: `.env` は `.gitignore` に追加し、公開リポジトリにコミットしない。`.env.example` をテンプレートとして用意。

#### 市区町村境界データの入手

- **推奨ソース**: 国土数値情報「行政区域データ」（GeoJSON/Shapefile）
  - URL: https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-v3_1.html
  - 最新年度版をダウンロードし、`data/boundaries.geojson` に配置。
  - `properties.N03_007` が 5 桁市区町村コード（先頭 2 桁が都道府県）。
- **前処理**: API の `MunicipalityCode` と境界データのコードが不一致の場合、マッピング表（CSV）を別途用意。

#### README 追記項目

- セットアップ手順（venv、依存インストール、`.env` 設定）
- API キーの申請方法・レート制限の確認先
- 実行例（最小、全県、特定県のみ）
- 出力ディレクトリ構造
- トラブルシューティング（タイムアウト、キャッシュクリア、文字化け）
- ライセンス・データ利用規約への言及

### マップでの傾き色分け（期間・アルゴリズム可変）

- **目的**: スライダーだけでは一瞥で変化量の大小が分かりづらいため、ゼロを中心とした発散色スキーム（青=マイナス、大=赤）で傾きを塗り分け。年区間とアルゴリズムを切替可能にする。

- **UI 提案**

  - 期間選択: `開始年`/`終了年`（ダブルハンドル or 2 セレクト）
  - アルゴリズム: `OLS（最小二乗）` / `Theil–Sen` / `CAGR（年平均成長率）`
  - 対象指標: `Price` / `PricePerUnit`
  - 最小年数: 期間内の有効データ年数 ≥ N（例: 2）
  - スケーリング: `そのまま` / `年当たり変化量` / `Z スコア`（任意）
  - カラードメイン: 絶対値の 95 パーセンタイルを上限（外れ値耐性）

- **データ要件**

  - GeoJSON `feature.properties.metrics[year] = { Price, PricePerUnit }` を保持（既提案の構造）
  - 前計算は不要（ブラウザで期間・アルゴリズムごとにオンザフライ計算可能）

- **Python（任意: バックエンド側の検証/バッチ算出に）**

```python
from typing import Literal
import numpy as np

def compute_slope_xy(years, values, method: Literal["ols","theil-sen","cagr"] = "ols"):
    years = np.asarray(years, dtype=float)
    values = np.asarray(values, dtype=float)
    mask = np.isfinite(years) & np.isfinite(values)
    years, values = years[mask], values[mask]
    if years.size < 2:
        return None
    if method == "ols":
        slope, _ = np.polyfit(years, values, 1)
        return float(slope)
    if method == "theil-sen":
        diffs = []
        for i in range(len(years) - 1):
            for j in range(i + 1, len(years)):
                denom = years[j] - years[i]
                if denom != 0:
                    diffs.append((values[j] - values[i]) / denom)
        return float(np.median(diffs)) if diffs else None
    if method == "cagr":
        v0, v1 = values[0], values[-1]
        t = years[-1] - years[0]
        if v0 <= 0 or t <= 0:
            return None
        return float((v1 / v0) ** (1.0 / t) - 1.0)
    return None
```

- **フロントエンド（Google Maps JS）: 期間・手法に応じて傾きを算出し色分け**

```html
<!-- UI 例: 年の From/To、アルゴリズム選択、指標選択 -->
<label
  >期間: <input id="from" type="number" value="2018" /> -
  <input id="to" type="number" value="2024"
/></label>
<label
  >手法:
  <select id="method">
    <option value="ols">OLS</option>
    <option value="theil-sen">Theil–Sen</option>
    <option value="cagr">CAGR</option>
  </select>
</label>
<label
  >指標:
  <select id="metric">
    <option value="Price">Price</option>
    <option value="PricePerUnit">PricePerUnit</option>
  </select>
</label>
```

```javascript
function slopeForFeature(props, yearFrom, yearTo, metricKey, method = "ols") {
  const xs = [],
    ys = [];
  for (let y = yearFrom; y <= yearTo; y++) {
    const v = props.metrics?.[y]?.[metricKey];
    if (typeof v === "number" && isFinite(v)) {
      xs.push(y);
      ys.push(v);
    }
  }
  if (xs.length < 2) return null;
  if (method === "cagr") {
    const v0 = ys[0],
      v1 = ys[ys.length - 1];
    const t = xs[xs.length - 1] - xs[0];
    if (v0 <= 0 || t <= 0) return null;
    return Math.pow(v1 / v0, 1 / t) - 1; // 比率（年率）
  }
  if (method === "theil-sen") {
    const slopes = [];
    for (let i = 0; i < xs.length - 1; i++) {
      for (let j = i + 1; j < xs.length; j++) {
        const denom = xs[j] - xs[i];
        if (denom !== 0) slopes.push((ys[j] - ys[i]) / denom);
      }
    }
    return slopes.length ? quantile(slopes, 0.5) : null; // メディアン
  }
  // OLS（最小二乗）
  const xmean = xs.reduce((a, b) => a + b, 0) / xs.length;
  const ymean = ys.reduce((a, b) => a + b, 0) / ys.length;
  let num = 0,
    den = 0;
  for (let i = 0; i < xs.length; i++) {
    num += (xs[i] - xmean) * (ys[i] - ymean);
    den += (xs[i] - xmean) * (xs[i] - xmean);
  }
  return den === 0 ? null : num / den; // 値/年
}

function quantile(arr, q) {
  if (!arr.length) return null;
  const a = arr.slice().sort((x, y) => x - y);
  const pos = (a.length - 1) * q;
  const base = Math.floor(pos),
    rest = pos - base;
  return a[base + 1] !== undefined
    ? a[base] + rest * (a[base + 1] - a[base])
    : a[base];
}

function divergingColor(v, maxAbs) {
  if (v === null || v === undefined) return "#cccccc";
  const t = Math.max(-1, Math.min(1, v / maxAbs)); // -1~1
  const cneg = [49, 130, 189],
    c0 = [255, 255, 255],
    cpos = [222, 45, 38];
  const lerp = (a, b, u) => Math.round(a + u * (b - a));
  if (t < 0) {
    const u = t + 1; // 0~1
    return `rgb(${lerp(cneg[0], c0[0], u)},${lerp(cneg[1], c0[1], u)},${lerp(
      cneg[2],
      c0[2],
      u
    )})`;
  } else {
    const u = t; // 0~1
    return `rgb(${lerp(c0[0], cpos[0], u)},${lerp(c0[1], cpos[1], u)},${lerp(
      c0[2],
      cpos[2],
      u
    )})`;
  }
}

function updateStyleForSlope(features, yearFrom, yearTo, metricKey, method) {
  // 全 features の傾きを試算し、絶対値 95% 点でドメイン設定（外れ値対策）
  const slopes = features
    .map((f) =>
      slopeForFeature(f.properties, yearFrom, yearTo, metricKey, method)
    )
    .filter((v) => v !== null);
  if (!slopes.length) return { maxAbs: 1 };
  const absVals = slopes.map((v) => Math.abs(v));
  const maxAbs = quantile(absVals, 0.95) || Math.max(...absVals);
  return { maxAbs };
}
```

- **運用メモ**
  - デフォルトは `method=OLS`・`yearFrom=start_year`・`yearTo=end_year`・`metric=Price`。
  - CAGR は比率（年率）なので発散色の中心 0 は「成長ゼロ」を意味し直観的。単位は `%/年` として凡例に明記。
  - OLS/TS は値/年の単位となるため、凡例・単位の表示を指標に合わせて切替。
  - 欠損が多い市区町村は `minYears` 未満ならグレーで除外表示。

---

### テスト戦略

#### 単体テスト（`tests/test_analyze.py`）

- `compute_slope_xy` の端点テスト:
  - 1 年のみ: `None` を返す
  - 2 年（最小）: 正しい傾きを返す
  - 一定値: 傾き 0 を返す
  - 欠損混入: `np.nan` を除外して計算
- OLS/Theil–Sen/CAGR の比較（外れ値に対する頑健性）
- 負値での CAGR: `None` を返す

#### 統合テスト（`tests/test_integration.py`）

- API モック（`responses` ライブラリ）で全フロー実行
- キャッシュの読み書き
- 出力ファイルの存在確認（PNG/CSV/GeoJSON）

#### エッジケース

- 全年度欠損の市区町村: グレー表示
- 極端な外れ値（価格 1 億超）: 95% 分位でクリップ
- コード不一致: マッピング表での補完

---

### セキュリティ・コンプライアンス

#### API キー管理

- 環境変数のみで管理、コードにハードコード禁止
- CI/CD では GitHub Secrets / AWS Secrets Manager 利用
- ローカルは `.env` + `.gitignore`

#### Google Maps API キー

- HTTP リファラー制限（本番時）
- 使用量アラート設定（無料枠超過防止）
- **静的 HTML の場合**: API キーが露出するため、サーバサイド認証（署名付き URL）またはファイアウォールルールで保護
- 開発時のみローカルファイルで使用

#### データ利用規約

- 国交省 API: 利用規約（要確認）に従い、データの二次配布・商用利用の可否を明記
- 国土数値情報: 出典明示が必要（`README.md` に記載）

---

### パフォーマンス指標（目安）

| 構成           | 実行時間（初回） | 実行時間（キャッシュ有） | 備考                |
| -------------- | ---------------- | ------------------------ | ------------------- |
| 逐次（現状）   | ~8 分            | N/A                      | 470 req × 1 sec/req |
| 並列 4 workers | ~2 分            | ~5 秒                    | API 負荷次第で調整  |
| 並列 8 workers | ~1 分            | ~5 秒                    | レート制限に注意    |

**キャッシュヒット率**: 2 回目実行で ~100%（年度・県が同一の場合）

---

### データ構造定義

#### `df_grouped` の列定義

| 列名           | 型    | 説明                                               |
| -------------- | ----- | -------------------------------------------------- |
| `CityCode`     | str   | 5 桁市区町村コード（例: "13101" = 東京都千代田区） |
| `CityName`     | str   | 市区町村名（例: "千代田区"）                       |
| `Year`         | int   | 年度（例: 2024）                                   |
| `Price`        | float | 平均取引価格（万円）                               |
| `PricePerUnit` | float | 平均坪単価（万円/坪）                              |

#### GeoJSON `properties` 構造

```json
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [...] },
  "properties": {
    "CityCode": "13101",
    "CityName": "千代田区",
    "metrics": {
      "2018": { "Price": 5432.1, "PricePerUnit": 123.4 },
      "2019": { "Price": 5678.9, "PricePerUnit": 125.6 },
      ...
    },
    "slope_price": 123.45,
    "slope_ppu": 1.23
  }
}
```

---

### まとめ：改善提案の評価と修正点

#### 追加した内容

1. **具体的な運用制約**: API レート制限、境界データ入手先、セキュリティ扱い
2. **データ構造の明確化**: `df_grouped` の列定義、GeoJSON スキーマ
3. **テスト戦略**: 単体/統合/エッジケースの具体例
4. **パフォーマンス指標**: 実行時間の目安、キャッシュ効果
5. **セキュリティ考慮**: キー管理、規約遵守

#### 残存リスク

- API の詳細仕様が未公開の場合、実測ベースで調整が必要
- 市区町村合併・コード変更への対応（年度横断時の注意）
- 大規模データセット（全県 ×10 年）でのメモリ使用量

#### 推奨アクション

1. PR1（CLI 化・傾き是正）を最優先実装
2. API 仕様を実測で確認し、`max_workers` を調整
3. テストを段階的に追加（PR10 で完備）
4. ドキュメント整備（PR9）を最後に完了
