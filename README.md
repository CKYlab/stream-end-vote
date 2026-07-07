# Amemiya End Vote

これは開発用です。雨宮さんに渡すものではありません。

雨宮さんに渡すのは、`build_exe.bat`で作られる`release`フォルダの中身、または`配信終了投票くん_v0.5.zip`だけです。

## v0.5の重要な注意（安全仕様）

- **v0.5でも初期状態では配信は自動停止しません。**
- `stop_streaming_enabled`と`obs_websocket_enabled`の初期値はどちらも`false`です。
- 本当にOBSを停止させるには、GUIの「OBS設定」画面で`OBS連携`と`OBS停止`をONにします。
- `OBS停止`をONにする時は確認ダイアログを必ず出します。必ず配信外でテストしてください。
- どちらかが`false`の間は、カウントダウンが最後まで進んでも`would_stop`表示（「ここで停止予定です / OBS停止はOFFです」）だけで、OBSには一切接続しません。
- 停止はカウントダウン完走時のみ発動します。カウントダウンなしで即停止する経路はありません。
- GUIの「カウントダウンをキャンセル」ボタンでカウントダウン中に止められます。
- チャットコメントから停止やキャンセルはできません。操作はローカルGUIのみです。
- OBS接続に失敗してもアプリは落ちません。GUIとoverlayにエラーを表示して`stop_failed`になります。
- `trigger_once_per_live=true`なら同じ`liveId`では原則1回だけ発動します。
- 過去版の`v0.3.5-fixed`は、投票結果とカウントダウンを表示するだけの安全版です。
- v0.5候補では、OBSブラウザソースは入れっぱなしでOKです。普段は透明で表示されず、投票コマンドが来た時だけ投票パネルが表示されます。

## OBS側の設定（開発者向け）

OBSの配信停止を検証する場合のみ必要です。

1. OBSを開き、メニューの「ツール」→「WebSocketサーバー設定」を開く
2. 「WebSocketサーバーを有効にする」にチェック
3. ポートは既定で`4455`
4. 「認証を有効にする」がONの場合は「サーバーパスワード」を控える

その後、アプリの「OBS設定」画面で設定します。

OBSパスワードは、OBS側の「WebSocketサーバー設定」で設定する認証用パスワードです。配信終了投票くん専用のパスワードではありません。OBSで「ツール → WebSocketサーバー設定」を開いて確認・設定してください。認証がONの場合はそのパスワードを入力し、認証がOFFの場合は空欄で大丈夫です。このパスワードを作者や第三者に送る必要はありません。

```json
{
  "obs_websocket_enabled": true,
  "obs_host": "127.0.0.1",
  "obs_port": 4455,
  "obs_password": "（OBSのサーバーパスワード）",
  "stop_streaming_enabled": true
}
```

- `obs_websocket_enabled`: OBSへの接続を許可するか（初期値`false`）
- `obs_host` / `obs_port` / `obs_password`: obs-websocketの接続先（初期値`127.0.0.1` / `4455` / 空）
- `stop_streaming_enabled`: カウントダウン完走時に本当にStopStreamを送るか（初期値`false`）

GUIの「OBS設定」画面にある「OBS接続テスト」ボタンで、接続成功／パスワード違い／接続不可を確認できます。接続テストは`obs_websocket_enabled=true`のときだけ動きます。

## カウントダウンの状態遷移

`overlay_state.json`の`mode`は次のいずれかです。

- `normal`: 通常の投票メーター表示
- `countdown`: 終了ライン（`minimum_votes`票以上かつ終了率`end_rate_threshold`以上）到達。残り秒数を大きく表示
- `cancelled`: GUIでキャンセルされた。数秒表示してnormalへ戻る
- `would_stop`: カウントダウン完走したが停止OFF。表示のみ
- `stopping`: OBSへ停止要求中（停止ONのときのみ）
- `stopped`: StopStream成功。「配信停止を実行しました」
- `stop_failed`: StopStream失敗。エラー理由を表示（アプリは落ちない）

あわせて`visible` / `display_enabled` / `countdown_remaining` / `countdown_started_at` / `can_cancel` / `obs_connected` / `stop_streaming_enabled` / `stop_result` / `stop_error`が書き出され、`overlay.html`がOBS上に表示します。`display_enabled=true`は「必要時に表示してよい」、`visible=true`は「今OBSに表示する」という意味です。

## カウントダウン関連のconfig.json設定

- `countdown_enabled`: 終了ライン到達時にカウントダウン表示をするか（既定: `true`）
- `countdown_seconds`: カウントダウン秒数（既定: `30`）
- `trigger_once_per_live`: 同じ`liveId`では1回しか発動しないか（既定: `true`）

## v0.1の範囲

- わんコメのコメント保存ファイルを監視します。
- コメント保存ファイルは`.log`または`.jsonl`に対応します。
- リスナーが使える投票コマンドだけを処理します。
- `!寝ろ` / `!終了` / `！寝ろ` / `！終了` は終了票です。
- `!続行` / `!まだ` / `！続行` / `！まだ` は続行票です。
- `!投票開始`、`!リセット`などのチャット管理コマンドはありません。
- 直近3分のローリング集計です。
- 同一投票者は1票だけ持ち、後の投票で上書きされます。

## 開発用ファイル

- `src/`: アプリ本体のPythonコード
- `src/end_vote/obs_control.py`: obs-websocketクライアント（v0.4）
- `tests/`: ユニットテスト
- `run.py`: 開発中の起動ファイル
- `build_exe.bat`: PyInstallerでexeとreleaseを作るバッチ
- `01_最初に読む_使い方.txt`: releaseに入れる雨宮さん向け説明
- `overlay.html` / `overlay_state.json`: OBS表示用ファイル

## 依存ライブラリ

- `obsws-python`（純Python、依存はwebsocket-clientのみ。Python 3.11 / PyInstaller対応）

```powershell
python -m pip install -r requirements.txt
```

## 開発中の確認

```powershell
python run.py
```

サンプルログだけを読み込んで集計を確認する場合:

```powershell
python run.py --config config.sample.json --replay-sample
```

テスト:

```powershell
python -m unittest discover -s tests
```

## 配布用zipの作り方

1. `build_exe.bat`を実行する
2. `release`フォルダが作られる
3. `配信終了投票くん_v0.5.zip`が作られる
4. 雨宮さんに渡すのは`release`フォルダの中身、または`配信終了投票くん_v0.5.zip`だけ

`release`フォルダには次の5ファイルだけが入ります。

- `01_最初に読む_使い方.txt`
- `02_起動する_配信終了投票くん.exe`
- `03_OBSに入れる_overlay.html`
- `config.json`
- `overlay_state.json`

`make_release.py`は配布用`config.json`を必ず安全側（`stop_streaming_enabled=false`、`obs_websocket_enabled=false`、`obs_password`空）で作り直します。

## 配布前の個人パス確認

`make_release.py`はrelease用の`config.json`と`overlay_state.json`を初期状態で作り直します。念のため、配布前に以下を実行して、`.json` / `.txt` / `.html`に開発者環境の文字列が残っていないことを確認します。

```powershell
Select-String -Path release\*.json,release\*.txt,release\*.html -Pattern "CHiKA","ちか","CodexTest","C:\Users","D:\","v0.3.5" -SimpleMatch
```

何も表示されなければOKです。

## OBSブラウザソースの推奨サイズ

`overlay.html`を入れるブラウザソースは以下のサイズを推奨します。

- 幅 1920 / 高さ 1080
- または 幅 1280 / 高さ 720

OBSブラウザソースは入れっぱなしでOKです。通常時は`overlay.html`が透明になり、何も表示しません。`!寝ろ` / `!終了` / `!続行` / `!まだ`などの投票コマンドが来た時だけ、`voting_window_seconds`の間だけ投票パネルを表示します。終了ライン到達時は、これまで通りカウントダウンを大きく表示します。

カウントダウン大表示は`max-width: 90vw`と`clamp()`によるフォント調整で画面内に収まるため、800x600でも切れませんが、小さすぎると文字も小さくなります。投票メーターは右下固定表示のままです。

## わんコメ側で最初に1回だけ必要な設定

わんコメ公式ドキュメント上、コメントログをファイルとして出すには設定が必要です。

1. わんコメの設定を開く
2. 「その他」を開く
3. 「コメントログを残す」にチェック
4. 「ログをファイルとしても書き出し」にチェック
5. その後、コメントを取得するとコメント保存ファイルが作られます

## 投票者ID

- ツイキャス匿名コメントは`data.liveId`と`data.displayName`の`匿名コメント#番号`から作ります。
- ツイキャス匿名は`data.userId`などが同じでも、匿名番号が違えば別票として扱います。
- 通常ユーザーは`data.userId`、なければ`data.screenName`などから作ります。
- `data.id`はコメントIDの可能性があるため、投票者IDには使いません。
- Kick/Twitchも取得できるユーザーIDを優先し、なければ表示名系の値を使います。
