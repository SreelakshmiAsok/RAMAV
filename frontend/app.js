const { useState, useEffect, useCallback } = React;
const html = htm.bind(React.createElement);

const API = ""; // same-origin: Flask serves this file and the API

const SEVERITY_COLOR = {
  CRITICAL: "var(--danger)", HIGH: "var(--danger)", MEDIUM: "var(--warn)",
  LOW: "var(--info)", INFO: "var(--text-faint)",
};

const OUTCOME_CLASS = {
  AUTO_APPROVE: "approve", AUTO_REJECT: "reject", HUMAN_REVIEW_REQUIRED: "review",
};
const OUTCOME_BADGE = {
  AUTO_APPROVE: "badge-approve", AUTO_REJECT: "badge-reject", HUMAN_REVIEW_REQUIRED: "badge-review",
};
const OUTCOME_LABEL = {
  AUTO_APPROVE: "AUTO-APPROVE", AUTO_REJECT: "AUTO-REJECT", HUMAN_REVIEW_REQUIRED: "HUMAN REVIEW REQUIRED",
};

function pct(x) { return `${Math.round((x || 0) * 100)}%`; }

async function postJSON(path, body) {
  const options = { method: "POST" };
  if (body) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const res = await fetch(API + path, options);
  return res.json();
}
async function getJSON(path) {
  const res = await fetch(API + path);
  return res.json();
}

// ---------------------------------------------------------------------------
function Sidebar({ tab, setTab }) {
  const items = [
    ["overview", "Overview"],
    ["demo", "Demo Scenarios"],
    ["conversation", "Agent Conversation"],
    ["findings", "Findings & Evidence"],
    ["decision", "Risk & Decision"],
    ["search", "Investigation Trace"],
    ["peas", "PEAS & Architecture"],
    ["health", "System Health"],
    ["history", "Analysis History"],
  ];
  return html`
    <div class="sidebar">
      <div class="brand">
        <div class="mark">RAMAV</div>
        <div class="tagline">Risk-Aware Multi-Agent<br/>Automated Validation</div>
      </div>
      ${items.map(([key, label]) => html`
        <div key=${key} class="nav-item ${tab === key ? "active" : ""}" onClick=${() => setTab(key)}>
          <span class="nav-dot"></span>${label}
        </div>
      `)}
      <div class="sidebar-footer">
        Coordination layer, not another<br/>static-analysis tool. See<br/>"Why Coordination?" in PEAS tab.
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function DecisionBanner({ decision }) {
  if (!decision) return null;
  const cls = OUTCOME_CLASS[decision.outcome] || "review";
  return html`
    <div class="decision-banner ${cls}">
      <div>
        <div class="faint" style=${{ fontSize: "11px", marginBottom: "6px" }}>DECISION</div>
        <div class="decision-outcome">${OUTCOME_LABEL[decision.outcome] || decision.outcome}</div>
      </div>
      <div style=${{ textAlign: "right" }}>
        <div class="kv"><span>Risk</span><span>${decision.risk?.toFixed(2)}</span></div>
        <div class="kv"><span>Confidence</span><span>${decision.confidence?.toFixed(2)}</span></div>
      </div>
    </div>
  `;
}

function Metric({ label, value, color }) {
  return html`
    <div class="card">
      <h3>${label}</h3>
      <div class="metric-value" style=${{ color: color || "var(--text)" }}>${value}</div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function OverviewPage({ run }) {
  if (!run) {
    return html`
      <div class="empty-state">
        No analysis has been run yet in this session.<br/>
        Go to <b>Demo Scenarios</b> and click a scenario to see the multi-agent pipeline execute for real.
      </div>
    `;
  }
  const cs = run.changeset || {};
  const decision = run.decision;
  return html`
    <${DecisionBanner} decision=${decision} />
    <div class="grid grid-3 section">
      <${Metric} label="PR" value=${run.pr_id || "—"} />
      <${Metric} label="Files changed" value=${cs.files_changed ?? "—"} />
      <${Metric} label="Duration" value=${run.duration_seconds ? run.duration_seconds.toFixed(3) + "s" : "—"} />
    </div>
    <div class="section">
      <div class="section-title">Change Summary</div>
      <div class="card">
        <div class="kv"><span>Changed files</span><span>${(cs.changed_files || []).join(", ") || "none"}</span></div>
        <div class="kv"><span>Languages</span><span>${(cs.languages || []).join(", ") || "n/a"}</span></div>
        <div class="kv"><span>Security-sensitive</span><span>${String(cs.security_sensitive)}</span></div>
        <div class="kv"><span>Database access</span><span>${String(cs.database_access)}</span></div>
        <div class="kv"><span>Tests changed</span><span>${String(cs.tests_changed)}</span></div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Agent Status</div>
      <div class="grid grid-3">
        ${["security_agent", "testing_agent", "quality_agent", "dependency_agent", "performance_agent"].map(name => {
          const f = (run.findings || []).find(x => x.agent === name);
          return html`
            <div class="card" key=${name}>
              <h3>${name.replace("_", " ")}</h3>
              <span class="badge ${f ? "badge-neutral" : "badge-review"}">${f ? "COMPLETED" : "NO DATA"}</span>
              ${f ? html`<div class="dim" style=${{ marginTop: "8px", fontSize: "12px" }}>${f.title}</div>` : null}
            </div>
          `;
        })}
      </div>
    </div>
    <div class="section">
      <div class="section-title">Decision Explanation</div>
      <div class="card">
        <ul class="reason-list">
          ${(decision?.reasons || []).map((r, i) => html`<li key=${i}>${r}</li>`)}
        </ul>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function DemoPage({ onRun, onRunCustom, loading, activeScenario }) {
  const [customPath, setCustomPath] = useState("");
  const [customPrId, setCustomPrId] = useState("PR-1");
  const scenarios = [
    ["safe", "SAFE PR", "/api/demo/safe"],
    ["sql_injection", "SQL INJECTION PR", "/api/demo/security"],
    ["disagreement", "AGENT DISAGREEMENT", "/api/demo/disagreement"],
    ["repair", "REPAIR + REVALIDATE", "/api/demo/repair"],
    ["low_evidence", "MISSING TOOL / LOW EVIDENCE", "/api/demo/low_evidence"],
  ];
  return html`
    <div class="section">
      <div class="section-title">Run a demo scenario</div>
      <p class="dim" style=${{ maxWidth: "640px" }}>
        Each button below triggers the REAL backend pipeline against a real
        two-commit git repository in <span class="mono">demo-repository/scenarios/</span> —
        Change Analyzer, all five agents, the investigation search, disagreement
        detection, risk/confidence engines and the decision policy all execute live.
        Nothing here is a scripted animation.
      </p>
      <div class="demo-buttons">
        ${scenarios.map(([key, label, path]) => html`
          <button key=${key} class="btn ${activeScenario === key ? "btn-primary" : ""}"
                  disabled=${loading}
                  onClick=${() => onRun(key, path)}>
            ${loading === key ? "Running…" : label}
          </button>
        `)}
      </div>
    </div>
    <div class="section">
      <div class="section-title">Analyze a real local Git repository</div>
      <p class="dim" style=${{ maxWidth: "640px" }}>
        Point RAMAV to ANY local git repository on your machine. All specialized agents, real tools (Semgrep, Pytest),
        and the multi-agent investigation search will run live against the repository commits.
      </p>
      <div class="card" style=${{ maxWidth: "640px", marginTop: "12px" }}>
        <div style=${{ marginBottom: "12px" }}>
          <label class="dim" style=${{ display: "block", fontSize: "12px", marginBottom: "4px" }}>Local Repository Absolute Path</label>
          <input class="text-input" placeholder="/Users/nethra/Desktop/Academics/FOAI/ramav" value=${customPath} onInput=${e => setCustomPath(e.target.value)} />
        </div>
        <div style=${{ marginBottom: "16px" }}>
          <label class="dim" style=${{ display: "block", fontSize: "12px", marginBottom: "4px" }}>PR / Change Identifier</label>
          <input class="text-input" placeholder="PR-101" value=${customPrId} onInput=${e => setCustomPrId(e.target.value)} />
        </div>
        <button class="btn btn-primary" disabled=${loading || !customPath.trim()} onClick=${() => onRunCustom(customPath.trim(), customPrId.trim())}>
          ${loading === "custom" ? "Analyzing repository…" : "Analyze Repository"}
        </button>
      </div>
    </div>
    <div class="section">
      <div class="section-title">What each scenario demonstrates</div>
      <div class="grid grid-2">
        <div class="card">
          <h3>Safe PR</h3>
          <p class="dim" style=${{ fontSize: "12px" }}>Documentation-only change. All agents converge on low risk with high confidence → AUTO-APPROVE.</p>
        </div>
        <div class="card">
          <h3>SQL Injection PR</h3>
          <p class="dim" style=${{ fontSize: "12px" }}>Security Agent detects a vulnerability, asks Testing Agent for evidence, reassesses upward, Quality Agent challenges about repo conventions → AUTO-REJECT.</p>
        </div>
        <div class="card">
          <h3>Agent Disagreement</h3>
          <p class="dim" style=${{ fontSize: "12px" }}>A real failing regression test conflicts with clean security/quality scans. Orchestrator investigates but evidence stays insufficient → HUMAN REVIEW REQUIRED.</p>
        </div>
        <div class="card">
          <h3>Repair + Revalidate</h3>
          <p class="dim" style=${{ fontSize: "12px" }}>Same vulnerability class as scenario 2. Repair Agent patches it, the FULL pipeline re-runs against the patched tree before "Repair verified" is ever claimed.</p>
        </div>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function MessageItem({ m }) {
  const showReassess = m.type === "REASSESS";
  return html`
    <div class="msg msg-${m.type}">
      <div class="msg-header">
        <span><span class="msg-type">${m.type}</span>
          <span class="msg-parties">${m.sender}${m.receiver ? " → " + m.receiver : ""}</span>
        </span>
        <span>${new Date(m.timestamp * 1000).toLocaleTimeString()}</span>
      </div>
      <div class="msg-body">
        ${m.question ? html`<div><b>Q:</b> ${m.question}</div>` : null}
        ${m.content ? html`<div>${m.content}</div>` : null}
        ${m.reason ? html`<div class="dim">${m.reason}</div>` : null}
      </div>
      ${showReassess ? html`
        <div class="msg-reassess-line">
          risk ${m.risk_before?.toFixed(2)} → ${m.risk_after?.toFixed(2)} &nbsp;|&nbsp;
          confidence ${m.confidence_before?.toFixed(2)} → ${m.confidence_after?.toFixed(2)}
        </div>
      ` : null}
    </div>
  `;
}

function ConversationPage({ run }) {
  if (!run) return html`<div class="empty-state">Run a demo scenario first.</div>`;
  const messages = run.messages || [];
  return html`
    <div class="section">
      <div class="section-title">Complete agent conversation (${messages.length} messages)</div>
      <div class="msg-list">
        ${messages.map((m, i) => html`<${MessageItem} key=${i} m=${m} />`)}
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function FindingsPage({ run }) {
  if (!run) return html`<div class="empty-state">Run a demo scenario first.</div>`;
  const findings = run.findings || [];
  const evidence = run.evidence || [];
  const evidenceById = {};
  evidence.forEach(e => { evidenceById[e.evidence_id] = e; });

  return html`
    <div class="section">
      <div class="section-title">Findings (${findings.length})</div>
      <div class="card">
        <table class="findings">
          <thead><tr>
            <th>Agent</th><th>Title</th><th>Severity</th><th>Risk</th><th>Confidence</th><th>Source</th><th>File</th>
          </tr></thead>
          <tbody>
            ${findings.map(f => html`
              <tr key=${f.finding_id}>
                <td class="mono">${f.agent}</td>
                <td>${f.title}${f.history && f.history.length ? html` <span class="faint">(reassessed ${f.history.length}×)</span>` : null}</td>
                <td><span style=${{ color: SEVERITY_COLOR[f.severity] }}>${f.severity}</span></td>
                <td class="mono">${f.risk.toFixed(2)}</td>
                <td class="mono">${f.confidence.toFixed(2)}</td>
                <td><span class="badge badge-source-${f.source_type}">${f.source_type}</span></td>
                <td class="mono faint">${f.file || "—"}${f.line ? ":" + f.line : ""}</td>
              </tr>
            `)}
          </tbody>
        </table>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Evidence store (${evidence.length})</div>
      <div class="card">
        <table class="findings">
          <thead><tr><th>Agent</th><th>Description</th><th>Tool</th><th>Source</th><th>Strength</th></tr></thead>
          <tbody>
            ${evidence.map(e => html`
              <tr key=${e.evidence_id}>
                <td class="mono">${e.agent}</td>
                <td>${e.description}</td>
                <td class="mono faint">${e.tool || "—"}</td>
                <td><span class="badge badge-source-${e.source_type}">${e.source_type}</span></td>
                <td class="mono">${e.strength.toFixed(2)}</td>
              </tr>
            `)}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function RiskBar({ label, value, weight }) {
  const color = value >= 0.75 ? "var(--danger)" : value >= 0.4 ? "var(--warn)" : "var(--accent)";
  return html`
    <div style=${{ marginBottom: "12px" }}>
      <div style=${{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
        <span>${label} <span class="faint">(weight ${weight})</span></span>
        <span class="mono">${value.toFixed(2)}</span>
      </div>
      <div class="bar-track"><div class="bar-fill" style=${{ width: pct(value), background: color }}></div></div>
    </div>
  `;
}

function DecisionPage({ run }) {
  if (!run) return html`<div class="empty-state">Run a demo scenario first.</div>`;
  const risk = run.state?.risk || {};
  const confidence = run.state?.confidence || {};
  const decision = run.decision;

  return html`
    <${DecisionBanner} decision=${decision} />
    <div class="two-col">
      <div class="section">
        <div class="section-title">Risk breakdown</div>
        <div class="card">
          ${Object.entries(risk.category_scores || {}).map(([cat, val]) => html`
            <${RiskBar} key=${cat} label=${cat} value=${val} weight=${(risk.weights_used || {})[cat]?.toFixed(2) || "—"} />
          `)}
          ${risk.critical_override ? html`
            <div class="dim" style=${{ marginTop: "10px", color: "var(--danger)" }}>
              ⚠ ${risk.critical_reason}
            </div>
          ` : null}
        </div>
      </div>
      <div class="section">
        <div class="section-title">Confidence breakdown</div>
        <div class="card">
          <div class="metric-value" style=${{ marginBottom: "12px" }}>${(confidence.overall || 0).toFixed(2)}</div>
          ${Object.values(confidence.per_finding || {}).slice(0, 1).map((bd, i) => html`
            <div key=${i}>
              ${Object.entries(bd.components || {}).map(([k, v]) => html`
                <div class="kv" key=${k}><span>${k.replace(/_/g, " ")}</span><span>${v >= 0 ? "+" : ""}${v.toFixed(2)}</span></div>
              `)}
            </div>
          `)}
          <p class="faint" style=${{ fontSize: "11px", marginTop: "10px" }}>
            Showing the component breakdown for the first relevant finding. See docs/ARCHITECTURE.md for the full formula.
          </p>
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">Disagreements</div>
      <div class="card">
        ${(run.state?.disagreements || []).length === 0
          ? html`<div class="dim">No disagreement detected between agents.</div>`
          : (run.state.disagreements || []).map((d, i) => html`
              <div key=${i} class="dim" style=${{ marginBottom: "8px" }}>
                <b style=${{ color: "var(--violet)" }}>${d.agent_a}</b> vs <b style=${{ color: "var(--violet)" }}>${d.agent_b}</b>: ${d.reason}
              </div>
            `)}
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function SearchPage({ run }) {
  if (!run) return html`<div class="empty-state">Run a demo scenario first.</div>`;
  const completed = run.state?.completed_actions || [];
  return html`
    <div class="section">
      <div class="section-title">Adaptive investigation — best-first search</div>
      <p class="dim" style=${{ maxWidth: "640px" }}>
        priority(action) = severity × uncertainty × impact / estimated_cost.
        Actions below were popped from the priority queue in the order executed.
      </p>
      <div class="card">
        ${completed.length === 0
          ? html`<div class="dim">No further investigation was needed — initial evidence was already sufficient.</div>`
          : completed.map((a, i) => html`
              <div key=${i} class="investigation-step">
                #${i + 1} <b>${a.type}</b> → ${a.target_agent} &nbsp;
                <span class="faint">priority=${a.priority}</span><br/>
                <span class="dim">${a.description}</span>
              </div>
            `)}
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function PeasPage() {
  const [peas, setPeas] = useState(null);
  useEffect(() => { getJSON("/api/system/peas").then(setPeas); }, []);
  if (!peas) return html`<div class="empty-state">Loading…</div>`;
  const sections = [
    ["P — Performance Measure", peas.performance_measure],
    ["E — Environment", peas.environment],
    ["A — Actuators", peas.actuators],
    ["S — Sensors", peas.sensors],
  ];
  return html`
    <div class="grid grid-2">
      ${sections.map(([title, items]) => html`
        <div class="section" key=${title}>
          <div class="section-title">${title}</div>
          <div class="card">
            <ul class="reason-list">${items.map((it, i) => html`<li key=${i}>${it}</li>`)}</ul>
          </div>
        </div>
      `)}
    </div>
    <div class="section">
      <div class="section-title">Why coordination? (not just Semgrep + averaging)</div>
      <div class="card">
        <div class="two-col">
          <div>
            <b class="dim">Method A — static analysis only</b>
            <pre class="code-block">Semgrep\n  ↓\nFinding</pre>
          </div>
          <div>
            <b class="dim">Method B — independent agents (naive)</b>
            <pre class="code-block">Security  Testing  Quality\n     ↓        ↓        ↓\n        Average score</pre>
          </div>
        </div>
        <b class="dim">Method C — RAMAV (this project)</b>
        <pre class="code-block">Security ↔ Testing ↔ Quality
      ↓
   Evidence → Disagreement detection → Adaptive investigation
      ↓
  Confidence → Risk → Decision (with human-review escalation)</pre>
        <p class="dim" style=${{ fontSize: "13px" }}>
          The contribution is not another detector — it is the coordination and
          decision layer that turns several independent signals into one
          explainable, disagreement-aware, confidence-gated decision.
        </p>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function HealthPage() {
  const [tools, setTools] = useState(null);
  useEffect(() => { getJSON("/api/system/tools").then(setTools); }, []);
  if (!tools) return html`<div class="empty-state">Loading…</div>`;
  return html`
    <div class="section">
      <div class="section-title">Tool availability in this environment</div>
      <div class="card">
        ${Object.entries(tools).map(([name, info]) => html`
          <div class="tool-row" key=${name}>
            <span><span class="dot ${info.available ? "dot-ok" : "dot-off"}"></span>${name}</span>
            <span class="dim mono" style=${{ fontSize: "12px" }}>${info.detail || (info.available ? "available" : "unavailable")}</span>
          </div>
        `)}
      </div>
      <p class="faint" style=${{ fontSize: "12px", marginTop: "10px" }}>
        When a real tool is unavailable, the corresponding agent uses a clearly-labeled
        deterministic fallback — findings are never presented as REAL_TOOL when they are not.
      </p>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function HistoryPage() {
  const [rows, setRows] = useState([]);
  useEffect(() => { getJSON("/api/history").then(setRows); }, []);
  return html`
    <div class="section">
      <div class="section-title">Analysis history (persisted to SQLite)</div>
      <div class="card">
        <table class="findings">
          <thead><tr><th>PR</th><th>Scenario</th><th>Outcome</th><th>Risk</th><th>Confidence</th><th>Duration</th></tr></thead>
          <tbody>
            ${rows.map(r => html`
              <tr key=${r.id}>
                <td class="mono">${r.pr_id}</td>
                <td>${r.scenario}</td>
                <td><span class="badge ${OUTCOME_BADGE[r.decision_outcome] || "badge-neutral"}">${r.decision_outcome}</span></td>
                <td class="mono">${(r.risk ?? 0).toFixed(2)}</td>
                <td class="mono">${(r.confidence ?? 0).toFixed(2)}</td>
                <td class="mono faint">${(r.duration_seconds ?? 0).toFixed(3)}s</td>
              </tr>
            `)}
          </tbody>
        </table>
        ${rows.length === 0 ? html`<div class="empty-state">No runs yet.</div>` : null}
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function RepairPage({ run }) {
  if (!run) return html`<div class="empty-state">Run the repair scenario first.</div>`;
  return html`
    <div class="section">
      <div class="decision-banner ${run.repair_verified ? "approve" : "review"}">
        <div class="decision-outcome">${run.repair_verified ? "REPAIR VERIFIED" : "HUMAN REVIEW REQUIRED"}</div>
      </div>
      <p class="dim">${run.note}</p>
    </div>
    <div class="two-col">
      <div class="section">
        <div class="section-title">Pre-repair decision</div>
        <${DecisionBanner} decision=${run.pre_repair?.decision} />
      </div>
      <div class="section">
        <div class="section-title">Post-repair decision</div>
        ${run.post_repair ? html`<${DecisionBanner} decision=${run.post_repair.decision} />` : html`<div class="dim">No repair was attempted.</div>`}
      </div>
    </div>
    <div class="section">
      <div class="section-title">Patch log</div>
      <div class="card">
        ${(run.patch_log || []).map((p, i) => html`
          <div key=${i} class="dim" style=${{ marginBottom: "6px" }}>
            <span class="mono">${p.file}</span> — ${p.description}
          </div>
        `)}
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
function App() {
  const [tab, setTab] = useState("overview");
  const [run, setRun] = useState(null);
  const [repairRun, setRepairRun] = useState(null);
  const [activeScenario, setActiveScenario] = useState(null);
  const [loading, setLoading] = useState(null);

  const runScenario = useCallback(async (key, path) => {
    setLoading(key);
    try {
      const data = await postJSON(path);
      if (key === "repair") {
        setRepairRun(data);
        setRun(data.post_repair || data.pre_repair);
      } else {
        setRun(data);
      }
      setActiveScenario(key);
      setTab(key === "repair" ? "repair" : "overview");
    } finally {
      setLoading(null);
    }
  }, []);

  const runCustomRepo = useCallback(async (path, prId) => {
    setLoading("custom");
    try {
      const data = await postJSON("/api/analyze/repository", { path, pr_id: prId || "local-pr" });
      if (data.error) {
        alert(data.error);
        return;
      }
      setRun(data);
      setActiveScenario("custom");
      setTab("overview");
    } catch (err) {
      alert("Error analyzing repository: " + err);
    } finally {
      setLoading(null);
    }
  }, []);

  let page;
  if (tab === "overview") page = html`<${OverviewPage} run=${run} />`;
  else if (tab === "demo") page = html`<${DemoPage} onRun=${runScenario} onRunCustom=${runCustomRepo} loading=${loading} activeScenario=${activeScenario} />`;
  else if (tab === "conversation") page = html`<${ConversationPage} run=${run} />`;
  else if (tab === "findings") page = html`<${FindingsPage} run=${run} />`;
  else if (tab === "decision") page = html`<${DecisionPage} run=${run} />`;
  else if (tab === "search") page = html`<${SearchPage} run=${run} />`;
  else if (tab === "peas") page = html`<${PeasPage} />`;
  else if (tab === "health") page = html`<${HealthPage} />`;
  else if (tab === "history") page = html`<${HistoryPage} />`;
  else if (tab === "repair") page = html`<${RepairPage} run=${repairRun} />`;

  const titles = {
    overview: ["Overview", "Live state of the most recent analysis run"],
    demo: ["Demo Scenarios", "Trigger the real backend pipeline against real demo repositories"],
    conversation: ["Agent Conversation", "The complete, persisted message trace between agents"],
    findings: ["Findings & Evidence", "Every finding and its supporting evidence, with provenance"],
    decision: ["Risk & Decision", "How risk, confidence and disagreement produced the final decision"],
    search: ["Investigation Trace", "The best-first search that decided what to investigate next"],
    peas: ["PEAS & Architecture", "Performance measure, environment, actuators, sensors"],
    health: ["System Health", "Which real tools are available in this environment right now"],
    history: ["Analysis History", "Every analysis run persisted this session"],
    repair: ["Repair + Revalidation", "Closed-loop verification — a patch is never trusted on its own"],
  };
  const [title, subtitle] = titles[tab] || titles.overview;

  return html`
    <div class="app-shell">
      <${Sidebar} tab=${tab} setTab=${setTab} />
      <div class="main">
        <h1 class="page-title">${title}</h1>
        <p class="page-subtitle">${subtitle}</p>
        ${page}
      </div>
    </div>
  `;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
