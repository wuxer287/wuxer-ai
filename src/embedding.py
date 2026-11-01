import numpy as np
from sentence_transformers import SentenceTransformer
from consts import MODEL_PROMPT_NAMES

def loadModel(name: str) -> SentenceTransformer:
    return SentenceTransformer(name)

def embeddedTexts(model: SentenceTransformer, texts: list, model_name: str, text_type: str) -> np.ndarray:
    embeddings = model.encode(texts, prompt_name=MODEL_PROMPT_NAMES[model_name][text_type])

    return np.asarray(embeddings, dtype=np.float32)
