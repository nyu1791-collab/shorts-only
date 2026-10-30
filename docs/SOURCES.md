# 参考元と採用範囲

以下はGitHubのREADME・公開メタデータを参照したものです。全ツールを実行済みという意味ではありません。本リポジトリの制御・状態管理・時刻対応コードは独自実装です。

| リポジトリ | 公開情報から分かる用途 | 今回の採用 |
|---|---|---|
| [GuanYixuan/pyCapCut](https://github.com/GuanYixuan/pyCapCut) | Pythonで動画・テキスト・テンプレートを含むCapCutドラフトを生成。最終書き出しはCapCutアプリで手動 | `pycapcut==0.0.4` を任意依存として使用。次期トラックAPI変更を避けて版を固定 |
| [ClipsAI/clipsai](https://github.com/ClipsAI/clipsai) | WhisperXによる文字起こしベースの切り抜き、Pyannoteを使う話者中心のリフレーム。音声主体の動画向け | リフレームと切り抜きを分離する構成を参考。未導入。今回のワイプは設定座標で配置 |
| [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) | 音量や動きによる区間選択。余白を残す無音削除 | 時刻対応と余白の考え方を参考。依存追加はせず、必要時のみFFmpegの無音検出を使用 |
| [aaurelions/short-video-maker](https://github.com/aaurelions/short-video-maker) | テキストから教育用ショート生成。Gemini、SQLite、再開、APIキーローテーション | SQLiteで制作を分ける設計のみ参考。キーローテーションや制限回避は採用しない |
| [gyoridavid/short-video-maker](https://github.com/gyoridavid/short-video-maker) | Kokoro TTS・Whisper・Pexels・Remotionによる生成、MCP/REST入口 | 各処理を入口から分離する構成を参考。MCPサーバー自体は今回未実装 |
| [nyu1791-collab/ClipForge](https://github.com/nyu1791-collab/ClipForge) | 既存の話題選定、Transcribe、整文、素材取得、描画、非公開保存 | 実制作のバックエンドとしてそのまま呼び出す |

pyCapCut上流のGitHubライセンス欄は取得時点で未表示でした。ソースや素材の複製は行わず、PyPIのライブラリを外部依存として使用しています。テンプレート・フォント・Pro素材の権利や利用可否はそれぞれの提供元の条件に従います。

素材取得について、今回のURL対応はClipForgeに委譲します。ふわっちのアーカイブ取得やコメント取得を追加実装したとは扱いません。チャット急増を起点にする検出、顔の自動追跡、CapCutの自動最終書き出し、ネイティブ単語カラオケの生成も今回の実装範囲には含まれません。
