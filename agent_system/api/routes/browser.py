from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from agent_system.core.auth.middleware import get_current_user
from agent_system.core import browser_client

router = APIRouter(prefix="/api/browser", dependencies=[Depends(get_current_user)])


class CaptureRequest(BaseModel):
    url: str | None = Field(default=None, max_length=4096)
    html: str | None = Field(default=None, max_length=200000)
    mobile: bool = False

    @model_validator(mode="after")
    def source(self):
        if bool(self.url) == bool(self.html):
            raise ValueError("حدد رابطًا أو HTML فقط")
        return self


@router.get("/status")
def status():
    return {"configured": browser_client.configured()}


@router.post("/capture")
def capture(request: CaptureRequest):
    try:
        return browser_client.capture(**request.model_dump())
    except browser_client.BrowserError as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc), "code": exc.code, "request_id": exc.request_id})
    except ValueError as exc:
        raise HTTPException(502, str(exc))
