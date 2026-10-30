import json
import sqlite3
import time
import uuid
from .settings import data_dir


def connect():
    db = sqlite3.connect(data_dir() / 'pipeline.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, streamer TEXT NOT NULL, url TEXT NOT NULL,
        format TEXT NOT NULL, status TEXT NOT NULL, profile TEXT NOT NULL,
        output TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
        created REAL NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, job TEXT NOT NULL,
        action TEXT NOT NULL, started REAL NOT NULL, finished REAL, exit_code INTEGER);''')
    return db


def create(url, profile, output_format, force_new=False):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM jobs WHERE streamer=? AND url=? AND format=? ORDER BY created DESC LIMIT 1',
                         (profile['streamer'], url, output_format)).fetchone()
        if old and not force_new:
            return dict(old), False
        jid = uuid.uuid4().hex[:16]
        output = str(data_dir() / 'jobs' / jid)
        now = time.time()
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (jid, profile['streamer'], url, output_format, 'created', json.dumps(profile, ensure_ascii=False), output, '', now, now))
        return dict(db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()), True


def get(jid):
    with connect() as db:
        row = db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()
    if row is None:
        raise ValueError(f'制作IDが見つかりません: {jid}')
    return dict(row)


def update(jid, status, error=''):
    with connect() as db:
        db.execute('UPDATE jobs SET status=?,error=?,updated=? WHERE id=?', (status, error, time.time(), jid))


def attempt(jid, action):
    with connect() as db:
        return db.execute('INSERT INTO attempts(job,action,started) VALUES (?,?,?)', (jid, action, time.time())).lastrowid


def finish(aid, code):
    with connect() as db:
        db.execute('UPDATE attempts SET finished=?,exit_code=? WHERE id=?', (time.time(), code, aid))


def listing():
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT id,streamer,format,status,output,error FROM jobs ORDER BY created DESC')]
