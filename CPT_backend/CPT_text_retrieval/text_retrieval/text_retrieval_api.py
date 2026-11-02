"""
===============================================================
FASTAPI CPT RETRIEVAL API
===============================================================

Purpose
-------
Production-ready API for:

    query text
        ↓
retrieve top-k similar training texts
        ↓
expand associated CPT codes
        ↓
return CPT scores

Features
--------
✓ Model initialized ONCE
✓ FAISS loaded ONCE
✓ Fast inference
✓ CPU optimized
✓ Supports continuous requests
✓ Top-K configurable

Run
---
uvicorn cpt_retrieval_api:app --host 0.0.0.0 --port 8083

API Docs
--------
http://localhost:8083/docs

===============================================================
"""

from __future__ import annotations

import pickle
from collections import defaultdict

import faiss
import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

# ============================================================
# CONFIG
# ============================================================

FAISS_DIR = "./faiss_store"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

DEFAULT_TOP_K = 20

MAX_TOP_K = 100

# ============================================================
# FASTAPI INIT
# ============================================================

app = FastAPI(
    title="CPT Retrieval API",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# GLOBAL OBJECTS
# ============================================================

model = None

index = None

metadata = None

text_to_cpts = None


# ============================================================
# REQUEST SCHEMA
# ============================================================

class RetrievalRequest(BaseModel):
    text: str

    k: int = DEFAULT_TOP_K


# ============================================================
# RESPONSE SCHEMA
# ============================================================

class RetrievalResponse(BaseModel):
    top_k_suggested_code: list[str]

    top_k_suggested_score: list[float]


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup_event():
    global model
    global index
    global metadata
    global text_to_cpts

    print("\n================================================")
    print("INITIALIZING CPT RETRIEVAL API")
    print("================================================")

    # --------------------------------------------------------
    # LOAD MODEL
    # --------------------------------------------------------

    print("\nLoading SentenceTransformer model...")

    model = SentenceTransformer(
        MODEL_NAME,
        device="cpu",
    )

    model.max_seq_length = 256

    # --------------------------------------------------------
    # LOAD FAISS
    # --------------------------------------------------------

    print("\nLoading FAISS index...")

    index = faiss.read_index(
        f"{FAISS_DIR}/faiss.index"
    )

    print(
        f"Indexed vectors: "
        f"{index.ntotal:,}"
    )

    # --------------------------------------------------------
    # LOAD METADATA
    # --------------------------------------------------------

    print("\nLoading metadata...")

    metadata = pd.read_parquet(
        f"{FAISS_DIR}/metadata.parquet"
    )

    print(
        f"Metadata rows: "
        f"{len(metadata):,}"
    )

    # --------------------------------------------------------
    # LOAD CPT MAPPING
    # --------------------------------------------------------

    print("\nLoading CPT mappings...")

    with open(
            f"{FAISS_DIR}/text_to_cpts.pkl",
            "rb"
    ) as f:
        text_to_cpts = pickle.load(f)

    print(
        f"Text mappings: "
        f"{len(text_to_cpts):,}"
    )

    print("\n================================================")
    print("API READY")
    print("================================================")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def health_check():
    return {
        "status": "running",
        "service": "CPT Retrieval API",
    }


# ============================================================
# RETRIEVAL FUNCTION
# ============================================================

def retrieve_cpts(
        query_text: str,
        top_k: int,
):
    # --------------------------------------------------------
    # ENCODE QUERY
    # --------------------------------------------------------

    query_embedding = model.encode(

        [query_text],

        normalize_embeddings=True,

        convert_to_numpy=True,

    ).astype(np.float32)

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    scores, indices = index.search(
        query_embedding,
        top_k,
    )

    scores = scores[0]
    indices = indices[0]

    # --------------------------------------------------------
    # AGGREGATE CPT SCORES
    # --------------------------------------------------------

    cpt_score_map = defaultdict(list)

    for idx, score in zip(indices, scores):

        row = metadata.iloc[idx]

        matched_text = row["text"]

        matched_cpts = text_to_cpts.get(
            matched_text,
            []
        )

        # ----------------------------------------------------
        # NORMALIZE SCORE
        # ----------------------------------------------------

        score = float(score)

        score = np.clip(
            score,
            -1.0,
            1.0,
        )

        normalized_score = (
                                   score + 1.0
                           ) / 2.0

        # ----------------------------------------------------
        # SAME SCORE FOR ALL CPTS
        # ----------------------------------------------------

        for cpt in matched_cpts:
            cpt_score_map[cpt].append(
                normalized_score
            )

    # --------------------------------------------------------
    # AGGREGATE FINAL SCORES
    # --------------------------------------------------------

    final_results = []

    for cpt, score_list in cpt_score_map.items():
        final_score = max(score_list)

        final_results.append(
            (cpt, final_score)
        )

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    final_results = sorted(

        final_results,

        key=lambda x: x[1],

        reverse=True,
    )

    # --------------------------------------------------------
    # LIMIT
    # --------------------------------------------------------

    final_results = final_results[:top_k]

    # --------------------------------------------------------
    # FORMAT OUTPUT
    # --------------------------------------------------------

    output_codes = [
        x[0]
        for x in final_results
    ]

    output_scores = [
        round(float(x[1]), 6)
        for x in final_results
    ]

    return {

        "top_k_suggested_code":
            output_codes,

        "top_k_suggested_score":
            output_scores,
    }


# ============================================================
# API ENDPOINT
# ============================================================

@app.post(
    "/retrieve",
    response_model=RetrievalResponse,
)
def retrieve(
        request: RetrievalRequest
):
    text = request.text.strip()

    k = request.k

    # --------------------------------------------------------
    # SAFETY
    # --------------------------------------------------------

    if not text:
        return {

            "top_k_suggested_code": [],

            "top_k_suggested_score": [],
        }

    k = max(1, min(k, MAX_TOP_K))

    # --------------------------------------------------------
    # RETRIEVE
    # --------------------------------------------------------

    result = retrieve_cpts(
        query_text=text,
        top_k=k,
    )

    return result


# ============================================================
# LOCAL TEST
# ============================================================

if __name__ == "__main__":
    import uvicorn

    if __name__ == "__main__":
        import uvicorn

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8083,
        )
