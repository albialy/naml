"""Optional simulation API. Saving a scenario never runs an experiment."""
from typing import Literal
from fastapi import APIRouter, Depends
from agent_system.core.auth.middleware import get_current_user
from agent_system.core.auth.models import User
from agent_system.simulation import service
from agent_system.simulation.schema import SaveScenario, RunRequest, template

router = APIRouter(prefix="/api/simulation")

@router.get("/status")
def status(user: User = Depends(get_current_user)):
    return service.availability()

@router.get("/templates/{domain}")
def templates(domain: Literal["production", "workflow"], user: User = Depends(get_current_user)):
    return template(domain)

@router.get("/scenarios")
def scenarios(user: User = Depends(get_current_user)):
    return service.list_scenarios(user.id)

@router.post("/scenarios", status_code=201)
def save(body: SaveScenario, user: User = Depends(get_current_user)):
    return service.save_scenario(user.id, body)

@router.get("/runs")
def runs(user: User = Depends(get_current_user)):
    return service.list_runs(user.id)

@router.post("/runs", status_code=202)
def run(body: RunRequest, user: User = Depends(get_current_user)):
    return service.enqueue(user.id, body)

@router.get("/runs/{run_id}")
def get_run(run_id: str, user: User = Depends(get_current_user)):
    return service.get_run(user.id, run_id)

@router.post("/runs/{run_id}/cancel")
def cancel(run_id: str, user: User = Depends(get_current_user)):
    return service.cancel(user.id, run_id)
