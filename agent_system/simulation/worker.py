"""Run separately: python -m agent_system.simulation.worker."""
import logging
import signal
import threading
import time
from . import service
from .engine import run_experiment

log = logging.getLogger(__name__)

class Cancelled(Exception):
    pass

def run_one():
    service.pulse()
    job = service.claim()
    if not job:
        return False
    last_check = 0.0
    def check():
        nonlocal last_check
        if time.monotonic() - last_check >= 0.5:
            last_check = time.monotonic()
            service.pulse()
            if not service.still_owned(job["id"], job["lease_token"]):
                raise Cancelled()
    try:
        result = run_experiment(job["spec"], job["repetitions"], job["seed"], check)
        service.finish(job["id"], job["lease_token"], result=result)
    except Cancelled:
        pass  # Cancellation or a newer lease wins; never publish a stale result.
    except Exception as exc:
        log.exception("Simulation run failed: %s", job["id"])
        service.finish(job["id"], job["lease_token"], error_type=type(exc).__name__)
    return True

def main():
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    if not service.enabled():
        raise SystemExit("Set NAML_SIMULATION_ENABLED=true on the API and worker.")
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            busy = run_one()
        except Exception:
            log.exception("Simulation queue unavailable")
            busy = False
        if not busy:
            stopped.wait(1)

if __name__ == "__main__":
    main()
