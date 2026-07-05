# Amemiya End Vote

わんコメのコメント保存ファイルを監視して、ツイキャス/Kick/Twitchの配信終了投票を集計するWindows用ツールです。v0.1ではOBS停止は行わず、`overlay_state.json`を書き出して`overlay.html`に表示するだけです。

## v0.1の範囲

- リスナーが使える投票コマンドだけを処理します。
- `!寝ろ` / `!終了` / `！寝ろ` / `！終了` は終了票です。
- `!続行` / `!まだ` / `！続行` / `！まだ` は続行票です。
- `!投票開始`、`!リセット`などのチャット管理コマンドはありません。
- 管理操作はGUIの「わんコメログを自動で探す」「手動でログファイルを選ぶ」「OBS表示 ON/OFF」「投票をリセット」「終了する」だけです。
- 直近3分のローリング集計です。
- 同一投票者は1票だけ持ち、後の投票で上書きされます。
- OBS停止機能は入れていません。

## GUI

- ログ未選択時は「今やること：わんコメログを自動で探してください」と表示します。
- 「わんコメログを自動で探す」で、わんコメが保存した新しいコメント保存ファイルを探します。
- 自動検出に失敗した時は、手動選択を急かさず、まずわんコメ側の「コメントログを残す」と「ログをファイルとしても書き出し」を確認するよう表示します。
- 監視中は「監視中：コメントを待っています」と表示します。
- 監視エラーは「監視エラー: ...」として画面に表示します。
- 画面下部に最後に読んだコメント、投票者ID、判定結果、ignored理由を表示します。

## ファイル

- `run.py`: GUIアプリの起動ファイルです。
- `config.json`: 本番用の設定です。
- `config.sample.json`: サンプルログを軽いしきい値で試すための設定です。
- `overlay_state.json`: Pythonが書き出す現在の投票状態です。
- `overlay.html`: OBSのブラウザソースに指定する表示ファイルです。
- `README_使い方.txt`: releaseに同梱するexe利用者向けREADMEです。
- `samples/sample_log.jsonl`: 開発中の動作確認用サンプルです。

## 開発中の使い方

```powershell
python run.py
```

サンプルログだけを読み込んで集計を確認する場合:

```powershell
python run.py --config config.sample.json --replay-sample
```

## config.json

本番用の既定値は、起動前の既存ログを読まず、最低20票かつ終了率70%以上で終了ライン到達とします。

```json
{
  "log_file_path": "onecomme_log.jsonl",
  "overlay_state_path": "overlay_state.json",
  "voting_window_seconds": 180,
  "minimum_votes": 20,
  "end_rate_threshold": 0.7,
  "poll_interval_seconds": 0.5,
  "supported_services": ["twicas", "kick", "twitch"],
  "read_existing_log_on_start": false
}
```

`log_file_path`はGUIの「わんコメログを自動で探す」または「手動でログファイルを選ぶ」から変更でき、選んだコメント保存ファイルのパスが`config.json`に保存されます。雨宮が`config.json`を直接編集する前提にはしません。

## わんコメ側で最初に1回だけ必要な設定

わんコメ公式ドキュメント上、コメントログをファイルとして出すには設定が必要です。

1. わんコメの設定を開く
2. 「その他」を開く
3. 「コメントログを残す」にチェック
4. 「ログをファイルとしても書き出し」にチェック
5. その後、コメントを取得するとコメントファイルが作られます

## 投票者ID

- ツイキャス匿名コメントは`data.liveId`と`data.displayName`の`匿名コメント#番号`から作ります。
- ツイキャス匿名は`data.userId`などが同じでも、匿名番号が違えば別票として扱います。
- 通常ユーザーは`data.userId`、なければ`data.screenName`などから作ります。
- `data.id`はコメントIDの可能性があるため、投票者IDには使いません。
- Kick/Twitchも取得できるユーザーIDを優先し、なければ表示名系の値を使います。

## exeビルド

PyInstallerでexeを作る場合:

```powershell
build_exe.bat
```

成功時は`release`フォルダが作られます。

## releaseフォルダ

雨宮に渡すreleaseフォルダには、次の5ファイルだけを入れます。

- `01_最初に読む_使い方.txt`
- `02_起動する_配信終了投票くん.exe`
- `03_OBSに入れる_overlay.html`
- `config.json`
- `overlay_state.json`

`build_exe.bat`は上記5ファイルを`release`フォルダへコピーします。zip化する場合は、この`release`フォルダをzipにします。
