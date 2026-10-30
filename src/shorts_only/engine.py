"""Standalone production and reusable editor drafts."""
import json
import os
from pathlib import Path
from filelock import FileLock
from . import store
from .settings import location


def clips(job):
    base=Path(job['output'])
    found={}
    # Completed files from older versions remain usable without the old engine.
    for root in (base/'tiktok',base/'tiktok-capcut'):
        found.update({p.name:p for p in (root/'completed').glob('clip-*/clips/clip-*') if (p/'video.mp4').is_file()})
        found.update({p.name:p for p in (root/'clips'/'clips').glob('clip-*') if (p/'video.mp4').is_file()})
    found.update({p.name:p for p in (base/'clips').glob('clip-*') if (p/'video.mp4').is_file() or (p/'source.json').is_file()})
    return [found[name] for name in sorted(found)]


def drafts_dir():
    value = os.getenv('CAPCUT_DRAFTS_DIR', '')
    return location(value) if value else None


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def execute(job, resume=False):
    from .standalone import execute as produce
    return produce(job,resume=resume)


def resume(job):
    return execute(job,resume=True)


def export_drafts(job, override=None, hook=None):
    from .capcut import export
    previous = store.last_production(job['id'])
    production_failed = previous and previous['exit_code'] not in (None, 0)
    production_message = f"制作終了コード {previous['exit_code']}。" if production_failed else ''
    root = Path(override).expanduser().resolve() if override else drafts_dir()
    if root is None:
        store.update(job['id'], 'draft_pending', production_message + 'CAPCUT_DRAFTS_DIR を設定して draft --job で続行できます')
        return []
    profile = json.loads(job['profile'])
    if hook is not None:
        profile['hook'] = hook
    output = Path(job['output'])
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / 'drafts.json'
    records = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else []
    finished = {r.get('clip_key', r['source']) for r in records if (Path(r['draft'])/'draft_content.json').is_file()
                and Path(r['draft']).parent.resolve() == root.resolve() and r.get('profile') == profile}
    collected = clips(job)
    errors = []
    for clip in collected:
        clip_key = str(clip.resolve())
        try:
            clip_key = json.loads((clip/'render.json').read_text(encoding='utf-8')).get('key') or clip_key
        except (OSError, ValueError, AttributeError):
            pass
        if clip_key in finished or str(clip.resolve()) in finished:
            continue
        aid = store.attempt(job['id'], 'draft:' + clip.name)
        try:
            source_path=clip/'source.json'
            if source_path.is_file():
                source=json.loads(source_path.read_text(encoding='utf-8'))
                effective=dict(profile)
                if effective.get('hook_seconds'):
                    effective['hook_seconds']=[source['start']+float(p) for p in effective['hook_seconds']]
                record=export(clip,root,effective,source_video=source['video'],source_srt=source.get('srt'),
                              start=source['start'],end=source['end'])
                record['profile']=profile
            else:
                record=export(clip,root,profile)
            record['clip_key'] = clip_key
            records.append(record)
            save_json(manifest, records)
            store.finish(aid, 0)
        except Exception as error:
            store.finish(aid, 1)
            message = f'{clip.name}: {error}'
            errors.append(message)
            print(message, flush=True)
    if errors:
        store.update(job['id'], 'draft_pending', production_message + '\n'.join(errors))
    elif not collected:
        store.update(job['id'], 'draft_pending', production_message + '回収済み動画はまだありません')
    elif production_failed:
        store.update(job['id'], 'partial', f"回収済み動画のドラフト作成済み。制作終了コード {previous['exit_code']}")
    else:
        store.update(job['id'], 'completed' if previous and previous['exit_code'] == 0 else 'drafts_ready')
    return records

