"""
===============================================================
BUILD FAISS INDEX FOR CPT RETRIEVAL
===============================================================

Run this script ONLY ONCE.

Outputs
-------
faiss_store/
    ├── faiss.index
    ├── metadata.parquet
    ├── text_to_cpts.pkl

===============================================================
"""

from __future__ import annotations

import pickle
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# ============================================================
# CONFIG
# ============================================================

TRAIN_CSV = "/home/dhanachandra/Downloads/CPT_Index_formatted.tsv"

OUTPUT_DIR = "./faiss_store"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

BATCH_SIZE = 32

LEVEL_COLUMNS = [
    "level_0",
    "level_1",
    "level_2",
    "level_3",
    "level_4",
    "level_5",
]

# ============================================================
# OUTPUT DIR
# ============================================================

Path(OUTPUT_DIR).mkdir(
    parents=True,
    exist_ok=True,
)

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
# LOAD DATA
# ============================================================

print("\nLoading dataset...")

df = pd.read_csv(
    TRAIN_CSV,
    dtype=str,
    sep='\t'
)

print(f"Rows loaded: {len(df):,}")

# ============================================================
# BUILD TEXT
# ============================================================

for col in LEVEL_COLUMNS:

    if col in df.columns:
        df[col] = df[col].fillna("")

df["text"] = (

    df[LEVEL_COLUMNS]

    .astype(str)

    .agg(" ".join, axis=1)

    .str.replace(r"\s+", " ", regex=True)

    .str.strip()
)

# ============================================================
# REMOVE EMPTY
# ============================================================

df = df[
    df["text"].str.len() > 0
].reset_index(drop=True)

print(f"Valid rows: {len(df):,}")

# ============================================================
# BUILD TEXT -> CPT MAPPING
# ============================================================

print("\nBuilding text-to-CPT mapping...")

text_to_cpts = (

    df.groupby("text")["cpt_code"]

    .apply(list)

    .to_dict()
)

# ============================================================
# UNIQUE TEXTS
# ============================================================

unique_texts = list(
    text_to_cpts.keys()
)

print(
    f"Unique texts: "
    f"{len(unique_texts):,}"
)

# ============================================================
# ENCODE TEXTS WITH TQDM
# ============================================================

print("\nEncoding texts...")

all_embeddings = []

num_batches = (
    len(unique_texts) + BATCH_SIZE - 1
) // BATCH_SIZE

for start_idx in tqdm(
    range(0, len(unique_texts), BATCH_SIZE),
    total=num_batches,
    desc="Embedding batches",
):

    batch_texts = unique_texts[
        start_idx:start_idx + BATCH_SIZE
    ]

    batch_embeddings = model.encode(

        batch_texts,

        batch_size=BATCH_SIZE,

        normalize_embeddings=True,

        convert_to_numpy=True,

        show_progress_bar=False,
    )

    all_embeddings.append(
        batch_embeddings
    )

# ============================================================
# CONCATENATE
# ============================================================

embeddings = np.vstack(
    all_embeddings
).astype(np.float32)

print(
    f"\nEmbedding shape: "
    f"{embeddings.shape}"
)
# ============================================================
# BUILD FAISS INDEX
# ============================================================

print("\nBuilding FAISS index...")

embedding_dim = embeddings.shape[1]

index = faiss.IndexFlatIP(
    embedding_dim
)

index.add(embeddings)

print(
    f"Indexed vectors: "
    f"{index.ntotal:,}"
)

# ============================================================
# SAVE INDEX
# ============================================================

faiss.write_index(
    index,
    f"{OUTPUT_DIR}/faiss.index"
)

print("Saved faiss.index")

# ============================================================
# SAVE METADATA
# ============================================================

metadata = pd.DataFrame({

    "text": unique_texts
})

metadata.to_parquet(
    f"{OUTPUT_DIR}/metadata.parquet",
    index=False,
)

print("Saved metadata.parquet")

# ============================================================
# SAVE CPT MAPPING
# ============================================================

with open(
    f"{OUTPUT_DIR}/text_to_cpts.pkl",
    "wb"
) as f:

    pickle.dump(
        text_to_cpts,
        f,
        protocol=pickle.HIGHEST_PROTOCOL
    )

print("Saved text_to_cpts.pkl")

print("\n================================================")
print("INDEX BUILD COMPLETE")
print("================================================")