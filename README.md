# shorts-only

配信切り抜きをショート動画とCapCutドラフトにまとめる、PC用のPython CLIです。制作は既存の[ClipForge](https://github.com/nyu1791-collab/ClipForge)へ依頼し、配信者プリセットと制作状態をこのリポジトリで管理します。

15〜60秒・5本・9:16を目安にします。尺や本数が目標に届かなくても素材を捨てず、品質監査・追加の査読モデル・目標不足による自動再生成は行いません。元素材不存在や接続失敗は、その事実を表示します。

## 最初の準備

Python 3.11以降と、CapCutのドラフトを開くWindows PCを用意します。GitHub CLIはClipForge制作時に使います。既存の動画からドラフトを作るだけならモデル認証は不要です。

```powershell
git clone https://github.com/nyu1791-collab/shorts-only.git
cd shorts-only
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-capcut.txt
Copy-Item .env.example .env
Copy-Item config\streamers.example.yaml config\streamers.yaml
```

`.env` の `CLIPFORGE_DIR` に隣のClipForgeを、`CAPCUT_DRAFTS_DIR` にCapCut設定画面の「ドラフト保存先」を指定します。Windowsパスは例のように `/` 区切りで記載できます。

```dotenv
CLIPFORGE_DIR=C:/work/ClipForge
CAPCUT_DRAFTS_DIR=C:/Users/your-name/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft
```

CapCut用フォルダの実際の位置はPCの設定を使ってください。出力したドラフトはCapCutで開き、必要な調整後に書き出します。CapCut Proの購入やライセンス認証をこのプログラムから行うことはありません。

ClipForgeをまだPCに用意していなければ、隣に取得して制御用Python環境を作ります。推論や重い描画は従来どおりActions・Vertex・Colab側で動きます。

```powershell
cd ..
git clone https://github.com/nyu1791-collab/ClipForge.git
cd ClipForge
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
cd ..\shorts-only
gh auth status
.\.venv\Scripts\python main.py connect
```

既存のGitHub/Vertex/Colab認証を利用します。接続設定は[ClipForgeのQUICK_START](https://github.com/nyu1791-collab/ClipForge/blob/main/docs/QUICK_START.md)にあります。`connect` は登録案内の表示で、推論の成功確認ではありません。`unknown` は一覧権限が確認できない状態です。別APIキーへの自動切り替えやキーローテーションは追加していません。Antigravity SDKによるTranscribeの置換は実施しておらず、現行ClipForgeの接続経路を使います。

Windowsでは以後 `run-windows.cmd` が仮想環境を用意してコマンドを実行できます。Linux/macOSでは `python main.py ...` を同じように実行します。

## 操作

まずは接続・課金を行わず、制作指示を表示できます。

```powershell
.\run-windows.cmd run "https://kick.com/example/videos/archive-id" --streamer_id 01 --plan
```

配信者01のCapCut向け素材とドラフトを制作：

```powershell
.\run-windows.cmd run "https://kick.com/example/videos/archive-id" --streamer_id 01 --format draft
```

字幕入りMP4を制作：

```powershell
.\run-windows.cmd run "https://example.com/archive.mp4" --streamer_id 02 --format mp4
```

`--format both` は、1回のCapCut向け制作から「字幕を焼き込まないMP4＋SRT」とドラフトを保存します。モデル処理を2回発注しません。冒頭フックやプリセットの装飾はドラフトに反映されます。ドラフトのタイムラインを反映したMP4はCapCutから書き出してください。`--format mp4` の字幕・レイアウトはClipForgeのTikTok設定を使用します。

複数配信者を並列に進める場合は `config/batch.example.yaml` を参考に、PC上の個人用YAMLを作ります。

```powershell
.\run-windows.cmd batch C:/work/private-batch.yaml --workers 2
.\run-windows.cmd jobs
.\run-windows.cmd jobs --job 制作ID
.\run-windows.cmd resume 制作ID
```

既存URLを再指定すると保存済みの制作IDを返します。別の新規依頼にしたい場合だけ `run --new` を使います。`resume` は既存Runの監視・回収へ再接続します。失敗したAPI要求を新たなRunで再試行する指示にはなりません。ドラフト待ちの場合は回収済み素材だけを使います。アプリを止めても外部ActionsのRunが終了するとは限らないため、保存済みRunへ再接続してください。

回収済みクリップだけからドラフト作成：

```powershell
.\run-windows.cmd draft --clip C:/work/clip-001 --streamer_id 01
.\run-windows.cmd draft --job 制作ID
```

`--clip` には `video.mp4` と、あれば `captions.srt` / `render.json` を含むフォルダを指定します。ClipForgeの `caption_mode: editable` が記録された素材には編集可能な字幕を置きます。字幕焼き込み済み・状態不明の素材は映像を保ち、字幕を二重に重ねません。素材の移動でドラフトが壊れないよう、参照動画と元字幕を新しいドラフト内にもコピーします。

PC上の元動画から、再描画せずに直接ドラフトを作ることもできます。

```powershell
.\run-windows.cmd source C:/work/archive.mp4 --start 120 --end 165 --srt C:/work/archive.srt --streamer_id 01
```

この経路は元動画の120〜165秒を参照するタイムラインを作り、MP4の再エンコードもモデル呼び出しも行いません。SRTは元動画と同じ時間軸のものを指定します。元動画はその場所で保管してください。`--copy-media` を付けた場合だけ元動画全体をドラフト内へコピーします。字幕なしで作る場合は `--srt` を省略できます。

## 配信者プリセットと演出

`config/streamers.yaml` の配信者ごとに、色・フォント・字幕位置・映像の拡大と位置を設定できます。`video_crop: [x,y,w,h]` で正規化座標の切り抜き、`face` で顔ワイプ用の別レイヤーを指定できます。座標はドラフトに渡す動画基準です。これは固定レイアウトで、自動顔追跡ではありません。

```yaml
streamers:
  '01':
    name: 配信者01
    accent_color: '#66D9EF'
    subtitle_y: -0.65
    hook: auto
    # 任意の1秒プレビュー開始秒（クリップ内の秒数）
    hook_seconds: [5, 12, 20]
    # 任意の本編カット。元動画に戻れるよう対応表を保存します。
    cuts: [[0, 12.5], [13.2, 30]]
    # 任意の顔ワイプ。二重音声を避けるため、このレイヤーは無音です。
    face:
      crop: [0.7, 0, 0.3, 0.3]
      scale: 0.35
      x: 0
      y: 0.55
```

`hook: auto` は指定したピーク秒、または字幕の感嘆表現などから最大3か所・各約1秒のプレビューを作ります。Geminiがピークを追加解析したと見せかけず、選定方式を `shorts-only.json` に記録します。字幕や候補が少なければ実際に取れる数で進みます。`hook: off` で本編だけにできます。

字幕は元のSRT時刻と本編カット・フックの対応表から配置します。フック内の字幕も移動先に合わせます。単語時刻をSRTから推定して捏造する処理はありません。ドラフトは発話単位の編集可能な字幕で、CapCutネイティブの単語カラオケ生成ではありません。ClipForgeの字幕入りMP4では既存の字幕設定を使用します。

明文テンプレートの装飾トラックを流用する場合：

```yaml
    template_draft: MyShortsTemplate  # 同じCapCutドラフト保存先にあるテンプレート名
    template_tracks:
      - kind: text
        name: brand
    # video_effect: 利用するpyCapCutのエフェクト名
```

`template_tracks` で明示した動画・音声・テキストの装飾トラックを新規ドラフトに読み込みます。元テンプレートは編集しません。長さと内容はテンプレートのままなので、装飾用トラックを指定してください。任意の演出が利用できなければその演出を省き、`omitted_features` に理由を残して基本ドラフトを保存します。Pro素材はCapCut側の契約と素材ダウンロードに依存します。暗号化テンプレートには対応していません。

## 保存と納品

既定の保存先は `~/.shorts-only` です。`.env` の `SHORTS_DATA_DIR` で変更できます。SQLite、動画、字幕、個人用設定、`.env` はGitに含めません。

```text
~/.shorts-only/
  pipeline.sqlite3
  jobs/<制作ID>/
    controller.log
    delivery-manifest.json
    drafts.json
    tiktok-capcut/production-state.json
    tiktok-capcut/clips/clips/clip-001/...
```

制作・再接続・ドラフト処理の所要時間と終了コードはSQLiteへ記録します。モデル別の使用量・トークン数はClipForge側の原記録を参照します。ここでは推定課金を新しく作ったり、クレジット適用を推測したりしません。

[ClipForge-Delivery](https://github.com/nyu1791-collab/ClipForge-Delivery)とは別リポジトリです。`delivery-manifest.json` のクリップフォルダをDeliveryの「完成動画を取り込む」に指定できます。ドラフト内で編集した完成版はCapCutから `video.mp4` として新しいフォルダに書き出して取り込みます。自動送信・SNS投稿・DeliveryのDBへの直接書き込みは行いません。

構成と参考元の詳細は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) と [docs/SOURCES.md](docs/SOURCES.md) にあります。
