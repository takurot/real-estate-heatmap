# Cursor IDE での MCP サーバー設定方法

このファイルは、Cursor IDE から mlit-mcp の MCP サーバーにアクセスするための設定手順です。

## 設定ファイルの場所

Cursor の MCP 設定ファイルは以下の場所にあります：

- **macOS**: `~/Library/Application Support/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`
- **Windows**: `%APPDATA%\Cursor\User\globalStorage\rooveterinaryinc.roo-cline\settings\cline_mcp_settings.json`
- **Linux**: `~/.config/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`

## 設定手順

1. **設定ファイルを開く**
   - 上記のパスにある `cline_mcp_settings.json` を開きます（存在しない場合は作成してください）

2. **設定を追加**
   - `mcp-config.json.example` の内容を参考に、以下の設定を追加します：

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

3. **API キーの設定**
   - `MLIT_API_KEY` を実際の API キーに置き換えてください
   - `.env` ファイルの `HUDOUSAN_API_KEY` と同じ値を使用できます

4. **仮想環境を使用する場合**
   - プロジェクトの仮想環境を使用する場合は、`command` を絶対パスに変更してください：
   ```json
   "command": "/Users/takurot/src/real-estate/env/bin/python"
   ```
   - または、プロジェクトルートからの相対パスを使用することもできます（環境によって異なります）

5. **Cursor の再起動**
   - 設定を反映させるため、Cursor を再起動してください

## 動作確認

Cursor のチャットで以下のように指示して、MCP サーバーが動作しているか確認できます：

- 「mlit-mcp の list_municipalities ツールを使って東京（都道府県コード13）の市区町村一覧を取得して」
- 「東京都の市区町村データを取得して」

## トラブルシューティング

### MCP サーバーに接続できない

- 設定ファイルの JSON 形式が正しいか確認してください
- `MLIT_API_KEY` が正しく設定されているか確認してください
- 仮想環境を使用している場合、`command` のパスが正しいか確認してください
- Cursor を再起動してください

### API キーエラー

- `.env` ファイルに `MLIT_API_KEY` が設定されているか確認してください
- または、MCP 設定ファイルの `env` セクションに直接 API キーを設定してください



