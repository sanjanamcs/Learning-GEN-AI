from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from call_bot.db import get_db, engine
from . import models, schemas, crud

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Welcome to the Call Bot API"}
@app.post("/log-call/", response_model=schemas.CallLogResponse)
def log_call(call_log: schemas.CallLogCreate, db: Session = Depends(get_db)):
    return crud.create_call_log(db, call_log)

@app.get("/logs/", response_model=list[schemas.CallLogResponse])
def fetch_logs(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_call_logs(db, skip, limit)
