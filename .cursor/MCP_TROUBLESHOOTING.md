# MCP サーバーのトラブルシューティング

## 問題: "No tools, prompts, or resources" と表示される

### 確認事項

1. **環境変数の設定**
   - `.env` ファイルに `MLIT_API_KEY` が設定されているか確認してください
   - または、CursorのMCP設定ファイルの `env` セクションに `MLIT_API_KEY` が設定されているか確認してください

2. **MCPサーバーの起動確認**
   - ターミナルで以下のコマンドを実行して、MCPサーバーが正しく起動するか確認してください：
   ```bash
   cd /Users/takurot/src/real-estate
   source env/bin/activate
   python -m mlit_mcp
   ```
   - エラーメッセージが表示される場合は、その内容を確認してください

3. **ツールの登録確認**
   - 以下のコマンドでツールが正しく登録されているか確認できます：
   ```bash
   cd /Users/takurot/src/real-estate
   source env/bin/activate
   python test_mcp_tools.py
   ```

4. **Cursorの設定確認**
   - CursorのMCP設定ファイルが正しいか確認してください
   - 設定ファイルの場所：
     - macOS: `~/Library/Application Support/Cursor/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`
   - 設定例：
   ```json
   {
     "mcpServers": {
       "mlit-mcp": {
         "command": "/Users/takurot/src/real-estate/env/bin/python",
         "args": ["-m", "mlit_mcp"],
         "env": {
           "MLIT_API_KEY": "your-api-key-here"
         }
       }
     }
   }
   ```

5. **Cursorの再起動**
   - 設定を変更した場合は、Cursorを完全に再起動してください

6. **ログの確認**
   - Cursorの開発者ツールでエラーログを確認してください
   - Cursor > 設定 > 開発者ツール > コンソール

### よくある問題

#### 問題1: APIキーが設定されていない

**症状**: MCPサーバーが起動しない、またはエラーが発生する

**解決方法**: 
- `.env` ファイルに `MLIT_API_KEY` を設定する
- または、CursorのMCP設定ファイルの `env` セクションに `MLIT_API_KEY` を設定する

#### 問題2: 仮想環境のパスが間違っている

**症状**: MCPサーバーが起動しない

**解決方法**: 
- CursorのMCP設定ファイルの `command` を絶対パスに変更する
- 例: `"command": "/Users/takurot/src/real-estate/env/bin/python"`

#### 問題3: ツールが認識されない

**症状**: "No tools, prompts, or resources" と表示される

**解決方法**: 
- `test_mcp_tools.py` を実行して、ツールが正しく登録されているか確認する
- MCPサーバーが正しく起動しているか確認する
- Cursorを再起動する



