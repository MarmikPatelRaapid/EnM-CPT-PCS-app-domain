// Model / thinking-budget dropdown choices, read from prompts.db via the
// prompts API rather than hardcoded here, so they can be managed centrally.
// Used wherever a Gemini call can be tuned (single-document coding and batch
// processing both use these).

const PROMPTS_API_BASE = "http://localhost:8087";

// Fallbacks only used if the DB is unreachable, so the UI still renders.
const FALLBACK_MODEL_OPTIONS = [
  { label: "Service default", value: "", is_default: false },
  { label: "Gemini 3.8 Flash", value: "gemini-3.8-flash", is_default: true }
];

const FALLBACK_THINKING_BUDGET_OPTIONS = [
  { label: "Service default", value: "", is_default: false },
  { label: "Low (1,024)", value: "1024", is_default: true }
];

let cachedPromise = null;

function fetchDropdownOptions() {
  if (!cachedPromise) {
    cachedPromise = fetch(`${PROMPTS_API_BASE}/dropdown-options`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((data) => ({
        modelOptions:
          Array.isArray(data.model_options) && data.model_options.length > 0
            ? data.model_options
            : FALLBACK_MODEL_OPTIONS,
        thinkingBudgetOptions:
          Array.isArray(data.thinking_budget_options) && data.thinking_budget_options.length > 0
            ? data.thinking_budget_options
            : FALLBACK_THINKING_BUDGET_OPTIONS
      }))
      .catch(() => ({
        modelOptions: FALLBACK_MODEL_OPTIONS,
        thinkingBudgetOptions: FALLBACK_THINKING_BUDGET_OPTIONS
      }));
  }
  return cachedPromise;
}

function pickDefaultValue(options) {
  const defaultOption = options.find((option) => option.is_default);
  return defaultOption ? defaultOption.value : "";
}

// Loads { modelOptions, thinkingBudgetOptions, defaultModel, defaultThinkingBudget }
// once from the DB; safe to call from multiple components, the network
// request itself only happens once.
export async function loadModelDropdownConfig() {
  const { modelOptions, thinkingBudgetOptions } = await fetchDropdownOptions();
  return {
    modelOptions,
    thinkingBudgetOptions,
    defaultModel: pickDefaultValue(modelOptions),
    defaultThinkingBudget: pickDefaultValue(thinkingBudgetOptions)
  };
}

// Builds the optional model_name / thinking_budget fields to merge into a
// request body or FormData payload. Omits a field entirely when left at
// "Service default" so the backend falls back to its own configured value.
export function buildModelOverrides(modelName, thinkingBudget) {
  const overrides = {};
  if (modelName) {
    overrides.model_name = modelName;
  }
  if (thinkingBudget !== "" && thinkingBudget !== undefined && thinkingBudget !== null) {
    overrides.thinking_budget = Number(thinkingBudget);
  }
  return overrides;
}
