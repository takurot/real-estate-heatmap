import os
import argparse
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# 都道府県コードと都道府県名のマッピング辞書
PREFECTURE_MAP = {
    "01": "北海道",
    "02": "青森県",
    "03": "岩手県",
    "04": "宮城県",
    "05": "秋田県",
    "06": "山形県",
    "07": "福島県",
    "08": "茨城県",
    "09": "栃木県",
    "10": "群馬県",
    "11": "埼玉県",
    "12": "千葉県",
    "13": "東京都",
    "14": "神奈川県",
    "15": "新潟県",
    "16": "富山県",
    "17": "石川県",
    "18": "福井県",
    "19": "山梨県",
    "20": "長野県",
    "21": "岐阜県",
    "22": "静岡県",
    "23": "愛知県",
    "24": "三重県",
    "25": "滋賀県",
    "26": "京都府",
    "27": "大阪府",
    "28": "兵庫県",
    "29": "奈良県",
    "30": "和歌山県",
    "31": "鳥取県",
    "32": "島根県",
    "33": "岡山県",
    "34": "広島県",
    "35": "山口県",
    "36": "徳島県",
    "37": "香川県",
    "38": "愛媛県",
    "39": "高知県",
    "40": "福岡県",
    "41": "佐賀県",
    "42": "長崎県",
    "43": "熊本県",
    "44": "大分県",
    "45": "宮崎県",
    "46": "鹿児島県",
    "47": "沖縄県"
}

# APIエンドポイントの設定
API_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001"
PRICE_CLASSIFICATION = "01"  # 不動産取引価格情報


def setup_fonts():
    """日本語フォントの設定（フォールバック付き）"""
    import warnings
    import logging
    
    # matplotlibのフォント警告を抑制
    logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
    
    font_families = ['Hiragino Sans', 'Noto Sans CJK JP', 'MS Gothic', 'DejaVu Sans']
    # matplotlibのフォントリストに設定（利用可能なフォントを自動選択）
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
        plt.rcParams['font.family'] = font_families


def compute_slopes(df_grouped: pd.DataFrame, target_col: str = "Price") -> dict[tuple[str, str], float]:
    """
    市区町村ごとの傾きを計算（集計済みデータを使用）
    
    Args:
        df_grouped: 市区町村 × 年で平均済みのDataFrame
        target_col: 傾きを計算する対象列（"Price" または "PricePerUnit"）
    
    Returns:
        {(city_code, city_name): slope} の辞書
    """
    slopes = {}
    for (city_code, city_name), group in df_grouped.groupby(["CityCode", "CityName"]):
        gg = group.sort_values("Year")
        if gg["Year"].nunique() < 2:
            continue
        x = gg["Year"].values
        y = gg[target_col].values
        slope, _ = np.polyfit(x, y, 1)
        slopes[(city_code, city_name)] = float(slope)
    return slopes


def process_prefecture(
    prefecture_code: str,
    prefecture_name: str,
    years: list[int],
    api_key: str,
    output_dir: Path,
    top_n: int = 5
):
    """
    都道府県ごとのデータ取得・分析・可視化
    
    Args:
        prefecture_code: 都道府県コード（2桁）
        prefecture_name: 都道府県名
        years: 年度リスト
        api_key: APIキー
        output_dir: 出力ディレクトリのルート
        top_n: 上位何件を表示するか
    """
    price_data = []

    # 市町村ごとの価格データを収集
    for year in years:
        params = {
            "year": year,
            "area": prefecture_code,
            "priceClassification": PRICE_CLASSIFICATION,
        }
        headers = {"Ocp-Apim-Subscription-Key": api_key}
        response = requests.get(API_URL, params=params, headers=headers)
        
        # エラーチェック
        if response.status_code != 200:
            print(f"Failed to fetch data for {prefecture_name} in {year}. Status code: {response.status_code}")
            continue
        
        try:
            data = response.json()
            if data.get("status") == "OK" and isinstance(data.get("data"), list):
                for item in data["data"]:
                    city_code = item.get("MunicipalityCode")
                    city_name = item.get("Municipality")
                    price = item.get("TradePrice")
                    price_per_unit = item.get("PricePerUnit")
                    if city_code and city_name and price and price_per_unit:
                        price_data.append({
                            "Year": year,
                            "CityCode": city_code,
                            "CityName": city_name,
                            "Price": float(price),
                            "PricePerUnit": float(price_per_unit)
                        })
            else:
                print(f"Unexpected data format or error for {prefecture_name} in {year}: {data}")
                continue
        
        except ValueError as e:
            print(f"JSON decode error for {prefecture_name} in {year}: {e}")
            continue

    # DataFrameに変換し、集計
    df = pd.DataFrame(price_data)
    if df.empty:
        print(f"No valid data available for {prefecture_name}.")
        return
    
    # 市区町村ごとの平均価格とPricePerUnitの平均を計算
    df_grouped = df.groupby(["CityCode", "CityName", "Year"]).agg({
        'Price': 'mean',
        'PricePerUnit': 'mean'
    }).reset_index()
    
    # 出力ディレクトリの作成
    pref_output_dir = output_dir / prefecture_code
    plots_dir = pref_output_dir / "plots"
    tables_dir = pref_output_dir / "tables"
    plots_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    
    # CSV保存
    df_grouped.to_csv(tables_dir / "df_grouped.csv", index=False, encoding="utf-8-sig")
    
    # 線形近似の傾きを計算（df_groupedを使用）
    slopes = compute_slopes(df_grouped, target_col="Price")
    
    # 傾きが大きい順に並べ替え
    sorted_slopes = sorted(slopes.items(), key=lambda x: x[1], reverse=True)[:top_n]
    top_n_cities = [(city_name, slope) for (city_code, city_name), slope in sorted_slopes]

    # トップNの市区町村のみ抽出
    top_n_city_names = [city_name for city_name, _ in top_n_cities]
    df_top_n = df_grouped[df_grouped["CityName"].isin(top_n_city_names)]

    # グラフ化（Price）
    if not df_top_n.empty:
        plt.figure(figsize=(12, 8))
        sns.lineplot(
            data=df_top_n,
            x="Year",
            y="Price",
            marker="o",
            hue="CityName"
        )
        plt.title(f"{prefecture_name}で不動産価格の傾きが大きい市区町村トップ{top_n}（{years[0]}-{years[-1]}）")
        plt.xlabel("年")
        plt.ylabel("平均価格（万円）")
        if len(df_top_n["CityName"].unique()) > 0:
            plt.legend(title="市区町村", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.grid()
        plt.tight_layout()
        plt.savefig(plots_dir / f"growth_with_price_{prefecture_code}.png", dpi=150)
        plt.close()

    # PricePerUnitのグラフ化
    if not df_top_n.empty:
        plt.figure(figsize=(12, 8))
        sns.lineplot(
            data=df_top_n,
            x="Year",
            y="PricePerUnit",
            marker="o",
            hue="CityName"
        )
        plt.title(f"{prefecture_name}で不動産価格の傾きが大きい市区町村トップ{top_n}（{years[0]}-{years[-1]}）")
        plt.xlabel("年")
        plt.ylabel("平均坪単価（万円）")
        if len(df_top_n["CityName"].unique()) > 0:
            plt.legend(title="市区町村", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.grid()
        plt.tight_layout()
        plt.savefig(plots_dir / f"growth_with_price_per_unit_{prefecture_code}.png", dpi=150)
        plt.close()


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="不動産価格の時系列変化を分析し、傾きが大きい市区町村を可視化"
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2015,
        help="開始年（デフォルト: 2015）"
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2024,
        help="終了年（デフォルト: 2024）"
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="上位何件を表示するか（デフォルト: 5）"
    )
    parser.add_argument(
        "--prefectures",
        nargs="+",
        default=None,
        help="対象都道府県コード（例: 13 14）。指定しない場合は全47都道府県"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="出力ディレクトリ（デフォルト: output）"
    )
    
    args = parser.parse_args()
    
    # APIキーの取得
    api_key = os.getenv("HUDOUSAN_API_KEY")
    if not api_key:
        raise ValueError("APIキーが設定されていません。環境変数 'HUDOUSAN_API_KEY' にAPIキーを設定してください。")
    
    # 年度範囲の設定
    start_year = args.start_year
    end_year = args.end_year
    years = list(range(start_year, end_year + 1))
    
    # 出力ディレクトリの作成
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # フォント設定
    setup_fonts()
    
    # 対象都道府県の決定
    if args.prefectures:
        target_prefectures = {
            code: name for code, name in PREFECTURE_MAP.items()
            if code in args.prefectures
        }
    else:
        target_prefectures = PREFECTURE_MAP
    
    # 都道府県ごとに処理
    for prefecture_code, prefecture_name in target_prefectures.items():
        print(f"Processing {prefecture_name} ({prefecture_code})...")
        process_prefecture(
            prefecture_code=prefecture_code,
            prefecture_name=prefecture_name,
            years=years,
            api_key=api_key,
            output_dir=output_dir,
            top_n=args.top_n
        )


if __name__ == "__main__":
    main()
