import copy
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from agent_system.simulation.schema import ProcessSpec, SaveScenario, RunRequest, template
from agent_system.simulation.engine import run_experiment
from agent_system.simulation import service
from agent_system.simulation.worker import run_one
from agent_system.core.database import Database

def simple(**patch):
    spec = template()
    spec.update(horizon_minutes=20, arrival_interval_minutes=3, max_entities=3,
                stages=[{"id": "one", "name": "خدمة", "minutes": 2, "capacity": 1}], **patch)
    return spec

def test_deterministic_conservation_and_hand_calculated_queue():
    result = run_experiment(simple(), repetitions=2, seed=1)
    trial = result["trials"][0]
    assert trial["arrived"] == trial["completed"] == 3
    assert trial["work_in_progress"] == 0
    assert trial["mean_flow_minutes"] == 2
    assert trial["stations"][0]["mean_wait_minutes"] == 0
    assert trial["stations"][0]["utilization"] == pytest.approx(6 / 20)
    assert trial["throughput_per_hour"] == 9

def test_overload_excludes_horizon_events_and_accounts_for_unfinished_work():
    spec = simple()
    spec.update(horizon_minutes=10, arrival_interval_minutes=1, max_entities=100)
    spec["stages"][0]["minutes"] = 2
    trial = run_experiment(spec, 1)["trials"][0]
    assert trial["arrived"] == 10 and trial["completed"] == 4
    assert trial["work_in_progress"] == 6
    assert trial["stations"][0]["in_service_at_end"] == 1
    assert trial["stations"][0]["queued_at_end"] == 5
    assert trial["stations"][0]["utilization"] == 1
    assert trial["stations"][0]["mean_wait_minutes"] == 2

def test_more_capacity_improves_overloaded_example():
    spec = simple()
    spec.update(horizon_minutes=10, arrival_interval_minutes=1, max_entities=100)
    spec["stages"][0]["minutes"] = 2
    before = run_experiment(spec, 1)
    spec["stages"][0]["capacity"] = 2
    after = run_experiment(spec, 1)
    assert after["summary"]["completed"]["mean"] > before["summary"]["completed"]["mean"]
    assert after["stations"][0]["mean_wait_minutes"]["mean"] == 0

def test_seeded_variability_replays_exactly_and_is_not_fake_confidence():
    spec = simple()
    spec["stages"][0].update(duration="triangular", minimum=1, maximum=5)
    a = run_experiment(spec, 5, 82)
    assert a == run_experiment(copy.deepcopy(spec), 5, 82)
    assert a != run_experiment(spec, 5, 83)
    assert a["summary"]["mean_flow_minutes"]["max"] > a["summary"]["mean_flow_minutes"]["min"]
    assert "confidence" not in a

def test_empty_completion_and_bounds_are_explicit():
    spec = simple()
    spec["stages"][0]["minutes"] = 100
    assert run_experiment(spec, 1)["summary"]["mean_flow_minutes"] is None
    spec["stages"][0]["minutes"] = float("nan")
    with pytest.raises(ValidationError):
        ProcessSpec.model_validate(spec)
    spec = simple()
    spec["stages"][0].update(duration="triangular", minimum=4, maximum=2)
    with pytest.raises(ValidationError):
        ProcessSpec.model_validate(spec)
    spec = template()
    spec.update(max_entities=5000)
    with pytest.raises(ValueError, match="work_budget"):
        run_experiment(spec, 20)
    with pytest.raises(ValidationError):
        ProcessSpec.model_validate({**template(), "code": "import os"})

def test_check_interrupts_computation():
    class Stop(Exception): pass
    def stop(): raise Stop()
    with pytest.raises(Stop):
        run_experiment(template(), check=stop)

def save(owner="alice"):
    return service.save_scenario(owner, SaveScenario(spec=ProcessSpec.model_validate(simple())))

def request(scenario, key="request-key-0001"):
    return RunRequest(scenario_id=scenario["id"], request_key=key, reviewed=True)

@pytest.fixture
def ready(database, monkeypatch):
    monkeypatch.setenv("NAML_SIMULATION_ENABLED", "true")
    service.pulse()
    return database

def test_save_never_queues_and_survives_reopening(database):
    scenario = save()
    assert database.get_document(service.QUEUE, []) == []
    other = Database(backend="sqlite", path=database.path, legacy_dir=Path(database.path).parent / "legacy")
    assert other.get_document("simulation:scenario:" + scenario["id"])["input_hash"] == scenario["input_hash"]
    with pytest.raises(HTTPException) as e:
        service.enqueue("alice", request(scenario))
    assert e.value.status_code == 503

def test_idempotent_enqueue_and_atomic_claim(ready):
    scenario = save()
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: service.enqueue("alice", request(scenario)), range(4)))
    assert len({j["id"] for j in jobs}) == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: service.claim(), range(4)))
    assert sum(j is not None for j in claims) == 1
    with pytest.raises(HTTPException) as e:
        service.enqueue("alice", request(scenario).model_copy(update={"seed": 99}))
    assert e.value.status_code == 409

def test_cancel_and_lease_fencing_reject_stale_results(ready):
    job = service.enqueue("alice", request(save()))
    first = service.claim()
    doc = ready.get_document("simulation:run:" + job["id"])
    doc["lease_until"] = 0
    ready.set_document("simulation:run:" + job["id"], doc)
    second = service.claim()
    assert second["attempt"] == 2 and first["lease_token"] != second["lease_token"]
    assert not service.finish(job["id"], first["lease_token"], result={"bad": True})
    service.cancel("alice", job["id"])
    assert not service.finish(job["id"], second["lease_token"], result={"bad": True})
    assert service.get_run("alice", job["id"])["status"] == "cancelled"

def test_worker_runs_snapshot_and_hides_internal_fields(ready):
    scenario = save()
    job = service.enqueue("alice", request(scenario))
    assert run_one()
    result = service.get_run("alice", job["id"])
    assert result["status"] == "complete"
    assert result["result"]["summary"]["completed"]["mean"] == 3
    assert result["input_hash"] == scenario["input_hash"]
    assert not {"lease_token", "lease_until", "attempt", "error_type", "user_id"} & result.keys()
    assert not {"engine_version", "simpy_version"} & result["result"].keys()
    assert ready.get_document(service.QUEUE) == []
    for operation in (lambda: service.get_run("bob", job["id"]), lambda: service.cancel("bob", job["id"]), lambda: service.enqueue("bob", request(scenario))):
        with pytest.raises(HTTPException) as e:
            operation()
        assert e.value.status_code == 404
    assert service.list_runs("bob") == []
    assert service.list_scenarios("bob") == []

def test_run_admission_limits(ready):
    scenario = save()
    service.enqueue("alice", request(scenario, "request-first"))
    service.enqueue("alice", request(scenario, "request-second"))
    with pytest.raises(HTTPException) as e:
        service.enqueue("alice", request(scenario, "request-third"))
    assert e.value.status_code == 429
    with pytest.raises(ValidationError):
        RunRequest(scenario_id=scenario["id"], request_key="request-fourth", reviewed=False)
