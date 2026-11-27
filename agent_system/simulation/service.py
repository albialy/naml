"""Durable owned snapshots and a bounded queue, shared by API and worker."""
import hashlib
import json
import os
import time
import uuid
from fastapi import HTTPException
from agent_system.core.database import get_database, now
from agent_system.core.projects import get_project
from .schema import SaveScenario, RunRequest

QUEUE = "simulation:queue"
LEASE_SECONDS = 120
ACTIVE = ("queued", "running")

def enabled():
    return os.getenv("NAML_SIMULATION_ENABLED", "false").lower() == "true"

def pulse():
    get_database().set_document("simulation:heartbeat", {"at": time.time()})

def availability():
    heartbeat = get_database().get_document("simulation:heartbeat", {}).get("at", 0)
    return {"enabled": enabled(), "available": enabled() and time.time() - heartbeat < 30}

def owned(doc, user_id):
    if not doc or doc.get("user_id") != user_id:
        raise HTTPException(404, "التجربة غير موجودة أو غير متاحة لحسابك")
    return doc

def digest(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

def public(doc):
    fields = ("id", "created_at", "project_id", "project_revision", "parent_id", "spec",
              "input_hash", "scenario_id", "seed", "repetitions", "status", "message",
              "started_at", "completed_at")
    result = {k: doc[k] for k in fields if k in doc}
    if "result" in doc:
        raw = doc.get("result")
        result["result"] = {k: raw[k] for k in ("unit", "seed", "repetitions", "summary", "stations", "trials", "limitations") if k in raw} if raw else None
    return result

def list_scenarios(user_id):
    db = get_database()
    ids = db.get_document("simulation:scenarios:" + user_id, [])
    return [public(owned(db.get_document("simulation:scenario:" + sid), user_id)) for sid in reversed(ids)]

def save_scenario(user_id, body: SaveScenario):
    db = get_database()
    project = None
    if body.project_id:
        try:
            project = get_project(body.project_id, user_id)
        except KeyError:
            raise HTTPException(404, "المشروع غير متاح")
    if body.parent_id:
        parent = owned(db.get_document("simulation:scenario:" + body.parent_id), user_id)
        if parent.get("project_id") != body.project_id:
            raise HTTPException(409, "نسخة السيناريو يجب أن تبقى داخل المشروع نفسه")
    spec = body.spec.model_dump()
    doc = {"id": str(uuid.uuid4()), "user_id": user_id, "created_at": now(),
           "project_id": body.project_id, "project_revision": project["revision"] if project else None,
           "parent_id": body.parent_id, "spec": spec, "input_hash": digest(spec)}
    with db.connection(write=True) as conn:
        key = "simulation:scenarios:" + user_id
        db.lock(conn, key)
        ids = db._get(conn, key, [])
        if len(ids) >= 100:
            raise HTTPException(429, "وصلت إلى حد 100 نسخة محفوظة في هذه المرحلة")
        db._put(conn, "simulation:scenario:" + doc["id"], doc)
        db._put(conn, key, ids + [doc["id"]])
    return public(doc)

def get_run(user_id, run_id):
    return public(owned(get_database().get_document("simulation:run:" + run_id), user_id))

def list_runs(user_id):
    db = get_database()
    ids = db.get_document("simulation:runs:" + user_id, [])
    rows = []
    for rid in reversed(ids):
        doc = owned(db.get_document("simulation:run:" + rid), user_id)
        rows.append({k: doc.get(k) for k in ("id", "scenario_id", "project_id", "status", "created_at", "seed", "repetitions")} |
                    {"name": doc["spec"]["name"], "summary": (doc.get("result") or {}).get("summary")})
    return rows

def enqueue(user_id, body: RunRequest):
    db = get_database()
    scenario = owned(db.get_document("simulation:scenario:" + body.scenario_id), user_id)
    spec = scenario["spec"]
    if spec["max_entities"] * len(spec["stages"]) * body.repetitions > 200000:
        raise HTTPException(422, "قلل عدد الوحدات أو المراحل أو التكرارات؛ التجربة تتجاوز حد الحساب")
    with db.connection(write=True) as conn:
        db.lock(conn, QUEUE)
        key = "simulation:runs:" + user_id
        ids = db._get(conn, key, [])
        previous = [db._get(conn, "simulation:run:" + rid) for rid in ids]
        duplicate = next((r for r in previous if r["request_key"] == body.request_key), None)
        if duplicate:
            if (duplicate["scenario_id"], duplicate["seed"], duplicate["repetitions"]) != (body.scenario_id, body.seed, body.repetitions):
                raise HTTPException(409, "طلب التشغيل مكرر بمدخلات مختلفة")
            return public(duplicate)
        heartbeat = db._get(conn, "simulation:heartbeat", {}).get("at", 0)
        if not enabled() or time.time() - heartbeat >= 30:
            raise HTTPException(503, "المحاكاة غير جاهزة للتشغيل الآن. يمكنك حفظ السيناريو والعودة إليه لاحقًا.")
        if sum(r["status"] in ACTIVE for r in previous) >= 2:
            raise HTTPException(429, "لديك تجربتان قيد التنفيذ. انتظر اكتمالهما أو أوقف إحداهما.")
        if len(ids) >= 200 or sum(r["created_at"][:10] == now()[:10] for r in previous) >= 30:
            raise HTTPException(429, "وصلت إلى حد التجارب المتاح لهذا الحساب")
        queue = db._get(conn, QUEUE, [])
        if len(queue) >= 100:
            raise HTTPException(429, "التجارب مشغولة حاليًا. أعد المحاولة لاحقًا.")
        doc = {"id": str(uuid.uuid4()), "user_id": user_id, "scenario_id": scenario["id"],
               "project_id": scenario["project_id"], "project_revision": scenario["project_revision"],
               "spec": spec, "input_hash": scenario["input_hash"],
               "seed": body.seed, "repetitions": body.repetitions, "request_key": body.request_key,
               "status": "queued", "created_at": now(), "attempt": 0,
               "result": None, "message": "في انتظار بدء التجربة"}
        db._put(conn, "simulation:run:" + doc["id"], doc)
        db._put(conn, key, ids + [doc["id"]])
        db._put(conn, QUEUE, queue + [doc["id"]])
    return public(doc)

def cancel(user_id, run_id):
    db = get_database()
    with db.connection(write=True) as conn:
        db.lock(conn, QUEUE)
        key = "simulation:run:" + run_id
        doc = owned(db._get(conn, key), user_id)
        if doc["status"] in ACTIVE:
            doc.update(status="cancelled", completed_at=now(), message="تم إيقاف التجربة")
            db._put(conn, key, doc)
            db._put(conn, QUEUE, [rid for rid in db._get(conn, QUEUE, []) if rid != run_id])
    return public(doc)

def claim():
    """One queue lock makes claims atomic on both SQLite and PostgreSQL."""
    db = get_database()
    with db.connection(write=True) as conn:
        db.lock(conn, QUEUE)
        queue = db._get(conn, QUEUE, [])
        retained, selected = [], None
        for rid in queue:
            key = "simulation:run:" + rid
            doc = db._get(conn, key)
            if not doc or doc["status"] not in ACTIVE:
                continue
            if doc["status"] == "running" and doc.get("lease_until", 0) < time.time():
                if doc["attempt"] >= 2:
                    doc.update(status="failed", completed_at=now(), message="توقفت التجربة. يمكنك إعادة تشغيل نسخة جديدة.")
                else:
                    doc.update(status="queued", message="إعادة تشغيل التجربة بعد انقطاع")
                db._put(conn, key, doc)
            if doc["status"] not in ACTIVE:
                continue
            retained.append(rid)
            if selected is None and doc["status"] == "queued":
                doc.update(status="running", started_at=now(), message="جارٍ حساب النتائج",
                           attempt=doc["attempt"] + 1, lease_token=str(uuid.uuid4()),
                           lease_until=time.time() + LEASE_SECONDS)
                db._put(conn, key, doc)
                selected = doc
        db._put(conn, QUEUE, retained)
    return selected

def still_owned(run_id, token):
    doc = get_database().get_document("simulation:run:" + run_id)
    return bool(doc and doc["status"] == "running" and doc.get("lease_token") == token
                and doc.get("lease_until", 0) > time.time())

def finish(run_id, token, result=None, error_type=None):
    db = get_database()
    with db.connection(write=True) as conn:
        db.lock(conn, QUEUE)
        key = "simulation:run:" + run_id
        doc = db._get(conn, key)
        if not doc or doc["status"] != "running" or doc.get("lease_token") != token or doc.get("lease_until", 0) <= time.time():
            return False
        doc.update(status="failed" if error_type else "complete", result=result,
                   completed_at=now(), error_type=error_type,
                   message="تعذر إكمال التجربة. راجع المدخلات وأعد المحاولة." if error_type else "اكتملت التجربة")
        db._put(conn, key, doc)
        db._put(conn, QUEUE, [rid for rid in db._get(conn, QUEUE, []) if rid != run_id])
    return True
