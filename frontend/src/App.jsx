import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import raapidLogo from "../raapid_logo.png";
import DomainWorkbench from "./DomainWorkbench.jsx";
import "./workbench.css";
import { loadModelDropdownConfig, buildModelOverrides } from "./modelOptions.js";

export const API_BASE_URLS = {
  // Relative paths, proxied by Vite (see frontend/vite.config.js) to each
  // backend port server-side. This works whether the app is opened from the
  // same machine (local dev) or remotely through a load balancer — the
  // browser only ever talks to wherever the frontend itself is served from.
  synthetic: "/api/em-synth",
  cptSynthetic: "/api/cpt-synth",
  evidence: "/api/evidence",
  em: "/api/em",
  cpt: "/api/cpt",
  pcs: "/api/pcs"
};

const WORKFLOW_OPTIONS = [
  { label: "E&M", value: "em" },
  { label: "CPT", value: "cpt" },
  { label: "PCS", value: "pcs" }
];

const CATEGORY_OPTIONS_BY_WORKFLOW = {
  em: [],
  cpt: [
    "Anesthesia",
    "Surgery",
    "Radiology",
    "Pathology & Laboratory",
    "Medicines",
    "Proprietary Laboratory Analyses (PLA)"
  ],
  pcs: [
    "Medical and Surgical",
    "Obstetrics",
    "Placement",
    "Administration",
    "Measurement and Monitoring",
    "Extracorporeal or Systemic Assistance and Performance",
    "Extracorporeal or Systemic Therapies",
    "Osteopathic",
    "Other Procedures",
    "Chiropractic",
    "Imaging",
    "Nuclear Medicine",
    "Radiation Therapy",
    "Physical Rehabilitation and Diagnostic Audiology",
    "Mental Health",
    "Substance Abuse Treatment",
    "New Technology"
  ]
};

const WORKFLOW_LABELS = {
  em: "E&M",
  cpt: "CPT",
  pcs: "PCS"
};

const TOOL_NAME = "Synthetic Clinical Documentation & Coding Simulator";
const TOOL_SUBTITLE =
  "Simulate realistic clinical documentation and evaluate coding outcomes across E&M, CPT and PCS workflows.";

const FRIENDLY_MAPPER_LABELS = {
  facility_type: "Facility Type",
  service_type: "Service Type",
  patient_type: "Patient Type",
  time_value: "Time (minutes)",
  patient_age: "Patient Age",
  patient_age_unit: "Patient Age Unit",
  mdm_level: "MDM Level"
};

const EVIDENCE_FIELDS_BY_WORKFLOW = {
  em: [
    "facility",
    "service",
    "patient",
    "physician_time_spent_with_patient",
    "staff_time_spent_with_patient",
    "complexity",
    "data_to_review",
    "risk_of_morbidity"
  ],
  cpt: [
    "procedure_evidences",
    "anatomy_evidences",
    "approach_evidences",
    "procedure_type_evidences",
    "imaging_guidance_evidences",
    "anesthesia_type_evidences",
    "other_evidences"
  ],
  pcs: [
    "evidence_for_first_character",
    "evidence_for_second_character",
    "evidence_for_third_character",
    "evidence_for_fourth_character",
    "evidence_for_fifth_character",
    "evidence_for_sixth_character",
    "evidence_for_seventh_character"
  ]
};

const PCS_CHARACTER_LABEL_BY_KEY = {
  evidence_for_first_character: "First Character",
  evidence_for_second_character: "Second Character",
  evidence_for_third_character: "Third Character",
  evidence_for_fourth_character: "Fourth Character",
  evidence_for_fifth_character: "Fifth Character",
  evidence_for_sixth_character: "Sixth Character",
  evidence_for_seventh_character: "Seventh Character"
};

const EM_MDM_EVIDENCE_KEYS = new Set(["complexity", "data_to_review", "risk_of_morbidity"]);
const EM_MDM_DETAIL_KEY_BY_EVIDENCE_KEY = {
  complexity: "complexity",
  data_to_review: "data_to_review",
  risk_of_morbidity: "risk"
};

const initialForm = {
  workflow: "em",
  categories: [],
  codeInput: "",
  numDocs: "1"
};

function createEmptyWorkflowInputState() {
  return {
    categories: [],
    codeInput: "",
    numDocs: "1"
  };
}

function createEmptyWorkflowViewState() {
  return {
    documents: [],
    selectedDocIndex: null,
    resultsByDocument: {},
    codingErrorsByDocument: {},
    editingDocumentId: null
  };
}

function parseCodeInput(codeInput) {
  return String(codeInput ?? "")
    .split(",")
    .map((code) => code.trim())
    .filter(Boolean);
}

function normalizeWorkflow(workflow) {
  if (workflow === "em" || workflow === "cpt" || workflow === "pcs") {
    return workflow;
  }
  return "em";
}

function workflowLabel(workflow) {
  return WORKFLOW_LABELS[normalizeWorkflow(workflow)] ?? "E&M";
}

function createDocId(prefix, code, index) {
  const cleanCode = String(code ?? "").replace(/[^A-Za-z0-9]/g, "").slice(0, 16);
  return `${prefix}-${index}-${cleanCode || "doc"}-${Math.random().toString(16).slice(2, 6)}`;
}

function normalizeCode(rawCode) {
  return String(rawCode ?? "")
    .trim()
    .toUpperCase()
    .replace(/[^0-9A-Z]/g, "");
}

function classifyCptCategoryByRange(rawCode) {
  const normalizedCode = normalizeCode(rawCode);
  if (!normalizedCode) {
    return "Unmapped";
  }

  const numericCodeMatch = normalizedCode.match(/^\d{5}$/);
  if (numericCodeMatch) {
    const numericValue = Number(normalizedCode);
    if (numericValue >= 100 && numericValue <= 1999) {
      return "Anaesthesia";
    }
    if (numericValue >= 10021 && numericValue <= 69990) {
      return "Surgery";
    }
    if (numericValue >= 70010 && numericValue <= 79999) {
      return "Radiology";
    }
    if (numericValue >= 80047 && numericValue <= 89398) {
      return "Pathology & Laboratory";
    }
    if (numericValue >= 90281 && numericValue <= 99607) {
      return "Medicines";
    }
  }

  const plaCodeMatch = normalizedCode.match(/^(\d{4})U$/);
  if (plaCodeMatch) {
    const plaNumericValue = Number(plaCodeMatch[1]);
    if (plaNumericValue >= 1 && plaNumericValue <= 599) {
      return "Proprietary Laboratory Analyses (PLA)";
    }
  }

  return "Unmapped";
}

function classifyPcsCategoryByCode(rawCode) {
  const normalizedCode = normalizeCode(rawCode);
  const prefix = normalizedCode.charAt(0);
  if (!prefix) {
    return "Unmapped";
  }

  const categoryByPrefix = {
    "0": "Medical and Surgical",
    "1": "Obstetrics",
    "2": "Placement",
    "3": "Administration",
    "4": "Measurement and Monitoring",
    "5": "Extracorporeal or Systemic Assistance and Performance",
    "6": "Extracorporeal or Systemic Therapies",
    "7": "Osteopathic",
    "8": "Other Procedures",
    "9": "Chiropractic",
    B: "Imaging",
    C: "Nuclear Medicine",
    D: "Radiation Therapy",
    F: "Physical Rehabilitation and Diagnostic Audiology",
    G: "Mental Health",
    H: "Substance Abuse Treatment",
    X: "New Technology"
  };

  return categoryByPrefix[prefix] ?? "Unmapped";
}

// Some model outputs double-escape control characters, so the generated text
// arrives containing literal "\n" / "\r\n" / "\t" sequences (backslash + letter)
// instead of real line breaks. Convert the common ones back so the document
// preview renders newlines correctly.
function normalizeDocumentNewlines(text) {
  const raw = String(text ?? "");
  if (!raw) {
    return raw;
  }
  return raw
    .replace(/\\r\\n/g, "\n")
    .replace(/\\n/g, "\n")
    .replace(/\\r/g, "\n")
    .replace(/\\t/g, "\t");
}

function normalizeSyntheticDocuments(responseJson, workflow, categories, traceIdFromServer) {
  const docs = Array.isArray(responseJson?.documents) ? responseJson.documents : [];
  return docs.map((doc, index) => {
    const code =
      workflow === "em"
        ? String(doc?.["e&mcode"] ?? doc?.em_code ?? "")
        : String(doc?.cpt_code ?? doc?.["cpt code"] ?? "");
    const code_description =
      workflow === "em"
        ? String(doc?.["e&mcodedescription"] ?? doc?.em_code_description ?? "")
        : "";
    const resolvedCategory =
      workflow === "em"
        ? "E&M"
        : workflow === "cpt"
          ? classifyCptCategoryByRange(code)
          : categories.join(", ") || "Unmapped";
    return {
      id: createDocId(workflow, code, index),
      workflow,
      workflowLabel: workflowLabel(workflow),
      category: resolvedCategory,
      code,
      code_description,
      rational: String(doc?.rational ?? doc?.rationale ?? doc?.Justification ?? doc?.justification ?? ""),
      generated_document: normalizeDocumentNewlines(doc?.generated_document),
      trace_id: traceIdFromServer,
      document_ref: `generated-${index + 1}`,
      rawDocument: doc,
      isCustom: false
    };
  });
}

function normalizePcsDocuments(responseJson, categories) {
  const docs = Array.isArray(responseJson?.documents) ? responseJson.documents : [];
  return docs.map((doc, index) => ({
    id: createDocId("pcs", doc?.icd10_pcs_code, index),
    workflow: "pcs",
    workflowLabel: "PCS",
    category: classifyPcsCategoryByCode(doc?.icd10_pcs_code),
    code: String(doc?.icd10_pcs_code ?? ""),
    code_description: String(doc?.icd10_pcs_code_description ?? ""),
    rational: String(doc?.rational ?? doc?.rationale ?? ""),
    generated_document: normalizeDocumentNewlines(doc?.generated_document),
    trace_id: `pcs-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
    document_ref: `pcs-generated-${index + 1}`,
    rawDocument: doc,
    isCustom: false
  }));
}

function createCustomDocument(defaultWorkflow) {
  const uniqueId = `custom-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const traceId = `manual-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
  return {
    id: uniqueId,
    workflow: defaultWorkflow,
    workflowLabel: workflowLabel(defaultWorkflow),
    generated_document: "",
    code: "",
    category: "Custom Input",
    code_description: "",
    rational: "",
    trace_id: traceId,
    document_ref: uniqueId,
    rawDocument: {},
    isCustom: true
  };
}

// Number of automatic retries (in addition to the first attempt) for model-backed
// calls that occasionally fail because the LLM returns malformed JSON.
const MODEL_CALL_RETRY_ATTEMPTS = 2;
const MODEL_CALL_RETRY_BASE_DELAY_MS = 600;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetriableModelError(status, errorBody) {
  if (status >= 500) {
    return true;
  }
  const text = String(errorBody ?? "").toLowerCase();
  return (
    text.includes("not valid json") ||
    text.includes("parse attempts failed") ||
    text.includes("model response")
  );
}

// POST helper that retries the same payload when the backend reports a transient
// model failure (e.g. "Model response is not valid JSON") or a network/5xx error.
async function postJsonWithRetry(
  url,
  { headers, body, label, retries = MODEL_CALL_RETRY_ATTEMPTS, onRetry } = {}
) {
  let lastError = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    let response;
    try {
      response = await fetch(url, { method: "POST", headers, body });
    } catch (networkError) {
      lastError = networkError;
      if (attempt < retries) {
        onRetry?.(attempt + 1, networkError.message);
        await delay(MODEL_CALL_RETRY_BASE_DELAY_MS * (attempt + 1));
        continue;
      }
      throw networkError;
    }

    if (response.ok) {
      return response;
    }

    const errorBody = await response.text();
    lastError = new Error(errorBody || `${label ?? "Request"} failed with status ${response.status}`);
    if (attempt < retries && isRetriableModelError(response.status, errorBody)) {
      onRetry?.(attempt + 1, errorBody);
      await delay(MODEL_CALL_RETRY_BASE_DELAY_MS * (attempt + 1));
      continue;
    }
    throw lastError;
  }
  throw lastError ?? new Error(`${label ?? "Request"} failed`);
}

function downloadJson(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

function toDisplayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? "N/A" : value.join(", ");
  }
  return String(value);
}

function toTitleCaseWords(value) {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return "N/A";
  }
  return raw
    .replaceAll("_", " ")
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function formatDocumentParagraphs(rawDocument) {
  const text = String(rawDocument ?? "").trim();
  if (!text) {
    return [];
  }

  const byNewline = text
    .split(/\n+/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  if (byNewline.length > 1) {
    return byNewline;
  }

  const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g)?.map((part) => part.trim()) ?? [text];
  const groupedParagraphs = [];
  for (let index = 0; index < sentences.length; index += 2) {
    groupedParagraphs.push(sentences.slice(index, index + 2).join(" "));
  }
  return groupedParagraphs;
}

function formatEvidenceCategory(key) {
  return toTitleCaseWords(String(key ?? "").replaceAll("_", " "));
}

function normalizeEvidenceObject(evidence, meta) {
  const text = String(evidence?.text ?? "").trim();
  if (!text) {
    return null;
  }
  return {
    text,
    pgNo: evidence?.pg_no ?? null,
    reftxtbefore: String(evidence?.reftxtbefore ?? ""),
    reftxtafter: String(evidence?.reftxtafter ?? ""),
    ...meta
  };
}

function getEmMdmSubcategoryClass(selectedEmResult, evidenceKey) {
  if (!EM_MDM_EVIDENCE_KEYS.has(evidenceKey)) {
    return "";
  }
  const detailKey = EM_MDM_DETAIL_KEY_BY_EVIDENCE_KEY[evidenceKey] ?? evidenceKey;
  const detailsCategory = selectedEmResult?.classification?.details?.[detailKey]?.category;
  const classificationCategory = selectedEmResult?.classification?.[detailKey];
  return String(detailsCategory ?? classificationCategory ?? "").trim();
}

function getEmMdmElementLabel(evidenceKey) {
  if (!EM_MDM_EVIDENCE_KEYS.has(evidenceKey)) {
    return "";
  }
  const detailKey = EM_MDM_DETAIL_KEY_BY_EVIDENCE_KEY[evidenceKey] ?? evidenceKey;
  return toTitleCaseWords(detailKey);
}

function buildDataToReviewCategoryMap(selectedEvidenceResult) {
  const categoryMap = new Map();
  if (!selectedEvidenceResult || typeof selectedEvidenceResult !== "object") {
    return categoryMap;
  }

  const addCategoryEntries = (entries, categoryKey) => {
    const categoryLabel = formatEvidenceCategory(categoryKey);
    const evidenceEntries = Array.isArray(entries) ? entries : [];
    evidenceEntries.forEach((entry) => {
      const text = String(entry?.text ?? "").trim();
      const before = String(entry?.reftxtbefore ?? "");
      const after = String(entry?.reftxtafter ?? "");
      if (!text) {
        return;
      }
      const entryKey = [text, before, after].join("||");
      if (!categoryMap.has(entryKey)) {
        categoryMap.set(entryKey, new Set());
      }
      categoryMap.get(entryKey).add(categoryLabel);
    });
  };

  const visitNode = (node) => {
    if (!node || typeof node !== "object") {
      return;
    }

    if (!Array.isArray(node) && node.data_to_review && typeof node.data_to_review === "object") {
      Object.entries(node.data_to_review).forEach(([categoryKey, entries]) => {
        addCategoryEntries(entries, categoryKey);
      });
    }

    if (Array.isArray(node)) {
      node.forEach((item) => visitNode(item));
      return;
    }

    Object.values(node).forEach((value) => visitNode(value));
  };

  visitNode(selectedEvidenceResult);
  return categoryMap;
}

function buildComplexityPathMap(selectedEvidenceResult) {
  const pathMap = new Map();
  if (!selectedEvidenceResult || typeof selectedEvidenceResult !== "object") {
    return pathMap;
  }

  const addEvidencePaths = (entries, pathParts) => {
    const evidenceEntries = Array.isArray(entries) ? entries : [];
    const pathLabel = pathParts.map((segment) => toTitleCaseWords(segment)).join(" > ");
    evidenceEntries.forEach((entry) => {
      const text = String(entry?.text ?? "").trim();
      const before = String(entry?.reftxtbefore ?? "");
      const after = String(entry?.reftxtafter ?? "");
      if (!text) {
        return;
      }
      const entryKey = [text, before, after].join("||");
      if (!pathMap.has(entryKey)) {
        pathMap.set(entryKey, new Set());
      }
      pathMap.get(entryKey).add(pathLabel);
    });
  };

  const visitComplexityNode = (node, pathParts) => {
    if (!node || typeof node !== "object") {
      return;
    }

    if (!Array.isArray(node) && Array.isArray(node.disease_evidence)) {
      addEvidencePaths(node.disease_evidence, pathParts);
    }

    if (Array.isArray(node)) {
      node.forEach((item) => visitComplexityNode(item, pathParts));
      return;
    }

    Object.entries(node).forEach(([key, value]) => {
      if (key === "disease_evidence" || key === "norm_disease_name") {
        return;
      }
      if (key === "data_to_review" || key === "risk_of_morbidity") {
        return;
      }
      if (!value || typeof value !== "object") {
        return;
      }
      visitComplexityNode(value, [...pathParts, key]);
    });
  };

  const complexityRoots = [
    "self_limited_minor_problem",
    "chronic_illness",
    "acute_illness",
    "undiagnosed_problem"
  ];
  complexityRoots.forEach((rootKey) => {
    const rootNode = selectedEvidenceResult?.[rootKey];
    if (rootNode) {
      visitComplexityNode(rootNode, [rootKey]);
    }
  });

  return pathMap;
}

function extractEmEvidenceItems(selectedEmResult, selectedEvidenceResult) {
  const source = selectedEmResult?.evidences ?? {};
  const dataToReviewCategoryMap = buildDataToReviewCategoryMap(selectedEvidenceResult);
  const complexityPathMap = buildComplexityPathMap(selectedEvidenceResult);
  const patientAge = selectedEvidenceResult?.patient_age?.age;
  const patientAgeUnit = String(selectedEvidenceResult?.patient_age?.age_unit ?? "").trim();
  const patientAgeDisplay =
    patientAge === null || patientAge === undefined || patientAge === ""
      ? ""
      : `${String(patientAge)}${patientAgeUnit ? ` ${patientAgeUnit}` : ""}`;
  const emTypeByCategoryKey = {
    facility: String(selectedEvidenceResult?.facility?.facility_type ?? "").trim(),
    service: String(selectedEvidenceResult?.service?.service_type ?? "").trim(),
    patient: String(selectedEvidenceResult?.patient?.patient_type ?? "").trim()
  };
  const emTimeByCategoryKey = {
    physician_time_spent_with_patient:
      selectedEvidenceResult?.physician_time_spent_with_patient?.time_in_mins,
    staff_time_spent_with_patient: selectedEvidenceResult?.staff_time_spent_with_patient?.time_in_mins
  };
  const items = [];
  EVIDENCE_FIELDS_BY_WORKFLOW.em.forEach((key) => {
    const entries = Array.isArray(source?.[key]) ? source[key] : [];
    const mdmSubcategoryClass = getEmMdmSubcategoryClass(selectedEmResult, key);
    const mdmElementLabel = getEmMdmElementLabel(key);
    entries.forEach((entry) => {
      const dataToReviewMapKey = [
        String(entry?.text ?? "").trim(),
        String(entry?.reftxtbefore ?? ""),
        String(entry?.reftxtafter ?? "")
      ].join("||");
      const dataToReviewCategories =
        key === "data_to_review"
          ? Array.from(dataToReviewCategoryMap.get(dataToReviewMapKey) ?? []).sort()
          : [];
      const complexityEvidencePaths =
        key === "complexity"
          ? Array.from(complexityPathMap.get(dataToReviewMapKey) ?? []).sort()
          : [];
      const normalized = normalizeEvidenceObject(entry, {
        workflow: "em",
        categoryKey: key,
        categoryLabel: formatEvidenceCategory(key),
        mdmElementLabel,
        mdmSubcategoryClass,
        dataToReviewCategories,
        complexityEvidencePaths,
        emCategoryType: emTypeByCategoryKey[key] ?? "",
        patientAgeDisplay: key === "patient" ? patientAgeDisplay : "",
        emTimeInMinutes:
          key === "physician_time_spent_with_patient" || key === "staff_time_spent_with_patient"
            ? emTimeByCategoryKey[key]
            : null
      });
      if (normalized) {
        items.push(normalized);
      }
    });
  });

  // Patient age evidences are provided by evidence JSON (`/predict`) and may not always
  // appear in flattened `emResult.evidences`, so include them explicitly.
  const patientAgeEvidences = Array.isArray(selectedEvidenceResult?.patient_age?.evidences)
    ? selectedEvidenceResult.patient_age.evidences
    : [];
  patientAgeEvidences.forEach((entry) => {
    const normalized = normalizeEvidenceObject(entry, {
      workflow: "em",
      categoryKey: "patient_age",
      categoryLabel: "Patient Age",
      patientAgeDisplay
    });
    if (normalized) {
      items.push(normalized);
    }
  });

  return items;
}

function extractCptEvidenceItems(selectedCptResult) {
  const auditedCodes = Array.isArray(selectedCptResult?.audited_codes)
    ? selectedCptResult.audited_codes
    : [];
  const items = [];
  auditedCodes.forEach((codeItem) => {
    const finalCptCode = String(codeItem?.final_cpt_code ?? "").trim();
    const finalCptCodeDescription = String(codeItem?.final_cpt_code_description ?? "").trim();
    EVIDENCE_FIELDS_BY_WORKFLOW.cpt.forEach((evidenceObjectName) => {
      const entries = Array.isArray(codeItem?.[evidenceObjectName]) ? codeItem[evidenceObjectName] : [];
      entries.forEach((entry) => {
        const normalized = normalizeEvidenceObject(entry, {
          workflow: "cpt",
          evidenceObjectName,
          evidenceObjectLabel: formatEvidenceCategory(evidenceObjectName),
          finalCptCode,
          finalCptCodeDescription
        });
        if (normalized) {
          items.push(normalized);
        }
      });
    });
  });
  return items;
}

function extractPcsEvidenceItems(selectedPcsResult) {
  const source = Array.isArray(selectedPcsResult?.results)
    ? selectedPcsResult.results[0]?.pcs_code_detection_output ?? {}
    : selectedPcsResult?.pcs_code_detection_output ?? selectedPcsResult ?? {};
  const items = [];
  [
    { key: "billable", label: "Billable" },
    { key: "non_billable", label: "Non-Billable" }
  ].forEach(({ key, label }) => {
    const codeItems = Array.isArray(source?.[key]) ? source[key] : [];
    codeItems.forEach((codeItem) => {
      const mainCode = String(codeItem?.code ?? "").trim();
      const procedureName = String(codeItem?.procedure_name ?? "").trim();
      const evidences = codeItem?.evidences ?? {};
      EVIDENCE_FIELDS_BY_WORKFLOW.pcs.forEach((evidenceObjectName) => {
        const entries = Array.isArray(evidences?.[evidenceObjectName]) ? evidences[evidenceObjectName] : [];
        entries.forEach((entry) => {
          const normalized = normalizeEvidenceObject(entry, {
            workflow: "pcs",
            evidenceObjectName,
            evidenceObjectLabel: formatEvidenceCategory(evidenceObjectName),
            codeCategoryLabel: label,
            mainCode,
            procedureName,
            characterLabel: PCS_CHARACTER_LABEL_BY_KEY[evidenceObjectName] ?? formatEvidenceCategory(evidenceObjectName)
          });
          if (normalized) {
            items.push(normalized);
          }
        });
      });
    });
  });
  return items;
}

function extractSelectedEvidenceItems({
  selectedLastRunPipeline,
  selectedDocumentWorkflow,
  selectedEvidenceResult,
  selectedEmResult,
  selectedCptResult,
  selectedPcsResult
}) {
  const activePipeline = selectedLastRunPipeline ?? selectedDocumentWorkflow ?? "em";
  if (activePipeline === "cpt") {
    return extractCptEvidenceItems(selectedCptResult);
  }
  if (activePipeline === "pcs") {
    return extractPcsEvidenceItems(selectedPcsResult);
  }
  return extractEmEvidenceItems(selectedEmResult, selectedEvidenceResult);
}

function evidenceDedupKey(item) {
  return [
    item.workflow,
    item.text,
    item.reftxtbefore,
    item.reftxtafter,
    item.categoryKey ?? "",
    item.evidenceObjectName ?? "",
    item.finalCptCode ?? "",
    item.mainCode ?? "",
    item.characterLabel ?? "",
    item.codeCategoryLabel ?? "",
    Array.isArray(item.dataToReviewCategories) ? item.dataToReviewCategories.join(",") : "",
    Array.isArray(item.complexityEvidencePaths) ? item.complexityEvidencePaths.join(",") : "",
    item.pgNo ?? ""
  ].join("||");
}

function normalizeForContextMatch(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function escapeRegExp(value) {
  return String(value ?? "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function getOverlapLength(sourceValue, targetValue) {
  const source = String(sourceValue ?? "").toLowerCase();
  const target = String(targetValue ?? "").toLowerCase();
  const maxLength = Math.min(source.length, target.length);
  for (let length = maxLength; length > 0; length -= 1) {
    if (source.slice(-length) === target.slice(0, length)) {
      return length;
    }
  }
  return 0;
}

function getContextNeedleVariants(context, text, side) {
  const rawContext = String(context ?? "");
  const normalizedContext = normalizeForContextMatch(rawContext);
  const variants = new Set();
  if (normalizedContext) {
    variants.add(normalizedContext);
  }

  if (side === "before") {
    const overlapLength = getOverlapLength(rawContext, text);
    if (overlapLength > 0) {
      const trimmed = normalizeForContextMatch(rawContext.slice(0, rawContext.length - overlapLength));
      if (trimmed) {
        variants.add(trimmed);
      }
    }
  }

  if (side === "after") {
    const overlapLength = getOverlapLength(text, rawContext);
    if (overlapLength > 0) {
      const trimmed = normalizeForContextMatch(rawContext.slice(overlapLength));
      if (trimmed) {
        variants.add(trimmed);
      }
    }
  }

  const tokens = normalizedContext.split(" ").filter(Boolean);
  if (tokens.length >= 3) {
    if (side === "before") {
      variants.add(tokens.slice(Math.max(0, tokens.length - 4)).join(" "));
    } else {
      variants.add(tokens.slice(0, 4).join(" "));
    }
  }
  return Array.from(variants).filter((item) => item.length >= 3);
}

function contextWindowMatches(windowText, variants) {
  if (!variants.length) {
    return false;
  }
  return variants.some((variant) => windowText.includes(variant));
}

function findEvidenceRange(documentText, evidence, searchStart = 0) {
  const source = String(documentText ?? "");
  const text = String(evidence?.text ?? "").trim();
  if (!source || !text) {
    return null;
  }
  const fromIndex = Math.max(0, Number(searchStart) || 0);
  const before = String(evidence?.reftxtbefore ?? "");
  const after = String(evidence?.reftxtafter ?? "");

  // Only the side(s) with a non-empty context are required. Evidence at the very
  // start/end of a document (or section) legitimately has an empty before/after,
  // so requiring both would drop those highlights entirely.
  const beforeNeedleVariants = before.trim()
    ? getContextNeedleVariants(before, text, "before")
    : [];
  const afterNeedleVariants = after.trim()
    ? getContextNeedleVariants(after, text, "after")
    : [];
  const requireBefore = beforeNeedleVariants.length > 0;
  const requireAfter = afterNeedleVariants.length > 0;

  const textPattern = new RegExp(escapeRegExp(text), "gi");
  textPattern.lastIndex = fromIndex;
  let textMatch = textPattern.exec(source);
  while (textMatch) {
    const matchedText = textMatch[0];
    const start = textMatch.index;
    const end = start + matchedText.length;

    const contextPadding = Math.max(before.length * 6, after.length * 6, 220);
    const beforeWindow = normalizeForContextMatch(
      source.slice(Math.max(0, start - contextPadding), start)
    );
    const afterWindow = normalizeForContextMatch(
      source.slice(end, Math.min(source.length, end + contextPadding))
    );

    const beforeMatches = !requireBefore || contextWindowMatches(beforeWindow, beforeNeedleVariants);
    const afterMatches = !requireAfter || contextWindowMatches(afterWindow, afterNeedleVariants);
    if (beforeMatches && afterMatches) {
      return { start, end };
    }
    textMatch = textPattern.exec(source);
  }

  return null;
}

function hasOverlap(start, end, ranges) {
  return ranges.some((range) => start < range.end && end > range.start);
}

function buildEvidenceHighlights(documentText, evidenceItems) {
  const source = String(documentText ?? "");
  if (!source || !Array.isArray(evidenceItems) || evidenceItems.length === 0) {
    return [];
  }

  const dedupedByKey = new Map();
  evidenceItems.forEach((item) => {
    if (!item?.text) {
      return;
    }
    dedupedByKey.set(evidenceDedupKey(item), item);
  });

  const sortedCandidates = Array.from(dedupedByKey.values()).sort((left, right) => {
    const leftContextScore = Number(Boolean(left.reftxtbefore)) + Number(Boolean(left.reftxtafter));
    const rightContextScore = Number(Boolean(right.reftxtbefore)) + Number(Boolean(right.reftxtafter));
    if (leftContextScore !== rightContextScore) {
      return rightContextScore - leftContextScore;
    }
    const lengthDelta = String(right.text).length - String(left.text).length;
    if (lengthDelta !== 0) {
      return lengthDelta;
    }
    return String(left.text).localeCompare(String(right.text));
  });

  const acceptedRanges = [];
  const rangeMap = new Map();

  sortedCandidates.forEach((item) => {
    let searchStart = 0;
    while (searchStart < source.length) {
      const found = findEvidenceRange(source, item, searchStart);
      if (!found) {
        break;
      }

      if (!hasOverlap(found.start, found.end, acceptedRanges)) {
        const key = `${found.start}:${found.end}`;
        const existing = rangeMap.get(key);
        if (existing) {
          existing.evidenceItems.push(item);
        } else {
          const nextRange = { start: found.start, end: found.end, evidenceItems: [item] };
          acceptedRanges.push(nextRange);
          rangeMap.set(key, nextRange);
        }
        break;
      }
      searchStart = found.start + 1;
    }
  });

  return acceptedRanges.sort((left, right) => left.start - right.start);
}

function getDocumentParagraphRanges(rawText) {
  const text = String(rawText ?? "");
  if (!text.trim()) {
    return [];
  }

  const newlineMatches = Array.from(text.matchAll(/\n+/g));
  if (newlineMatches.length > 0) {
    let cursor = 0;
    const byNewline = [];
    newlineMatches.forEach((match) => {
      const newlineStart = match.index ?? 0;
      if (newlineStart > cursor) {
        const chunk = text.slice(cursor, newlineStart);
        if (chunk.trim()) {
          byNewline.push({ start: cursor, end: newlineStart });
        }
      }
      cursor = newlineStart + match[0].length;
    });
    if (cursor < text.length) {
      const tail = text.slice(cursor);
      if (tail.trim()) {
        byNewline.push({ start: cursor, end: text.length });
      }
    }
    if (byNewline.length > 1) {
      return byNewline;
    }
  }

  const sentenceMatches = Array.from(text.matchAll(/[^.!?]+[.!?]+|[^.!?]+$/g));
  if (sentenceMatches.length === 0) {
    return [{ start: 0, end: text.length }];
  }

  const groupedRanges = [];
  for (let index = 0; index < sentenceMatches.length; index += 2) {
    const first = sentenceMatches[index];
    const second = sentenceMatches[index + 1];
    const start = first.index ?? 0;
    const end = second
      ? (second.index ?? 0) + second[0].length
      : (first.index ?? 0) + first[0].length;
    const chunk = text.slice(start, end);
    if (chunk.trim()) {
      groupedRanges.push({ start, end });
    }
  }

  return groupedRanges.length > 0 ? groupedRanges : [{ start: 0, end: text.length }];
}

function tooltipTitleForWorkflow(workflow) {
  if (workflow === "cpt") {
    return "CPT Evidence";
  }
  if (workflow === "pcs") {
    return "PCS Evidence";
  }
  return "E&M Evidence";
}

function EvidenceTooltipRow({ label, value, useCodeStyle = false }) {
  if (!String(value ?? "").trim()) {
    return null;
  }
  return (
    <div className="evidence-tooltip-row">
      <span className="evidence-tooltip-label">{label}</span>
      <span className={useCodeStyle ? "evidence-tooltip-value evidence-tooltip-code" : "evidence-tooltip-value"}>
        {String(value)}
      </span>
    </div>
  );
}

function EvidenceTooltipContent({ evidenceItems, className = "", style = undefined }) {
  if (!Array.isArray(evidenceItems) || evidenceItems.length === 0) {
    return null;
  }

  const title = tooltipTitleForWorkflow(evidenceItems[0]?.workflow);
  const workflow = evidenceItems[0]?.workflow;
  const pcsCategoryBadgeLabel =
    workflow === "pcs"
      ? Array.from(
          new Set(
            evidenceItems.map((item) => String(item.codeCategoryLabel ?? "").trim()).filter(Boolean)
          )
        ).join(" / ")
      : "";
  const pcsCategoryBadgeTone =
    pcsCategoryBadgeLabel.toLowerCase() === "billable"
      ? "billable"
      : pcsCategoryBadgeLabel.toLowerCase() === "non-billable"
        ? "nonbillable"
        : "neutral";
  return (
    <span className={`evidence-tooltip ${className}`.trim()} style={style} role="tooltip">
      <span className="evidence-tooltip-title-row">
        <span className="evidence-tooltip-title">{title}</span>
        {workflow === "pcs" && pcsCategoryBadgeLabel ? (
          <span className={`evidence-tooltip-badge evidence-tooltip-badge--${pcsCategoryBadgeTone}`}>
            {pcsCategoryBadgeLabel}
          </span>
        ) : null}
      </span>
      {evidenceItems.map((item, index) => {
        const shouldShowMdm = item.workflow === "em" && EM_MDM_EVIDENCE_KEYS.has(item.categoryKey);
        return (
          <span className="evidence-tooltip-block" key={`${item.workflow}-${item.text}-${index}`}>
            {item.workflow === "em" ? (
              <>
                {shouldShowMdm ? (
                  <EvidenceTooltipRow label="MDM Element" value={item.mdmElementLabel} />
                ) : (
                  <EvidenceTooltipRow label="Category" value={item.categoryLabel} />
                )}
                {shouldShowMdm ? (
                  <EvidenceTooltipRow
                    label="Element Type"
                    value={toTitleCaseWords(item.mdmSubcategoryClass)}
                  />
                ) : null}
                {item.categoryKey === "data_to_review" ? (
                  <EvidenceTooltipRow
                    label="Category"
                    value={Array.isArray(item.dataToReviewCategories) ? item.dataToReviewCategories.join(", ") : ""}
                  />
                ) : null}
                {item.categoryKey === "complexity" ? (
                  <EvidenceTooltipRow
                    label="Disease Evidence Path"
                    value={Array.isArray(item.complexityEvidencePaths) ? item.complexityEvidencePaths.join(", ") : ""}
                  />
                ) : null}
                {item.categoryKey === "facility" ? (
                  <EvidenceTooltipRow label="Facility Type" value={item.emCategoryType} />
                ) : null}
                {item.categoryKey === "service" ? (
                  <EvidenceTooltipRow label="Service Type" value={item.emCategoryType} />
                ) : null}
                {item.categoryKey === "patient" ? (
                  <EvidenceTooltipRow label="Patient Type" value={item.emCategoryType} />
                ) : null}
                {item.categoryKey === "patient" ? (
                  <EvidenceTooltipRow label="Age" value={item.patientAgeDisplay} />
                ) : null}
                {item.categoryKey === "patient_age" ? (
                  <EvidenceTooltipRow label="Age" value={item.patientAgeDisplay} />
                ) : null}
                {item.categoryKey === "physician_time_spent_with_patient" ? (
                  <EvidenceTooltipRow label="Time (minutes)" value={item.emTimeInMinutes} />
                ) : null}
                {item.categoryKey === "staff_time_spent_with_patient" ? (
                  <EvidenceTooltipRow label="Time (minutes)" value={item.emTimeInMinutes} />
                ) : null}
              </>
            ) : null}

            {item.workflow === "cpt" ? (
              <>
                <EvidenceTooltipRow label="Code" value={item.finalCptCode} useCodeStyle />
                <EvidenceTooltipRow
                  label="Code Description"
                  value={item.finalCptCodeDescription}
                />
                <EvidenceTooltipRow label="Evidence Category" value={item.evidenceObjectLabel} />
              </>
            ) : null}

            {item.workflow === "pcs" ? (
              <>
                <EvidenceTooltipRow label="Code" value={item.mainCode} useCodeStyle />
                <EvidenceTooltipRow label="Procedure Name" value={item.procedureName} />
                <EvidenceTooltipRow label="Character" value={item.characterLabel} />
              </>
            ) : null}

          </span>
        );
      })}
    </span>
  );
}

function getTooltipPosition(anchorRect) {
  const viewportWidth = window.innerWidth || 1280;
  const viewportHeight = window.innerHeight || 720;
  const horizontalPadding = 12;
  const tooltipWidth = Math.min(320, Math.max(240, viewportWidth - horizontalPadding * 2));
  const preferredTop = anchorRect.top - 12;
  const hasSpaceAbove = preferredTop >= 190;
  const placement = hasSpaceAbove ? "top" : "bottom";
  const left = Math.min(
    viewportWidth - horizontalPadding - tooltipWidth / 2,
    Math.max(horizontalPadding + tooltipWidth / 2, anchorRect.left + anchorRect.width / 2)
  );
  const top = placement === "top" ? preferredTop : Math.min(viewportHeight - 12, anchorRect.bottom + 12);
  return { left, top, placement, width: tooltipWidth };
}

function resolveAnchorRect(targetElement, pointerPosition) {
  if (!targetElement) {
    return null;
  }
  const lineRects = Array.from(targetElement.getClientRects());
  if (lineRects.length === 0) {
    return targetElement.getBoundingClientRect();
  }
  if (!pointerPosition) {
    return lineRects[0];
  }

  // For wrapped inline highlights, choose the line rect nearest to cursor position.
  const byY = lineRects.filter(
    (rect) => pointerPosition.y >= rect.top - 2 && pointerPosition.y <= rect.bottom + 2
  );
  const candidates = byY.length > 0 ? byY : lineRects;
  return candidates.reduce((best, rect) => {
    const bestCenter = best.left + best.width / 2;
    const rectCenter = rect.left + rect.width / 2;
    return Math.abs(rectCenter - pointerPosition.x) < Math.abs(bestCenter - pointerPosition.x)
      ? rect
      : best;
  }, candidates[0]);
}

function EvidenceHighlightMark({ workflowName, highlightText, evidenceItems, tooltipKey }) {
  const markRef = useRef(null);
  const pointerRef = useRef(null);
  const [isTooltipOpen, setIsTooltipOpen] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({
    left: 0,
    top: 0,
    placement: "top",
    width: 320
  });

  useEffect(() => {
    if (!isTooltipOpen || !markRef.current) {
      return undefined;
    }

    const updatePosition = () => {
      if (!markRef.current) {
        return;
      }
      const anchorRect = resolveAnchorRect(markRef.current, pointerRef.current);
      if (!anchorRect) {
        return;
      }
      setTooltipPosition(getTooltipPosition(anchorRect));
    };

    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [isTooltipOpen, evidenceItems]);

  return (
    <mark
      ref={markRef}
      className={`evidence-highlight evidence-highlight--${workflowName}`}
      tabIndex={0}
      onMouseEnter={(event) => {
        pointerRef.current = { x: event.clientX, y: event.clientY };
        setIsTooltipOpen(true);
      }}
      onMouseMove={(event) => {
        pointerRef.current = { x: event.clientX, y: event.clientY };
      }}
      onMouseLeave={() => setIsTooltipOpen(false)}
      onFocus={() => setIsTooltipOpen(true)}
      onBlur={() => setIsTooltipOpen(false)}
    >
      {highlightText}
      {isTooltipOpen
        ? createPortal(
            <EvidenceTooltipContent
              evidenceItems={evidenceItems}
              className={`evidence-tooltip--${tooltipPosition.placement}`}
              style={{
                left: `${tooltipPosition.left}px`,
                top: `${tooltipPosition.top}px`,
                width: `${tooltipPosition.width}px`
              }}
            />,
            document.body,
            `tooltip-${tooltipKey}`
          )
        : null}
    </mark>
  );
}

function HighlightedDocumentText({ text, highlights, preserveRawNewlines = false }) {
  const source = String(text ?? "");
  if (!source.trim()) {
    return null;
  }

  const ranges = Array.isArray(highlights) ? highlights : [];
  if (ranges.length === 0) {
    if (preserveRawNewlines) {
      return <div className="document-text-prewrap">{source}</div>;
    }
    return formatDocumentParagraphs(source).map((paragraph, index) => (
      <p key={`paragraph-${index}`}>{paragraph}</p>
    ));
  }

  if (preserveRawNewlines) {
    const fragments = [];
    let cursor = 0;
    ranges.forEach((range, index) => {
      if (range.start > cursor) {
        fragments.push(<span key={`raw-plain-${cursor}`}>{source.slice(cursor, range.start)}</span>);
      }
      const workflowName = range.evidenceItems?.[0]?.workflow ?? "em";
      fragments.push(
        <EvidenceHighlightMark
          key={`raw-highlight-${range.start}-${index}`}
          workflowName={workflowName}
          highlightText={source.slice(range.start, range.end)}
          evidenceItems={range.evidenceItems}
          tooltipKey={`raw-${range.start}-${index}`}
        />
      );
      cursor = range.end;
    });
    if (cursor < source.length) {
      fragments.push(<span key={`raw-tail-${cursor}`}>{source.slice(cursor)}</span>);
    }
    return <div className="document-text-prewrap">{fragments}</div>;
  }

  const paragraphRanges = getDocumentParagraphRanges(source);
  return paragraphRanges.map((paragraphRange, paragraphIndex) => {
    const clippedHighlights = ranges
      .filter((range) => range.end > paragraphRange.start && range.start < paragraphRange.end)
      .map((range) => ({
        ...range,
        start: Math.max(range.start, paragraphRange.start),
        end: Math.min(range.end, paragraphRange.end)
      }))
      .filter((range) => range.start < range.end)
      .sort((left, right) => left.start - right.start);

    const fragments = [];
    let cursor = paragraphRange.start;

    clippedHighlights.forEach((range, index) => {
      if (range.start > cursor) {
        fragments.push(
          <span key={`plain-${paragraphIndex}-${cursor}`}>{source.slice(cursor, range.start)}</span>
        );
      }

      const workflowName = range.evidenceItems?.[0]?.workflow ?? "em";
      fragments.push(
        <EvidenceHighlightMark
          key={`highlight-${paragraphIndex}-${range.start}-${index}`}
          workflowName={workflowName}
          highlightText={source.slice(range.start, range.end)}
          evidenceItems={range.evidenceItems}
          tooltipKey={`${paragraphIndex}-${range.start}-${index}`}
        />
      );
      cursor = range.end;
    });

    if (cursor < paragraphRange.end) {
      fragments.push(
        <span key={`plain-tail-${paragraphIndex}-${cursor}`}>{source.slice(cursor, paragraphRange.end)}</span>
      );
    }

    return <p key={`highlighted-paragraph-${paragraphIndex}`}>{fragments}</p>;
  });
}

function parseTsvCodeDescriptions(text) {
  const map = new Map();
  for (const line of String(text ?? "").split(/\r?\n/)) {
    if (!line.trim()) {
      continue;
    }
    const tabIndex = line.indexOf("\t");
    if (tabIndex === -1) {
      continue;
    }
    const code = line.slice(0, tabIndex).trim();
    const description = line.slice(tabIndex + 1).trim();
    if (!code || code.toLowerCase() === "code") {
      continue;
    }
    map.set(code.toUpperCase(), description);
  }
  return map;
}

function parsePcsCodeDescriptions(text) {
  const map = new Map();
  for (const rawLine of String(text ?? "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }
    const spaceIndex = line.indexOf(" ");
    if (spaceIndex === -1) {
      continue;
    }
    const code = line.slice(0, spaceIndex).trim();
    const description = line.slice(spaceIndex + 1).trim();
    if (!code) {
      continue;
    }
    map.set(code.toUpperCase(), description);
  }
  return map;
}

// Lazily fetched + parsed code->description maps, cached for the session.
const CODE_DESCRIPTION_SOURCES = {
  em: { url: "/code_descriptions/EandM_Code_Descriptions.tsv", parse: parseTsvCodeDescriptions },
  pcs: { url: "/code_descriptions/icd10pcs_codes_2026.txt", parse: parsePcsCodeDescriptions }
};
const codeDescriptionCache = {};
const codeDescriptionPromises = {};

function loadCodeDescriptions(kind) {
  if (codeDescriptionCache[kind]) {
    return Promise.resolve(codeDescriptionCache[kind]);
  }
  if (!codeDescriptionPromises[kind]) {
    const source = CODE_DESCRIPTION_SOURCES[kind];
    if (!source) {
      return Promise.resolve(new Map());
    }
    codeDescriptionPromises[kind] = fetch(source.url)
      .then((response) => (response.ok ? response.text() : ""))
      .then((text) => {
        const map = source.parse(text);
        codeDescriptionCache[kind] = map;
        return map;
      })
      .catch(() => {
        const empty = new Map();
        codeDescriptionCache[kind] = empty;
        return empty;
      });
  }
  return codeDescriptionPromises[kind];
}

function useCodeDescriptions(kind) {
  const [descriptions, setDescriptions] = useState(() => (kind ? codeDescriptionCache[kind] : undefined));
  useEffect(() => {
    if (!kind) {
      return undefined;
    }
    if (codeDescriptionCache[kind]) {
      setDescriptions(codeDescriptionCache[kind]);
      return undefined;
    }
    let active = true;
    loadCodeDescriptions(kind).then((map) => {
      if (active) {
        setDescriptions(map);
      }
    });
    return () => {
      active = false;
    };
  }, [kind]);
  return descriptions;
}

function lookupCodeDescription(descriptions, code) {
  if (!descriptions || code === null || code === undefined) {
    return "";
  }
  return descriptions.get(String(code).trim().toUpperCase()) ?? "";
}

function KeyValueRow({ label, value, valueClassName = "", labelClassName = "" }) {
  const combinedValueClassName = valueClassName
    ? `result-value ${valueClassName}`
    : "result-value";
  const combinedLabelClassName = labelClassName
    ? `result-label ${labelClassName}`
    : "result-label";
  return (
    <div className="result-row">
      <span className={combinedLabelClassName}>{label}</span>
      <span className={combinedValueClassName}>{toDisplayValue(value)}</span>
    </div>
  );
}

function StructuredResultView({ result }) {
  const emDescriptions = useCodeDescriptions("em");
  if (!result || typeof result !== "object") {
    return (
      <div className="placeholder">
        Run E&M coding on a selected document to view results.
      </div>
    );
  }

  const filters = result.mapper_filters ?? {};
  const filterEntries = Object.entries(filters);
  const classification = result.classification ?? {};
  const codes = Array.isArray(result.codes) ? result.codes : [];

  return (
    <div className="result-grid">
      <section className="result-card full-width code-highlight-card">
        <h4>Final E&amp;M Codes</h4>
        {codes.length === 0 ? (
          <div className="result-empty">No final E&amp;M codes returned.</div>
        ) : (
          <div className="final-code-list">
            {codes.map((item, index) => {
              const codeValue =
                typeof item === "string" || typeof item === "number"
                  ? item
                  : item?.Code ?? item?.code ?? item?.CPT_Code ?? item?.cpt_code ?? "N/A";
              const description = lookupCodeDescription(emDescriptions, codeValue);
              return (
                <div className="final-code-item" key={`${codeValue}-${index}`}>
                  <span className="final-code-chip">{String(codeValue)}</span>
                  {description ? (
                    <span className="final-code-description">{description}</span>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="result-card full-width">
        <h4>MDM Criteria Selection Summary</h4>
        <div className="mdm-primary-flag">
          <span className="mdm-primary-label">MDM Level</span>
          <span className="mdm-primary-value">{toTitleCaseWords(classification.mdm_level)}</span>
        </div>

        <div className="mdm-criteria-block">
          <h5>Criteria Categories</h5>
          <div className="mdm-criteria-row">
            <span className="mdm-criteria-label">Complexity Category</span>
            <span className="mdm-criteria-value">{toTitleCaseWords(classification.complexity)}</span>
          </div>
          <div className="mdm-criteria-row">
            <span className="mdm-criteria-label">Data To Review Category</span>
            <span className="mdm-criteria-value">
              {toTitleCaseWords(classification.data_to_review)}
            </span>
          </div>
          <div className="mdm-criteria-row">
            <span className="mdm-criteria-label">Risk Category</span>
            <span className="mdm-criteria-value">{toTitleCaseWords(classification.risk)}</span>
          </div>
        </div>
      </section>

      <section className="result-card full-width">
        <h4>E&amp;M Relational Parameters</h4>
        {filterEntries.length === 0 ? (
          <div className="result-empty">No mapper filters returned.</div>
        ) : (
          filterEntries.map(([key, value]) => (
            <KeyValueRow
              key={key}
              label={FRIENDLY_MAPPER_LABELS[key] ?? key.replaceAll("_", " ")}
              value={value}
              valueClassName="relational-value"
            />
          ))
        )}
      </section>
    </div>
  );
}

function CptResultView({ result }) {
  if (!result || typeof result !== "object") {
    return (
      <div className="placeholder">
        Run CPT coding on a selected document to view results.
      </div>
    );
  }

  const auditedCodes = Array.isArray(result.audited_codes) ? result.audited_codes : [];
  if (auditedCodes.length === 0) {
    return <div className="result-empty">No audited CPT codes returned.</div>;
  }

  return (
    <div className="result-grid">
      {auditedCodes.map((item, index) => {
        const finalCode = item?.final_cpt_code ?? "N/A";
        const description = item?.final_cpt_code_description ?? "N/A";
        const justification = item?.final_cpt_code_justification ?? "N/A";
        return (
          <section className="result-card full-width cpt-result-card" key={`${finalCode}-${index}`}>
            <div className="result-row">
              <span className="result-label cpt-result-label">CPT Code</span>
              <span className="result-value">
                <span className="final-code-chip">{String(finalCode)}</span>
              </span>
            </div>
            <div style={{ marginTop: "12px" }}>
              <KeyValueRow
                label="CPT Code Description"
                value={description}
                labelClassName="cpt-result-label"
              />
              <KeyValueRow
                label="CPT Code Justification"
                value={justification}
                labelClassName="cpt-result-label"
              />
            </div>
          </section>
        );
      })}
    </div>
  );
}

function PcsResultView({ result }) {
  const pcsDescriptions = useCodeDescriptions("pcs");
  if (!result || typeof result !== "object") {
    return (
      <div className="placeholder">
        Run PCS coding on a selected document to view results.
      </div>
    );
  }

  const source = Array.isArray(result.results)
    ? result.results[0]?.pcs_code_detection_output ?? {}
    : result?.pcs_code_detection_output ?? result;
  const billable = Array.isArray(source.billable) ? source.billable : [];
  const nonBillable = Array.isArray(source.non_billable) ? source.non_billable : [];

  if (billable.length === 0 && nonBillable.length === 0) {
    return <div className="result-empty">No PCS codes returned.</div>;
  }

  return (
    <div className="result-grid">
      <section className="result-card full-width pcs-result-card">
        <h4>Billable Codes</h4>
        {billable.length === 0 ? (
          <div className="result-empty">No billable PCS codes.</div>
        ) : (
          billable.map((item, index) => {
            const description = lookupCodeDescription(pcsDescriptions, item?.code);
            return (
              <div className="pcs-result-row" key={`billable-${item?.code ?? "na"}-${index}`}>
                <span className="final-code-chip">{String(item?.code ?? "N/A")}</span>
                {description ? <span className="pcs-procedure-name">{description}</span> : null}
              </div>
            );
          })
        )}
      </section>

      <section className="result-card full-width pcs-result-card">
        <h4>Non-Billable Codes</h4>
        {nonBillable.length === 0 ? (
          <div className="result-empty">No non-billable PCS codes.</div>
        ) : (
          nonBillable.map((item, index) => {
            const description = lookupCodeDescription(pcsDescriptions, item?.code);
            return (
              <div className="pcs-result-row" key={`nonbillable-${item?.code ?? "na"}-${index}`}>
                <span className="final-code-chip">{String(item?.code ?? "N/A")}</span>
                {description ? <span className="pcs-procedure-name">{description}</span> : null}
              </div>
            );
          })
        )}
      </section>
    </div>
  );
}

export default function App() {
  const [formData, setFormData] = useState(initialForm);
  const [workflowInputState, setWorkflowInputState] = useState({
    em: createEmptyWorkflowInputState(),
    cpt: createEmptyWorkflowInputState(),
    pcs: createEmptyWorkflowInputState()
  });
  const [workflowViewState, setWorkflowViewState] = useState({
    em: createEmptyWorkflowViewState(),
    cpt: createEmptyWorkflowViewState(),
    pcs: createEmptyWorkflowViewState()
  });
  const [documents, setDocuments] = useState([]);
  const [selectedDocIndex, setSelectedDocIndex] = useState(null);
  const [resultsByDocument, setResultsByDocument] = useState({});
  const [codingErrorsByDocument, setCodingErrorsByDocument] = useState({});
  const [generateError, setGenerateError] = useState("");
  const [infoNotice, setInfoNotice] = useState("");
  const [isGeneratingByWorkflow, setIsGeneratingByWorkflow] = useState({
    em: false,
    cpt: false,
    pcs: false
  });
  const [isEmCoding, setIsEmCoding] = useState(false);
  const [emCodingDocumentId, setEmCodingDocumentId] = useState(null);
  const [isCptCoding, setIsCptCoding] = useState(false);
  const [cptCodingDocumentId, setCptCodingDocumentId] = useState(null);
  const [isPcsCoding, setIsPcsCoding] = useState(false);
  const [pcsCodingDocumentId, setPcsCodingDocumentId] = useState(null);
  const [editingDocumentId, setEditingDocumentId] = useState(null);
  const [view, setView] = useState("workspace");
  const [selectedModel, setSelectedModel] = useState("");
  const [selectedThinkingBudget, setSelectedThinkingBudget] = useState("");
  const [modelOptions, setModelOptions] = useState([]);
  const [thinkingBudgetOptions, setThinkingBudgetOptions] = useState([]);

  useEffect(() => {
    let isMounted = true;
    loadModelDropdownConfig().then((config) => {
      if (!isMounted) return;
      setModelOptions(config.modelOptions);
      setThinkingBudgetOptions(config.thinkingBudgetOptions);
      setSelectedModel(config.defaultModel);
      setSelectedThinkingBudget(config.defaultThinkingBudget);
    });
    return () => {
      isMounted = false;
    };
  }, []);
  const currentWorkflowRef = useRef(formData.workflow);
  const workflowInputStateRef = useRef(workflowInputState);
  const workflowViewStateRef = useRef(workflowViewState);
  const activeViewStateRef = useRef(createEmptyWorkflowViewState());

  useEffect(() => {
    currentWorkflowRef.current = formData.workflow;
  }, [formData.workflow]);

  useEffect(() => {
    workflowInputStateRef.current = workflowInputState;
  }, [workflowInputState]);

  useEffect(() => {
    workflowViewStateRef.current = workflowViewState;
  }, [workflowViewState]);

  useEffect(() => {
    activeViewStateRef.current = {
      documents,
      selectedDocIndex,
      resultsByDocument,
      codingErrorsByDocument,
      editingDocumentId
    };
  }, [documents, selectedDocIndex, resultsByDocument, codingErrorsByDocument, editingDocumentId]);

  const selectedDocument = useMemo(() => {
    if (selectedDocIndex === null) {
      return null;
    }
    return documents[selectedDocIndex] ?? null;
  }, [documents, selectedDocIndex]);

  const selectedDocumentResult = useMemo(() => {
    if (!selectedDocument?.id) {
      return null;
    }
    return resultsByDocument[selectedDocument.id] ?? null;
  }, [resultsByDocument, selectedDocument]);

  const selectedEvidenceResult = selectedDocumentResult?.evidenceResult ?? null;
  const selectedEmResult = selectedDocumentResult?.emResult ?? null;
  const selectedCptResult = selectedDocumentResult?.cptResult ?? null;
  const selectedPcsResult = selectedDocumentResult?.pcsResult ?? null;
  const selectedLastRunPipeline = selectedDocumentResult?.lastRunPipeline ?? null;
  const selectedCodingError = selectedDocument?.id
    ? codingErrorsByDocument[selectedDocument.id] ?? ""
    : "";
  const isEmCodingSelectedDocument =
    isEmCoding && Boolean(selectedDocument?.id) && selectedDocument.id === emCodingDocumentId;
  const isCptCodingSelectedDocument =
    isCptCoding && Boolean(selectedDocument?.id) && selectedDocument.id === cptCodingDocumentId;
  const isPcsCodingSelectedDocument =
    isPcsCoding && Boolean(selectedDocument?.id) && selectedDocument.id === pcsCodingDocumentId;
  const isCustomSelectedDocument = Boolean(selectedDocument?.isCustom);
  const isEditingSelectedDocument =
    Boolean(selectedDocument?.id) && selectedDocument.id === editingDocumentId;
  const selectedDocumentHasText = Boolean(String(selectedDocument?.generated_document ?? "").trim());
  const selectedDocumentWorkflow = normalizeWorkflow(selectedDocument?.workflow);
  const selectedEvidenceItems = useMemo(
    () =>
      extractSelectedEvidenceItems({
        selectedLastRunPipeline,
        selectedDocumentWorkflow,
        selectedEvidenceResult,
        selectedEmResult,
        selectedCptResult,
        selectedPcsResult
      }),
    [
      selectedLastRunPipeline,
      selectedDocumentWorkflow,
      selectedEvidenceResult,
      selectedEmResult,
      selectedCptResult,
      selectedPcsResult
    ]
  );
  const selectedEvidenceHighlights = useMemo(
    () => buildEvidenceHighlights(selectedDocument?.generated_document, selectedEvidenceItems),
    [selectedDocument?.generated_document, selectedEvidenceItems]
  );
  const activeCategories = CATEGORY_OPTIONS_BY_WORKFLOW[formData.workflow] ?? [];
  const showCategorySelection = formData.workflow !== "em";
  const codePlaceholder =
    formData.workflow === "pcs"
      ? "01N50ZZ, 03BY0ZZ"
      : "99213, 99214 or 99201-99215";
  const isGeneratingCurrentWorkflow = isGeneratingByWorkflow[formData.workflow] ?? false;

  function getWorkflowSnapshot(targetWorkflow) {
    const normalizedTarget = normalizeWorkflow(targetWorkflow);
    if (currentWorkflowRef.current === normalizedTarget) {
      return activeViewStateRef.current;
    }
    return workflowViewStateRef.current[normalizedTarget] ?? createEmptyWorkflowViewState();
  }

  function updateActiveWorkflowInputs(updater) {
    const activeWorkflow = currentWorkflowRef.current;
    setWorkflowInputState((prev) => {
      const currentInputs = prev[activeWorkflow] ?? createEmptyWorkflowInputState();
      const nextInputs =
        typeof updater === "function" ? updater(currentInputs) : { ...currentInputs, ...updater };
      setFormData((prevForm) => ({
        ...prevForm,
        ...nextInputs
      }));
      return {
        ...prev,
        [activeWorkflow]: nextInputs
      };
    });
  }

  function writeWorkflowSnapshot(targetWorkflow, nextSnapshot) {
    const normalizedTarget = normalizeWorkflow(targetWorkflow);
    setWorkflowViewState((prev) => ({
      ...prev,
      [normalizedTarget]: nextSnapshot
    }));

    if (currentWorkflowRef.current !== normalizedTarget) {
      return;
    }

    setDocuments(nextSnapshot.documents);
    setSelectedDocIndex(nextSnapshot.selectedDocIndex);
    setResultsByDocument(nextSnapshot.resultsByDocument);
    setCodingErrorsByDocument(nextSnapshot.codingErrorsByDocument);
    setEditingDocumentId(nextSnapshot.editingDocumentId);
  }

  async function handleGenerateDocuments() {
    const targetWorkflow = formData.workflow;
    setGenerateError("");
    setInfoNotice("");
    setResultsByDocument({});
    setCodingErrorsByDocument({});
    setEmCodingDocumentId(null);
    setCptCodingDocumentId(null);
    setPcsCodingDocumentId(null);
    setEditingDocumentId(null);

    const codes = parseCodeInput(formData.codeInput);
    if (codes.length === 0) {
      setGenerateError("Enter at least one code.");
      return;
    }
    if (!/^\d+$/.test(formData.numDocs) || Number(formData.numDocs) < 1) {
      setGenerateError("Number of documents must be a positive integer.");
      return;
    }
    if (formData.workflow === "cpt" && formData.categories.length === 0) {
      setGenerateError("Select at least one CPT category before generating documents.");
      return;
    }
    if (formData.workflow === "pcs" && formData.categories.length === 0) {
      setGenerateError("Select at least one PCS category before generating documents.");
      return;
    }
    if (formData.workflow === "pcs" && codes.some((code) => code.includes("-"))) {
      setGenerateError("PCS supports single codes or comma-separated codes only.");
      return;
    }

    setIsGeneratingByWorkflow((prev) => ({
      ...prev,
      [targetWorkflow]: true
    }));
    try {
      let nextDocuments = [];
      if (formData.workflow === "pcs") {
        const response = await fetch(`${API_BASE_URLS.pcs}/pcs/synthetic-data`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            categories: formData.categories,
            icd10_pcs_code: codes.join(","),
            total_no_of_documents: Number(formData.numDocs),
            ...buildModelOverrides(selectedModel, selectedThinkingBudget)
          })
        });

        if (!response.ok) {
          const errorBody = await response.text();
          throw new Error(errorBody || `PCS generate failed with status ${response.status}`);
        }
        const json = await response.json();
        nextDocuments = normalizePcsDocuments(json, formData.categories);
      } else if (formData.workflow === "cpt") {
        const response = await fetch(`${API_BASE_URLS.cptSynthetic}/generate`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            code_category: formData.categories.join(", "),
            cptcode: codes.join(", "),
            total_no_of_documents: Number(formData.numDocs),
            ...buildModelOverrides(selectedModel, selectedThinkingBudget)
          })
        });

        if (!response.ok) {
          const errorBody = await response.text();
          throw new Error(errorBody || `Generate failed with status ${response.status}`);
        }
        const json = await response.json();
        const traceIdFromServer =
          response.headers.get("x-trace-id") ||
          `ui-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
        nextDocuments = normalizeSyntheticDocuments(
          json,
          formData.workflow,
          formData.categories,
          traceIdFromServer
        );
      } else {
        const response = await fetch(`${API_BASE_URLS.synthetic}/generate`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            EMcode: codes.join(", "),
            EMcodedescription: "",
            total_no_of_documents: Number(formData.numDocs),
            ...buildModelOverrides(selectedModel, selectedThinkingBudget)
          })
        });

        if (!response.ok) {
          const errorBody = await response.text();
          throw new Error(errorBody || `Generate failed with status ${response.status}`);
        }
        const json = await response.json();
        const traceIdFromServer =
          response.headers.get("x-trace-id") ||
          `ui-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
        nextDocuments = normalizeSyntheticDocuments(
          json,
          formData.workflow,
          formData.categories,
          traceIdFromServer
        );
      }

      if (nextDocuments.length === 0) {
        throw new Error("Generate response did not include a non-empty documents array.");
      }

      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        documents: nextDocuments,
        selectedDocIndex: 0,
        resultsByDocument: {},
        codingErrorsByDocument: {},
        editingDocumentId: null
      });
    } catch (error) {
      setGenerateError(`Failed to generate documents: ${error.message}`);
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        documents: [],
        selectedDocIndex: null,
        resultsByDocument: {},
        codingErrorsByDocument: {},
        editingDocumentId: null
      });
    } finally {
      setIsGeneratingByWorkflow((prev) => ({
        ...prev,
        [targetWorkflow]: false
      }));
    }
  }

  async function handleRunEmCoding() {
    if (!selectedDocument) {
      return;
    }

    const targetWorkflow = normalizeWorkflow(selectedDocument.workflow);
    const currentDocumentId = selectedDocument.id;
    {
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        codingErrorsByDocument: {
          ...snapshot.codingErrorsByDocument,
          [currentDocumentId]: ""
        }
      });
    }
    setInfoNotice("");
    setEmCodingDocumentId(currentDocumentId);
    setIsEmCoding(true);

    try {
      const traceId =
        selectedDocument.trace_id || `ui-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
      const documentId = selectedDocument.document_ref || selectedDocument.id || "selected-document";
      const evidencePayload = {
        documents: [
          {
            generated_document: selectedDocument.generated_document
          }
        ],
        ...buildModelOverrides(selectedModel, selectedThinkingBudget)
      };

      const notifyRetry = (attempt) =>
        setInfoNotice(
          `Model returned an invalid response. Retrying E&M coding (attempt ${attempt} of ${MODEL_CALL_RETRY_ATTEMPTS})...`
        );

      const evidenceResponse = await postJsonWithRetry(`${API_BASE_URLS.evidence}/predict`, {
        headers: {
          "Content-Type": "application/json",
          "X-Trace-Id": traceId,
          "X-Document-Id": documentId
        },
        body: JSON.stringify(evidencePayload),
        label: "Evidence generation",
        onRetry: notifyRetry
      });

      const evidenceJson = await evidenceResponse.json();
      const emResponse = await postJsonWithRetry(`${API_BASE_URLS.em}/resolve-predict`, {
        headers: {
          "Content-Type": "application/json",
          "X-Trace-Id": traceId,
          "X-Document-Id": documentId
        },
        body: JSON.stringify(evidenceJson),
        label: "E&M resolution",
        onRetry: notifyRetry
      });

      const emJson = await emResponse.json();
      setInfoNotice("");
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        resultsByDocument: {
          ...snapshot.resultsByDocument,
          [currentDocumentId]: {
            ...(snapshot.resultsByDocument[currentDocumentId] ?? {}),
            evidenceResult: evidenceJson,
            emResult: emJson,
            lastRunPipeline: "em"
          }
        }
      });
    } catch (error) {
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        codingErrorsByDocument: {
          ...snapshot.codingErrorsByDocument,
          [currentDocumentId]: `Failed to run E&M coding: ${error.message}`
        }
      });
    } finally {
      setIsEmCoding(false);
      setEmCodingDocumentId(null);
    }
  }

  async function handleRunCptCoding() {
    if (!selectedDocument) {
      return;
    }

    const targetWorkflow = normalizeWorkflow(selectedDocument.workflow);
    const currentDocumentId = selectedDocument.id;
    {
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        codingErrorsByDocument: {
          ...snapshot.codingErrorsByDocument,
          [currentDocumentId]: ""
        }
      });
    }
    setInfoNotice("");
    setCptCodingDocumentId(currentDocumentId);
    setIsCptCoding(true);

    try {
      const cptResponse = await postJsonWithRetry(`${API_BASE_URLS.cpt}/audit-cpt-codes`, {
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          text: selectedDocument.generated_document,
          ...buildModelOverrides(selectedModel, selectedThinkingBudget)
        }),
        label: "CPT coding",
        onRetry: (attempt) =>
          setInfoNotice(
            `Model returned an invalid response. Retrying CPT coding (attempt ${attempt} of ${MODEL_CALL_RETRY_ATTEMPTS})...`
          )
      });

      const cptJson = await cptResponse.json();
      setInfoNotice("");
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        resultsByDocument: {
          ...snapshot.resultsByDocument,
          [currentDocumentId]: {
            ...(snapshot.resultsByDocument[currentDocumentId] ?? {}),
            cptResult: cptJson,
            lastRunPipeline: "cpt"
          }
        }
      });
    } catch (error) {
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        codingErrorsByDocument: {
          ...snapshot.codingErrorsByDocument,
          [currentDocumentId]: `Failed to run CPT coding: ${error.message}`
        }
      });
    } finally {
      setIsCptCoding(false);
      setCptCodingDocumentId(null);
    }
  }

  async function handleRunPcsCoding() {
    if (!selectedDocument) {
      return;
    }

    const targetWorkflow = normalizeWorkflow(selectedDocument.workflow);
    const currentDocumentId = selectedDocument.id;
    {
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        codingErrorsByDocument: {
          ...snapshot.codingErrorsByDocument,
          [currentDocumentId]: ""
        }
      });
    }
    setInfoNotice("");
    setPcsCodingDocumentId(currentDocumentId);
    setIsPcsCoding(true);

    try {
      const payload = {
        documents: [
          {
            generated_document: selectedDocument.generated_document,
            icd10_pcs_code: selectedDocument.code,
            icd10_pcs_code_description: selectedDocument.code_description,
            rational: selectedDocument.rational
          }
        ],
        ...buildModelOverrides(selectedModel, selectedThinkingBudget)
      };
      const pcsResponse = await postJsonWithRetry(`${API_BASE_URLS.pcs}/pcs/code-detection`, {
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload),
        label: "PCS coding",
        onRetry: (attempt) =>
          setInfoNotice(
            `Model returned an invalid response. Retrying PCS coding (attempt ${attempt} of ${MODEL_CALL_RETRY_ATTEMPTS})...`
          )
      });

      const pcsJson = await pcsResponse.json();
      setInfoNotice("");
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        resultsByDocument: {
          ...snapshot.resultsByDocument,
          [currentDocumentId]: {
            ...(snapshot.resultsByDocument[currentDocumentId] ?? {}),
            pcsResult: pcsJson,
            lastRunPipeline: "pcs"
          }
        }
      });
    } catch (error) {
      const snapshot = getWorkflowSnapshot(targetWorkflow);
      writeWorkflowSnapshot(targetWorkflow, {
        ...snapshot,
        codingErrorsByDocument: {
          ...snapshot.codingErrorsByDocument,
          [currentDocumentId]: `Failed to run PCS coding: ${error.message}`
        }
      });
    } finally {
      setIsPcsCoding(false);
      setPcsCodingDocumentId(null);
    }
  }

  function setWorkflow(nextWorkflow) {
    if (nextWorkflow === formData.workflow) {
      return;
    }

    const currentWorkflow = formData.workflow;
    const currentInputSnapshot = {
      categories: formData.categories,
      codeInput: formData.codeInput,
      numDocs: formData.numDocs
    };
    const restoreInputSnapshot =
      workflowInputStateRef.current[nextWorkflow] ?? createEmptyWorkflowInputState();
    const currentSnapshot = activeViewStateRef.current;
    const restoreSnapshot =
      workflowViewStateRef.current[nextWorkflow] ?? createEmptyWorkflowViewState();

    setWorkflowInputState((prev) => ({
      ...prev,
      [currentWorkflow]: currentInputSnapshot
    }));
    setWorkflowViewState((prev) => ({
      ...prev,
      [currentWorkflow]: currentSnapshot
    }));

    setDocuments(restoreSnapshot.documents);
    setSelectedDocIndex(restoreSnapshot.selectedDocIndex);
    setResultsByDocument(restoreSnapshot.resultsByDocument);
    setCodingErrorsByDocument(restoreSnapshot.codingErrorsByDocument);
    setEditingDocumentId(restoreSnapshot.editingDocumentId);

    setFormData((prev) => ({
      ...prev,
      workflow: nextWorkflow,
      categories: restoreInputSnapshot.categories,
      codeInput: restoreInputSnapshot.codeInput,
      numDocs: restoreInputSnapshot.numDocs
    }));
    setGenerateError("");
    setInfoNotice("");
  }

  function toggleCategorySelection(option) {
    updateActiveWorkflowInputs((currentInputs) => {
      const alreadySelected = currentInputs.categories.includes(option);
      const nextCategories = alreadySelected
        ? currentInputs.categories.filter((item) => item !== option)
        : [...currentInputs.categories, option];
      return {
        ...currentInputs,
        categories: nextCategories
      };
    });
  }

  function handleAddCustomDocument() {
    const newCustomDocument = createCustomDocument(formData.workflow);
    const nextDocuments = [...documents, newCustomDocument];
    setDocuments(nextDocuments);
    setSelectedDocIndex(nextDocuments.length - 1);
    setEditingDocumentId(newCustomDocument.id);
  }

  function handleSelectedDocumentTextChange(nextValue) {
    if (selectedDocIndex === null) {
      return;
    }
    setDocuments((prev) =>
      prev.map((document, index) =>
        index === selectedDocIndex ? { ...document, generated_document: nextValue } : document
      )
    );
  }

  function toggleSelectedDocumentEditor() {
    if (!selectedDocument) {
      return;
    }
    setEditingDocumentId((prev) => (prev === selectedDocument.id ? null : selectedDocument.id));
  }

  const canGenerate = !isGeneratingCurrentWorkflow;
  const canRunEmCoding =
    Boolean(selectedDocument) &&
    selectedDocumentHasText &&
    !isGeneratingCurrentWorkflow &&
    !isEmCoding &&
    selectedDocumentWorkflow === "em";
  const canRunCptCoding =
    Boolean(selectedDocument) &&
    selectedDocumentHasText &&
    !isGeneratingCurrentWorkflow &&
    !isCptCoding &&
    selectedDocumentWorkflow === "cpt";
  const canRunPcsCoding =
    Boolean(selectedDocument) &&
    selectedDocumentHasText &&
    !isGeneratingCurrentWorkflow &&
    !isPcsCoding &&
    selectedDocumentWorkflow === "pcs";
  const shouldShowEmCodingButton = Boolean(selectedDocument) && selectedDocumentWorkflow === "em";
  const shouldShowCptCodingButton = Boolean(selectedDocument) && selectedDocumentWorkflow === "cpt";
  const shouldShowPcsCodingButton = Boolean(selectedDocument) && selectedDocumentWorkflow === "pcs";
  const canDownloadEvidence = Boolean(selectedEvidenceResult);
  const canDownloadEm = Boolean(selectedEmResult);
  const canDownloadCpt = Boolean(selectedCptResult);
  const canDownloadPcs = Boolean(selectedPcsResult);
  const shouldShowEmDownloadButtons = Boolean(selectedDocument) && selectedDocumentWorkflow === "em";
  const shouldShowCptDownloadButton = Boolean(selectedDocument) && selectedDocumentWorkflow === "cpt";
  const shouldShowPcsDownloadButton = Boolean(selectedDocument) && selectedDocumentWorkflow === "pcs";

  const activeResultPipeline = isPcsCodingSelectedDocument
    ? "pcs"
    : isCptCodingSelectedDocument
      ? "cpt"
      : isEmCodingSelectedDocument
        ? "em"
        : selectedLastRunPipeline ?? selectedDocumentWorkflow;
  const shouldShowLoadingSkeleton =
    (activeResultPipeline === "pcs" && isPcsCodingSelectedDocument && !selectedPcsResult) ||
    (activeResultPipeline === "cpt" && isCptCodingSelectedDocument && !selectedCptResult) ||
    (activeResultPipeline === "em" && isEmCodingSelectedDocument && !selectedEmResult);

  const hasResolvedResultContext =
    isGeneratingCurrentWorkflow ||
    Boolean(selectedDocument) ||
    selectedLastRunPipeline === "em" ||
    selectedLastRunPipeline === "cpt" ||
    selectedLastRunPipeline === "pcs";
  const resultPanelPipeline = hasResolvedResultContext
    ? isGeneratingCurrentWorkflow
      ? formData.workflow
      : activeResultPipeline
    : null;
  const resultTitle =
    resultPanelPipeline === "pcs"
      ? "PCS Coding Result"
      : resultPanelPipeline === "cpt"
        ? "CPT Coding Result"
        : resultPanelPipeline === "em"
          ? "E&M Resolution Result"
          : "Coding Result";

  if (view === "workbench") {
    return <DomainWorkbench onBack={() => setView("workspace")} />;
  }

  return (
    <div className="app-shell">
      <header className="top-panel">
        <div className="brand-bar">
          <img className="brand-logo" src={raapidLogo} alt="Raapid logo" />
          <div className="brand-text">
            <h1>{TOOL_NAME}</h1>
            <p>{TOOL_SUBTITLE}</p>
          </div>
          <button
            type="button"
            className="prompts-open-btn"
            onClick={() => setView("workbench")}
          >
            Domain Workbench
          </button>
        </div>

        <div className="workflow-layout">
          <div className="workflow-row">
            <label className="field workflow-selector">
              <div className="field-label-row">
                <span className="field-label">Coding Workflow</span>
              </div>
              <div className="workflow-button-group">
                {WORKFLOW_OPTIONS.map((option) => (
                  <button
                    type="button"
                    key={option.value}
                    className={formData.workflow === option.value ? "workflow-btn active" : "workflow-btn"}
                    aria-pressed={formData.workflow === option.value}
                    onClick={() => setWorkflow(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </label>

            <label className="field category-panel">
              <div className="field-label-row">
                <span className="field-label">Category</span>
                {showCategorySelection ? (
                  <span className="field-hint">Click one or more categories to select.</span>
                ) : null}
              </div>
              {showCategorySelection ? (
                <div className={`category-chip-grid ${formData.workflow === "pcs" ? "large" : ""}`}>
                  {activeCategories.map((option) => (
                    <button
                      type="button"
                      key={option}
                      className={
                        formData.categories.includes(option) ? "category-chip active" : "category-chip"
                      }
                      aria-pressed={formData.categories.includes(option)}
                      onClick={() => toggleCategorySelection(option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="placeholder">No category selection needed for E&M workflow.</div>
              )}
            </label>
          </div>

          <div className="code-count-row">
            <label className="field code-field">
              <div className="field-label-row">
                <span className="field-label">Codes</span>
              </div>
              <textarea
                className="code-textarea"
                value={formData.codeInput}
                onChange={(event) =>
                  updateActiveWorkflowInputs((currentInputs) => ({
                    ...currentInputs,
                    codeInput: event.target.value
                  }))
                }
                placeholder={codePlaceholder}
                rows={1}
              />
            </label>

            <label className="field count-field">
              <div className="field-label-row">
                <span className="field-label">Number of Documents</span>
              </div>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                value={formData.numDocs}
                onKeyDown={(event) => {
                  const allowedControlKeys = new Set([
                    "Backspace",
                    "Delete",
                    "ArrowLeft",
                    "ArrowRight",
                    "Tab",
                    "Home",
                    "End"
                  ]);
                  if (allowedControlKeys.has(event.key)) {
                    return;
                  }
                  if (!/^\d$/.test(event.key)) {
                    event.preventDefault();
                  }
                }}
                onPaste={(event) => {
                  const pastedText = event.clipboardData.getData("text");
                  if (!/^\d+$/.test(pastedText)) {
                    event.preventDefault();
                  }
                }}
                onChange={(event) => {
                  const onlyDigits = event.target.value.replace(/\D/g, "");
                  updateActiveWorkflowInputs((currentInputs) => ({
                    ...currentInputs,
                    numDocs: onlyDigits
                  }));
                }}
              />
            </label>

            <div className="actions-row">
              <button type="button" onClick={handleGenerateDocuments} disabled={!canGenerate}>
                {isGeneratingCurrentWorkflow ? (
                  <>
                    <span className="spinner" /> Generating...
                  </>
                ) : (
                  "Generate Documents"
                )}
              </button>
            </div>
          </div>
        </div>

        {generateError ? <div className="error-banner">{generateError}</div> : null}
        {infoNotice ? <div className="info-banner">{infoNotice}</div> : null}
      </header>

      <main className="bottom-panels">
        <aside className="documents-sidebar">
          <div className="documents-header">
            <h3>Documents</h3>
            <button type="button" className="add-doc-btn" onClick={handleAddCustomDocument}>
              + Add Document
            </button>
          </div>
          {isGeneratingCurrentWorkflow ? (
            <div className="skeleton-list">
              {Array.from({ length: 4 }).map((_, index) => (
                <div className="skeleton-item" key={`skeleton-${index}`} />
              ))}
            </div>
          ) : documents.length === 0 ? (
            <div className="empty-sidebar">No documents generated yet.</div>
          ) : (
            <ul>
              {documents.map((document, index) => (
                <li key={document.id}>
                  <button
                    type="button"
                    className={selectedDocIndex === index ? "doc-btn active" : "doc-btn"}
                    onClick={() => setSelectedDocIndex(index)}
                  >
                    <span className="doc-btn-content">
                      <span className="doc-label">{`Document ${index + 1}`}</span>
                      <div className="doc-meta-tags">
                        <span className="doc-workflow-tag">{document.workflowLabel}</span>
                        {!(normalizeWorkflow(document.workflow) === "em" && document.category === "E&M") ? (
                          <span className="doc-category-tag">{document.category || "Unmapped"}</span>
                        ) : null}
                        <span className="doc-code-tag">{document.code || "No Code"}</span>
                      </div>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="viewer-panel">
          <div className="viewer-header">
            <h3>Document Viewer</h3>
            <div className="viewer-actions">
              <label className="model-select-field">
                <span>Model</span>
                <select
                  value={selectedModel}
                  onChange={(event) => setSelectedModel(event.target.value)}
                >
                  {modelOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="model-select-field">
                <span>Thinking budget</span>
                <select
                  value={selectedThinkingBudget}
                  onChange={(event) => setSelectedThinkingBudget(event.target.value)}
                >
                  {thinkingBudgetOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              {selectedDocument ? (
                <button
                  type="button"
                  className="secondary-btn"
                  onClick={toggleSelectedDocumentEditor}
                >
                  {isEditingSelectedDocument ? "Preview Document" : "Edit Document"}
                </button>
              ) : null}

              {shouldShowEmCodingButton ? (
                <button type="button" onClick={handleRunEmCoding} disabled={!canRunEmCoding}>
                  {isEmCodingSelectedDocument ? (
                    <>
                      <span className="spinner" /> Running E&amp;M...
                    </>
                  ) : (
                    "Run E&M Coding"
                  )}
                </button>
              ) : null}
              {shouldShowCptCodingButton ? (
                <button type="button" onClick={handleRunCptCoding} disabled={!canRunCptCoding}>
                  {isCptCodingSelectedDocument ? (
                    <>
                      <span className="spinner" /> Running CPT...
                    </>
                  ) : (
                    "Run CPT Coding"
                  )}
                </button>
              ) : null}
              {shouldShowPcsCodingButton ? (
                <button type="button" onClick={handleRunPcsCoding} disabled={!canRunPcsCoding}>
                  {isPcsCodingSelectedDocument ? (
                    <>
                      <span className="spinner" /> Running PCS...
                    </>
                  ) : (
                    "Run PCS Coding"
                  )}
                </button>
              ) : null}

              {shouldShowEmDownloadButtons ? (
                <button
                  type="button"
                  className="secondary-btn"
                  disabled={!canDownloadEvidence}
                  onClick={() => {
                    if (!selectedEvidenceResult || selectedDocIndex === null) {
                      return;
                    }
                    downloadJson(
                      selectedEvidenceResult,
                      `em_evidence_document_${selectedDocIndex + 1}.json`
                    );
                  }}
                >
                  Download Evidence JSON
                </button>
              ) : null}
              {shouldShowEmDownloadButtons ? (
                <button
                  type="button"
                  className="secondary-btn"
                  disabled={!canDownloadEm}
                  onClick={() => {
                    if (!selectedEmResult || selectedDocIndex === null) {
                      return;
                    }
                    downloadJson(selectedEmResult, `em_result_document_${selectedDocIndex + 1}.json`);
                  }}
                >
                  Download E&M JSON
                </button>
              ) : null}
              {shouldShowCptDownloadButton ? (
                <button
                  type="button"
                  className="secondary-btn"
                  disabled={!canDownloadCpt}
                  onClick={() => {
                    if (!selectedCptResult || selectedDocIndex === null) {
                      return;
                    }
                    downloadJson(selectedCptResult, `cpt_result_document_${selectedDocIndex + 1}.json`);
                  }}
                >
                  Download CPT JSON
                </button>
              ) : null}
              {shouldShowPcsDownloadButton ? (
                <button
                  type="button"
                  className="secondary-btn"
                  disabled={!canDownloadPcs}
                  onClick={() => {
                    if (!selectedPcsResult || selectedDocIndex === null) {
                      return;
                    }
                    downloadJson(selectedPcsResult, `pcs_result_document_${selectedDocIndex + 1}.json`);
                  }}
                >
                  Download PCS JSON
                </button>
              ) : null}
            </div>
          </div>

          <div className="document-view">
            {!selectedDocument ? (
              <div className="placeholder">Select a generated document to view its content.</div>
            ) : isEditingSelectedDocument ? (
              <textarea
                className="document-editor-textarea"
                value={selectedDocument.generated_document}
                onChange={(event) => handleSelectedDocumentTextChange(event.target.value)}
                placeholder={
                  selectedDocument.isCustom
                    ? "Paste your document text here, then click a coding workflow button."
                    : "Edit generated document text here before running coding."
                }
              />
            ) : (
              <div className="document-prose">
                <HighlightedDocumentText
                  text={selectedDocument.generated_document}
                  highlights={selectedEvidenceHighlights}
                  preserveRawNewlines={
                    selectedDocumentWorkflow === "pcs" ||
                    /\r?\n/.test(selectedDocument.generated_document ?? "")
                  }
                />
              </div>
            )}
          </div>

          {selectedCodingError ? <div className="error-banner">{selectedCodingError}</div> : null}
          {selectedDocument && !selectedDocumentHasText ? (
            <div className="info-banner">
              Add document text in the editor to enable coding actions.
            </div>
          ) : null}

          <div className="result-sections">
            <section className="result-wrapper">
              <h3>{resultTitle}</h3>
              {isGeneratingCurrentWorkflow ? (
                <div className="placeholder">
                  Generating documents for {workflowLabel(formData.workflow)} workflow...
                </div>
              ) : shouldShowLoadingSkeleton ? (
                <div className="skeleton-card" />
              ) : resultPanelPipeline === "pcs" ? (
                <PcsResultView result={selectedPcsResult} />
              ) : resultPanelPipeline === "cpt" ? (
                <CptResultView result={selectedCptResult} />
              ) : (
                <StructuredResultView result={selectedEmResult} />
              )}
            </section>
          </div>
        </section>
      </main>
    </div>
  );
}
