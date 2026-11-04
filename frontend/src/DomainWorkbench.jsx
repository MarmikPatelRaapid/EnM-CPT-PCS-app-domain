import { useEffect, useMemo, useRef, useState } from "react";
import { loadModelDropdownConfig } from "./modelOptions.js";

// Relative paths, proxied by Vite (see frontend/vite.config.js) to each
// backend port server-side — works identically for local dev and for a
// remote deployment behind a load balancer, since the browser only ever
// talks to wherever the frontend itself is served from.
const PROMPTS_API_BASE = "/api/prompts-mgmt";
const BATCH_API_BASE = "/api/batch";
const POLL_INTERVAL_MS = 1200;
const ACTIVE_JOB_STATUSES = new Set(["queued", "running"]);

const DOMAINS = [
  { key: "overview", group: null, title: "Overview" },
  { key: "em", group: "E&M", title: "E&M" },
  { key: "cpt", group: "CPT", title: "CPT" },
  { key: "pcs", group: "PCS", title: "PCS" }
];

const SERVICE_CHECKS = [
  { label: "E&M synthetic generation", url: "/api/em-synth/docs" },
  { label: "E&M evidence extraction", url: "/api/evidence/docs" },
  { label: "E&M code resolver", url: "/api/em/docs" },
  { label: "CPT synthetic generation", url: "/api/cpt-synth/docs" },
  { label: "CPT retrieval", url: "/api/cpt-retrieval/docs" },
  { label: "CPT pipeline", url: "/api/cpt/docs" },
  { label: "PCS pipeline", url: "/api/pcs/docs" },
  { label: "Prompt & schema store", url: `${PROMPTS_API_BASE}/prompts` },
  { label: "Batch processor", url: `${BATCH_API_BASE}/batch/jobs/_` }
];

function formatTimestamp(value) {
  if (!value) {
    return "not yet saved";
  }
  try {
    return new Date(value).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch {
    return value;
  }
}

function Flag({ state, children }) {
  return <span className={`wb-flag wb-flag--${state}`}>{children}</span>;
}

function EditableEntry({ item, kind, onSaved }) {
  const [isOpen, setIsOpen] = useState(false);
  const [draft, setDraft] = useState(item.content);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [justSaved, setJustSaved] = useState(false);

  useEffect(() => {
    setDraft(item.content);
  }, [item.content]);

  const hasChanges = draft !== item.content;
  const endpoint = kind === "schema" ? "schemas" : "prompts";

  function handleSave() {
    if (kind === "schema") {
      try {
        JSON.parse(draft);
      } catch (err) {
        setError(`Not valid JSON: ${err.message}`);
        return;
      }
    }
    setIsSaving(true);
    setError("");
    fetch(
      `${PROMPTS_API_BASE}/${endpoint}/${encodeURIComponent(item.service)}/${encodeURIComponent(item.key)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: draft })
      }
    )
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || `Save failed (HTTP ${response.status})`);
        }
        return response.json();
      })
      .then((data) => {
        onSaved({ ...item, content: draft, updated_at: data.updated_at, length: draft.length });
        setJustSaved(true);
        setTimeout(() => setJustSaved(false), 2400);
      })
      .catch((err) => setError(err.message || "Save failed"))
      .finally(() => setIsSaving(false));
  }

  return (
    <div className="wb-entry">
      <button type="button" className="wb-entry-head" onClick={() => setIsOpen((v) => !v)}>
        <span className="wb-entry-caret" aria-hidden="true">
          {isOpen ? "v" : ">"}
        </span>
        <span className="wb-entry-label">{item.label}</span>
        <span className="wb-entry-meta">
          {item.content.length.toLocaleString()} chars, saved {formatTimestamp(item.updated_at)}
        </span>
      </button>

      {isOpen ? (
        <div className="wb-entry-body">
          <textarea
            className="wb-textarea"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            spellCheck={false}
            rows={kind === "schema" ? 14 : 16}
          />
          <div className="wb-entry-actions">
            <button
              type="button"
              className="wb-button wb-button--primary"
              onClick={handleSave}
              disabled={!hasChanges || isSaving || !draft.trim()}
            >
              {isSaving ? "Saving" : "Save"}
            </button>
            {hasChanges ? <Flag state="pending">Unsaved changes</Flag> : null}
            {justSaved ? <Flag state="normal">Saved</Flag> : null}
            {error ? <Flag state="abnormal">{error}</Flag> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function BatchRunner({ domainKey, domainTitle }) {
  const storageKey = `workbench.batch.${domainKey}.jobId`;
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [job, setJob] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [selectedThinkingBudget, setSelectedThinkingBudget] = useState("");
  const [modelOptions, setModelOptions] = useState([]);
  const [thinkingBudgetOptions, setThinkingBudgetOptions] = useState([]);
  const [isDragActive, setIsDragActive] = useState(false);
  const [history, setHistory] = useState([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [retryingJobId, setRetryingJobId] = useState(null);
  const [isStoppingJob, setIsStoppingJob] = useState(false);
  const dragDepthRef = useRef(0);
  const fileInputRef = useRef(null);
  const pollTimeoutRef = useRef(null);

  const isJobActive = job ? ACTIVE_JOB_STATUSES.has(job.status) : false;

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

  useEffect(() => {
    let storedJobId = "";
    try {
      storedJobId = localStorage.getItem(storageKey) || "";
    } catch {
      storedJobId = "";
    }
    if (storedJobId) {
      fetch(`${BATCH_API_BASE}/batch/jobs/${storedJobId}`)
        .then((response) => {
          if (!response.ok) throw new Error("not found");
          return response.json();
        })
        .then((data) => {
          setJob(data);
          if (ACTIVE_JOB_STATUSES.has(data.status)) {
            schedulePoll(storedJobId);
          }
        })
        .catch(() => {
          try {
            localStorage.removeItem(storageKey);
          } catch {
            /* ignore */
          }
        });
    }
    return () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function schedulePoll(jobId) {
    if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    pollTimeoutRef.current = setTimeout(() => pollJob(jobId), POLL_INTERVAL_MS);
  }

  function loadHistory() {
    setIsHistoryLoading(true);
    fetch(`${BATCH_API_BASE}/batch/jobs?workflow=${domainKey}&limit=20`)
      .then((response) => (response.ok ? response.json() : { jobs: [] }))
      .then((data) => setHistory(Array.isArray(data.jobs) ? data.jobs : []))
      .catch(() => {})
      .finally(() => setIsHistoryLoading(false));
  }

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function pollJob(jobId) {
    try {
      const response = await fetch(`${BATCH_API_BASE}/batch/jobs/${jobId}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setJob(data);
      if (ACTIVE_JOB_STATUSES.has(data.status)) {
        schedulePoll(jobId);
      } else {
        loadHistory();
      }
    } catch (error) {
      setSubmitError(error.message || "Lost contact with the batch processor.");
    }
  }

  function handleDownloadJob(jobId) {
    const link = document.createElement("a");
    link.href = `${BATCH_API_BASE}/batch/jobs/${jobId}/download`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  async function handleStopJob(jobId) {
    setIsStoppingJob(true);
    setSubmitError("");
    try {
      const response = await fetch(`${BATCH_API_BASE}/batch/jobs/${jobId}/cancel`, { method: "POST" });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${response.status}`);
      }
      await pollJob(jobId);
      loadHistory();
    } catch (error) {
      setSubmitError(error.message || "Failed to stop the run.");
    } finally {
      setIsStoppingJob(false);
    }
  }

  async function handleRetryJob(jobId) {
    setRetryingJobId(jobId);
    setSubmitError("");
    try {
      const response = await fetch(`${BATCH_API_BASE}/batch/jobs/${jobId}/retry`, { method: "POST" });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${response.status}`);
      }
      const data = await response.json();
      setJob({
        job_id: data.job_id,
        workflow: domainKey,
        status: "queued",
        total: data.total,
        completed: 0,
        failed: 0,
        files: []
      });
      try {
        localStorage.setItem(storageKey, data.job_id);
      } catch {
        /* ignore */
      }
      schedulePoll(data.job_id);
      loadHistory();
    } catch (error) {
      setSubmitError(error.message || "Failed to retry the failed files.");
    } finally {
      setRetryingJobId(null);
    }
  }

  function labelForModel(value) {
    if (!value) return "Service default";
    const match = modelOptions.find((option) => option.value === value);
    return match ? match.label : value;
  }

  function labelForWorkflow(value) {
    const labels = { em: "E&M", cpt: "CPT", pcs: "PCS" };
    return labels[value] || value;
  }

  function labelForThinkingBudget(value) {
    if (value === null || value === undefined || value === "") return "Service default";
    const match = thinkingBudgetOptions.find((option) => option.value === String(value));
    return match ? match.label : String(value);
  }

  function addFiles(fileList) {
    const incoming = Array.from(fileList ?? []).filter((file) =>
      file.name.toLowerCase().endsWith(".txt")
    );
    if (incoming.length === 0) return;
    setSelectedFiles((current) => {
      const existingNames = new Set(current.map((file) => `${file.name}:${file.size}`));
      const deduped = incoming.filter((file) => !existingNames.has(`${file.name}:${file.size}`));
      return [...current, ...deduped];
    });
  }

  function handleFilesSelected(event) {
    addFiles(event.target.files);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleDragEnter(event) {
    event.preventDefault();
    if (isJobActive || isSubmitting) return;
    dragDepthRef.current += 1;
    setIsDragActive(true);
  }

  function handleDragOver(event) {
    event.preventDefault();
  }

  function handleDragLeave(event) {
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setIsDragActive(false);
  }

  function handleDrop(event) {
    event.preventDefault();
    dragDepthRef.current = 0;
    setIsDragActive(false);
    if (isJobActive || isSubmitting) return;
    addFiles(event.dataTransfer?.files);
  }

  function handleRemoveFile(index) {
    setSelectedFiles((current) => current.filter((_, i) => i !== index));
  }

  async function handleRun() {
    if (selectedFiles.length === 0 || isSubmitting || isJobActive) return;
    setIsSubmitting(true);
    setSubmitError("");
    setJob(null);
    try {
      const formData = new FormData();
      formData.append("workflow", domainKey);
      for (const file of selectedFiles) formData.append("files", file, file.name);
      if (selectedModel) formData.append("model_name", selectedModel);
      if (selectedThinkingBudget !== "") formData.append("thinking_budget", selectedThinkingBudget);

      const response = await fetch(`${BATCH_API_BASE}/batch/jobs`, { method: "POST", body: formData });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Could not start the run (HTTP ${response.status})`);
      }
      const data = await response.json();
      setJob({
        job_id: data.job_id,
        workflow: domainKey,
        status: "queued",
        total: data.total,
        completed: 0,
        failed: 0,
        files: selectedFiles.map((file) => ({ name: file.name, status: "queued", summary: "", error: "" }))
      });
      try {
        localStorage.setItem(storageKey, data.job_id);
      } catch {
        /* ignore */
      }
      schedulePoll(data.job_id);
      loadHistory();
    } catch (error) {
      setSubmitError(error.message || "Could not start the run.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleDownload() {
    if (!job?.job_id) return;
    const link = document.createElement("a");
    link.href = `${BATCH_API_BASE}/batch/jobs/${job.job_id}/download`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  const progressPercent = job && job.total ? Math.round((job.completed / job.total) * 100) : 0;
  const hasCompletedResults = job ? job.files.some((f) => f.status === "done") : false;

  return (
    <div className="wb-batch">
      <div
        className={isDragActive ? "wb-dropzone wb-dropzone--active" : "wb-dropzone"}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => {
          if (!isJobActive && !isSubmitting) fileInputRef.current?.click();
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            if (!isJobActive && !isSubmitting) fileInputRef.current?.click();
          }
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".txt"
          onChange={handleFilesSelected}
          disabled={isJobActive || isSubmitting}
          className="wb-file-input"
          onClick={(event) => event.stopPropagation()}
        />
        <p className="wb-dropzone-hint">
          {isDragActive
            ? "Drop .txt files to add them"
            : "Drag .txt files here, or use Choose files"}
        </p>
      </div>

      {selectedFiles.length > 0 ? (
        <ul className="wb-file-chip-list">
          {selectedFiles.map((file, index) => (
            <li key={`${file.name}-${file.size}-${index}`} className="wb-file-chip">
              <span>{file.name}</span>
              <button
                type="button"
                className="wb-file-chip-remove"
                onClick={() => handleRemoveFile(index)}
                disabled={isJobActive || isSubmitting}
                aria-label={`Remove ${file.name}`}
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="wb-batch-controls">
        <label className="wb-model-field">
          Model
          <select
            value={selectedModel}
            onChange={(event) => setSelectedModel(event.target.value)}
            disabled={isJobActive || isSubmitting}
          >
            {modelOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="wb-model-field">
          Thinking budget
          <select
            value={selectedThinkingBudget}
            onChange={(event) => setSelectedThinkingBudget(event.target.value)}
            disabled={isJobActive || isSubmitting}
          >
            {thinkingBudgetOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="wb-button wb-button--primary"
          onClick={handleRun}
          disabled={selectedFiles.length === 0 || isSubmitting || isJobActive}
        >
          {isSubmitting ? "Starting" : isJobActive ? "Running" : `Run ${selectedFiles.length || ""}`.trim()}
        </button>
        {isJobActive ? (
          <button
            type="button"
            className="wb-button"
            onClick={() => handleStopJob(job.job_id)}
            disabled={isStoppingJob}
          >
            {isStoppingJob ? "Stopping..." : "Stop"}
          </button>
        ) : null}
        <button type="button" className="wb-button" onClick={handleDownload} disabled={!hasCompletedResults}>
          Download results
        </button>
      </div>

      {submitError ? <Flag state="abnormal">{submitError}</Flag> : null}

      {job ? (
        <>
          <div className="wb-progress-row">
            <div className="wb-progress-track">
              <div className="wb-progress-fill" style={{ width: `${progressPercent}%` }} />
            </div>
            <span className="wb-progress-label">
              {job.completed} of {job.total} processed
              {job.failed > 0 ? `, ${job.failed} failed` : ""}
            </span>
          </div>

          <table className="wb-table">
            <thead>
              <tr>
                <th>File</th>
                <th>Status</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {job.files.map((item, index) => (
                <tr key={`${item.name}-${index}`}>
                  <td className="wb-table-file">{item.name}</td>
                  <td>
                    <Flag
                      state={
                        item.status === "done" ? "normal" : item.status === "error" ? "abnormal" : "pending"
                      }
                    >
                      {item.status === "done"
                        ? "Done"
                        : item.status === "error"
                        ? "Failed"
                        : item.status === "running"
                        ? "Running"
                        : "Queued"}
                    </Flag>
                  </td>
                  <td className="wb-table-summary">
                    {item.status === "error" ? item.error : item.summary || "--"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <p className="wb-hint">
          Choose one or more .txt documents to run them through the {domainTitle} pipeline.
        </p>
      )}

      <div className="wb-history">
        <h4>Previous runs</h4>
        {isHistoryLoading ? (
          <p className="wb-hint">Loading previous runs...</p>
        ) : history.length === 0 ? (
          <p className="wb-hint">No previous runs yet.</p>
        ) : (
          <table className="wb-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Workflow</th>
                <th>Files</th>
                <th>Model</th>
                <th>Thinking budget</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {history.map((entry) => (
                <tr key={entry.job_id}>
                  <td className="wb-table-file">{formatTimestamp(entry.created_at)}</td>
                  <td>{labelForWorkflow(entry.workflow)}</td>
                  <td>
                    {entry.completed}/{entry.total}
                    {entry.failed > 0 ? `, ${entry.failed} failed` : ""}
                  </td>
                  <td>{labelForModel(entry.model_name)}</td>
                  <td>{labelForThinkingBudget(entry.thinking_budget)}</td>
                  <td>
                    <Flag
                      state={
                        entry.status === "completed"
                          ? "normal"
                          : entry.status === "completed_with_errors"
                          ? "abnormal"
                          : "pending"
                      }
                    >
                      {entry.status.replace(/_/g, " ")}
                    </Flag>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="wb-button"
                      onClick={() => handleDownloadJob(entry.job_id)}
                      disabled={entry.completed - entry.failed <= 0}
                    >
                      Download
                    </button>
                    {entry.failed > 0 || entry.status === "cancelled" ? (
                      <button
                        type="button"
                        className="wb-button"
                        onClick={() => handleRetryJob(entry.job_id)}
                        disabled={retryingJobId === entry.job_id || isJobActive}
                      >
                        {retryingJobId === entry.job_id ? "Retrying..." : "Retry failed"}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function OverviewSection({ prompts, schemas }) {
  const [checks, setChecks] = useState(SERVICE_CHECKS.map((c) => ({ ...c, state: "unknown" })));
  const [isChecking, setIsChecking] = useState(false);
  const [concurrency, setConcurrency] = useState(null);
  const [concurrencyDraft, setConcurrencyDraft] = useState("");
  const [concurrencyBounds, setConcurrencyBounds] = useState({ min: 1, max: 16 });
  const [isSavingConcurrency, setIsSavingConcurrency] = useState(false);
  const [concurrencyError, setConcurrencyError] = useState("");

  useEffect(() => {
    fetch(`${BATCH_API_BASE}/batch/settings`)
      .then((response) => response.json())
      .then((data) => {
        setConcurrency(data.concurrency);
        setConcurrencyDraft(String(data.concurrency));
        setConcurrencyBounds({ min: data.min_concurrency, max: data.max_concurrency });
      })
      .catch(() => {});
  }, []);

  function handleSaveConcurrency() {
    const parsed = Number(concurrencyDraft);
    if (!Number.isInteger(parsed)) {
      setConcurrencyError("Enter a whole number.");
      return;
    }
    setIsSavingConcurrency(true);
    setConcurrencyError("");
    fetch(`${BATCH_API_BASE}/batch/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concurrency: parsed })
    })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || `Failed to save (HTTP ${response.status})`);
        }
        return response.json();
      })
      .then((data) => {
        setConcurrency(data.concurrency);
        setConcurrencyDraft(String(data.concurrency));
      })
      .catch((error) => setConcurrencyError(error.message || "Failed to save."))
      .finally(() => setIsSavingConcurrency(false));
  }

  async function runChecks() {
    setIsChecking(true);
    const results = await Promise.all(
      SERVICE_CHECKS.map(async (check) => {
        try {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 4000);
          const response = await fetch(check.url, { signal: controller.signal });
          clearTimeout(timeout);
          return { ...check, state: response.ok || response.status === 404 ? "normal" : "abnormal" };
        } catch {
          return { ...check, state: "abnormal" };
        }
      })
    );
    setChecks(results);
    setIsChecking(false);
  }

  useEffect(() => {
    runChecks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const countsByGroup = useMemo(() => {
    const counts = { "E&M": { prompts: 0, schemas: 0 }, CPT: { prompts: 0, schemas: 0 }, PCS: { prompts: 0, schemas: 0 } };
    for (const p of prompts) {
      if (counts[p.group]) counts[p.group].prompts += 1;
    }
    for (const s of schemas) {
      if (counts[s.group]) counts[s.group].schemas += 1;
    }
    return counts;
  }, [prompts, schemas]);

  return (
    <section className="wb-section">
      <h2 className="wb-section-title">Overview</h2>
      <p className="wb-section-intro">
        One console for the prompts, response schemas, and batch runs behind the E&amp;M, CPT, and PCS
        coding pipelines.
      </p>

      <div className="wb-overview-grid">
        {["E&M", "CPT", "PCS"].map((group) => (
          <div className="wb-overview-card" key={group}>
            <h3>{group}</h3>
            <dl>
              <div>
                <dt>Prompts</dt>
                <dd>{countsByGroup[group].prompts}</dd>
              </div>
              <div>
                <dt>Response schemas</dt>
                <dd>{countsByGroup[group].schemas}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>

      <div className="wb-service-panel">
        <div className="wb-service-panel-head">
          <h3>Service status</h3>
          <button type="button" className="wb-button" onClick={runChecks} disabled={isChecking}>
            {isChecking ? "Checking" : "Recheck"}
          </button>
        </div>
        <table className="wb-table">
          <thead>
            <tr>
              <th>Service</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {checks.map((check) => (
              <tr key={check.label}>
                <td>{check.label}</td>
                <td>
                  <Flag state={check.state === "unknown" ? "pending" : check.state}>
                    {check.state === "unknown" ? "Checking" : check.state === "normal" ? "Up" : "Down"}
                  </Flag>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="wb-service-panel">
        <div className="wb-service-panel-head">
          <h3>Batch processing workers</h3>
        </div>
        <p className="wb-hint">
          How many files the batch processor runs at the same time, across every workflow.
        </p>
        <div className="wb-concurrency-row">
          <input
            type="number"
            min={concurrencyBounds.min}
            max={concurrencyBounds.max}
            value={concurrencyDraft}
            onChange={(event) => setConcurrencyDraft(event.target.value)}
            className="wb-concurrency-input"
          />
          <button
            type="button"
            className="wb-button wb-button--primary"
            onClick={handleSaveConcurrency}
            disabled={isSavingConcurrency || concurrencyDraft === String(concurrency)}
          >
            {isSavingConcurrency ? "Saving" : "Save"}
          </button>
          {concurrency !== null ? (
            <span className="wb-hint">Currently {concurrency} worker(s).</span>
          ) : null}
        </div>
        {concurrencyError ? <Flag state="abnormal">{concurrencyError}</Flag> : null}
      </div>
    </section>
  );
}

async function fetchJson(url) {
  let response;
  try {
    response = await fetch(url);
  } catch (networkError) {
    throw new Error(`Could not reach ${url}: ${networkError.message}`);
  }
  const bodyText = await response.text();
  if (!response.ok) {
    throw new Error(
      `${url} returned HTTP ${response.status}${bodyText ? `: ${bodyText.slice(0, 300)}` : " (empty response)"}`
    );
  }
  if (!bodyText) {
    throw new Error(`${url} returned an empty response (expected JSON).`);
  }
  try {
    return JSON.parse(bodyText);
  } catch {
    throw new Error(`${url} did not return valid JSON: ${bodyText.slice(0, 300)}`);
  }
}

export default function DomainWorkbench({ onBack }) {
  const [activeDomain, setActiveDomain] = useState("overview");
  const [prompts, setPrompts] = useState([]);
  const [schemas, setSchemas] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    setIsLoading(true);
    setLoadError("");
    Promise.all([
      fetchJson(`${PROMPTS_API_BASE}/prompts`),
      fetchJson(`${PROMPTS_API_BASE}/schemas`)
    ])
      .then(([promptsData, schemasData]) => {
        setPrompts(Array.isArray(promptsData.prompts) ? promptsData.prompts : []);
        setSchemas(Array.isArray(schemasData.schemas) ? schemasData.schemas : []);
      })
      .catch((error) => setLoadError(error.message || "Could not load prompts and schemas."))
      .finally(() => setIsLoading(false));
  }, []);

  function handlePromptSaved(updated) {
    setPrompts((current) =>
      current.map((item) => (item.service === updated.service && item.key === updated.key ? updated : item))
    );
  }

  function handleSchemaSaved(updated) {
    setSchemas((current) =>
      current.map((item) => (item.service === updated.service && item.key === updated.key ? updated : item))
    );
  }

  const activeDomainInfo = DOMAINS.find((d) => d.key === activeDomain);
  const domainPrompts = activeDomainInfo?.group
    ? prompts.filter((p) => p.group === activeDomainInfo.group)
    : [];
  const domainSchemas = activeDomainInfo?.group
    ? schemas.filter((s) => s.group === activeDomainInfo.group)
    : [];

  return (
    <div className="wb-root">
      <header className="wb-masthead">
        <div className="wb-masthead-title">
          <span className="wb-masthead-kicker">Domain Workbench</span>
          <h1>Prompts, schemas &amp; batch runs</h1>
        </div>
        <button type="button" className="wb-button" onClick={onBack}>
          Back to coding workspace
        </button>
      </header>

      <div className="wb-body">
        <nav className="wb-rail">
          {DOMAINS.map((domain) => (
            <button
              key={domain.key}
              type="button"
              className={domain.key === activeDomain ? "wb-rail-item active" : "wb-rail-item"}
              onClick={() => setActiveDomain(domain.key)}
            >
              {domain.title}
            </button>
          ))}
        </nav>

        <main className="wb-main">
          {isLoading ? (
            <p className="wb-hint">Loading prompts and schemas...</p>
          ) : loadError ? (
            <Flag state="abnormal">{loadError}</Flag>
          ) : activeDomain === "overview" ? (
            <OverviewSection prompts={prompts} schemas={schemas} />
          ) : (
            <section className="wb-section">
              <h2 className="wb-section-title">{activeDomainInfo.title}</h2>

              <div className="wb-subsection">
                <h3>Prompts</h3>
                {domainPrompts.length === 0 ? (
                  <p className="wb-hint">No prompts registered for this workflow.</p>
                ) : (
                  domainPrompts.map((item) => (
                    <EditableEntry
                      key={`${item.service}:${item.key}`}
                      item={item}
                      kind="prompt"
                      onSaved={handlePromptSaved}
                    />
                  ))
                )}
              </div>

              <div className="wb-subsection">
                <h3>Response schemas</h3>
                {domainSchemas.length === 0 ? (
                  <p className="wb-hint">No response schemas registered for this workflow.</p>
                ) : (
                  domainSchemas.map((item) => (
                    <EditableEntry
                      key={`${item.service}:${item.key}`}
                      item={item}
                      kind="schema"
                      onSaved={handleSchemaSaved}
                    />
                  ))
                )}
              </div>

              <div className="wb-subsection">
                <h3>Batch processing</h3>
                <BatchRunner domainKey={activeDomain} domainTitle={activeDomainInfo.title} />
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
