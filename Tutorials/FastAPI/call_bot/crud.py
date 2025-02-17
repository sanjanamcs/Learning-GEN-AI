from sqlalchemy.orm import Session
from . import models, schemas

def create_call_log(db: Session, call_log: schemas.CallLogCreate):
    db_call_log = models.CallLog(**call_log.dict())
    db.add(db_call_log)
    db.commit()
    db.refresh(db_call_log)
    return db_call_log

def get_call_logs(db: Session, skip: int = 0, limit: int = 10):
    return db.query(models.CallLog).offset(skip).limit(limit).all()
