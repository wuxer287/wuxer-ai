import secrets
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from openai import OpenAI
from pydantic import BaseModel
from generation import createClient
from evaluation import loadQuestions
from readers import validateFile
from service import (
    Engine,
    EmptyCategoryError,
    indexFiles,
    answerQuestion,
    listSources,
    evaluate,
    probeQuestion,
    addQuestion,
    readQuestionsFile
)
from consts import (
    CATEGORY_MODELS,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    WEB_PASSWORD,
    MODES,
    STRATEGIES,
    LABELS,
    QUESTIONS_PATH,
    UPLOAD_DIR,
    WEB_DIR,
    DEFAULT_CATEGORY,
    DEFAULT_MODE,
    DEFAULT_TOP_K,
    DEFAULT_POOL,
    DEFAULT_STRATEGY,
    DEFAULT_DIMENSION,
    DEFAULT_OVERLAP,
    MAX_UPLOAD_MB,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_FILES,
    SAFE_NAME
)

security = HTTPBasic(auto_error=False)

def checkAuth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    if WEB_PASSWORD is None:
        return

    if credentials is None or not secrets.compare_digest(credentials.password.encode(), WEB_PASSWORD.encode()):
        raise HTTPException(401, "Password richiesta", headers={"WWW-Authenticate": "Basic"})

engine = Engine()

model_lock = threading.Lock()
questions_lock = threading.Lock()
jobs: dict[str, dict] = {}
client = None
models_state = {
    "ready": False,
    "error": None
}

def loadModels() -> None:
    try:
        with model_lock:
            engine.preload()

        models_state["ready"] = True
    except Exception as e:
        models_state["error"] = f"{type(e).__name__}: {e}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=loadModels, daemon=True).start()

    yield

app = FastAPI(dependencies=[Depends(checkAuth)], lifespan=lifespan)


class QueryRequest(BaseModel):
    text: str
    category: str = DEFAULT_CATEGORY
    mode: str = DEFAULT_MODE
    top_k: int = DEFAULT_TOP_K
    rerank: bool = False
    pool: int = DEFAULT_POOL
    min_sim: float | None = None
    rerank_min: float | None = None
    temperature: float | None = None

class EvalRequest(BaseModel):
    top_k: int = DEFAULT_TOP_K
    rerank: bool = True
    pool: int = DEFAULT_POOL
    rerank_min: float | None = None

class ProbeRequest(BaseModel):
    question: str
    category: str = DEFAULT_CATEGORY
    top_k: int = DEFAULT_TOP_K
    pool: int = DEFAULT_POOL

class QuestionRequest(BaseModel):
    question: str
    category: str
    label: str
    expected_source: list[str] | None = None

def getClient() -> OpenAI:
    global client

    if client is None:
        if not DEEPSEEK_API_KEY:
            raise HTTPException(500, "Manca DEEPSEEK_API_KEY")

        client = createClient(DEEPSEEK_API_KEY)

    return client

def checkCategory(category: str) -> None:
    if category not in CATEGORY_MODELS:
        raise HTTPException(400, "Categoria sconosciuta")

def checkReady() -> None:
    if models_state["error"]:
        raise HTTPException(500, f"Caricamento dei modelli fallito: {models_state['error']}")

    if not models_state["ready"]:
        raise HTTPException(503, "I modelli sono ancora in caricamento")

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

def checkUploadSize(request: Request) -> None:
    length = request.headers.get("content-length", "")

    if length.isdigit() and int(length) > MAX_UPLOAD_BYTES * MAX_UPLOAD_FILES:
        raise HTTPException(413, "La richiesta è troppo grande")

def saveUpload(upload: UploadFile) -> Path:
    name = upload.filename or ""

    if not SAFE_NAME.fullmatch(name):
        raise HTTPException(400, f"{name or "file senza nome"}: nome non valido (ammessi .md e .pdf con lettere, numeri, spazi e . _ - ( ) )")

    temp = UPLOAD_DIR / f"{uuid.uuid4().hex}{Path(name).suffix}"
    size = 0

    try:
        with open(temp, "wb") as out:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)

                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"{name}: supera il limite di {MAX_UPLOAD_MB} MB")

                out.write(chunk)

        try:
            validateFile(temp)
        except ValueError as e:
            raise HTTPException(400, f"{name}: {e}")

        target = UPLOAD_DIR / name
        temp.replace(target)

        return target
    finally:
        temp.unlink(missing_ok=True)


@app.get("/")
def home():
    return FileResponse(WEB_DIR / "index.html")

@app.get("/index.css")
def style():
    return FileResponse(WEB_DIR / "index.css")

@app.get("/index.js")
def script():
    return FileResponse(WEB_DIR / "index.js")

@app.get("/api/status")
def status():
    return models_state

@app.get("/api/config")
def config():
    return {
        "categories": {
            name: {
                "min_sim": c["min_sim"],
                "rerank_min": c["rerank_min"]
            } for name, c in CATEGORY_MODELS.items()
        },
        "modes": MODES,
        "strategies": STRATEGIES,
        "labels": LABELS,
        "defaults": {
            "category": DEFAULT_CATEGORY,
            "mode": DEFAULT_MODE,
            "top_k": DEFAULT_TOP_K,
            "strategy": DEFAULT_STRATEGY,
            "dimension": DEFAULT_DIMENSION,
            "overlap": DEFAULT_OVERLAP
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

@app.post("/api/index", dependencies=[Depends(checkUploadSize)])
def index(category: str = Form(DEFAULT_CATEGORY), dimension: int = Form(DEFAULT_DIMENSION), overlap: int = Form(DEFAULT_OVERLAP), strategy: str = Form(DEFAULT_STRATEGY), files: list[UploadFile] = File(default=[])):
    checkReady()
    checkCategory(category)

    if strategy not in ("word", "sentence"):
        raise HTTPException(400, "Strategia sconosciuta")

    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(400, f"Al massimo {MAX_UPLOAD_FILES} file per volta")

    UPLOAD_DIR.mkdir(exist_ok=True)
    paths = [saveUpload(upload) for upload in files]

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
            return answerQuestion(engine, getClient(), DEEPSEEK_MODEL, req.text, req.category, req.mode, req.temperature, top_k=req.top_k, min_sim=req.min_sim, use_rerank=req.rerank, rerank_min=req.rerank_min, pool=req.pool)
    except EmptyCategoryError:
        raise HTTPException(404, "Nessun contenuto indicizzato per questa categoria")

@app.post("/api/eval")
def runEval(req: EvalRequest):
    checkReady()

    try:
        with questions_lock:
            questions = loadQuestions(QUESTIONS_PATH, list(CATEGORY_MODELS.keys()))
    except (OSError, ValueError) as e:
        raise HTTPException(400, f"Impossibile leggere le domande: {e}")

    def work(job):
        def onProgress(number, total, name):
            job["progress"] = f"[{number}/{total}] {name}"

        return evaluate(engine, questions, req.top_k, req.rerank, req.pool, req.rerank_min, onProgress)

    return {
        "job": startJob(work)
    }

@app.post("/api/probe")
def probe(req: ProbeRequest):
    checkReady()
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
