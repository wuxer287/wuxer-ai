import sqlite3
import sqlite_vec
import numpy as np
from consts import ANSWERS_DIR

def createConnection(path: str, vector: bool = False):
    conn = sqlite3.connect(path)

    if vector:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

    return conn

def createTableChunk(conn: sqlite3.Connection, dim: int) -> None:
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            source TEXT,
            hf_model_name TEXT,
            category TEXT
        )
    """)

    cur.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
            chunk_id INTEGER PRIMARY KEY,
            category TEXT PARTITION KEY,
            embedding FLOAT[{dim}] DISTANCE_METRIC=cosine
        )
    """)

    cur.close()
    conn.commit()

def insertChunk(conn: sqlite3.Connection, text: str, embedding: np.ndarray, source: str, hf_model_name: str, category: str) -> None:
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO chunks (text, source, hf_model_name, category)
        VALUES (?, ?, ?, ?)
    """, (text, source, hf_model_name, category))

    chunk_id = cur.lastrowid

    cur.execute("""
        INSERT INTO chunk_vectors (chunk_id, category, embedding)
        VALUES (?, ?, ?)
    """, (chunk_id, category, embedding.tobytes()))

    cur.close()
    conn.commit()

def countChunksByCategory(conn: sqlite3.Connection, category: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM chunks WHERE category = ?", (category,)).fetchone()[0]

def deleteChunksBySource(conn: sqlite3.Connection, source: str) -> None:
    cur = conn.cursor()

    ids = [row[0] for row in cur.execute("SELECT id FROM chunks WHERE source = ?", (source,))]

    cur.executemany("""
        DELETE FROM chunk_vectors
        WHERE chunk_id = ?
    """, [(i,) for i in ids])

    cur.execute("""
        DELETE FROM chunks
        WHERE source = ?
    """, (source,))

    cur.close()
    conn.commit()

def createTableLog(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_hf TEXT,
            timestamp TEXT,
            query TEXT,
            category TEXT,
            num_results INTEGER,
            sources TEXT,
            answer_mode TEXT,
            model_name_api TEXT,
            input_tokens INTEGER,
            input_cached_tokens INTEGER,
            output_tokens INTEGER,
            reasoning_tokens INTEGER,
            total_tokens INTEGER,
            elapsed_seconds REAL
        )
    """)

    cur.close()
    conn.commit()

def logQuery(conn: sqlite3.Connection, model_hf: str, timestamp: str, query: str, category: str, num_results: int, sources: str, answer_mode: str, model_name_api: str, inp_tokens: int, inp_cached_tokens: int, out_tokens: int, reasoning_tokens: int, total_tokens: int, elapsed_seconds: float) -> None:
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO query_log (model_hf, timestamp, query, category, num_results, sources, answer_mode, model_name_api, input_tokens, input_cached_tokens, output_tokens, reasoning_tokens, total_tokens, elapsed_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (model_hf, timestamp, query, category, num_results, sources, answer_mode, model_name_api, inp_tokens, inp_cached_tokens, out_tokens, reasoning_tokens, total_tokens, elapsed_seconds))

    cur.close()
    conn.commit()

def saveAnswerToFile(query: str, answer: str, timestamp: str, sources: str, mode: str, category: str) -> None:
    safe_timestamp = timestamp.replace(":", "_")
    filename = f"query_{safe_timestamp}_v2.txt"

    ANSWERS_DIR.mkdir(exist_ok=True)

    file_path = ANSWERS_DIR / filename
    file_path.write_text(f"Domanda: {query}\n\nRisposta:\n{answer}\n\n[{sources}]\nMode: {mode}\nCategory: {category}", encoding="utf-8")
