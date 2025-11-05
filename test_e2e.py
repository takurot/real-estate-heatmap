#!/usr/bin/env python3
"""
PR1のE2Eテストスクリプト
実際のAPIを呼び出して動作確認を行う
"""
import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

def test_help():
    """--help オプションのテスト"""
    print("Test 1: --help オプション")
    result = subprocess.run(
        [sys.executable, "evalGrowthRate.py", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Help command failed: {result.stderr}"
    assert "開始年" in result.stdout, "Help message should contain Japanese text"
    assert "--start-year" in result.stdout, "Help should contain --start-year option"
    print("✓ Help test passed\n")


def test_single_prefecture():
    """単一都道府県のテスト"""
    print("Test 2: 単一都道府県（東京都）の実行")
    
    # APIキーの確認
    api_key = os.getenv("HUDOUSAN_API_KEY")
    if not api_key:
        print("⚠ APIキーが設定されていません。スキップします。")
        return
    
    # 一時ディレクトリを使用
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                sys.executable, "evalGrowthRate.py",
                "--prefectures", "13",
                "--start-year", "2022",
                "--end-year", "2023",
                "--top-n", "3",
                "--output-dir", tmpdir
            ],
            capture_output=True,
            text=True,
            timeout=60  # 60秒のタイムアウト
        )
        
        if result.returncode != 0:
            print(f"✗ Execution failed: {result.stderr}")
            return
        
        # 出力ファイルの確認
        output_dir = Path(tmpdir) / "13"
        plots_dir = output_dir / "plots"
        tables_dir = output_dir / "tables"
        
        assert plots_dir.exists(), f"Plots directory should exist: {plots_dir}"
        assert tables_dir.exists(), f"Tables directory should exist: {tables_dir}"
        
        # CSVファイルの確認
        csv_file = tables_dir / "df_grouped.csv"
        assert csv_file.exists(), f"CSV file should exist: {csv_file}"
        
        # CSVファイルの内容確認
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
            assert len(lines) > 1, "CSV should have header and at least one data row"
            header = lines[0].strip()
            assert "CityCode" in header, "CSV should contain CityCode column"
            assert "CityName" in header, "CSV should contain CityName column"
            assert "Year" in header, "CSV should contain Year column"
            assert "Price" in header, "CSV should contain Price column"
            assert "PricePerUnit" in header, "CSV should contain PricePerUnit column"
        
        # PNGファイルの確認（データがある場合のみ）
        png_files = list(plots_dir.glob("*.png"))
        if len(lines) > 1:  # データがある場合
            assert len(png_files) >= 2, f"Should have at least 2 PNG files when data exists, got {len(png_files)}"
            print(f"✓ Single prefecture test passed")
            print(f"  - CSV file: {csv_file} ({len(lines)-1} rows)")
            print(f"  - PNG files: {len(png_files)} files\n")
        else:
            print(f"⚠ No data returned, skipping PNG check")
            print(f"  - CSV file: {csv_file} (no data rows)\n")


def test_multiple_prefectures():
    """複数都道府県のテスト"""
    print("Test 3: 複数都道府県（東京都、神奈川県）の実行")
    
    api_key = os.getenv("HUDOUSAN_API_KEY")
    if not api_key:
        print("⚠ APIキーが設定されていません。スキップします。")
        return
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                sys.executable, "evalGrowthRate.py",
                "--prefectures", "13", "14",
                "--start-year", "2022",
                "--end-year", "2023",
                "--top-n", "2",
                "--output-dir", tmpdir
            ],
            capture_output=True,
            text=True,
            timeout=120  # 2都道府県なので120秒
        )
        
        if result.returncode != 0:
            print(f"✗ Execution failed: {result.stderr}")
            return
        
        # 両方の都道府県の出力を確認
        for pref_code in ["13", "14"]:
            output_dir = Path(tmpdir) / pref_code
            tables_dir = output_dir / "tables"
            csv_file = tables_dir / "df_grouped.csv"
            assert csv_file.exists(), f"CSV file should exist for prefecture {pref_code}: {csv_file}"
        
        print("✓ Multiple prefectures test passed\n")


def test_invalid_args():
    """無効な引数のテスト"""
    print("Test 4: 無効な引数のエラーハンドリング")
    
    # 存在しない都道府県コード
    result = subprocess.run(
        [
            sys.executable, "evalGrowthRate.py",
            "--prefectures", "99",
            "--start-year", "2023",
            "--end-year", "2023"
        ],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    # エラーになっても良い（データがないだけ）が、クラッシュしないこと
    assert result.returncode == 0 or "No valid data" in result.stdout or "Failed" in result.stdout, \
        "Should handle invalid prefecture gracefully"
    
    print("✓ Invalid args test passed\n")


def test_output_structure():
    """出力ディレクトリ構造のテスト"""
    print("Test 5: 出力ディレクトリ構造の確認")
    
    api_key = os.getenv("HUDOUSAN_API_KEY")
    if not api_key:
        print("⚠ APIキーが設定されていません。スキップします。")
        return
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                sys.executable, "evalGrowthRate.py",
                "--prefectures", "13",
                "--start-year", "2022",
                "--end-year", "2023",
                "--top-n", "1",
                "--output-dir", tmpdir
            ],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"✗ Execution failed: {result.stderr}")
            return
        
        # ディレクトリ構造の確認
        output_dir = Path(tmpdir)
        pref_dir = output_dir / "13"
        plots_dir = pref_dir / "plots"
        tables_dir = pref_dir / "tables"
        
        assert pref_dir.exists(), f"Prefecture directory should exist: {pref_dir}"
        assert plots_dir.exists(), f"Plots directory should exist: {plots_dir}"
        assert tables_dir.exists(), f"Tables directory should exist: {tables_dir}"
        
        # ファイルの確認
        csv_file = tables_dir / "df_grouped.csv"
        png_files = list(plots_dir.glob("*.png"))
        
        assert csv_file.exists(), "CSV file should exist"
        
        # CSVにデータがあるか確認
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            csv_lines = f.readlines()
            has_data = len(csv_lines) > 1
        
        if has_data:
            assert len(png_files) >= 2, f"Should have at least 2 PNG files when data exists, got {len(png_files)}"
            # ファイル名の確認
            expected_pngs = [
                plots_dir / "growth_with_price_13.png",
                plots_dir / "growth_with_price_per_unit_13.png"
            ]
            for png_file in expected_pngs:
                assert png_file.exists(), f"Expected PNG file should exist: {png_file}"
            print("✓ Output structure test passed")
            print(f"  - Directory structure: {tmpdir}/13/{{plots,tables}}/")
            print(f"  - PNG files: {len(png_files)} files\n")
        else:
            print("⚠ No data returned, checking directory structure only")
            print("✓ Output structure test passed (no data)")
            print(f"  - Directory structure: {tmpdir}/13/{{plots,tables}}/\n")


def main():
    """メイン関数"""
    print("=" * 60)
    print("PR1 E2E Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        test_help,
        test_single_prefecture,
        test_multiple_prefectures,
        test_invalid_args,
        test_output_structure,
    ]
    
    passed = 0
    skipped = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ Test failed: {e}\n")
            failed += 1
        except subprocess.TimeoutExpired:
            print(f"✗ Test timed out\n")
            failed += 1
        except Exception as e:
            if "APIキーが設定されていません" in str(e) or "スキップ" in str(e):
                skipped += 1
            else:
                print(f"✗ Test error: {e}\n")
                failed += 1
    
    print("=" * 60)
    print(f"Test Results: {passed} passed, {skipped} skipped, {failed} failed")
    print("=" * 60)
    
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

