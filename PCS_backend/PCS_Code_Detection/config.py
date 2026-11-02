import os

LLM_PROVIDER    = "gemini_vertex"    # "azure_openai" | "claude_vertex" | "openai"
MODEL_NAME      = os.getenv("PCS_MODEL_NAME", "gemini-2.5-pro")
PROJECT_ID      = os.getenv("VERTEX_PROJECT_ID", "raapid-genai")
LOCATION        = os.getenv("VERTEX_LOCATION", "global")
AZURE_ENDPOINT  = ""
AZURE_API_VER   = "2024-02-01"
MAX_CONCURRENCY = 20
RETRY_ATTEMPTS  = 5
TEMPERATURE     = 0.30
TOP_P           = 0.20
THINKING_BUDGET = None  # None = model default; overridden per-request

# LLM calling mode: on_demand only for now.
# Batch support (Claude Message Batches, OpenAI/Azure Batch, Vertex AI Batch Prediction)
# is planned for a future release — it requires a BFS-style traversal rewrite for Agent 2
# and provider-specific submit/poll implementations.
LLM_CALL_MODE   = "on_demand"
