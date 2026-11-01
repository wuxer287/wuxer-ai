import os
import secrets
import shutil
import threading
import uuid
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from openai import OpenAI
from pydantic import BaseModel
from generation import createClient
from evaluation import loadQuestions
from service import (
    Engine,
    CATEGORY_MODELS,
    EmptyCategoryError,
    listIndexableFiles,
    indexFiles,
    answerQuestion,
    listSources,
    evaluate,
    probeQuestion,
    addQuestion,
    readQuestionsFile
)

load_dotenv()

PASSWORD = os.getenv("WEB_PASSWORD")
API_MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
QUESTIONS_PATH = "eval/questions.json"
UPLOAD_DIR = Path("uploads")
WEB_DIR = Path(__file__).parent.parent / "web"
MODES = ("strict", "standard", "full")

security = HTTPBasic(auto_error=False)

def checkAuth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    if PASSWORD is None:
        return

    if credentials is None or not secrets.compare_digest(credentials.password.encode(), PASSWORD.encode()):
        raise HTTPException(401, "Password richiesta", headers={"WWW-Authenticate": "Basic"})

app = FastAPI(dependencies=[Depends(checkAuth)])
engine = Engine()

model_lock = threading.Lock()
questions_lock = threading.Lock()
jobs: dict[str, dict] = {}
client = None


class QueryRequest(BaseModel):
    text: str
    category: str = "note"
    mode: str = "strict"
    top_k: int = 5
    rerank: bool = False
    pool: int = 20
    min_sim: float | None = None
    rerank_min: float | None = None
    temperature: float | None = None

class EvalRequest(BaseModel):
    top_k: int = 5
    rerank: bool = True
    pool: int = 20
    rerank_min: float | None = None

class ProbeRequest(BaseModel):
    question: str
    category: str = "note"
    top_k: int = 5
    pool: int = 20

class QuestionRequest(BaseModel):
    question: str
    category: str
    label: str
    expected_source: list[str] | None = None

def getClient() -> OpenAI:
    global client

    if client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")

        if not api_key:
            raise HTTPException(500, "Manca DEEPSEEK_API_KEY")

        client = createClient(api_key)

    return client

def checkCategory(category: str) -> None:
    if category not in CATEGORY_MODELS:
        raise HTTPException(400, "Categoria sconosciuta")

def startJob(work) -> str:
    job_id = uuid.uuid4().hex[:8]
    job = {
        "state": "running",
        "progress": "in attesa",
        "result": None,
        "error": None
    }
    jobs[job_id] = job

    def run():
        try:
            with model_lock:
                job["progress"] = "in corso"
                job["result"] = work(job)

            job["state"] = "done"
        except Exception as e:
            job["state"] = "error"
            job["error"] = f"{type(e).__name__}: {e}"

    threading.Thread(target=run, daemon=True).start()

    return job_id


@app.get("/")
def home():
    return FileResponse(WEB_DIR / "index.html")

@app.get("/index.css")
def style():
    return FileResponse(WEB_DIR / "index.css")

@app.get("/index.js")
def script():
    return FileResponse(WEB_DIR / "index.js")

@app.get("/api/config")
def config():
    return {
        "categories": {
            name: {
                "min_sim": c["min_sim"],
                "rerank_min": c["rerank_min"]
            } for name, c in CATEGORY_MODELS.items()
        }
    }

@app.get("/api/jobs/{job_id}")
def jobStatus(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job sconosciuto")

    return jobs[job_id]

@app.get("/api/sources")
def sources():
    return listSources(engine)

@app.post("/api/index")
def index(category: str = Form("note"), dimension: int = Form(40), overlap: int = Form(1), strategy: str = Form("sentence"), folder: str = Form(""), files: list[UploadFile] = File(default=[])):
    checkCategory(category)

    if strategy not in ("word", "sentence"):
        raise HTTPException(400, "Strategia sconosciuta")

    paths = []

    if folder.strip():
        folder_path = Path(folder.strip())

        if not folder_path.is_dir():
            raise HTTPException(400, "La cartella non esiste")

        paths = listIndexableFiles(folder_path)
    else:
        UPLOAD_DIR.mkdir(exist_ok=True)

        for upload in files:
            name = Path(upload.filename or "").name

            if Path(name).suffix not in (".md", ".pdf"):
                raise HTTPException(400, f"{name or "file senza nome"}: sono ammessi solo .md e .pdf")

            target = UPLOAD_DIR / name

            with open(target, "wb") as out:
                shutil.copyfileobj(upload.file, out)

            paths.append(target)

    if not paths:
        raise HTTPException(400, "Nessun file da indicizzare")

    def work(job):
        def onProgress(number, total, name):
            job["progress"] = f"[{number}/{total}] {name}"

        return {
            "indexed": indexFiles(engine, paths, category, dimension, overlap, strategy, onProgress)
        }

    return {
        "job": startJob(work)
    }

@app.post("/api/query")
def query(req: QueryRequest):
    checkCategory(req.category)

    if req.mode not in MODES:
        raise HTTPException(400, "Modalità sconosciuta")

    if not req.text.strip():
        raise HTTPException(400, "La domanda è vuota")

    try:
        with model_lock:
            return answerQuestion(engine, getClient(), API_MODEL_NAME, req.text, req.category, req.mode, req.temperature, top_k=req.top_k, min_sim=req.min_sim, use_rerank=req.rerank, rerank_min=req.rerank_min, pool=req.pool)
    except EmptyCategoryError:
        raise HTTPException(404, "Nessun contenuto indicizzato per questa categoria")

@app.post("/api/eval")
def runEval(req: EvalRequest):
    try:
        with questions_lock:
            questions = loadQuestions(QUESTIONS_PATH, list(CATEGORY_MODELS.keys()))
    except (OSError, ValueError) as e:
        raise HTTPException(400, f"Impossibile leggere le domande: {e}")

    return {
        "job": startJob(lambda job: evaluate(engine, questions, req.top_k, req.rerank, req.pool, req.rerank_min))
    }

@app.post("/api/probe")
def probe(req: ProbeRequest):
    checkCategory(req.category)

    try:
        with model_lock:
            return probeQuestion(engine, req.question, req.category, req.top_k, req.pool)
    except EmptyCategoryError:
        raise HTTPException(404, "Nessun contenuto indicizzato per questa categoria")

@app.get("/api/questions")
def questionList():
    with questions_lock:
        return readQuestionsFile(QUESTIONS_PATH)

@app.post("/api/questions")
def questionsAdd(req: QuestionRequest):
    try:
        with questions_lock:
            total = addQuestion(QUESTIONS_PATH, req.question, req.category, req.label, req.expected_source)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "total": total
    }
