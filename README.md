# shorts-only

ローカル動画や公開動画URLから、縦型ショート動画・編集可能なCapCutドラフトを制作する独立したPythonアプリです。**他のリポジトリ、ClipForgeの環境、GitHub Actionsを必要としません。**

15〜60秒・5本を目安にします。素材が短い、本数が少ない、演出を付けられないことを理由に停止・水増し・自動再生成する品質ゲートはありません。

## 準備

Python 3.11以降とFFmpeg/FFprobeを用意します。CapCutドラフトを使う場合はPC版CapCutも必要です。

```powershell
git clone https://github.com/nyu1791-collab/shorts-only.git
cd shorts-only
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-capcut.txt
Copy-Item .env.example .env
Copy-Item config\streamers.example.yaml config\streamers.yaml
```

`.env` の `CAPCUT_DRAFTS_DIR` にCapCut設定画面の実際のドラフト保存先を指定します。MP4だけならCapCutやpyCapCutは不要で、`requirements.txt` の基本依存だけで動きます。

動画サイトのURLを取得する場合は、追加で次を導入します。直接のMP4などのHTTPSファイルはPythonの標準機能で取得します。

```powershell
.\.venv\Scripts\python -m pip install -r requirements-download.txt
```

Windowsでは `run-windows.cmd` から操作できます。手動なら `.venv` のPythonで `main.py` を実行します。

## 単独で制作する

元動画と、同じ時間軸の字幕を使う例：

```powershell
.\run-windows.cmd run C:/work/archive.mp4 --srt C:/work/archive.srt --streamer_id 01 --format mp4
.\run-windows.cmd run C:/work/archive.mp4 --srt C:/work/archive.srt --streamer_id 01 --format draft
```

`config/streamers.yaml` の配信者設定に `cuts: [[120,165],[340,385]]` を指定すれば、その区間を採用します。区間指定がなく字幕がある場合は感嘆表現などを手掛かりに抜粋します。字幕も区間指定もない基本モードでは、動画全体から間隔を置いて抜粋します。**この基本モードをAIによる撮れ高判定とは表示しません。** 選定方式は `selections.json` に記録します。

| 形式 | 出力 |
|---|---|
| `draft` | 元動画の採用区間を直接参照するCapCutドラフト。中間MP4を描画しない |
| `mp4` | 縦型MP4。字幕があれば焼き込み、元SRTも保持 |
| `both` | MP4とドラフト。文字起こしを二重に依頼しない |

ドラフトで加えたプレビュー・装飾は、別途生成したMP4には反映されません。ドラフトを調整した完成動画はCapCutから書き出してください。

## 任意のGemini制作

```powershell
.\.venv\Scripts\python -m pip install -r requirements-ai.txt
$env:GOOGLE_CLOUD_PROJECT = '利用するプロジェクトID'
# このPCでGoogle CloudのADC認証を準備したうえで実行します。
.\run-windows.cmd run C:/work/archive.mp4 --streamer_id 01 --format draft --ai
```

明示した `--ai` またはプリセットの `analysis: gemini` だけがVertexを使用します。

1. Gemini 3.8 Flashで音声から採用区間を選ぶ。
2. 採用区間だけをGemini 3.5 Transcribeで単語時刻・話者付き文字起こしする。
3. Gemini 3.5 Flashで字幕本文を整える。時刻を推定し直さない。

モデル名はプリセットの `selection_model`、`transcription_model`、`cleanup_model` で明示できます。プロジェクトは `project` または `GOOGLE_CLOUD_PROJECT`、接続はVertexです。別APIキーへの暗黙切替やSDK経由のTranscribe置換はありません。モデルの提供可否・権限・料金は接続先に依存します。

既存のSRTを指定した場合はその時刻と本文を使い、文字起こし・整文の新規要求を省略します。

成功した応答・音声を再利用します。一時的な429・対象5xx・通信障害のみ合計3回まで再試行します。任意の整文が完了しなかった場合は理由を残して元の文字起こし本文を使います。原単語時刻・話者・元SRTを保存し、字幕不足を推測で補いません。使用量は `model-usage.jsonl` に工程別で記録します。

## 配信者設定・並列・続行

配信者ごとの色、フォント、字幕位置、固定ワイプ、冒頭の最大3プレビュー、本編カットを `config/streamers.yaml` に設定します。テンプレートと装飾の設定例はサンプルYAMLを参照してください。利用できない任意の装飾は省いて理由を記録します。CapCutのPro素材はPC側の契約・ダウンロードに依存します。

```powershell
.\run-windows.cmd batch C:/work/private-batch.yaml --workers 2
.\run-windows.cmd jobs
.\run-windows.cmd resume 制作ID
.\run-windows.cmd draft --job 制作ID
```

バッチ一覧の各項目には `ai: true` や `srt: path/to/source.srt` も指定できます。バッチ内の相対SRTパスは一覧ファイルの場所が基準です。

配信間とクリップ間の並列数は別に設定できます。クリップ間はプリセットの `workers`（既定2）。同じURL・形式の再指定は既存の制作へ続行し、成功分を再利用します。別の区間・字幕・AI設定で新規依頼にする場合だけ `--new` を付けます。素材・依頼の保存場所は `~/.shorts-only` が既定で、`.env` の `SHORTS_DATA_DIR` で変更できます。

元動画の指定区間だけをすぐドラフトにする操作も使えます。

```powershell
.\run-windows.cmd source C:/work/archive.mp4 --start 120 --end 165 --srt C:/work/archive.srt --streamer_id 01
```

これは再エンコードもモデル呼び出しも行いません。元動画を移動しないでください。素材もコピーして保管する場合は `--copy-media` を付けます。

## 編集データの書き出し

```powershell
.\run-windows.cmd handoff 制作ID --output C:/work/edit-assets
```

`assets.json`、区間表CSV、タイムラインJSON、編集後の時間軸のSRTを出力します。任意のOpenTimelineIO形式と素材の同梱にも対応します。別リポジトリのDBやAPIへ接続する機能ではありません。詳しくは [編集データの書き出し](docs/HANDOFF.md) を参照してください。

構成は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)、参考にした公開リポジトリと採用範囲は [docs/SOURCES.md](docs/SOURCES.md) に記載しています。

サンプル素材で単独のMP4・ドラフト・OTIO出力を作成しました。Windows版CapCutでの表示と、有料モデルを使う実制作は未実施です。品質監査・検査スクリプトは追加していません。
