import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_PREFIXES = {
    "paraphrase-multilingual-mpnet-base-v2": {
        "query": "",
        "passage": ""
    },
    "intfloat/multilingual-e5-large": {
        "query": "query: ",
        "passage": "passage: "
    }
}

MODEL_PROMPT_NAMES = {
    "google/embeddinggemma-2": {
        "query": "SearchQuery",
        "passage": "Document"
    }
}

def loadModel(name: str) -> SentenceTransformer:
    return SentenceTransformer(name)

def embeddedTexts(model: SentenceTransformer, texts: list, model_name: str, text_type: str) -> np.ndarray:
    if model_name in MODEL_PROMPT_NAMES:
        embeddings = model.encode(texts, prompt_name=MODEL_PROMPT_NAMES[model_name][text_type])
    else:
        prefix = MODEL_PREFIXES.get(model_name, {}).get(text_type, "")
        embeddings = model.encode([prefix + t for t in texts])

    return np.asarray(embeddings, dtype=np.float32)
