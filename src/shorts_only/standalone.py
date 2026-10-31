"""Independent short-video production from local media or a public HTTPS URL."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.parse
import urllib.request
from filelock import FileLock
from . import ffmpeg_recipes as fr
from . import store
from .settings import location
from .timeline import read_srt, remap, srt_text, build


def save(path, value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)



def _ass_color(value,default='FFFFFF'):
    value=str(value or default).lstrip('#')
    value=value if len(value)==6 else default
    return '&H00'+value[4:6]+value[2:4]+value[0:2]


def caption_style(profile):
    """Bold, outlined captions sized for vertical video. Libass scales SRT styles
    from a 288px-high script, so sizes here are relative to that."""
    size=round(float(profile.get('subtitle_size',8))*1.75)
    margin=max(8,round((1+float(profile.get('subtitle_y',-0.65)))/2*288))
    font=profile.get('burn_font') or 'Noto Sans CJK JP'
    return ','.join([f'Fontname={font}',f'FontSize={size}','Bold=1',
        f"PrimaryColour={_ass_color(profile.get('subtitle_color'))}",'OutlineColour=&H00000000',
        'BackColour=&H80000000','BorderStyle=1','Outline=1.6','Shadow=0.6','Alignment=2',
        f'MarginV={margin}','MarginL=16','MarginR=16'])


def acquire(job):
    output=Path(job['output'])
    state=output/'source-state.json'
    if state.is_file():
        source=Path(json.loads(state.read_text(encoding='utf-8'))['path'])
        if source.is_file():
            return source
        raise FileNotFoundError(f'保存済み元動画が見つかりません: {source}')
    url=job['url']
    if not url.startswith('https://'):
        source=Path(url).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f'元動画が見つかりません: {source}')
    else:
        parsed=urllib.parse.urlsplit(url)
        if parsed.username or parsed.password:
            raise ValueError('認証情報を埋め込んだURLは使用できません')
        source=output/'source.mp4'
        if parsed.path.lower().endswith(('.mp4','.mov','.mkv','.webm')):
            temporary=output/'source.download'
            with urllib.request.urlopen(url,timeout=120) as response, temporary.open('wb') as stream:
                if urllib.parse.urlsplit(response.url).scheme!='https':
                    raise ValueError('素材取得先はHTTPSを指定してください')
                shutil.copyfileobj(response,stream)
            temporary.replace(source)
        else:
            with (output/'download.log').open('ab') as log:
                subprocess.run(['yt-dlp','--no-playlist','--no-overwrites','--retries','0',
                                '-f','bv*[height<=720]+ba/b[height<=720]/b','--merge-output-format','mp4',
                                '-o',str(output/'download.%(ext)s'),url],check=True,
                               stdout=log,stderr=subprocess.STDOUT)
            source=next((p for p in output.glob('download.*') if p.suffix.lower() in ('.mp4','.mkv','.webm','.mov')),None)
            if source is None:
                raise FileNotFoundError('ダウンロード済み動画が見つかりません')
    save(state,{'path':str(source)})
    return source


def media_info(video):
    result=subprocess.run(['ffprobe','-v','error','-show_entries',
        'format=duration:stream=codec_type,width,height,r_frame_rate','-of','json',str(video)],
        capture_output=True,text=True,check=True)
    info=json.loads(result.stdout)
    stream=next(s for s in info['streams'] if s['codec_type']=='video')
    return {'duration':float(info['format']['duration']),'width':stream['width'],'height':stream['height'],
            'frame_rate':stream.get('r_frame_rate','30'),'audio':any(s['codec_type']=='audio' for s in info['streams'])}


def choose(video, output, profile, media, source_key):
    saved=output/'selections.json'
    if saved.is_file():
        record=json.loads(saved.read_text(encoding='utf-8'))
        if record['source_key']!=source_key:
            raise ValueError('元動画が変更されています。別の新規依頼として制作してください')
        return record['items']
    duration=media['duration']
    if profile.get('cuts'):
        rows=[{'start':max(0,float(a)),'end':min(duration,float(b)),'title':f"{profile['name']} ショート {i}"}
              for i,(a,b) in enumerate(profile['cuts'],1) if min(duration,float(b))>max(0,float(a))]
        method='explicit_ranges'
    elif profile.get('analysis')=='gemini':
        from .gemini import select_ranges
        rows=select_ranges(video,output,profile,duration)
        method='gemini_audio_selection'
    else:
        cues=read_srt(location(profile['source_srt'])) if profile.get('source_srt') else []
        count=max(1,int(profile.get('clips',5)))
        seconds=min(duration,max(1,float(profile.get('target_seconds',45))))
        if cues:
            ranked=sorted(cues,key=lambda c:sum(c['text'].count(w) for w in ('!','！','?','？','すご','やば','まじ')),reverse=True)
            starts=[]
            for cue in ranked:
                start=max(0,min(cue['start'],duration-seconds))
                if all(abs(start-other)>=seconds for other in starts):
                    starts.append(start)
                if len(starts)>=count:
                    break
            method='subtitle_heuristic'
        else:
            starts=[]
            for i in range(count):
                start=max(0,min(i*duration/count,duration-seconds))
                if start not in starts:
                    starts.append(start)
            method='uniform_excerpt'
        rows=[{'start':start,'end':min(duration,start+seconds),'title':f"{profile['name']} ショート {i}"} for i,start in enumerate(starts,1)]
    rows=[{**row,'start':max(0,float(row['start'])),'end':min(duration,float(row['end'])),'method':method}
          for row in rows if min(duration,float(row['end']))>max(0,float(row['start']))]
    save(saved,{'source_key':source_key,'items':rows,'method':method})
    return rows


def execute(job,resume=False):
    from .engine import export_drafts
    output=Path(job['output'])
    output.mkdir(parents=True,exist_ok=True)
    with FileLock(str(output/'controller.lock'),timeout=0):
        profile=json.loads(job['profile'])
        store.update(job['id'],'producing')
        aid=store.attempt(job['id'],'produce')
        try:
            video=acquire(job)
            media=media_info(video)
            stat=video.stat()
            source_key=hashlib.sha256(json.dumps([str(video),stat.st_size,stat.st_mtime_ns]).encode()).hexdigest()
            selections=choose(video,output,profile,media,source_key)
        except Exception as error:
            store.finish(aid,1)
            store.update(job['id'],'failed',str(error))
            raise
        original_cues=read_srt(location(profile['source_srt'])) if profile.get('source_srt') else []
        def produce_clip(pair):
            number,item=pair
            clip=output/'clips'/f'clip-{number:03d}'
            clip.mkdir(parents=True,exist_ok=True)
            start,end=item['start'],item['end']
            duration=end-start
            receipt=clip/'render.json'
            prior=json.loads(receipt.read_text(encoding='utf-8')) if receipt.is_file() else {}
            if prior.get('status')=='ready' and (job['format']=='draft' or (clip/'video.mp4').is_file()):
                return None
            try:
                source_srt=location(profile['source_srt']) if profile.get('source_srt') else None
                cues=remap(original_cues,build(media['duration'],[],hook='off',cuts=[(start,end)])['segments'])
                if profile.get('analysis')=='gemini' and not source_srt:
                    from .gemini import transcribe_clip
                    transcribe_clip(video,clip,profile,start,end)
                    cues=read_srt(clip/'captions.srt')
                    source_srt=clip/'source-captions.srt'
                    source_srt.write_text(srt_text([{**c,'start':c['start']+start,'end':c['end']+start} for c in cues]),encoding='utf-8')
                (clip/'captions.srt').write_text(srt_text(cues),encoding='utf-8')
                save(clip/'source.json',{'video':str(video),'start':start,'end':end,
                                       'srt':str(source_srt) if source_srt else None})
                width,height=int(profile.get('width',720)),int(profile.get('height',1280))
                length=duration
                if job['format'] in ('mp4','both') and not (clip/'video.mp4').is_file():
                    cut=None
                    if profile.get('jump_cuts'):
                        # Remove dead air (auto-editor style) and move captions with the cut.
                        ranges=fr.keep_ranges(duration,fr.detect_silences(video,start=start,duration=duration),
                                              margin=float(profile.get('jump_margin',0.15)))
                        if len(ranges)>1:
                            cut=fr.jump_cut_filter(ranges)
                            length=sum(b-a for a,b in ranges)
                            cues=[{**c,'start':fr.remap_time(c['start'],ranges),'end':fr.remap_time(c['end'],ranges)}
                                  for c in cues]
                            cues=[c for c in cues if c['end']-c['start']>0.05]
                            (clip/'captions.srt').write_text(srt_text(cues),encoding='utf-8')
                    vf=fr.fit_frame(width,height,profile.get('background','blur'))
                    if cut:
                        vf=cut[0]+','+vf
                    if cues:
                        vf+=",subtitles=captions.srt:force_style='"+caption_style(profile)+"'"
                    video_fade,audio_fade=fr.fades(length)
                    if video_fade:
                        vf+=','+video_fade
                    af=fr.voice_chain(denoise=bool(profile.get('denoise',False)))
                    if cut:
                        af=cut[1]+','+af
                    if audio_fade:
                        af+=','+audio_fade
                    with (clip/'render.log').open('ab') as log:
                        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-ss',str(start),'-i',str(video),'-t',str(duration),
                            '-vf',vf,'-af',af,*fr.delivery_args(profile.get('quality','standard'),profile.get('encoder','libx264')),
                            'video.next.mp4'],cwd=clip,check=True,stdout=log,stderr=subprocess.STDOUT)
                    (clip/'video.next.mp4').replace(clip/'video.mp4')
                save(receipt,{'key':f'{source_key}:{start}:{end}','status':'ready','selection':item,
                    'media':{**media,'duration':length,**({'width':width,'height':height} if job['format'] in ('mp4','both') else {})},'captions':{'caption_mode':'burned' if cues and job['format'] in ('mp4','both') else 'editable'}})
            except Exception as error:
                message=f'{clip.name}: {error}'
                print(message,flush=True)
                return message
            return None
        with ThreadPoolExecutor(max_workers=max(1,int(profile.get('workers',2)))) as pool:
            errors=[message for message in pool.map(produce_clip,enumerate(selections,1)) if message]
        store.finish(aid,1 if errors else 0)
        store.update(job['id'],'partial' if errors else 'collected','\n'.join(errors))
        if job['format']!='mp4':
            export_drafts(job)
        elif not errors:
            store.update(job['id'],'completed' if selections else 'completed_no_clips')
        print(json.dumps({'job':job['id'],'selected':len(selections),'errors':errors,'output':str(output)},ensure_ascii=False),flush=True)
        return 1 if errors else 0
