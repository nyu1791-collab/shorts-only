import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')


def location(value):
    path = Path(value).expanduser()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def data_dir():
    path = location(os.getenv('SHORTS_DATA_DIR') or str(Path.home() / '.shorts-only'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def preset(streamer):
    path = location(os.getenv('SHORTS_STREAMERS') or 'config/streamers.yaml')
    if not path.exists():
        path = ROOT / 'config/streamers.example.yaml'
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    profiles = {str(k): v for k, v in config.get('streamers', {}).items()}
    if streamer not in profiles:
        raise ValueError(f'配信者 {streamer} が設定されていません: {path}')
    return {**config.get('defaults', {}), **profiles[streamer], 'streamer': streamer}
