"""
===============================================================
CPT RETRIEVAL INFERENCE
===============================================================

Input:
    Query text

Output:
    Top-k similar training texts
    + associated CPT codes
    + similarity scores

===============================================================
"""

from __future__ import annotations

import pickle

import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

# ============================================================
# CONFIG
# ============================================================

FAISS_DIR = "./faiss_store"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

TOP_K = 20

# ============================================================
# LOAD MODEL
# ============================================================

print("\nLoading model...")

model = SentenceTransformer(
    MODEL_NAME,
    device="cpu",
)

model.max_seq_length = 64

# ============================================================
# LOAD FAISS INDEX
# ============================================================

print("Loading FAISS index...")

index = faiss.read_index(
    f"{FAISS_DIR}/faiss.index"
)

# ============================================================
# LOAD METADATA
# ============================================================

metadata = pd.read_parquet(
    f"{FAISS_DIR}/metadata.parquet"
)

# ============================================================
# LOAD CPT MAPPING
# ============================================================

with open(
        f"{FAISS_DIR}/text_to_cpts.pkl",
        "rb"
) as f:
    text_to_cpts = pickle.load(f)

# ============================================================
# RETRIEVAL FUNCTION
# ============================================================
import pandas as pd


def retrieve_top_k(
        query_text,
        top_k=20,
):
    if not query_text:
        return pd.DataFrame()

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
    # BUILD RESULTS
    # --------------------------------------------------------

    results = []

    rank = 1

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
        # SAME SCORE FOR ALL CPTs
        # ----------------------------------------------------

        for cpt in matched_cpts:
            results.append({

                "rank": rank,

                "cpt_code": cpt,

                "similarity_score": round(
                    normalized_score,
                    6
                ),

                "matched_text": matched_text,
            })

            rank += 1

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    results_df = pd.DataFrame(results)

    results_df = results_df.sort_values(
        by="similarity_score",
        ascending=False,
    )

    return results_df.reset_index(drop=True)


# ============================================================
# EXAMPLE
# ============================================================

if __name__ == "__main__":
    query = (
        "Fine needle aspiration "
        "biopsy ultrasound lesion"
    )

    results = retrieve_top_k(
        query,
        top_k=20,
    )

    print("\n================================================")
    print("QUERY")
    print("================================================")

    print(query)

    print("\n================================================")
    print("TOP MATCHES")
    print("================================================")

    print(
        results.to_string(index=False)
    )
