import sqlite3
import json
import time
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from contextlib import nullcontext
from storage import createConnection, createTableChunk, insertChunk, countChunksByCategory, deleteChunksBySource, createTableLog, logQuery, saveAnswerToFile
from chunking import chunkText, chunkTextBySentence
from embedding import loadModel, embeddedTexts
from search import search
from readers import readFile
from reranking import loadReranker, rerank
from generation import generateAnswer
from evaluation import groupByCategory, scoreQuestions, summarize, sweep, sweepThresholds
from consts import (
    CATEGORY_MODELS,
    LABELS,
    RERANK_SWEEP,
    DB_PATH,
    LOG_DB_PATH,
    DEFAULT_CATEGORY,
    DEFAULT_MODE,
    DEFAULT_DIMENSION,
    DEFAULT_OVERLAP,
    DEFAULT_TOP_K,
    DEFAULT_STRATEGY,
    DEFAULT_POOL
)

class EmptyCategoryError(Exception):
    pass

class Engine:
    def __init__(self, db_path: str = DB_PATH, log_path: str = LOG_DB_PATH):
        self.db_path = db_path
        self.log_path = log_path
        self._models = {}
        self._reranker = None

    def getModel(self, name: str):
        if name not in self._models:
            self._models[name] = loadModel(name)

        return self._models[name]

    def getReranker(self):
        if self._reranker is None:
            self._reranker = loadReranker()

        return self._reranker

    def preload(self) -> None:
        for name in {config["model"] for config in CATEGORY_MODELS.values()}:
            self.getModel(name)

        self.getReranker()

def listIndexableFiles(folder: Path) -> list[Path]:
    return sorted(chain(folder.glob("*.md"), folder.glob("*.pdf")))

def indexFiles(engine: Engine, files: list[Path], category: str, dimension: int = DEFAULT_DIMENSION, overlap: int = DEFAULT_OVERLAP, strategy: str = DEFAULT_STRATEGY, on_progress = None) -> int:
    hf_model_name = CATEGORY_MODELS[category]["model"]
    model = engine.getModel(hf_model_name)
    conn = createConnection(engine.db_path, vector=True)

    try:
        createTableChunk(conn, model.get_embedding_dimension())

        for number, file_path in enumerate(files, start=1):
            text = readFile(file_path)
            chunked_text = chunkText(text, dimension, overlap) if strategy == "word" else chunkTextBySentence(text, dimension, overlap)
            embed_chunk = embeddedTexts(model, chunked_text, hf_model_name, "index")

            deleteChunksBySource(conn, file_path.name)

            for i in range(len(chunked_text)):
                insertChunk(conn, chunked_text[i], embed_chunk[i], file_path.name, hf_model_name, category)

            if on_progress:
                on_progress(number, len(files), file_path.name)
    finally:
        conn.close()

    return len(files)

def listSources(engine: Engine) -> list[dict] | list:
    conn =  createConnection(engine.db_path)

    try:
        rows = conn.execute("""
            SELECT category, source, COUNT(*)
            FROM chunks
            GROUP BY category, source
            ORDER BY category, source
        """).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    return [{"category": category, "source": source, "chunks": count} for category, source, count in rows]


def retrieve(engine: Engine, query: str, category: str, top_k: int = DEFAULT_TOP_K, min_sim: float | None = None, use_rerank: bool = False, rerank_min: float | None = None, pool: int = DEFAULT_POOL) -> list[tuple]:
    config = CATEGORY_MODELS[category]
    hf_model_name = config["model"]
    model = engine.getModel(hf_model_name)
    conn = createConnection(engine.db_path, vector=True)

    try:
        createTableChunk(conn, model.get_embedding_dimension())

        if countChunksByCategory(conn, category) == 0:
            raise EmptyCategoryError(category)

        embed_query = embeddedTexts(model, [query], hf_model_name, "query")[0]

        if use_rerank:
            threshold = rerank_min if rerank_min is not None else config["rerank_min"]
            candidates = search(conn, embed_query, category, max(pool, top_k), -1.0)
            reranked = rerank(engine.getReranker(), query, candidates, top_k)

            return [chunk for chunk in reranked if chunk[1] >= threshold]

        threshold = min_sim if min_sim is not None else config["min_sim"]

        return search(conn, embed_query, category, top_k, threshold)
    finally:
        conn.close()

def answerQuestion(engine: Engine, client, api_model_name: str, query: str, category: str = DEFAULT_CATEGORY, mode: str = DEFAULT_MODE, temperature: float | None = None, lock = None, **retrieve_options) -> dict:
    start_time = time.time()

    with (lock() if lock else nullcontext()):
        result = retrieve(engine, query, category, **retrieve_options)

    chunks = [{"text": c[0], "score": float(c[1]), "source": c[2]} for c in result]
    sources = sorted({c[2] for c in result})

    if not result and mode == "strict":
        return {"answer": "Nessuna informazione pertinente è stata trovata...", "sources": [], "chunks": [], "usage": None}

    answer_text, usage = generateAnswer(client, api_model_name, result, query, mode, temperature)
    elapsed_time = time.time() - start_time
    timestamp = datetime.now(timezone.utc).isoformat()
    input_tokens = usage.prompt_tokens
    input_cached_tokens = usage.prompt_tokens_details.cached_tokens or 0
    output_tokens = usage.completion_tokens
    reasoning_tokens = usage.completion_tokens_details.reasoning_tokens if usage.completion_tokens_details and usage.completion_tokens_details.reasoning_tokens is not None else 0
    total_tokens = usage.total_tokens

    conn_log = createConnection(engine.log_path)

    try:
        createTableLog(conn_log)
        logQuery(conn_log, CATEGORY_MODELS[category]["model"], timestamp, query, category, len(result), ", ".join(sources), mode,  api_model_name, input_tokens, input_cached_tokens, output_tokens, reasoning_tokens, total_tokens, elapsed_time)
    finally:
        conn_log.close()

    saveAnswerToFile(query, answer_text, timestamp, ", ".join(sources), mode, category)

    return {
        "answer": answer_text,
        "sources": sources,
        "chunks": chunks,
        "usage": {
            "input": input_tokens,
            "cached": input_cached_tokens,
            "output": output_tokens,
            "reasoning": reasoning_tokens,
            "total": total_tokens
        },
        "elapsed": elapsed_time
    }


def readQuestionsFile(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def evaluate(engine: Engine, questions: list[dict], top_k: int = DEFAULT_TOP_K, use_rerank: bool = False, pool: int = DEFAULT_POOL, rerank_min: float | None = None, on_progress = None) -> dict:
    reports = {}
    groups = groupByCategory(questions)
    steps = 2 if use_rerank else 1
    total = len(groups) * steps
    number = 0
    conn = createConnection(engine.db_path, vector=True)

    try:
        for category, group in groupByCategory(questions).items():
            config = CATEGORY_MODELS[category]
            hf_model_name = config["model"]
            model = engine.getModel(hf_model_name)
            createTableChunk(conn, model.get_embedding_dimension())

            if countChunksByCategory(conn, category) == 0:
                reports[category] = {"skipped": True}
                number += steps

                continue

            number += 1

            if on_progress:
                on_progress(number, total, f"{category}: coseno")

            results = scoreQuestions(conn, model, hf_model_name, category, group, top_k)
            threshold = config["min_sim"]
            report = {
                "cosine": {
                    "threshold": threshold,
                    "results": results,
                    "summary": summarize(results, threshold),
                    "sweep": sweep(results, sweepThresholds(threshold))
                }
            }

            if use_rerank:
                number += 1

                if on_progress:
                    on_progress(number, total, f"{category}: re-ranking")

                rr_results = scoreQuestions(conn, model, hf_model_name, category, group, top_k, engine.getReranker(), pool)
                rr_threshold = rerank_min if rerank_min is not None else config["rerank_min"]
                report["rerank"] = {
                    "threshold": rr_threshold,
                    "results": rr_results,
                    "summary": summarize(rr_results, rr_threshold),
                    "sweep": sweep(rr_results, sorted(set(RERANK_SWEEP) | {rr_threshold}))
                }

            reports[category] = report
    finally:
        conn.close()

    return reports

def probeQuestion(engine: Engine, question: str, category: str, top_k: int = DEFAULT_TOP_K, pool: int = DEFAULT_POOL) -> dict:
    config = CATEGORY_MODELS[category]
    hf_model_name = config["model"]
    model = engine.getModel(hf_model_name)
    conn = createConnection(engine.db_path, vector=True)

    def format(chunks):
        return [{"text": c[0], "score": float(c[1]), "source": c[2]} for c in chunks]

    try:
        createTableChunk(conn, model.get_embedding_dimension())

        if countChunksByCategory(conn, category) == 0:
            raise EmptyCategoryError(category)

        embed_query = embeddedTexts(model, [question], hf_model_name, "query")[0]
        candidates = search(conn, embed_query, category, max(pool, top_k), -1.0)
        reranked = rerank(engine.getReranker(), question, candidates, top_k)

        return {
            "cosine": format(candidates[:top_k]),
            "rerank": format(reranked),
            "min_sim": config["min_sim"],
            "rerank_min": config["rerank_min"]
        }
    finally:
        conn.close()

def addQuestion(path: str, question: str, category: str, label: str, expected_source: list[str] | None = None) -> int:
    if category not in CATEGORY_MODELS:
        raise ValueError(f"Categoria '{category}' sconosciuta")

    if label not in LABELS:
        raise ValueError(f"Label '{label}' non valida (usa {", ".join(LABELS)})")

    if not question.strip():
        raise ValueError("La domanda è vuota")

    questions = readQuestionsFile(path)
    entry = {
        "question": question.strip(),
        "category": category,
        "label": label
    }

    if expected_source:
        entry["expected_source"] = expected_source[0] if len(expected_source) == 1 else expected_source

    questions.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=4)
        f.write("\n")

    return len(questions)
