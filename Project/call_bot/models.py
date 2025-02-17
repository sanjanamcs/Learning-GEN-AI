from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, func
from call_bot.db import Base

class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    caller_id = Column(String(50), nullable=False)
    call_time = Column(TIMESTAMP, server_default=func.now())
    query = Column(Text)
    response = Column(Text)
