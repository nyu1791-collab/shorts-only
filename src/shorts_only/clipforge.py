"""Delegate model work to ClipForge's existing public Actions entry point."""
import json
import os
from pathlib import Path
import subprocess
from filelock import FileLock
from . import store
from .settings import clipforge_dir, location


def command(job, resume=False):
    engine = clipforge_dir()
    python = engine / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    script = engine / 'tools' / ('produce_with_gemini.py' if resume else 'produce_formats.py')
    if resume:
        return [str(python), str(script), '--resume', '--output', str(production_dir(job))]
    profile = json.loads(job['profile'])
    return [str(python), str(script), job['url'], '--mode', 'tiktok' if job['format']=='mp4' else 'tiktok-capcut',
            '--output', job['output'], '--clips', str(profile.get('clips',5))]


def production_dir(job):
    return Path(job['output']) / ('tiktok' if job['format']=='mp4' else 'tiktok-capcut')


def clips(job):
    return sorted(p for p in (production_dir(job) / 'clips' / 'clips').glob('clip-*') if (p/'video.mp4').is_file())


def drafts_dir():
    value = os.getenv('CAPCUT_DRAFTS_DIR', '')
    return location(value) if value else None


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def resume(job):
    saved = production_dir(job) / 'production-state.json'
    previous = store.last_production(job['id'])
    # A missing executable or an OS launch failure never started a production.
    never_started = previous is None or previous['action'] == 'launch_failed'
    return execute(job, resume=saved.is_file() or not never_started)


def export_drafts(job, override=None, hook=None):
    from .capcut import export
    previous = store.last_production(job['id'])
    production_failed = previous and previous['exit_code'] not in (None, 0)
    production_message = f"ClipForge終了コード {previous['exit_code']}。" if production_failed else ''
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
    finished = {r['source'] for r in records if (Path(r['draft'])/'draft_content.json').is_file()
                and Path(r['draft']).parent.resolve() == root.resolve() and r.get('profile') == profile}
    collected = clips(job)
    errors = []
    for clip in collected:
        if str(clip.resolve()) in finished:
            continue
        aid = store.attempt(job['id'], 'draft:' + clip.name)
        try:
            records.append(export(clip, root, profile))
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
        store.update(job['id'], 'partial', f"回収済み動画のドラフト作成済み。ClipForge終了コード {previous['exit_code']}")
    else:
        store.update(job['id'], 'completed' if previous and previous['exit_code'] == 0 else 'drafts_ready')
    return records


def execute(job, resume=False):
    output = Path(job['output'])
    output.mkdir(parents=True, exist_ok=True)
    with FileLock(str(output/'controller.lock'), timeout=0):
        saved = production_dir(job) / 'production-state.json'
        if resume and not saved.is_file():
            raise ValueError(f'保存済みRunがありません。新規投入は行いません: {output}')
        cmd = command(job, resume)
        if not Path(cmd[0]).is_file() or not Path(cmd[1]).is_file():
            raise FileNotFoundError('CLIPFORGE_DIR とClipForgeの .venv を設定してください')
        store.update(job['id'], 'observing' if resume else 'producing')
        aid = store.attempt(job['id'], 'resume' if resume else 'produce')
        print(f"[{job['id']}] {'再接続' if resume else '制作開始'} → {output}", flush=True)
        try:
            with (output/'controller.log').open('ab') as log:
                result = subprocess.run(cmd, cwd=clipforge_dir(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                        env={**os.environ, 'PYTHONUTF8':'1'})
            store.finish(aid, result.returncode)
        except OSError as error:
            store.finish(aid, -1, action='launch_failed')
            store.update(job['id'], 'failed', str(error))
            raise
        collected = clips(job)
        # Export what actually exists; a shortfall never triggers another model call.
        (output/'delivery-manifest.json').write_text(json.dumps({
            'job':job['id'], 'streamer':job['streamer'], 'source_url':job['url'],
            'format':job['format'], 'clips':[str(p.resolve()) for p in collected],
            'engine_output':str(production_dir(job)), 'api_cost':'see original engine usage records; no estimate inferred'},
            ensure_ascii=False, indent=2), encoding='utf-8')
        if result.returncode:
            store.update(job['id'], 'failed', f'ClipForge終了コード {result.returncode}; {output}/controller.log')
            print(f"[{job['id']}] 未完了。完成済み {len(collected)}本を保持。resume で既存Runへ再接続できます", flush=True)
            if collected and job['format'] != 'mp4':
                export_drafts(job)
            return result.returncode
        if not collected:
            store.update(job['id'], 'completed_no_clips', 'ClipForgeの処理は終了しましたが、回収済み動画は0本です')
            print(f"[{job['id']}] 処理終了。回収済み動画は0本です", flush=True)
            return 0
        store.update(job['id'], 'collected')
        if job['format'] != 'mp4':
            export_drafts(job)
        else:
            store.update(job['id'], 'completed')
        current = store.get(job['id'])
        print(f"[{job['id']}] 回収 {len(collected)}本 / {current['status']} {current['error']}", flush=True)
        return 0
