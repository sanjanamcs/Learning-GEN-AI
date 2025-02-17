from pydantic import BaseModel
from datetime import datetime

class CallLogCreate(BaseModel):
    caller_id: str
    query: str
    response: str

class CallLogResponse(CallLogCreate):
    id: int
    call_time: datetime

    class Config:
        from_attributes = True
