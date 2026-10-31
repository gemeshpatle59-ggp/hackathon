"""
SHARED CARE PLAN: the single source of truth every agent reads from and writes to.
SQLite here for zero-setup demos; the SQL is plain enough to port to PostgreSQL.
"""
import json
import sqlite3
from datetime import datetime, timedelta

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients(id TEXT PRIMARY KEY, profile TEXT);
CREATE TABLE IF NOT EXISTS medications(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, name TEXT,
    dose TEXT, times TEXT, notes TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS dose_log(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, ts TEXT, name TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS vitals(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, ts TEXT, systolic REAL,
    diastolic REAL, glucose REAL, spo2 REAL, heart_rate REAL, temp_c REAL);
CREATE TABLE IF NOT EXISTS symptoms(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, ts TEXT, symptom TEXT,
    symptom_en TEXT, severity REAL, duration TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS risk_history(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, ts TEXT, level TEXT,
    score REAL, reasons TEXT, red_flags TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, ts TEXT,
    audience TEXT, level TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS summaries(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, ts TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT, ts TEXT, agent TEXT,
    type TEXT, payload TEXT);
"""

VITAL_KEYS = ("systolic", "diastolic", "glucose", "spo2", "heart_rate", "temp_c")


def _conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _q(sql, params=()):
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def _x(sql, params=()):
    with _conn() as c:
        c.execute(sql, params)


def _num(v):
    try:
        return None if v in (None, "", "null") else float(v)
    except (TypeError, ValueError):
        return None


# ---- profile ---------------------------------------------------------------
def upsert_patient(pid: str, profile: dict):
    _x("INSERT OR REPLACE INTO patients(id, profile) VALUES (?, ?)", (pid, json.dumps(profile, ensure_ascii=False)))


def get_profile(pid: str) -> dict:
    rows = _q("SELECT profile FROM patients WHERE id=?", (pid,))
    return json.loads(rows[0]["profile"]) if rows else {}


def update_profile(pid: str, **fields):
    p = get_profile(pid)
    p.update({k: v for k, v in fields.items() if v})
    upsert_patient(pid, p)


# ---- medicines ---------------------------------------------------------------
def add_medication(pid, name, dose="", times=None, notes=""):
    _x("UPDATE medications SET active=0 WHERE patient_id=? AND lower(name)=lower(?)", (pid, name))
    _x("INSERT INTO medications(patient_id,name,dose,times,notes) VALUES (?,?,?,?,?)",
       (pid, name, dose, json.dumps(times or []), notes))


def remove_medication(pid, name):
    _x("UPDATE medications SET active=0 WHERE patient_id=? AND lower(name)=lower(?)", (pid, name))


def log_dose(pid, name, status, ts=None):
    _x("INSERT INTO dose_log(patient_id,ts,name,status) VALUES (?,?,?,?)", (pid, ts or _now(), name, status))


def adherence(pid, last_n=20):
    """% of recent scheduled doses actually taken (taken / [taken+skipped+missed]); None if no data yet."""
    rows = _q("SELECT status FROM dose_log WHERE patient_id=? ORDER BY id DESC LIMIT ?", (pid, last_n))
    if not rows:
        return None
    return round(100 * sum(1 for r in rows if r["status"] == "taken") / len(rows))


def missed_doses(pid, now=None, grace_min=60):
    """Doses scheduled today that are >= grace_min overdue with no taken/skipped/missed entry logged."""
    now = now or datetime.now()
    missed = []
    for m in _q("SELECT name,dose,times FROM medications WHERE patient_id=? AND active=1", (pid,)):
        for t in json.loads(m["times"] or "[]"):
            h, mi = (int(x) for x in t.split(":"))
            sched = now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if now - sched < timedelta(minutes=grace_min):
                continue                                   # not due yet / still within grace period
            since = (sched - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
            handled = _q("SELECT 1 FROM dose_log WHERE patient_id=? AND lower(name)=lower(?) AND ts>=? LIMIT 1",
                         (pid, m["name"], since))
            if not handled:
                missed.append({"name": m["name"], "dose": m["dose"], "scheduled": t})
    return missed


def due_medications(pid, hhmm: str) -> list:
    meds = _q("SELECT name,dose,times FROM medications WHERE patient_id=? AND active=1", (pid,))
    return [m for m in meds if hhmm in json.loads(m["times"] or "[]")]


# ---- measurements & symptoms -----------------------------------------------------
def add_vital(pid, **kw):
    vals = {k: _num(kw.get(k)) for k in VITAL_KEYS}
    if all(v is None for v in vals.values()):
        return
    _x("INSERT INTO vitals(patient_id,ts,systolic,diastolic,glucose,spo2,heart_rate,temp_c) VALUES (?,?,?,?,?,?,?,?)",
       (pid, _now(), *[vals[k] for k in VITAL_KEYS]))


def add_symptom(pid, symptom, symptom_en="", severity=None, duration="", notes=""):
    _x("INSERT INTO symptoms(patient_id,ts,symptom,symptom_en,severity,duration,notes) VALUES (?,?,?,?,?,?,?)",
       (pid, _now(), symptom, symptom_en or symptom, _num(severity), duration or "", notes or ""))


# ---- risk / notifications / summaries / events -------------------------------------
def save_risk(pid, level, score, reasons, red_flags):
    _x("INSERT INTO risk_history(patient_id,ts,level,score,reasons,red_flags) VALUES (?,?,?,?,?,?)",
       (pid, _now(), level, score, json.dumps(reasons, ensure_ascii=False), json.dumps(red_flags, ensure_ascii=False)))


def add_notification(pid, audience, level, message):
    _x("INSERT INTO notifications(patient_id,ts,audience,level,message) VALUES (?,?,?,?,?)",
       (pid, _now(), audience, level, message))


def save_summary(pid, text):
    _x("INSERT INTO summaries(patient_id,ts,text) VALUES (?,?,?)", (pid, _now(), text))


def log_event(pid, agent, type_, payload):
    _x("INSERT INTO events(patient_id,ts,agent,type,payload) VALUES (?,?,?,?,?)",
       (pid, _now(), agent, type_, json.dumps(payload, ensure_ascii=False)))


def recent_chat(pid, n=6) -> list:
    rows = _q("SELECT payload FROM events WHERE patient_id=? AND type='chat' ORDER BY id DESC LIMIT ?", (pid, n))
    return [json.loads(r["payload"]) for r in reversed(rows)]


def notifications(pid, limit=10) -> list:
    return _q("SELECT ts,audience,level,message FROM notifications WHERE patient_id=? ORDER BY id DESC LIMIT ?",
              (pid, limit))


# ---- the snapshot every agent reads --------------------------------------------------
def snapshot(pid: str) -> dict:
    return {
        "profile": get_profile(pid),
        "medications": _q("SELECT name,dose,times,notes FROM medications WHERE patient_id=? AND active=1", (pid,)),
        "medication_adherence_pct": adherence(pid),
        "recent_doses": _q("SELECT ts,name,status FROM dose_log WHERE patient_id=? ORDER BY id DESC LIMIT 10", (pid,)),
        "recent_vitals": _q("SELECT * FROM vitals WHERE patient_id=? ORDER BY id DESC LIMIT 5", (pid,)),
        "recent_symptoms": _q("SELECT ts,symptom_en,severity,duration,notes FROM symptoms WHERE patient_id=? "
                              "ORDER BY id DESC LIMIT 10", (pid,)),
        "recent_risk": _q("SELECT ts,level,score,reasons FROM risk_history WHERE patient_id=? ORDER BY id DESC LIMIT 3",
                          (pid,)),
        "last_summary": (_q("SELECT ts,text FROM summaries WHERE patient_id=? ORDER BY id DESC LIMIT 1", (pid,)) or [None])[0],
    }
