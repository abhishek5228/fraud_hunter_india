"""Append-only audit trail in SQLite: who was scored, what was decided, by which model version, and every human action.
Set FH_AUDIT_DB to put it on a persistent disk. On a host with an ephemeral filesystem it resets on redeploy."""
import json
import os
import sqlite3
import threading
import time


class Audit:
    def __init__(s, path):
        s.path, s.lk = path, threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        s.db = sqlite3.connect(path, check_same_thread=False)
        s.db.execute("""create table if not exists audit(id integer primary key autoincrement, at real, kind text, case_id text, uid text,
                        amt real, chan text, decision text, p real, codes text, model text, detail text)""")
        s.db.execute("create index if not exists ix_case on audit(case_id)")
        s.db.commit()

    def log(s, kind, case_id=None, uid=None, amt=None, chan=None, decision=None, p=None, codes=None, model=None, detail=None):
        with s.lk:
            s.db.execute("insert into audit(at,kind,case_id,uid,amt,chan,decision,p,codes,model,detail) values (?,?,?,?,?,?,?,?,?,?,?)",
                         (time.time(), kind, case_id, uid, amt, chan, decision, p, "|".join(codes or []), model, json.dumps(detail) if detail is not None else None))
            s.db.commit()

    def recent(s, limit=50, kind=None):
        q, a = "select id,at,kind,case_id,uid,amt,chan,decision,p,codes,model,detail from audit", []
        if kind:
            q, a = q + " where kind=?", [kind]
        with s.lk:
            rows = s.db.execute(q + " order by id desc limit ?", a + [max(1, min(500, limit))]).fetchall()
        k = ("id", "at", "kind", "case_id", "uid", "amt", "chan", "decision", "p", "codes", "model", "detail")
        return [dict(zip(k, r)) for r in rows]

    def count(s):
        with s.lk:
            return s.db.execute("select count(*) from audit").fetchone()[0]
