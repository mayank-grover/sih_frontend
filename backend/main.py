# backend/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from pathlib import Path
import io
import json
import datetime as dt

app = FastAPI(title="AirCast Backend")

# Allow CORS from frontend dev origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
PRED_PATH = DATA_DIR / "predictions.parquet"  # efficient store
META_PATH = DATA_DIR / "metadata.json"

def now_iso():
    return dt.datetime.utcnow().isoformat()

# simple metadata to indicate last update time
def write_meta(ts=None):
    meta = {"last_update": ts or now_iso()}
    META_PATH.write_text(json.dumps(meta))

def read_meta():
    if META_PATH.exists():
        return json.loads(META_PATH.read_text())
    return {"last_update": None}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/predictions")
def get_predictions():
    """
    Return latest predictions as JSON.
    Optional query params:
        pollutant=NO2 or O3
    """
    if not PRED_PATH.exists():
        return {"last_update": None, "rows": []}
    df = pd.read_parquet(PRED_PATH)
    # convert timestamp to iso str for JSON serialization
    df = df.copy()
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    rows = df.to_dict(orient="records")
    return {"last_update": read_meta().get("last_update"), "rows": rows}

class PushResult(BaseModel):
    status: str
    rows_received: int

@app.post("/upload_csv", response_model=PushResult)
async def upload_csv(file: UploadFile = File(...)):
    """
    Accepts a CSV file uploaded by backend or ingestion script.
    Expects columns:
    timestamp,station_id,station_name,lat,lon,pollutant,prediction,lower_q,upper_q[,observed]
    """
    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents), parse_dates=["timestamp"], infer_datetime_format=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

    # basic validation
    required = {"timestamp","station_id","station_name","lat","lon","pollutant","prediction","lower_q","upper_q"}
    if not required.issubset(set(df.columns)):
        raise HTTPException(status_code=400, detail=f"Missing required columns: {required - set(df.columns)}")

    # store as parquet (append or overwrite, we overwrite)
    df.to_parquet(PRED_PATH, index=False)
    write_meta()
    return {"status": "ok", "rows_received": len(df)}

@app.post("/upload_json", response_model=PushResult)
async def upload_json(payload: dict):
    """
    Accept a JSON payload with same structure:
    { rows: [ {timestamp:..., station_id:..., ...}, ... ] }
    """
    rows = payload.get("rows")
    if not rows:
        raise HTTPException(status_code=400, detail="No rows in payload")
    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.to_parquet(PRED_PATH, index=False)
    write_meta()
    return {"status": "ok", "rows_received": len(df)}

