"""One explicit process contract shared by factory and office templates."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

class Stage(Strict):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    capacity: int = Field(default=1, ge=1, le=100)
    duration: Literal["constant", "triangular"] = "constant"
    minutes: float = Field(gt=0, le=100000)
    minimum: float | None = Field(default=None, gt=0, le=100000)
    maximum: float | None = Field(default=None, gt=0, le=100000)

    @model_validator(mode="after")
    def distribution(self):
        if self.duration == "triangular" and not (
            self.minimum is not None and self.maximum is not None
            and self.minimum <= self.minutes <= self.maximum
        ):
            raise ValueError("الزمن المرجح يجب أن يقع بين الحد الأدنى والأعلى")
        return self

class ProcessSpec(Strict):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=100)
    domain: Literal["production", "workflow"] = "production"
    unit: Literal["minute"] = "minute"
    entity_label: str = Field(default="وحدة", min_length=1, max_length=40)
    horizon_minutes: float = Field(default=480, ge=1, le=100000)
    arrival_interval_minutes: float = Field(default=5, gt=0, le=100000)
    max_entities: int = Field(default=200, ge=1, le=5000)
    stages: list[Stage] = Field(min_length=1, max_length=12)
    assumptions: str = Field(min_length=1, max_length=4000)
    data_source: str = Field(default="قيم افتراضية تحتاج إلى معايرة", max_length=2000)

    @model_validator(mode="after")
    def unique(self):
        if len({s.id for s in self.stages}) != len(self.stages):
            raise ValueError("معرّف كل مرحلة يجب أن يكون فريدًا")
        return self

class SaveScenario(Strict):
    spec: ProcessSpec
    project_id: str | None = Field(default=None, max_length=100)
    parent_id: str | None = Field(default=None, max_length=100)

class RunRequest(Strict):
    scenario_id: str = Field(min_length=1, max_length=100)
    repetitions: int = Field(default=5, ge=1, le=20)
    seed: int = Field(default=42, ge=0, le=2147483600)
    request_key: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    reviewed: Literal[True]

def template(domain="production"):
    factory = domain == "production"
    names = ["التشكيل", "الفحص", "التعبئة"] if factory else ["استلام الطلب", "المراجعة", "الاعتماد"]
    durations = [6, 3, 4] if factory else [3, 12, 5]
    return ProcessSpec(
        name="خط إنتاج تجريبي" if factory else "مسار معاملات تجريبي",
        domain=domain, entity_label="عبوة" if factory else "معاملة",
        stages=[Stage(id=f"stage{i+1}", name=n, minutes=d) for i, (n, d) in enumerate(zip(names, durations))],
        assumptions="القيم للتجربة وليست قياسات فعلية. جميع الوحدات تمر بالمراحل بالترتيب، دون أعطال أو إعادة عمل أو ورديات.",
    ).model_dump()
