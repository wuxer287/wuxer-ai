import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
WEB_PASSWORD = os.getenv("WEB_PASSWORD")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

EMBEDDING_MODEL = "google/embeddinggemma-2"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
RERANKER_MAX_LENGTH = 1024

MODEL_PROMPT_NAMES = {
    "google/embeddinggemma-2": {
        "query": "SearchQuery",
        "index": "Document"
    }
}

CATEGORY_MODELS = {
    "note": {
        "model": EMBEDDING_MODEL,
        "min_sim": 0.735,
        "rerank_min": 0.06
    },
    "programma": {
        "model": EMBEDDING_MODEL,
        "min_sim": 0.65,
        "rerank_min": 0.03
    }
}

MODES = ("strict", "standard", "full")
STRATEGIES = ("word", "sentence")

TEMPERATURE = {
    "strict": 0.0,
    "standard": 0.3,
    "full": 0.6
}

DEFAULT_CATEGORY = "note"
DEFAULT_MODE = "strict"
DEFAULT_TOP_K = 5
DEFAULT_POOL = 20
DEFAULT_STRATEGY = "sentence"
DEFAULT_DIMENSION = 40
DEFAULT_OVERLAP = 1

MAX_K = 4096

LABELS = ("pertinente", "borderline", "fuori_tema")
REQUIRED_FIELDS = ("question", "category", "label")

RERANK_SWEEP = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9]

DB_PATH = "test.db"
LOG_DB_PATH = "logs_v2.db"
ANSWERS_DIR = Path("log_data_answer")
QUESTIONS_PATH = "eval/questions.json"
UPLOAD_DIR = Path("uploads")
WEB_DIR = Path(__file__).parent.parent / "web"

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_UPLOAD_FILES = 20
MAX_PDF_PAGES = 500

SAFE_NAME = re.compile(r"(?![. ])[\w .()\-]{1,100}\.(md|pdf)")

LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
LOCK_TIMEOUT = 30
JOB_TTL = 3600
