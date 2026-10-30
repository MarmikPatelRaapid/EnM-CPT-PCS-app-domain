"""
===============================================================
JSON CPT RETRIEVAL CLIENT
===============================================================

Purpose
-------
1. Read multiple JSON files
2. Extract CPT evidence objects
3. Build combined query text
4. Send retrieval requests to API
5. Save predictions into CSV

===============================================================
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

# ============================================================
# CONFIG
# ============================================================

JSON_FOLDER = "/home/dhanachandra/Downloads/CPT sample output updated/CPT sample output updated"

OUTPUT_CSV = "json_cpt_predictions.csv"

API_URL = "http://localhost:8000/retrieve"

TOP_K = 5

# ============================================================
# NORMALIZED KEYS
# ============================================================

# TEXT_KEYS = [
#
#     "norm_procedure_name",
#
#     "norm_disease_name",
#
#     "norm_anatomy",
#
#     "norm_laterality",
#
#     "norm_approach",
#
#     "norm_procedure_type",
#
#     "norm_extent_or_complexity",
#
#     "norm_technique",
#
#     "norm_imaging_guidance",
#
#     "norm_specimen",
#
#     "norm_measurement",
#
#     "norm_additional_procedure",
#
#     "norm_anesthesia_type",
#
#     "norm_modifier_indicator",
#
#     "norm_other",
# ]

TEXT_KEYS = [
    "norm_procedure_name",
    "norm_disease_name",
    "norm_anatomy",
    "norm_approach",
    "norm_procedure_type",
    "norm_technique",
    "norm_imaging_guidance",
    "norm_other"
]

# ============================================================
# GET JSON FILES
# ============================================================

json_files = sorted(

    list(
        Path(JSON_FOLDER).glob("*.json")
    )
)

print(
    f"\nJSON files found: "
    f"{len(json_files):,}"
)

# ============================================================
# OUTPUT ROWS
# ============================================================

output_rows = []

# ============================================================
# PROCESS FILES
# ============================================================

for json_file in tqdm(
    json_files,
    desc="Processing JSON files",
):

    file_name = json_file.name

    # --------------------------------------------------------
    # LOAD JSON
    # --------------------------------------------------------

    try:

        with open(
            json_file,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

    except Exception as e:

        print(
            f"\nERROR loading "
            f"{file_name}: {e}"
        )

        continue

    # --------------------------------------------------------
    # CPT OBJECTS
    # --------------------------------------------------------

    cpt_objects = data.get(
        "cpt_codes_found",
        []
    )

    # --------------------------------------------------------
    # PROCESS CPT OBJECTS
    # --------------------------------------------------------

    for obj in cpt_objects:

        # ----------------------------------------------------
        # TRUE CPT CODE
        # ----------------------------------------------------

        actual_cpt = str(
            obj.get(
                "cpt_code",
                ""
            )
        ).strip()

        # ----------------------------------------------------
        # BUILD COMBINED TEXT
        # ----------------------------------------------------

        text_parts = []

        for key in TEXT_KEYS:

            value = obj.get(
                key,
                None
            )

            # ------------------------------------------------
            # SKIP NULLS
            # ------------------------------------------------

            if value is None:
                continue

            value = str(value).strip()

            if not value:
                continue

            if value.lower() == "null":
                continue

            text_parts.append(value)

        combined_text = " ".join(
            text_parts
        )

        combined_text = " ".join(
            combined_text.split()
        )

        # ----------------------------------------------------
        # EMPTY TEXT
        # ----------------------------------------------------

        if not combined_text:

            row_data = {

                "File_Name": file_name,

                "cpt_code": actual_cpt,

                "Combine_Text": "",
            }

            for i in range(1, TOP_K + 1):

                row_data[
                    f"Top_{i}_Code"
                ] = ""

                row_data[
                    f"Top_{i}_Score"
                ] = ""

            output_rows.append(
                row_data
            )

            continue

        # ----------------------------------------------------
        # API PAYLOAD
        # ----------------------------------------------------

        payload = {

            "text": combined_text,

            "k": TOP_K,
        }

        # ----------------------------------------------------
        # API REQUEST
        # ----------------------------------------------------

        try:

            response = requests.post(

                API_URL,

                json=payload,

                timeout=120,
            )

            response.raise_for_status()

            result = response.json()

        except Exception as e:

            print(
                f"\nAPI ERROR "
                f"{file_name}: {e}"
            )

            row_data = {

                "File_Name": file_name,

                "cpt_code": actual_cpt,

                "Combine_Text": combined_text,
            }

            for i in range(1, TOP_K + 1):

                row_data[
                    f"Top_{i}_Code"
                ] = ""

                row_data[
                    f"Top_{i}_Score"
                ] = ""

            output_rows.append(
                row_data
            )

            continue

        # ----------------------------------------------------
        # PARSE RESPONSE
        # ----------------------------------------------------

        codes = result.get(
            "top_k_suggested_code",
            []
        )

        scores = result.get(
            "top_k_suggested_score",
            []
        )

        # ----------------------------------------------------
        # BUILD OUTPUT ROW
        # ----------------------------------------------------

        row_data = {

            "File_Name": file_name,

            "cpt_code": actual_cpt,

            "Combine_Text": combined_text,
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

        addon_code_objects = obj.get(
            "addon_codes",
            []
        )

        addon_cpts = []

        if isinstance(
                addon_code_objects,
                list
        ):

            for addon_obj in addon_code_objects:

                if not isinstance(
                        addon_obj,
                        dict
                ):
                    continue

                addon_cpt = str(
                    addon_obj.get(
                        "cpt_code",
                        ""
                    )
                ).strip()

                if addon_cpt:
                    addon_cpts.append(
                        addon_cpt
                    )
        for addon_cpt in addon_cpts:

            addon_row = {

                "File_Name": file_name,

                "cpt_code": addon_cpt,

                "Combine_Text": "",
            }

            # ------------------------------------------------
            # EMPTY RETRIEVAL COLUMNS
            # ------------------------------------------------

            for j in range(1, TOP_K + 1):
                addon_row[
                    f"Top_{j}_Code"
                ] = ""

                addon_row[
                    f"Top_{j}_Score"
                ] = ""

            output_rows.append(
                addon_row
            )

# ============================================================
# SAVE OUTPUT
# ============================================================

print("\nSaving output CSV...")

output_df = pd.DataFrame(
    output_rows
)

output_df.to_csv(
    OUTPUT_CSV,
    index=False,
)

print(f"\nSaved: {OUTPUT_CSV}")

print("\n================================================")
print("PROCESSING COMPLETE")
print("================================================")