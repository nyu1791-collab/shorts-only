"""Optional pyCapCut adapter. Creates a new, self-contained draft directory."""
import json
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from .timeline import build, read_srt, remap, srt_text, silence_cuts


def color(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i+2], 16)/255 for i in (0, 2, 4))


def export(clip, root, profile, source_video=None, source_srt=None, start=0, end=None):
    import pycapcut as cc
    clip, root = Path(clip).resolve(), Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = Path(source_video).resolve() if source_video else clip / 'video.mp4'
    receipt_path = clip / 'render.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.is_file() and not source_video else {}
    if source_video:
        receipt = {'captions':{'caption_mode':'editable'}, 'selection':{'title':source.stem}}
    material = cc.VideoMaterial(str(source))
    duration = material.duration / cc.SEC
    mode = (receipt.get('captions') or {}).get('caption_mode')
    # Burned captions remain visible: do not overlay a second subtitle track.
    burned = mode not in ('editable', 'none', 'off')
    captions_path = Path(source_srt).resolve() if source_srt else clip / 'captions.srt'
    captions = read_srt(captions_path) if source_srt or not source_video else []
    omitted = []
    cuts = profile.get('cuts')
    if source_video:
        cuts = [(start, duration if end is None else end)]
    if profile.get('jetcut') and cuts is None:
        try:
            cuts = silence_cuts(source,duration)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            omitted.append({'feature':'jetcut','reason':str(error)})
    timeline = build(duration, captions, profile.get('hook', 'auto'), cuts, profile.get('hook_seconds'))
    if not timeline['segments']:
        raise ValueError('利用できる動画区間がありません')
    name = 'shorts-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    script = cc.DraftFolder(str(root)).create_draft(name, int(profile.get('width',720)), int(profile.get('height',1280)))
    project = root / name
    media = project / 'media'
    media.mkdir()
    # Independent media lets the engine output be moved without breaking this draft.
    copy_media = not source_video or profile.get('copy_media',False)
    video_path = media / 'video.mp4' if copy_media else source
    if copy_media:
        shutil.copy2(source, video_path)
    if source_srt:
        shutil.copy2(captions_path, media/'captions.srt')
    if not source_video:
        for filename in ('captions.srt', 'captions.ass', 'render.json', 'words.json', 'transcript.json'):
            if (clip / filename).is_file():
                shutil.copy2(clip / filename, media / filename)
    material = cc.VideoMaterial(str(video_path))
    def cropped(region):
        x, y, w, h = map(float, region)
        return cc.VideoMaterial(str(video_path), crop_settings=cc.CropSettings(
            upper_left_x=x, upper_left_y=y, upper_right_x=x+w, upper_right_y=y,
            lower_left_x=x, lower_left_y=y+h, lower_right_x=x+w, lower_right_y=y+h))
    if profile.get('video_crop'):
        material = cropped(profile['video_crop'])
    script.add_track(cc.TrackType.video, 'video')
    for part in timeline['segments']:
        segment = cc.VideoSegment(material, cc.trange_seconds(part['target_start'], duration=part['duration']),
                                  source_timerange=cc.trange_seconds(part['source_start'], end=part['source_end']),
                                  clip_settings=cc.ClipSettings(scale_x=profile.get('video_scale',1), scale_y=profile.get('video_scale',1),
                                                                transform_x=profile.get('video_x',0), transform_y=profile.get('video_y',0)))
        if profile.get('video_effect'):
            try:
                segment.add_effect(cc.VideoSceneEffectType.from_name(profile['video_effect']))
            except Exception as error:
                omitted.append({'feature':'video_effect','reason':str(error)})
        script.add_segment(segment, 'video')
    face = profile.get('face') or {}
    if face.get('crop'):
        face_material = cropped(face['crop'])
        script.add_track(cc.TrackType.video, 'face', relative_index=2)
        for part in timeline['segments']:
            script.add_segment(cc.VideoSegment(face_material, cc.trange_seconds(part['target_start'], duration=part['duration']),
                source_timerange=cc.trange_seconds(part['source_start'], end=part['source_end']), volume=0,
                clip_settings=cc.ClipSettings(scale_x=face.get('scale',0.35), scale_y=face.get('scale',0.35),
                                              transform_x=face.get('x',0), transform_y=face.get('y',0.55))), 'face')
    mapped = remap(captions, timeline['segments'])
    (project / 'timeline-captions.srt').write_text(srt_text(mapped), encoding='utf-8')
    if not burned and mapped:
        script.add_track(cc.TrackType.text, 'captions')
        font = getattr(cc.FontType, profile.get('font',''), None)
        for cue in mapped:
            segment = cc.TextSegment(cue['text'], cc.trange_seconds(cue['start'], end=cue['end']), font=font,
                                     style=cc.TextStyle(size=profile.get('subtitle_size',8), bold=True, align=1,
                                                        color=color(profile.get('subtitle_color','#FFFFFF')), auto_wrapping=True),
                                     clip_settings=cc.ClipSettings(transform_y=profile.get('subtitle_y',-0.65)))
            script.add_segment(segment, 'captions')
    title = (receipt.get('selection') or {}).get('title', '')
    if title:
        script.add_track(cc.TrackType.text, 'heading')
        script.add_segment(cc.TextSegment(str(title), cc.trange_seconds(0, duration=min(3,timeline['duration'])),
                                          style=cc.TextStyle(size=8, bold=True, align=1, auto_wrapping=True,
                                                             color=color(profile.get('accent_color','#FFE568'))),
                                          clip_settings=cc.ClipSettings(transform_y=0.75)), 'heading')
    # Explicitly named decorative template tracks can carry user-owned Pro resources.
    # Missing optional resources are recorded and omitted; the base draft is still saved.
    if profile.get('template_draft'):
        try:
            template = cc.DraftFolder(str(root)).load_template(profile['template_draft'])
            for index, item in enumerate(profile.get('template_tracks', [])):
                track = template.get_imported_track(getattr(cc.TrackType, item['kind']), name=item['name'])
                script.import_track(template, track, new_name=f'template-{index}', relative_index=10+index)
        except Exception as error:
            omitted.append({'feature':'template_tracks','reason':str(error)})
    script.save()
    record = {'status':'created_not_opened_in_capcut', 'draft':str(project), 'source':str(clip),
              'timeline':timeline, 'subtitle_track':('unknown_source_preserved' if mode is None else 'burned_in_source') if burned else 'editable_phrases',
              'word_alignment':'original_files_preserved_no_new_alignment', 'profile':profile,
              'omitted_features':omitted, 'video':str(video_path), 'media_copied':copy_media}
    (project / 'shorts-only.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record
