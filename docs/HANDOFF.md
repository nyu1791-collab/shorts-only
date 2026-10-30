# 汎用の編集素材を書き出す

```powershell
.\run-windows.cmd handoff 制作ID --output C:/work/edit-assets
```

`assets.json` に元素材・描画済み動画（ある場合）・編集データの場所を保存します。クリップごとに `timeline.json`、区間表 `cuts.csv`、編集後の時間軸の `editor-timeline.srt` を作ります。保存したドラフト生成時の区間を使用し、CapCut画面で後から行った手編集を読み出す機能ではありません。

既定では素材をコピーせず保存先を参照します。`--copy-media` を付けると元動画・字幕・描画済み動画も含めます。参照を相対パスにするのでフォルダ全体を別PCへ移せます。元動画が長尺なら、そのコピーに応じた時間と容量を使います。

## OpenTimelineIO

```powershell
.\.venv\Scripts\python -m pip install -r requirements-editors.txt
.\run-windows.cmd handoff 制作ID --output C:/work/edit-assets --otio
```

`timeline.otio` に音声・映像の参照とカットを保存します。字幕は隣のSRTも使用してください。CapCut固有のエフェクト・ワイプ・フォントは移植しません。各編集ソフト側の読み込み対応・アダプターに依存します。

任意の依存がなければOTIOだけ省き、素材一覧とCSV・SRTは作成します。モデル呼び出しや再描画、別サービスへの投稿・納品は行いません。

`assets.json` はこのアプリの素材記録です。別リポジトリの設定やDBを読み書きする専用連携ではありません。ClipForgeやDeliveryを用意せずに使用できます。
