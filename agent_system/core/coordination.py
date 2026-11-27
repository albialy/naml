"""Versioned internal task handoffs; completion is not factual verification."""
import hashlib
import json
from datetime import datetime, timezone

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def emit(memory, worker, state, finding_indexes=None):
    with memory._lock:
        ledger = memory.coordination
        key = str(getattr(worker, "task_id", worker.name))
        task = ledger["tasks"].setdefault(key, {
            "id": key, "name": worker.name, "question": worker.sub_question,
            "depends_on": [str(x) for x in getattr(worker, "depends_on", [])],
            "attempt": 0,
        })
        if state == "running":
            task["attempt"] += 1
            task["input_revision"] = ledger["revision"]
            task["context_fingerprint"] = fingerprint({
                "project": memory.project_context,
                "history": memory.chat_history,
                "findings": getattr(worker, "context_snapshot", memory.findings),
            })
        ledger["revision"] += 1
        task["state"] = state
        task["finding_indexes"] = finding_indexes or []
        ledger["events"].append({
            "sequence": ledger["revision"], "task_id": key, "state": state,
            "at": datetime.now(timezone.utc).isoformat(),
            "attempt": task["attempt"], "finding_indexes": finding_indexes or [],
            "verification": "unverified",
        })
        ledger["events"] = ledger["events"][-500:]
        memory.save_to_file()

def execute(worker, memory):
    emit(memory, worker, "running")
    with memory._lock:
        start = len(memory.findings)
    try:
        result = worker.execute()
    except Exception:
        memory.add_finding(worker.name, worker.sub_question, "تعذر إكمال هذا الجزء", 0, status="failed")
        result = None
    with memory._lock:
        indexes = [i for i in range(start, len(memory.findings))
                   if memory.findings[i]["agent_name"] == worker.name]
        complete = bool(indexes) and memory.findings[indexes[-1]].get("status", "complete") == "complete"
    emit(memory, worker, "completed_unverified" if complete else "failed", indexes)
    return result
