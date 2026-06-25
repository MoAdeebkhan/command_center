import { useState, useEffect, useRef, useCallback } from "react";

const API = "http://localhost:8080";

const AGENTS = [
  { name: "Reader Agent",          icon: "ti-file-text",      desc: "Parses source file structure" },
  { name: "Business Logic Agent",  icon: "ti-brain",          desc: "Identifies rules & KPIs via llama3" },
  { name: "Extraction Agent",      icon: "ti-database",       desc: "Extracts fields & measures via llama3" },
  { name: "Conversion Agent",      icon: "ti-transform",      desc: "Translates formulas via llama3" },
  { name: "Documentation Agent",   icon: "ti-notebook",       desc: "Generates migration guide via llama3" },
  { name: "Validation Agent",      icon: "ti-shield-check",   desc: "Validates output quality via llama3" },
  { name: "Deployment Agent",      icon: "ti-rocket",         desc: "Assembles final output package" },
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function Badge({ text, color = "neutral" }) {
  return <span className={`badge badge-${color}`}>{text}</span>;
}

function FormatBadge({ format }) {
  const isTableau = format === "twbx" || format === "twb";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      background: isTableau ? "rgba(14,165,233,0.1)" : "rgba(139,92,246,0.1)",
      color: isTableau ? "#38bdf8" : "#a78bfa",
      fontSize: 11, fontWeight: 600, padding: "2px 8px",
      borderRadius: 99,
      border: `1px solid ${isTableau ? "rgba(14,165,233,0.3)" : "rgba(139,92,246,0.3)"}`,
    }}>
      <i className={`ti ${isTableau ? "ti-chart-bar" : "ti-report-analytics"}`} style={{ fontSize: 12 }} />
      {isTableau ? "Tableau" : "Power BI"}
    </span>
  );
}

// ── Ollama status indicator ───────────────────────────────────────────────────

function OllamaStatus() {
  const [state, setState] = useState({ status: "checking", model: "", models: [] });

  useEffect(() => {
    fetch(`${API}/api/ollama/status`)
      .then(r => r.json())
      .then(d => setState({
        status: d.reachable ? "online" : "offline",
        model: d.active_model || "",
        models: d.available_models || [],
      }))
      .catch(() => setState(s => ({ ...s, status: "offline" })));
  }, []);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--text-secondary)" }}>
      <span className={`ollama-dot ${state.status}`} />
      {state.status === "checking" ? "Checking Ollama…" : state.status === "online"
        ? <span>llama3 <span style={{ color: "var(--green)" }}>ready</span></span>
        : <span style={{ color: "var(--red)" }}>Ollama offline</span>
      }
    </div>
  );
}

// ── Upload zone ───────────────────────────────────────────────────────────────

function UploadZone({ onUpload, loading }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef();

  const handleFile = (file) => {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["twbx", "twb", "pbix"].includes(ext)) {
      alert("Only .twbx, .twb, or .pbix files supported");
      return;
    }
    onUpload(file);
  };

  return (
    <div
      className={`upload-zone ${dragging ? "dragging" : ""} ${loading ? "loading" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]); }}
      onClick={() => !loading && inputRef.current?.click()}
    >
      <input ref={inputRef} type="file" accept=".twbx,.twb,.pbix" style={{ display: "none" }}
        onChange={(e) => handleFile(e.target.files?.[0])} />
      <i className="ti ti-cloud-upload" style={{
        fontSize: 36, display: "block", marginBottom: 10,
        background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
        WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
      }} />
      {loading ? (
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
          <i className="ti ti-loader animate-spin" style={{ marginRight: 6 }} />
          Uploading & starting pipeline…
        </p>
      ) : (
        <>
          <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 4, color: "var(--text-primary)" }}>
            Drop file or click to browse
          </p>
          <p style={{ color: "var(--text-tertiary)", fontSize: 11 }}>
            <strong>.twbx / .twb</strong> Tableau &nbsp;·&nbsp; <strong>.pbix</strong> Power BI
          </p>
        </>
      )}
    </div>
  );
}

// ── Job row ───────────────────────────────────────────────────────────────────

function JobRow({ job, onClick, selected }) {
  const isTableau = job.source_format === "twbx" || job.source_format === "twb";
  const dirLabel = isTableau ? "Tableau → Power BI" : "Power BI → Tableau";
  const statusMap = {
    queued:          { label: "Queued",   color: "neutral" },
    running:         { label: "Running",  color: "info" },
    awaiting_review: { label: "Review",   color: "warning" },
    completed:       { label: "Done",     color: "success" },
    rejected:        { label: "Rejected", color: "danger" },
    failed:          { label: "Failed",   color: "danger" },
  };
  const s = statusMap[job.status] || { label: job.status, color: "neutral" };
  return (
    <div className={`job-row ${selected ? "selected" : ""}`} onClick={onClick}>
      <i className="ti ti-file-arrow-right" style={{ fontSize: 18, color: "var(--text-tertiary)", flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ margin: "0 0 2px", fontSize: 12, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text-primary)" }}>
          {job.filename}
        </p>
        <p style={{ margin: 0, fontSize: 11, color: "var(--text-tertiary)" }}>{dirLabel}</p>
      </div>
      <Badge text={s.label} color={s.color} />
    </div>
  );
}

// ── Agent timeline ────────────────────────────────────────────────────────────

function AgentTimeline({ steps, agents }) {
  const [expandedLogs, setExpandedLogs] = useState({});

  const toggleLog = (name) => setExpandedLogs(p => ({ ...p, [name]: !p[name] }));

  const statusIcon = { pending: "ti-clock", running: "ti-loader", completed: "ti-circle-check", failed: "ti-circle-x" };
  const statusColor = { pending: "var(--text-tertiary)", running: "var(--accent)", completed: "var(--green)", failed: "var(--red)" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {agents.map((agent, i) => {
        const step = steps.find(s => s.agent_name === agent.name) || {};
        const status = step.status || "pending";
        const hasLog = !!step.ai_log;

        return (
          <div key={agent.name} className={`agent-step ${status}`}>
            {/* Icon */}
            <div style={{
              width: 36, height: 36, borderRadius: "50%", flexShrink: 0,
              background: "var(--bg-surface)",
              border: `1.5px solid ${statusColor[status]}`,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <i className={`ti ${status === "running" ? "ti-loader animate-spin" : statusIcon[status]}`}
                style={{ fontSize: 16, color: statusColor[status] }} />
            </div>

            {/* Content */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                <i className={`ti ${agent.icon}`} style={{ fontSize: 13, color: "var(--text-tertiary)" }} />
                <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)" }}>{agent.name}</span>
                {status === "running" && (
                  <span className="animate-pulse" style={{ fontSize: 11, color: "var(--accent)" }}>Processing with llama3…</span>
                )}
              </div>
              <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
                {step.message || agent.desc}
              </p>

              {/* AI Log expander */}
              {hasLog && (
                <div style={{ marginTop: 8 }}>
                  <button
                    onClick={() => toggleLog(agent.name)}
                    style={{
                      background: "none", border: "none", cursor: "pointer",
                      color: "var(--accent)", fontSize: 11, padding: 0,
                      display: "flex", alignItems: "center", gap: 4,
                    }}
                  >
                    <i className={`ti ${expandedLogs[agent.name] ? "ti-chevron-up" : "ti-chevron-down"}`} style={{ fontSize: 11 }} />
                    {expandedLogs[agent.name] ? "Hide" : "Show"} llama3 response
                  </button>
                  {expandedLogs[agent.name] && (
                    <div className="ai-log-box" style={{ marginTop: 6 }}>
                      {step.ai_log}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Status pill */}
            <span style={{ fontSize: 11, color: statusColor[status], fontWeight: 600, flexShrink: 0, textTransform: "capitalize" }}>
              {status}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Migration report ──────────────────────────────────────────────────────────

function MigrationReport({ report, jobStatus, onApprove, onReject, jobId, onRefresh }) {
  const [editingFormula, setEditingFormula] = useState(null);
  const [editContent, setEditContent] = useState("");
  const [aiInstruction, setAiInstruction] = useState("");
  const [isFixing, setIsFixing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const { field_mappings = [], warnings = [], unsupported = [], stats = {}, translated_formulas = [], validation = {}, documentation = {} } = report;
  const [activeSection, setActiveSection] = useState("mappings");

  const mapped      = field_mappings.filter(m => m.status === "mapped");
  const needsReview = field_mappings.filter(m => m.status === "needs_review");

  const handleDownload = () => {
    window.open(`${API}/api/jobs/${jobId}/download`, "_blank");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* ── Stats row ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 10 }}>
        {[
          { label: "Total objects",  val: stats.total_objects  ?? "—", color: "var(--text-primary)" },
          { label: "Auto-migrated",  val: stats.auto_migrated  ?? "—", color: "var(--green)" },
          { label: "Needs review",   val: stats.needs_review   ?? "—", color: "var(--yellow)" },
          { label: "Unsupported",    val: stats.unsupported    ?? "—", color: "var(--red)" },
          { label: "AI confidence",  val: stats.confidence_score ?? "—", color: "var(--accent)" },
        ].map(m => (
          <div key={m.label} className="stat-card">
            <p style={{ fontSize: 10, color: "var(--text-tertiary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.5px" }}>{m.label}</p>
            <p style={{ fontSize: 24, fontWeight: 700, color: m.color }}>{m.val}</p>
          </div>
        ))}
      </div>

      {/* ── Section tabs ── */}
      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)" }}>
        {[["mappings","Field Mappings"],["formulas","Translated Formulas"],["warnings","Warnings"],["docs","Migration Guide"],["validation","Validation"]].map(([k, label]) => (
          <button key={k} className={`tab-btn ${activeSection === k ? "active" : ""}`} onClick={() => setActiveSection(k)}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Mappings ── */}
      {activeSection === "mappings" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div className="card">
            <div className="card-header">
              <i className="ti ti-check" style={{ color: "var(--green)" }} />
              <span>Auto-mapped ({mapped.length})</span>
            </div>
            <div style={{ maxHeight: 260, overflowY: "auto", padding: "8px 0" }}>
              {mapped.map((m, i) => (
                <div key={i} style={{ padding: "6px 16px", display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                  <span style={{ color: "var(--text-primary)", flex: 1 }}>{m.source_concept}</span>
                  <i className="ti ti-arrow-right" style={{ fontSize: 11, color: "var(--text-tertiary)", flexShrink: 0 }} />
                  <span style={{ color: "var(--text-secondary)", flex: 1, textAlign: "right", fontSize: 11 }}>{m.target_concept}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-header">
              <i className="ti ti-alert-triangle" style={{ color: "var(--yellow)" }} />
              <span>Needs review ({needsReview.length})</span>
            </div>
            <div style={{ maxHeight: 260, overflowY: "auto", padding: "8px 0" }}>
              {needsReview.map((m, i) => (
                <div key={i} style={{ padding: "6px 16px", fontSize: 12 }}>
                  <span style={{ color: "var(--yellow)" }}>{m.source_concept}</span>
                  {m.target_concept && <span style={{ color: "var(--text-tertiary)", marginLeft: 6, fontSize: 11 }}>→ {m.target_concept}</span>}
                </div>
              ))}
              {needsReview.length === 0 && <p style={{ padding: "8px 16px", fontSize: 12, color: "var(--text-tertiary)" }}>No items need review 🎉</p>}
            </div>
          </div>
        </div>
      )}

      {/* ── Translated formulas ── */}
      {activeSection === "formulas" && (
        <div className="card">
          <div className="card-header">
            <i className="ti ti-math" style={{ color: "var(--accent)" }} />
            <span>Formula translations — llama3</span>
          </div>
          <div style={{ maxHeight: 380, overflowY: "auto" }}>
            {translated_formulas.length === 0 ? (
              <p style={{ padding: "16px", fontSize: 12, color: "var(--text-tertiary)" }}>No formula translations in this migration.</p>
            ) : translated_formulas.map((f, i) => {
              const conf = f.confidence || "medium";
              const confColor = conf === "high" ? "var(--green)" : conf === "low" ? "var(--red)" : "var(--yellow)";
              return (
                <div key={i} style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span style={{ fontWeight: 600, fontSize: 12, color: "var(--text-primary)" }}>{f.name}</span>
                    <span style={{ fontSize: 10, color: confColor, fontWeight: 600, background: `${confColor}18`, padding: "1px 6px", borderRadius: 99 }}>{conf}</span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11 }}>
                    <div>
                      <p style={{ color: "var(--text-tertiary)", marginBottom: 3, fontSize: 10, textTransform: "uppercase", letterSpacing: "0.5px" }}>Original</p>
                      <code style={{ background: "var(--bg-base)", color: "#93c5fd", padding: "4px 8px", borderRadius: 6, display: "block", fontFamily: "Courier New", lineHeight: 1.5 }}>
                        {f.original_formula}
                      </code>
                    </div>
                    <div style={{ position: "relative" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                        <p style={{ color: "var(--text-tertiary)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.5px", margin: 0 }}>Translated</p>
                        {jobStatus === "awaiting_review" && editingFormula !== f.name && (
                          <button onClick={() => { setEditingFormula(f.name); setEditContent(f.translated_formula); setAiInstruction(""); }} style={{ fontSize: 10, padding: "2px 6px", background: "var(--bg-base)", border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer", color: "var(--text-secondary)" }}>
                            <i className="ti ti-edit" /> Edit
                          </button>
                        )}
                      </div>
                      
                      {editingFormula === f.name ? (
                        <div style={{ background: "var(--bg-base)", padding: 8, borderRadius: 6, border: "1px solid var(--border)" }}>
                          <textarea
                            value={editContent}
                            onChange={e => setEditContent(e.target.value)}
                            style={{ width: "100%", height: 60, background: "transparent", color: "#86efac", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontFamily: "Courier New", fontSize: 11, resize: "vertical", marginBottom: 8 }}
                          />
                          <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8 }}>
                            <input 
                              type="text" 
                              placeholder="Instructions for AI (e.g. Use CALCULATE)" 
                              value={aiInstruction}
                              onChange={e => setAiInstruction(e.target.value)}
                              style={{ flex: 1, background: "var(--bg-body)", border: "1px solid var(--border)", padding: "4px 8px", fontSize: 11, borderRadius: 4, color: "var(--text-primary)" }}
                            />
                            <button 
                              onClick={async () => {
                                setIsFixing(true);
                                try {
                                  const r = await fetch(`${API}/api/jobs/${jobId}/fix_formula`, {
                                    method: "POST", headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ original_formula: f.original_formula, translated_formula: editContent, instructions: aiInstruction })
                                  });
                                  const d = await r.json();
                                  if (r.ok) setEditContent(d.corrected_formula);
                                  else alert("AI Error: " + (d.detail || "failed"));
                                } catch (e) { alert("Error connecting to AI"); }
                                setIsFixing(false);
                              }}
                              disabled={isFixing}
                              style={{ background: "var(--accent)", color: "#fff", border: "none", padding: "4px 8px", fontSize: 11, borderRadius: 4, cursor: "pointer", opacity: isFixing ? 0.7 : 1 }}
                            >
                              {isFixing ? "Fixing..." : "Ask AI"}
                            </button>
                          </div>
                          <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
                            <button onClick={() => setEditingFormula(null)} style={{ background: "transparent", border: "1px solid var(--border)", padding: "4px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer", color: "var(--text-secondary)" }}>Cancel</button>
                            <button 
                              onClick={async () => {
                                setIsSaving(true);
                                try {
                                  const r = await fetch(`${API}/api/jobs/${jobId}/formulas`, {
                                    method: "POST", headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ formulas: [{ name: f.name, translated_formula: editContent }] })
                                  });
                                  if (r.ok) {
                                    setEditingFormula(null);
                                    if (onRefresh) onRefresh();
                                  } else alert("Failed to save");
                                } catch (e) { alert("Error saving formula"); }
                                setIsSaving(false);
                              }}
                              disabled={isSaving}
                              style={{ background: "var(--green)", color: "#fff", border: "none", padding: "4px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer", opacity: isSaving ? 0.7 : 1 }}
                            >
                              {isSaving ? "Saving..." : "Save Edit"}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <code style={{ background: "var(--bg-base)", color: conf === "low" ? "var(--yellow)" : "#86efac", padding: "4px 8px", borderRadius: 6, display: "block", fontFamily: "Courier New", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
                          {f.translated_formula}
                        </code>
                      )}
                    </div>
                  </div>
                  {f.notes && <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4 }}>📝 {f.notes}</p>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Warnings ── */}
      {activeSection === "warnings" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card">
            <div className="card-header">
              <i className="ti ti-alert-circle" style={{ color: "var(--yellow)" }} />
              <span>Warnings ({warnings.length})</span>
            </div>
            <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
              {warnings.map((w, i) => (
                <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12 }}>
                  <i className="ti ti-point-filled" style={{ fontSize: 8, color: "var(--yellow)", marginTop: 5, flexShrink: 0 }} />
                  <span style={{ color: "var(--text-primary)", lineHeight: 1.5 }}>{w}</span>
                </div>
              ))}
            </div>
          </div>
          {unsupported.length > 0 && (
            <div className="card">
              <div className="card-header">
                <i className="ti ti-ban" style={{ color: "var(--red)" }} />
                <span>Unsupported features ({unsupported.length})</span>
              </div>
              <div style={{ padding: "12px 16px", display: "flex", flexWrap: "wrap", gap: 8 }}>
                {unsupported.map((u, i) => <Badge key={i} text={u} color="danger" />)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Migration guide ── */}
      {activeSection === "docs" && (
        <div className="card">
          <div className="card-header">
            <i className="ti ti-notebook" style={{ color: "var(--accent)" }} />
            <span>Migration Guide — llama3 generated</span>
            {documentation?.estimated_effort && (
              <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-secondary)" }}>
                Est. effort: <strong style={{ color: "var(--yellow)" }}>{documentation.estimated_effort}</strong>
              </span>
            )}
          </div>
          <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: 16, maxHeight: 400, overflowY: "auto" }}>
            {(documentation?.sections || []).map((sec, i) => (
              <div key={i}>
                <h4 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 20, height: 20, background: "var(--accent)", color: "white", borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700 }}>{i + 1}</span>
                  {sec.title}
                </h4>
                <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.7, whiteSpace: "pre-line" }}>{sec.content}</p>
              </div>
            ))}
            {documentation?.recommendations?.length > 0 && (
              <div>
                <h4 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 8 }}>💡 Recommendations</h4>
                {documentation.recommendations.map((r, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12, marginBottom: 6 }}>
                    <i className="ti ti-arrow-right" style={{ fontSize: 11, color: "var(--accent)", marginTop: 3, flexShrink: 0 }} />
                    <span style={{ color: "var(--text-primary)", lineHeight: 1.5 }}>{r}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Validation ── */}
      {activeSection === "validation" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card">
            <div className="card-header">
              <i className="ti ti-shield-check" style={{ color: "var(--green)" }} />
              <span>Validation Score — llama3</span>
              <span style={{ marginLeft: "auto", fontSize: 22, fontWeight: 700, color: (validation.score || 0) >= 70 ? "var(--green)" : "var(--yellow)" }}>
                {validation.score ?? "—"}/100
              </span>
            </div>
            <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: 12 }}>
              {/* Score bar */}
              <div style={{ background: "var(--bg-base)", height: 8, borderRadius: 99, overflow: "hidden" }}>
                <div style={{ height: "100%", borderRadius: 99, width: `${validation.score || 0}%`, background: `linear-gradient(90deg, var(--accent), var(--green))`, transition: "width 0.6s ease" }} />
              </div>

              {validation.passed_checks?.length > 0 && (
                <div>
                  <p style={{ fontSize: 11, fontWeight: 600, color: "var(--green)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.5px" }}>Passed checks</p>
                  {validation.passed_checks.map((c, i) => (
                    <div key={i} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, marginBottom: 4 }}>
                      <i className="ti ti-circle-check" style={{ fontSize: 12, color: "var(--green)", flexShrink: 0 }} />
                      <span style={{ color: "var(--text-secondary)" }}>{c}</span>
                    </div>
                  ))}
                </div>
              )}

              {validation.issues?.length > 0 && (
                <div>
                  <p style={{ fontSize: 11, fontWeight: 600, color: "var(--yellow)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.5px" }}>Issues found</p>
                  {validation.issues.map((issue, i) => (
                    <div key={i} style={{ padding: "10px 12px", background: "var(--bg-base)", borderRadius: 8, marginBottom: 6, border: `1px solid ${issue.severity === "critical" ? "var(--red-bg)" : "var(--border)"}` }}>
                      <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                        <Badge text={issue.severity} color={issue.severity === "critical" ? "danger" : "warning"} />
                        <span style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500 }}>{issue.issue}</span>
                      </div>
                      {issue.recommendation && <p style={{ fontSize: 11, color: "var(--text-tertiary)", margin: 0 }}>→ {issue.recommendation}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── HITL checkpoint ── */}
      {jobStatus === "awaiting_review" && (
        <div style={{
          padding: "16px 20px", borderRadius: 12,
          border: "1px solid rgba(37,99,235,0.3)", background: "rgba(37,99,235,0.06)",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
        }}>
          <div>
            <p style={{ margin: "0 0 3px", fontWeight: 600, fontSize: 14, color: "var(--accent)" }}>
              <i className="ti ti-user-check" style={{ marginRight: 6 }} />
              Human-in-the-loop checkpoint
            </p>
            <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>
              Review the migration report above. Approve to finalise or reject to re-queue.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            <button className="btn btn-danger" onClick={onReject}>
              <i className="ti ti-x" /> Reject
            </button>
            <button className="btn btn-primary" onClick={onApprove}>
              <i className="ti ti-check" /> Approve migration
            </button>
          </div>
        </div>
      )}

      {/* ── Completed banner ── */}
      {jobStatus === "completed" && (
        <div style={{
          padding: "14px 20px", borderRadius: 12,
          border: "1px solid rgba(16,185,129,0.3)", background: "rgba(16,185,129,0.08)",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <i className="ti ti-circle-check" style={{ fontSize: 22, color: "var(--green)" }} />
            <div>
              <p style={{ margin: 0, fontWeight: 600, fontSize: 14, color: "var(--green)" }}>Migration approved & ready</p>
              <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>Output package is staged for download.</p>
            </div>
          </div>
          <button className="btn btn-primary" onClick={handleDownload}>
            <i className="ti ti-download" /> Download package
          </button>
        </div>
      )}

      {/* ── Rejected banner ── */}
      {jobStatus === "rejected" && (
        <div style={{
          padding: "14px 20px", borderRadius: 12,
          border: "1px solid rgba(239,68,68,0.3)", background: "rgba(239,68,68,0.08)",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <i className="ti ti-circle-x" style={{ fontSize: 22, color: "var(--red)" }} />
          <div>
            <p style={{ margin: 0, fontWeight: 600, fontSize: 14, color: "var(--red)" }}>Migration rejected</p>
            <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>Re-upload or adjust the source file and try again.</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobDetail, setJobDetail] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [tab, setTab] = useState("pipeline");
  const pollRef = useRef(null);

  const fetchJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/jobs`);
      setJobs(await r.json());
    } catch {}
  }, []);

  const fetchJobDetail = useCallback(async (id) => {
    try {
      const r = await fetch(`${API}/api/jobs/${id}`);
      setJobDetail(await r.json());
    } catch {}
  }, []);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  useEffect(() => {
    if (!selectedJob) return;
    fetchJobDetail(selectedJob);
    clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      fetchJobDetail(selectedJob);
      fetchJobs();
    }, 2500);
    return () => clearInterval(pollRef.current);
  }, [selectedJob, fetchJobDetail, fetchJobs]);

  useEffect(() => {
    if (jobDetail && !["running", "queued"].includes(jobDetail.status)) {
      clearInterval(pollRef.current);
    }
  }, [jobDetail]);

  const handleUpload = async (file) => {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch(`${API}/api/jobs`, { method: "POST", body: fd });
      const data = await r.json();
      if (data.job_id) {
        await fetchJobs();
        setSelectedJob(data.job_id);
        setTab("pipeline");
      } else {
        alert(data.detail || "Upload failed");
      }
    } catch {
      alert("Could not reach backend — make sure FastAPI is running on port 8000");
    } finally {
      setUploading(false);
    }
  };

  const handleApprove = async () => {
    await fetch(`${API}/api/jobs/${selectedJob}/approve`, { method: "POST" });
    fetchJobDetail(selectedJob);
    fetchJobs();
  };

  const handleReject = async () => {
    await fetch(`${API}/api/jobs/${selectedJob}/reject`, { method: "POST" });
    fetchJobDetail(selectedJob);
    fetchJobs();
  };

  const dirLabel = jobDetail
    ? (jobDetail.source_format === "twbx" || jobDetail.source_format === "twb"
      ? "Tableau → Power BI" : "Power BI → Tableau")
    : "";

  const jobStatusBadge = {
    queued:          { label: "Queued",          color: "neutral" },
    running:         { label: "Running",          color: "info" },
    awaiting_review: { label: "Awaiting review",  color: "warning" },
    completed:       { label: "Completed",        color: "success" },
    rejected:        { label: "Rejected",         color: "danger" },
    failed:          { label: "Failed",           color: "danger" },
  };

  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--bg-base)", color: "var(--text-primary)", fontFamily: "'Inter', sans-serif", minHeight: 600 }}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes slideIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
        @keyframes glow { 0%,100%{box-shadow:0 0 8px rgba(59,130,246,0.3)} 50%{box-shadow:0 0 20px rgba(59,130,246,0.6)} }
        @keyframes gradientShift { 0%,100%{background-position:0% 50%} 50%{background-position:100% 50%} }
      `}</style>

      {/* ── Sidebar ── */}
      <div className="sidebar">
        {/* Brand */}
        <div style={{ padding: "16px 14px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 30, height: 30, borderRadius: 8,
                background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <i className="ti ti-transform" style={{ fontSize: 16, color: "white" }} />
              </div>
              <div>
                <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>Migration Platform</p>
                <OllamaStatus />
              </div>
            </div>
          </div>
          <UploadZone onUpload={handleUpload} loading={uploading} />
        </div>

        {/* Jobs list */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          <p style={{ padding: "10px 14px 4px", fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "1px", margin: 0 }}>
            Jobs ({jobs.length})
          </p>
          {jobs.length === 0 ? (
            <p style={{ padding: "12px 14px", fontSize: 12, color: "var(--text-tertiary)" }}>Upload a file to start</p>
          ) : jobs.map(j => (
            <JobRow key={j.id} job={j} selected={selectedJob === j.id}
              onClick={() => { setSelectedJob(j.id); setTab("pipeline"); }} />
          ))}
        </div>

        {/* Footer */}
        <div style={{ padding: "10px 14px", borderTop: "1px solid var(--border)", fontSize: 10, color: "var(--text-tertiary)", display: "flex", alignItems: "center", gap: 6 }}>
          <i className="ti ti-cpu" style={{ fontSize: 12 }} />
          Powered by llama3:latest · Ollama 10.10.0.130
        </div>
      </div>

      {/* ── Main panel ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {!selectedJob ? (
          /* Empty state */
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16 }}>
            <div style={{
              width: 80, height: 80, borderRadius: 20,
              background: "linear-gradient(135deg, rgba(59,130,246,0.15), rgba(139,92,246,0.15))",
              border: "1px solid rgba(59,130,246,0.2)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <i className="ti ti-arrows-exchange" style={{ fontSize: 36, color: "var(--accent)" }} />
            </div>
            <div style={{ textAlign: "center" }}>
              <p style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, background: "linear-gradient(135deg, #3b82f6, #8b5cf6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                AI-Powered BI Migration
              </p>
              <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>
                Upload a file to start a 7-agent migration pipeline
              </p>
              <p style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                Tableau (.twbx / .twb) ↔ Power BI (.pbix) · llama3
              </p>
            </div>
            <div style={{ display: "flex", gap: 24, marginTop: 8 }}>
              {["Reader", "Business Logic", "Extraction", "Conversion", "Documentation", "Validation", "Deployment"].map((a, i) => (
                <div key={a} style={{ textAlign: "center", fontSize: 11, color: "var(--text-tertiary)" }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: "50%", margin: "0 auto 4px",
                    background: "var(--bg-elevated)", border: "1px solid var(--border)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>{i + 1}</span>
                  </div>
                  {a}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <>
            {/* Header */}
            <div style={{
              padding: "12px 20px", borderBottom: "1px solid var(--border)",
              display: "flex", alignItems: "center", gap: 12,
              background: "var(--bg-surface)",
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                  <span style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
                    {jobDetail?.filename || "Loading…"}
                  </span>
                  {jobDetail && <FormatBadge format={jobDetail.source_format} />}
                  {jobDetail && <i className="ti ti-arrow-right" style={{ fontSize: 12, color: "var(--text-tertiary)" }} />}
                  {jobDetail && <FormatBadge format={jobDetail.target_format} />}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 11, color: "var(--text-tertiary)" }}>
                  <span>{dirLabel}</span>
                  {jobDetail?.ollama_model && (
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <i className="ti ti-cpu" style={{ fontSize: 11 }} />
                      {jobDetail.ollama_model}
                    </span>
                  )}
                </div>
              </div>
              {jobDetail?.status && (
                <Badge text={(jobStatusBadge[jobDetail.status] || { label: jobDetail.status, color: "neutral" }).label}
                  color={(jobStatusBadge[jobDetail.status] || { color: "neutral" }).color} />
              )}
              {jobDetail?.status === "completed" && (
                <button className="btn btn-primary" onClick={() => window.open(`${API}/api/jobs/${selectedJob}/download`, "_blank")} style={{ fontSize: 12, padding: "6px 12px" }}>
                  <i className="ti ti-download" /> Download
                </button>
              )}
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", borderBottom: "1px solid var(--border)", padding: "0 20px", background: "var(--bg-surface)" }}>
              {[["pipeline", "ti-git-branch", "Agent Pipeline"], ["report", "ti-chart-bar", "Migration Report"]].map(([t, icon, label]) => (
                <button key={t} className={`tab-btn ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
                  <i className={`ti ${icon}`} style={{ marginRight: 5 }} />{label}
                </button>
              ))}
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
              {tab === "pipeline" && jobDetail && (
                <div className="animate-slide">
                  <AgentTimeline steps={jobDetail.steps || []} agents={AGENTS} />
                </div>
              )}
              {tab === "report" && jobDetail?.report && (
                <div className="animate-slide">
                  <MigrationReport
                    report={jobDetail.report}
                    jobStatus={jobDetail.status}
                    onApprove={handleApprove}
                    onReject={handleReject}
                    jobId={selectedJob}
                    onRefresh={() => fetchJobDetail(selectedJob)}
                  />
                </div>
              )}
              {tab === "report" && !jobDetail?.report && (
                <div style={{ textAlign: "center", padding: "4rem", color: "var(--text-tertiary)" }}>
                  <i className="ti ti-report" style={{ fontSize: 40, display: "block", marginBottom: 10 }} />
                  <p style={{ fontSize: 14, marginBottom: 4 }}>Report not ready yet</p>
                  <p style={{ fontSize: 12 }}>Report appears after the Conversion Agent completes</p>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
