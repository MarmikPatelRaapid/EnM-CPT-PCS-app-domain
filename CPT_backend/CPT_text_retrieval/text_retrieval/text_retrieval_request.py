"""
===============================================================
CPT RETRIEVAL API CLIENT
===============================================================

Purpose
-------
1. Read CSV input
2. Send requests to FastAPI retrieval API
3. Parse predictions
4. Save output CSV

Input CSV
---------
Must contain:

evidence_text

Output CSV
----------
evidence_text
Top_1_Code
Top_1_Score
Top_2_Code
Top_2_Score
...

===============================================================
"""

from __future__ import annotations

import pandas as pd
import requests
from tqdm import tqdm

# ============================================================
# CONFIG
# ============================================================

INPUT_CSV = "/home/dhanachandra/Downloads/Sample_input_2.csv"

OUTPUT_CSV = "output_predictions.csv"

API_URL = "http://localhost:8000/retrieve"

TOP_K = 50

# ============================================================
# LOAD INPUT
# ============================================================

print("\nLoading input CSV...")

df = pd.read_csv(
    INPUT_CSV,
    dtype=str,
)

print(f"Rows loaded: {len(df):,}")

# ============================================================
# VALIDATE
# ============================================================

if "evidence_text" not in df.columns:

    raise ValueError(
        "Input CSV must contain "
        "'evidence_text' column"
    )

# ============================================================
# CLEAN
# ============================================================

df["evidence_text"] = (

    df["evidence_text"]

    .fillna("")

    .astype(str)
)

# ============================================================
# PROCESS ROWS
# ============================================================

output_rows = []

print("\nSending API requests...")

for text in tqdm(
    df["evidence_text"],
    total=len(df),
):

    # --------------------------------------------------------
    # EMPTY INPUT
    # --------------------------------------------------------

    if not text.strip():

        row_data = {
            "evidence_text": text
        }

        for i in range(1, TOP_K + 1):

            row_data[f"Top_{i}_Code"] = ""

            row_data[f"Top_{i}_Score"] = ""

        output_rows.append(
            row_data
        )

        continue

    # --------------------------------------------------------
    # REQUEST PAYLOAD
    # --------------------------------------------------------

    payload = {

        "text": text,

        "k": TOP_K,
    }

    # --------------------------------------------------------
    # API REQUEST
    # --------------------------------------------------------

    try:

        response = requests.post(

            API_URL,

            json=payload,

            timeout=120,
        )

        response.raise_for_status()

        result = response.json()

    except Exception as e:

        print(f"\nAPI ERROR: {e}")

        row_data = {
            "evidence_text": text
        }

        for i in range(1, TOP_K + 1):

            row_data[f"Top_{i}_Code"] = ""

            row_data[f"Top_{i}_Score"] = ""

        output_rows.append(
            row_data
        )

        continue

    # --------------------------------------------------------
    # PARSE RESPONSE
    # --------------------------------------------------------

    codes = result.get(
        "top_k_suggested_code",
        []
    )

    scores = result.get(
        "top_k_suggested_score",
        []
    )

    # --------------------------------------------------------
    # BUILD OUTPUT ROW
    # --------------------------------------------------------

    row_data = {

        "evidence_text": text
    }

    for i in range(TOP_K):

        if i < len(codes):

            row_data[
                f"Top_{i+1}_Code"
            ] = codes[i]

            row_data[
                f"Top_{i+1}_Score"
            ] = scores[i]

        else:

            row_data[
                f"Top_{i+1}_Code"
            ] = ""

            row_data[
                f"Top_{i+1}_Score"
            ] = ""

    output_rows.append(
        row_data
    )

# ============================================================
# OUTPUT DATAFRAME
# ============================================================

output_df = pd.DataFrame(
    output_rows
)

# ============================================================
# SAVE
# ============================================================

print("\nSaving predictions...")

output_df.to_csv(
    OUTPUT_CSV,
    index=False,
)

print(f"\nSaved: {OUTPUT_CSV}")

print("\n================================================")
print("PROCESSING COMPLETE")
print("================================================")