import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
from pathlib import Path
import yaml
from filelock import FileLock, Timeout
from . import clipforge, store
from .settings import clipforge_dir, preset, engine_command


def show(value):
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def show_drafts(job, root=None, hook=None):
    records = clipforge.export_drafts(job, root, hook)
    current = store.get(job['id'])
    show({'status':current['status'], 'message':current['error'], 'drafts':records})


def continue_job(job):
    previous = store.last_production(job['id'])
    if job['status'] == 'completed_no_clips':
        show({'status':job['status'], 'output':job['output'], 'message':job['error']})
    elif job['status'] in ('collected','draft_pending','completed','drafts_ready') and (previous is None or previous['exit_code'] == 0):
        if job['format'] != 'mp4':
            Path(job['output']).mkdir(parents=True, exist_ok=True)
            with FileLock(str(Path(job['output'])/'controller.lock'),timeout=0):
                show_drafts(job)
        else:
            show({'status':job['status'], 'output':job['output']})
    else:
        return clipforge.resume(job)
    return 0


def run_one(url, streamer, output_format=None, count=None, hook=None, plan=False, new=False):
    profile = preset(str(streamer))
    if count is not None:
        profile['clips'] = count
    if hook is not None:
        profile['hook'] = hook
    fmt = output_format or profile.get('format','draft')
    if fmt not in ('draft','mp4','both'):
        raise ValueError('format は draft / mp4 / both を指定してください')
    if plan:
        job = {'url':url, 'format':fmt, 'profile':json.dumps(profile), 'output':'<job-output>'}
        show({'streamer':streamer, 'format':fmt, 'goals':{'seconds':'15-60 (advisory)', 'clips':profile.get('clips',5)},
              'command':clipforge.command(job), 'model_calls_performed':False})
        return 0
    job, created = store.create(url, profile, fmt, new)
    if not created:
        print(f"既存の制作を再利用します: {job['id']}", flush=True)
        return continue_job(job)
    try:
        return clipforge.execute(job)
    except Exception as error:
        if store.get(job['id'])['status'] != 'draft_pending':
            store.update(job['id'], 'failed', str(error))
        raise


def main():
    parser = argparse.ArgumentParser(description='ショート動画制作 → CapCutドラフト。尺・本数は目安。')
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run', help='1つの配信から制作')
    run.add_argument('url')
    run.add_argument('--streamer', '--streamer_id', default='01')
    run.add_argument('--format', choices=['draft','mp4','both'])
    run.add_argument('--clips', type=int, help='目安本数（ClipForgeの受付は1〜10）')
    run.add_argument('--hook', choices=['auto','off'])
    run.add_argument('--plan', action='store_true', help='接続・課金せず指示を表示')
    run.add_argument('--new', action='store_true', help='同じURLも別の新規依頼にする')
    batch = sub.add_parser('batch', help='複数配信を並列処理')
    batch.add_argument('file', type=Path)
    batch.add_argument('--workers', type=int, default=2)
    batch.add_argument('--plan', action='store_true')
    resume = sub.add_parser('resume', help='保存済みRunの監視・回収に再接続')
    resume.add_argument('job')
    draft = sub.add_parser('draft', help='回収済み動画からドラフト作成。モデルは呼ばない')
    group = draft.add_mutually_exclusive_group(required=True)
    group.add_argument('--clip', type=Path)
    group.add_argument('--job')
    draft.add_argument('--streamer', '--streamer_id', default='01')
    draft.add_argument('--drafts-dir', type=Path)
    draft.add_argument('--hook', choices=['auto','off'])
    source = sub.add_parser('source', help='元動画を再描画せず指定区間からドラフト作成')
    source.add_argument('video', type=Path)
    source.add_argument('--start', type=float, default=0)
    source.add_argument('--end', type=float)
    source.add_argument('--srt', type=Path, help='元動画と同じ時間軸のSRT')
    source.add_argument('--streamer', '--streamer_id', default='01')
    source.add_argument('--drafts-dir', type=Path)
    source.add_argument('--copy-media', action='store_true', help='元動画全体もドラフト内へコピー')
    source.add_argument('--hook', choices=['auto','off'])
    jobs = sub.add_parser('jobs', help='処理状態と保存先')
    jobs.add_argument('--job', help='制作1件の試行時間と状態を表示')
    sub.add_parser('connect', help='既存のClipForge接続案内。推論は行わない')
    args = parser.parse_args()
    try:
        if args.action == 'run':
            return run_one(args.url,args.streamer,args.format,args.clips,args.hook,args.plan,args.new)
        if args.action == 'batch':
            entries = yaml.safe_load(args.file.read_text(encoding='utf-8'))['jobs']
            def process(item):
                try:
                    return run_one(item['url'],str(item['streamer']),item.get('format'),item.get('clips'),item.get('hook'),args.plan)
                except Exception as error:
                    streamer = item.get('streamer', '?') if isinstance(item, dict) else '?'
                    print(f"{streamer}: {error}", file=sys.stderr, flush=True)
                    return 1
            with ThreadPoolExecutor(max_workers=max(1,args.workers)) as pool:
                codes = list(pool.map(process, entries))
            return 1 if any(codes) else 0
        if args.action == 'jobs':
            if args.job:
                job = store.get(args.job)
                with store.connect() as db:
                    job['attempts'] = [dict(r) for r in db.execute('SELECT action,started,finished,exit_code FROM attempts WHERE job=? ORDER BY id',(args.job,))]
                show(job)
            else:
                show(store.listing())
        elif args.action == 'connect':
            cmd = engine_command('produce_with_gemini.py', '--connections')
            return subprocess.run(cmd, cwd=clipforge_dir()).returncode
        elif args.action == 'resume':
            return continue_job(store.get(args.job))
        elif args.action == 'draft':
            if args.job:
                job = store.get(args.job)
                Path(job['output']).mkdir(parents=True, exist_ok=True)
                with FileLock(str(Path(job['output'])/'controller.lock'),timeout=0):
                    show_drafts(job,args.drafts_dir,args.hook)
            else:
                from .capcut import export
                root = args.drafts_dir or clipforge.drafts_dir()
                if root is None:
                    raise ValueError('--drafts-dir または CAPCUT_DRAFTS_DIR を指定してください')
                profile = preset(args.streamer)
                if args.hook:
                    profile['hook'] = args.hook
                show(export(args.clip,root,profile))
        elif args.action == 'source':
            from .capcut import export
            root = args.drafts_dir or clipforge.drafts_dir()
            if root is None:
                raise ValueError('--drafts-dir または CAPCUT_DRAFTS_DIR を指定してください')
            profile = preset(args.streamer)
            profile['copy_media'] = args.copy_media
            if args.hook:
                profile['hook'] = args.hook
            show(export(args.video.parent,root,profile,source_video=args.video,source_srt=args.srt,start=args.start,end=args.end))
        return 0
    except Timeout:
        print('この制作は処理中です。二重起動は行いません。', file=sys.stderr)
        return 1
    except Exception as error:
        print(f'実行できませんでした: {error}', file=sys.stderr)
        return 1
