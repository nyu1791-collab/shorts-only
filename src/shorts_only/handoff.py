"""Export collected media and edit decisions without rendering or model requests."""
import csv
import json
import shutil
from fractions import Fraction
from pathlib import Path
from .engine import clips, save_json
from .timeline import read_srt, remap, srt_text


def write_otio(path, video, receipt, plan, subtitles):
    import opentimelineio as otio
    fps = float(Fraction(str(receipt.get('media', {}).get('frame_rate') or '30')))
    def time(seconds):
        return otio.opentime.RationalTime(float(seconds) * fps, fps)
    timeline = otio.schema.Timeline(name=path.stem)
    timeline.metadata['shorts_only'] = {'subtitle_file':'editor-timeline.srt', 'subtitles':subtitles}
    for kind in ('Video', 'Audio'):
        if kind == 'Audio' and receipt.get('media', {}).get('audio') is False:
            continue
        track = otio.schema.Track(name=kind, kind=getattr(otio.schema.TrackKind, kind))
        for part in plan['segments']:
            track.append(otio.schema.Clip(name=part['kind'],
                media_reference=otio.schema.ExternalReference(target_url=video.as_uri() if video.is_absolute() else video.as_posix()),
                source_range=otio.opentime.TimeRange(time(part['source_start']), time(part['duration']))))
        timeline.tracks.append(track)
    otio.adapters.write_to_file(timeline, str(path))


def export_job(job, destination, copy_media=False, otio=False):
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    record_path = Path(job['output'])/'drafts.json'
    drafts = json.loads(record_path.read_text(encoding='utf-8')) if record_path.is_file() else []
    items, warnings = [], []
    for clip in clips(job):
        receipt_path = clip/'render.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.is_file() else {}
        key = receipt.get('key') or str(clip.resolve())
        draft = next((r for r in reversed(drafts) if r.get('clip_key',r.get('source')) in (key,str(clip.resolve()))), None)
        folder = destination/clip.name
        folder.mkdir(exist_ok=True)
        source_path=clip/'source.json'
        source_info=json.loads(source_path.read_text(encoding='utf-8')) if source_path.is_file() else None
        video=Path(source_info['video']) if source_info else clip/'video.mp4'
        captions=Path(source_info['srt']) if source_info and source_info.get('srt') else None
        local = folder/'media'
        if copy_media:
            local.mkdir(exist_ok=True)
            shutil.copy2(video,local/'video.mp4')
            if captions:
                shutil.copy2(captions,local/'source-captions.srt')
            video=local/'video.mp4'
        rendered=None
        if (clip/'video.mp4').is_file():
            rendered=clip/'video.mp4'
            if copy_media:
                rendered_folder=folder/'rendered'
                rendered_folder.mkdir(exist_ok=True)
                for name in ('video.mp4','captions.srt','captions.ass','render.json'):
                    if (clip/name).is_file():
                        shutil.copy2(clip/name,rendered_folder/name)
                rendered=rendered_folder/'video.mp4'
        duration = receipt.get('media',{}).get('duration')
        plan = draft.get('timeline') if draft else None
        if plan is None and duration:
            start=source_info['start'] if source_info else 0
            plan = {'segments':[{'source_start':start,'source_end':start+duration,'target_start':0,'duration':duration,'kind':'body'}], 'duration':duration}
        if plan:
            save_json(folder/'timeline.json',plan)
            with (folder/'cuts.csv').open('w',encoding='utf-8-sig',newline='') as stream:
                fields = ['source_start','source_end','target_start','duration','kind']
                writer=csv.DictWriter(stream,fieldnames=fields)
                writer.writeheader()
                writer.writerows({k:p[k] for k in fields} for p in plan['segments'])
            cue_path=captions if source_info else clip/'captions.srt'
            mapped=remap(read_srt(cue_path),plan['segments']) if cue_path else []
            (folder/'editor-timeline.srt').write_text(srt_text(mapped),encoding='utf-8')
            if otio:
                try:
                    reference=Path('media/video.mp4') if copy_media else video.resolve()
                    write_otio(folder/'timeline.otio',reference,receipt,plan,mapped)
                except Exception as error:
                    warnings.append(f'{clip.name}: OTIO出力を省略: {error}')
        elif otio:
            warnings.append(f'{clip.name}: 編集区間の記録がないためOTIO出力を省略')
        reference=video.relative_to(destination).as_posix() if copy_media else str(video.resolve())
        rendered_reference=(rendered.relative_to(destination).as_posix() if copy_media else str(rendered.resolve())) if rendered else None
        items.append({'source_video':reference,'rendered_video':rendered_reference,
                      'title':(receipt.get('selection') or {}).get('title',clip.name),
                      'editor_files':folder.relative_to(destination).as_posix()})
    manifest={'schema':'shorts-only-assets/v1','job':job['id'],'streamer':job['streamer'],
              'assets':items,'warnings':warnings,'media_copied':copy_media}
    save_json(destination/'assets.json',manifest)
    (destination/'はじめに.txt').write_text('assets.jsonは素材と編集データの一覧です。外部サービスや別のリポジトリへの接続は行いません。\n'
        'cuts.csvとtimeline.otioは編集用です。editor-timeline.srtは編集後の時間軸で、元動画用の字幕とは別です。\n'
        'OTIOにはカットと音声・映像参照を保存します。CapCut固有の装飾・フォント・ワイプは移植しません。\n'
        '素材をコピーしなかった場合、元の動画フォルダを移動しないでください。\n',encoding='utf-8')
    return {'manifest':str(destination/'assets.json'),'clips':len(items),'warnings':warnings}
