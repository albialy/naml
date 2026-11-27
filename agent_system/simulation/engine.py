"""Finite-horizon, FCFS serial queues. No generated code, network or model calls."""
import random
import statistics
import time
import simpy
from .schema import ProcessSpec

ENGINE_VERSION = "serial-queues/1"
LIMITATIONS = [
    "المراحل متتابعة وطوابيرها غير محدودة، دون أعطال أو ورديات أو إعادة عمل.",
    "أول وصول عند الدقيقة صفر؛ لا تُحتسب أحداث تقع عند نهاية المدة أو بعدها.",
    "زمن الإنجاز للوحدات المكتملة فقط؛ قد ينحاز إلى الوحدات الأسرع عند وجود عمل متبقٍ.",
    "متوسط الانتظار لكل مرحلة يخص الوحدات التي بدأت الخدمة؛ المنتظرون عند نهاية المدة معروضون منفصلين.",
    "النطاق بين التكرارات يصف تغير هذه التجارب، ولا يمثل ضمانًا أو فترة ثقة للواقع.",
    "النتائج تعتمد على الافتراضات المدخلة وتحتاج إلى معايرة ببيانات فعلية.",
]

def summary(values):
    return {"mean": statistics.mean(values), "min": min(values), "max": max(values)}

def once(spec: ProcessSpec, seed: int, check):
    env = simpy.Environment()
    # Independent per-stage random streams keep scenario comparisons reproducible.
    rngs = [random.Random(f"{seed}:{s.id}") for s in spec.stages]
    resources = [simpy.Resource(env, capacity=s.capacity) for s in spec.stages]
    stats = [{"id": s.id, "name": s.name, "started": 0, "finished": 0,
              "wait_total": 0.0, "busy": 0.0} for s in spec.stages]
    flows = []
    arrived = 0
    horizon = spec.horizon_minutes

    def entity(birth):
        for i, stage in enumerate(spec.stages):
            queued_at = env.now
            with resources[i].request() as request:
                yield request
                row = stats[i]
                row["started"] += 1
                row["wait_total"] += env.now - queued_at
                duration = stage.minutes if stage.duration == "constant" else rngs[i].triangular(
                    stage.minimum, stage.maximum, stage.minutes)
                row["busy"] += min(duration, max(0, horizon - env.now))
                yield env.timeout(duration)
                row["finished"] += 1
        flows.append(env.now - birth)

    def arrivals():
        nonlocal arrived
        for _ in range(spec.max_entities):
            arrived += 1
            env.process(entity(env.now))
            yield env.timeout(spec.arrival_interval_minutes)

    env.process(arrivals())
    steps = 0
    while env.peek() < horizon:
        if steps % 200 == 0:
            check()
        env.step()
        steps += 1
        if steps > 1000000:
            raise RuntimeError("event_budget")
    check()
    stations = []
    for stage, resource, row in zip(spec.stages, resources, stats):
        stations.append({
            "id": stage.id, "name": stage.name,
            "utilization": row["busy"] / (horizon * stage.capacity),
            "mean_wait_minutes": row["wait_total"] / row["started"] if row["started"] else None,
            "started": row["started"], "finished": row["finished"],
            "queued_at_end": len(resource.queue), "in_service_at_end": resource.count,
        })
    return {"seed": seed, "arrived": arrived, "completed": len(flows),
            "work_in_progress": arrived - len(flows),
            "throughput_per_hour": len(flows) * 60 / horizon,
            "mean_flow_minutes": statistics.mean(flows) if flows else None,
            "stations": stations}

def run_experiment(spec, repetitions=5, seed=42, check=lambda: None):
    spec = ProcessSpec.model_validate(spec)
    if not 1 <= repetitions <= 20 or not 0 <= seed <= 2147483600:
        raise ValueError("invalid_run_parameters")
    if spec.max_entities * len(spec.stages) * repetitions > 200000:
        raise ValueError("work_budget")
    started = time.monotonic()
    def bounded_check():
        if time.monotonic() - started > 45:
            raise TimeoutError("simulation_time_budget")
        check()
    trials = [once(spec, seed + i, bounded_check) for i in range(repetitions)]
    aggregate = {k: summary([r[k] for r in trials]) for k in
                 ("arrived", "completed", "work_in_progress", "throughput_per_hour")}
    flows = [r["mean_flow_minutes"] for r in trials if r["mean_flow_minutes"] is not None]
    aggregate["mean_flow_minutes"] = summary(flows) if flows else None
    aggregate["trials_with_completions"] = len(flows)
    stations = []
    for i, stage in enumerate(spec.stages):
        waits = [r["stations"][i]["mean_wait_minutes"] for r in trials
                 if r["stations"][i]["mean_wait_minutes"] is not None]
        stations.append({"id": stage.id, "name": stage.name,
            "utilization": summary([r["stations"][i]["utilization"] for r in trials]),
            "mean_wait_minutes": summary(waits) if waits else None,
            "queued_at_end": summary([r["stations"][i]["queued_at_end"] for r in trials]),
        })
    return {"engine_version": ENGINE_VERSION, "simpy_version": simpy.__version__,
            "unit": "minute", "seed": seed, "repetitions": repetitions,
            "summary": aggregate, "stations": stations, "trials": trials,
            "limitations": LIMITATIONS}
