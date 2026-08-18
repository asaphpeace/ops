from datetime import date, datetime
from pydantic import BaseModel


class ReleaseCreate(BaseModel):
    version: str
    released_at: date
    defects_fixed: int = 0
    improvements: int = 0
    notes: str | None = None
    is_latest: bool = False


class ReleaseOut(BaseModel):
    id: int
    version: str
    released_at: date
    defects_fixed: int
    improvements: int
    notes: str | None
    is_latest: bool
    created_at: datetime

    model_config = {"from_attributes": True}
