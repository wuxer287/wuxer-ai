import sqlite3
import numpy as np

MAX_K = 4096

def search(conn: sqlite3.Connection, query_embedding: np.ndarray, category: str, top_k: int, min_sim: float) -> list[tuple]:
    rows = conn.execute("""
        SELECT c.text, v.distance, c.source, c.hf_model_name
        FROM chunk_vectors v
        JOIN chunks c ON c.id = v.chunk_id
        WHERE v.embedding MATCH ? AND k = ? AND v.category = ?
        ORDER BY v.distance
    """, (query_embedding.tobytes(), min(top_k, MAX_K), category)).fetchall()

    results = [(text, 1 - distance, source, [model]) for text, distance, source, model in rows]

    return [r for r in results if r[1] >= min_sim]
