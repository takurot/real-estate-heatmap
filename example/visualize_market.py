
import os
import sys
import json
import argparse
import logging
from pathlib import Path
from collections import defaultdict
import glob
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from dotenv import load_dotenv

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mlit_mcp.http_client import MLITHttpClient
from mlit_mcp.cache import InMemoryTTLCache, BinaryFileCache
from mlit_mcp.settings import get_settings
from mlit_mcp.tools.fetch_transactions import FetchTransactionsTool, FetchTransactionsInput

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load Env
load_dotenv()

# Set Japanese Font based on OS
import platform
system = platform.system()
if system == "Darwin":
    font_family = "Hiragino Sans"
elif system == "Windows":
    font_family = "Meiryo"
else:
    font_family = "Noto Sans CJK JP"

sns.set_theme(font=font_family)
plt.rcParams['font.family'] = font_family


def resolve_resource(uri: str, cache_dir: Path) -> list[dict]:
    """Resolve resource:// URI to local file path and load data."""
    if not uri.startswith("resource://mlit/transactions/"):
        raise ValueError(f"Unknown resource URI format: {uri}")
    
    filename = uri.replace("resource://mlit/transactions/", "")
    file_path = cache_dir / filename
    
    if not file_path.exists():
        # Fallback logic could be added here if needed (e.g. search in subdirectories)
        logger.warning(f"Resource file not found at expected path: {file_path}")
        # checks purely by filename in the cache root for now
        pass

    logger.info(f"Loading resource from: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

async def main():
    parser = argparse.ArgumentParser(description="Visualize Real Estate Market Data")
    parser.add_argument("--area", required=True, help="Area code (2-digit prefecture or 5-digit city)")
    parser.add_argument("--from-year", type=int, required=True, help="Start year (e.g. 2015)")
    parser.add_argument("--to-year", type=int, required=True, help="End year (e.g. 2023)")
    parser.add_argument("--cache-dir", default=".cache", help="Directory for caching downloaded data")
    parser.add_argument("--output-dir", default="output", help="Directory for output graphs and CSV")
    
    args = parser.parse_args()
    
    # Setup Paths
    cache_path = Path(args.cache_dir).resolve()
    output_path = Path(args.output_dir).resolve()
    output_path.mkdir(exist_ok=True, parents=True)
    
    # Init MCP Components
    settings = get_settings()
    api_key = os.getenv("MLIT_API_KEY")
    if not api_key:
        logger.error("MLIT_API_KEY not found in environment variables.")
        sys.exit(1)
        
    json_cache = InMemoryTTLCache(maxsize=1000, ttl=3600)
    file_cache = BinaryFileCache(directory=cache_path, ttl_seconds=86400 * 30) # 30 days cache
    
    client = MLITHttpClient(
        base_url=str(settings.base_url),
        api_key=api_key,
        json_cache=json_cache,
        file_cache=file_cache
    )
    
    tool = FetchTransactionsTool(client)
    
    logger.info(f"Fetching transactions for Area: {args.area}, Year: {args.from_year}-{args.to_year}")
    
    try:
        input_data = FetchTransactionsInput(
            fromYear=args.from_year,
            toYear=args.to_year,
            area=args.area,
            format="json"
        )
        
        response = await tool.run(input_data)
        
        data = []
        if response.data:
            data = response.data
        elif response.resource_uri:
            logger.info(f"Large response received as resource: {response.resource_uri}")
            data = resolve_resource(response.resource_uri, cache_path)
            
        logger.info(f"Total records loaded: {len(data)}")
        
        if not data:
            logger.warning("No data found.")
            sys.exit(0)
            
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Preprocessing
        # Convert TradePrice to numeric
        df['TradePrice'] = pd.to_numeric(df['TradePrice'], errors='coerce')
        
        # Extract numeric Year from Period if Year field is missing or unreliable
        # The API usually returns 'Year' but let's be safe.
        # Actually API returns 'Period' like '2023年第2四半期' but likely purely 'Year' field is not always there?
        # Let's check keys in 'example/analyze_large_cache.py' output earlier... 
        # Ah, it wasn't shown. But typical XIT001 has TradePrice, Type, etc.
        # We can extract Year from Period if needed.
        # However, looking at FetchTransactionsTool logic, it fetches by 'year' param. 
        # API response SHOULD have keys. 
        # We will assume standard keys.
        
        # Clean up data
        df = df.dropna(subset=['TradePrice'])
        
        # Parse Period to Year for grouping
        def parse_year(period):
            if not isinstance(period, str): return None
            import re
            m = re.match(r'(\d{4})年', period)
            return int(m.group(1)) if m else None
            
        if 'Period' in df.columns:
            df['Year'] = df['Period'].apply(parse_year)
        
        # Chart 1: Price Trend (Average/Median)
        if 'Year' in df.columns:
            yearly_stats = df.groupby('Year')['TradePrice'].agg(['mean', 'median', 'count']).reset_index()
            
            plt.figure(figsize=(10, 6))
            sns.lineplot(data=yearly_stats, x='Year', y='mean', marker='o', label='Average Price')
            sns.lineplot(data=yearly_stats, x='Year', y='median', marker='s', linestyle='--', label='Median Price')
            plt.title(f"Price Trend in Area {args.area}")
            plt.ylabel("Price (JPY)")
            plt.grid(True)
            plt.legend()
            plt.savefig(output_path / "price_trend.png")
            plt.close()
            logger.info("Generated price_trend.png")

        # Chart 2: Price Distribution (Latest Year)
        if 'Year' in df.columns:
            max_year = df['Year'].max()
            latest_df = df[df['Year'] == max_year]
            
            plt.figure(figsize=(10, 6))
            sns.histplot(data=latest_df, x='TradePrice', bins=30, kde=True)
            plt.title(f"Price Distribution in {max_year}")
            plt.xlabel("Price (JPY)")
            plt.savefig(output_path / "price_distribution.png")
            plt.close()
            logger.info("Generated price_distribution.png")

        # Helper to parse Japanese Era or Western Year
        def parse_year_str(year_str):
            if not isinstance(year_str, str): return None
            import re
            
            # Removes "戦前" (Pre-war) handling for simplicity or treat as specific year
            if "戦前" in year_str: return 1940 
            
            # Try Western Year first (e.g. 2011年)
            match_w = re.match(r"(\d{4})年?", year_str)
            if match_w:
                return int(match_w.group(1))

            eras = {"昭和": 1925, "平成": 1988, "令和": 2018, "明治": 1867, "大正": 1911}
            match = re.match(r"(昭和|平成|令和|明治|大正)(\d+)年?", year_str)
            if match:
                era_name = match.group(1)
                year_num = int(match.group(2))
                return eras[era_name] + year_num
            return None

        if 'BuildingYear' in df.columns:
            df['BuiltYearAD'] = df['BuildingYear'].apply(parse_year_str)
            df['Age'] = df['Year'] - df['BuiltYearAD']
            
            # Filter valid age
            age_df = df.dropna(subset=['Age', 'TradePrice'])
            age_df = age_df[age_df['Age'] >= 0]
            
            if not age_df.empty:
                plt.figure(figsize=(10, 6))
                sns.scatterplot(data=age_df, x='Age', y='TradePrice', alpha=0.6)
                plt.title(f"Price vs Building Age in Area {args.area}")
                plt.xlabel("Building Age (Years)")
                plt.ylabel("Price (JPY)")
                # Use log scale for Price if range is huge
                # plt.yscale('log') 
                plt.grid(True)
                plt.savefig(output_path / "scatter_age_price.png")
                plt.close()
                logger.info("Generated scatter_age_price.png")

        # Export Summary CSV
        summary_csv = output_path / "summary.csv"
        df.to_csv(summary_csv, index=False)
        logger.info(f"Exported summary data to {summary_csv}")

        # Export Ranking (Top 10 Expensive)
        # Use available columns
        cols = ['TradePrice', 'Year', 'Type', 'Area', 'BuildingYear', 'DistrictName']
        cols = [c for c in cols if c in df.columns]
        top10 = df.nlargest(10, 'TradePrice')[cols]
        top10_csv = output_path / "ranking_top10.csv"
        top10.to_csv(top10_csv, index=False)
        logger.info(f"Exported top 10 ranking to {top10_csv}")
        
    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)
        sys.exit(1)
        
    finally:
        await client.aclose()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
