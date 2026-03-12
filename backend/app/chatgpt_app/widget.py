"""Static widget HTML for the ChatGPT app."""

from __future__ import annotations


def build_widget_html(default_view: str = "query") -> str:
    title = (
        "Constitutional AI Operator Dashboard"
        if default_view == "operator"
        else "Constitutional AI Query Report"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #efe6d6;
        --panel: rgba(255, 251, 243, 0.88);
        --panel-strong: #fffdf8;
        --ink: #1c2822;
        --muted: #55645d;
        --line: rgba(28, 40, 34, 0.12);
        --accent: #0f6a58;
        --accent-soft: rgba(15, 106, 88, 0.12);
        --warn: #875b1a;
        --shadow: 0 20px 40px rgba(25, 34, 30, 0.1);
        font-family: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
      }}
      * {{
        box-sizing: border-box;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(15, 106, 88, 0.18), transparent 30%),
          radial-gradient(circle at top right, rgba(135, 91, 26, 0.12), transparent 26%),
          linear-gradient(180deg, #f7f0e2 0%, var(--bg) 56%, #e8dcc8 100%);
      }}
      main {{
        max-width: 1080px;
        margin: 0 auto;
        padding: 18px;
      }}
      .shell {{
        border: 1px solid var(--line);
        border-radius: 28px;
        overflow: hidden;
        background: rgba(255, 255, 255, 0.4);
        box-shadow: var(--shadow);
        backdrop-filter: blur(10px);
      }}
      header {{
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 16px;
        padding: 22px;
        border-bottom: 1px solid var(--line);
        background:
          linear-gradient(135deg, rgba(15, 106, 88, 0.16), transparent 52%),
          linear-gradient(180deg, rgba(255, 255, 255, 0.8), rgba(255, 251, 243, 0.9));
      }}
      .eyebrow {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 11px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid rgba(15, 106, 88, 0.16);
        font-size: 0.8rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }}
      h1 {{
        margin: 10px 0 6px;
        font-size: clamp(1.6rem, 3vw, 2.35rem);
        line-height: 1.02;
        font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
      }}
      .lede {{
        margin: 0;
        max-width: 66ch;
        color: var(--muted);
        line-height: 1.55;
      }}
      .actions {{
        display: flex;
        align-items: start;
        gap: 10px;
        flex-wrap: wrap;
      }}
      button {{
        appearance: none;
        border: 0;
        border-radius: 999px;
        padding: 11px 16px;
        font: inherit;
        font-weight: 650;
        cursor: pointer;
        transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
      }}
      button:hover {{
        transform: translateY(-1px);
      }}
      button.primary {{
        color: white;
        background: linear-gradient(135deg, #0f6a58, #194f46);
        box-shadow: 0 10px 22px rgba(15, 106, 88, 0.22);
      }}
      button.secondary {{
        color: var(--ink);
        background: rgba(255, 255, 255, 0.78);
        border: 1px solid var(--line);
      }}
      .grid {{
        display: grid;
        gap: 14px;
        padding: 18px;
        grid-template-columns: repeat(12, minmax(0, 1fr));
      }}
      section {{
        grid-column: span 12;
        padding: 18px;
        border-radius: 22px;
        background: var(--panel);
        border: 1px solid var(--line);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
      }}
      section.hero {{
        background:
          linear-gradient(135deg, rgba(15, 106, 88, 0.08), rgba(255, 255, 255, 0.92)),
          var(--panel);
      }}
      @media (min-width: 860px) {{
        section.split {{
          grid-column: span 6;
        }}
      }}
      h2 {{
        margin: 0 0 8px;
        font-size: 1rem;
        letter-spacing: 0.03em;
        text-transform: uppercase;
      }}
      .subtle {{
        margin: 0;
        color: var(--muted);
        font-size: 0.92rem;
      }}
      .kpis {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 14px;
      }}
      .pill {{
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 7px 11px;
        border-radius: 999px;
        background: var(--panel-strong);
        border: 1px solid var(--line);
        font-size: 0.86rem;
      }}
      .answer {{
        margin-top: 16px;
        padding: 16px;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.74);
        border: 1px solid rgba(15, 106, 88, 0.12);
        line-height: 1.6;
        white-space: pre-wrap;
      }}
      ol, ul {{
        margin: 12px 0 0;
        padding-left: 20px;
      }}
      li + li {{
        margin-top: 10px;
      }}
      .source-title {{
        display: block;
        font-weight: 700;
      }}
      .source-meta, code, pre {{
        font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
      }}
      .source-meta {{
        color: var(--muted);
        font-size: 0.82rem;
      }}
      pre {{
        margin: 12px 0 0;
        padding: 14px;
        overflow: auto;
        font-size: 0.84rem;
        line-height: 1.45;
        border-radius: 16px;
        background: #f9f4ea;
        border: 1px solid rgba(28, 40, 34, 0.08);
      }}
      .empty {{
        margin-top: 12px;
        color: var(--muted);
        font-style: italic;
      }}
      .status-good {{
        color: var(--accent);
      }}
      .status-warn {{
        color: var(--warn);
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="shell">
        <header>
          <div>
            <div class="eyebrow">Internal operator app</div>
            <h1>{title}</h1>
            <p class="lede">
              Query results, runtime health, project understanding, and operator jobs
              rendered through the MCP Apps bridge.
            </p>
          </div>
          <div class="actions">
            <button id="refresh-button" class="primary" type="button">Refresh</button>
            <button id="expand-button" class="secondary" type="button">Expand</button>
          </div>
        </header>

        <div class="grid">
          <section class="hero">
            <h2>Bridge Status</h2>
            <p id="bridge-status" class="subtle">Waiting for ui/notifications/tool-result...</p>
            <div id="summary-kpis" class="kpis"></div>
            <div id="answer-box" class="answer">No tool result yet.</div>
          </section>

          <section class="split">
            <h2>Sources</h2>
            <p class="subtle">Rendered from widget-only `_meta.sources` when available.</p>
            <div id="sources-panel" class="empty">No sources yet.</div>
          </section>

          <section class="split">
            <h2>Runtime</h2>
            <p class="subtle">Health, readiness, model, and collection status.</p>
            <div id="runtime-panel" class="empty">No runtime snapshot yet.</div>
          </section>

          <section class="split">
            <h2>Project Insights</h2>
            <p class="subtle">Architecture summary, risks, and next-step planning.</p>
            <div id="project-panel" class="empty">No project snapshot yet.</div>
          </section>

          <section class="split">
            <h2>Jobs</h2>
            <p class="subtle">Background diagnostics and corpus operation state.</p>
            <div id="jobs-panel" class="empty">No job status yet.</div>
          </section>

          <section>
            <h2>Widget-only metadata</h2>
            <p class="subtle">Useful for debugging bridge payloads without exposing them to the model.</p>
            <pre id="meta-content">No widget metadata yet.</pre>
          </section>
        </div>
      </div>
    </main>

    <script type="module">
      const statusEl = document.getElementById("bridge-status");
      const answerEl = document.getElementById("answer-box");
      const kpisEl = document.getElementById("summary-kpis");
      const sourcesEl = document.getElementById("sources-panel");
      const runtimeEl = document.getElementById("runtime-panel");
      const projectEl = document.getElementById("project-panel");
      const jobsEl = document.getElementById("jobs-panel");
      const metaEl = document.getElementById("meta-content");
      const refreshButton = document.getElementById("refresh-button");
      const expandButton = document.getElementById("expand-button");

      let rpcId = 0;
      let currentView = "{default_view}";
      let latestToolInput = null;
      let latestToolOutput = null;
      let latestToolMeta = null;

      function escapeHtml(value) {{
        return String(value ?? "")
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;");
      }}

      function listMarkup(items, renderItem) {{
        if (!Array.isArray(items) || items.length === 0) {{
          return '<div class="empty">No data available.</div>';
        }}
        return `<ol>${{items.map(renderItem).join("")}}</ol>`;
      }}

      function renderKpis(pairs) {{
        const html = pairs
          .filter(([, value]) => value !== undefined && value !== null && value !== "")
          .map(([label, value]) => `<div class="pill"><strong>${{escapeHtml(label)}}:</strong> ${{escapeHtml(value)}}</div>`)
          .join("");
        kpisEl.innerHTML = html || '<div class="empty">No summary metrics yet.</div>';
      }}

      function renderSources(sources) {{
        if (!Array.isArray(sources) || sources.length === 0) {{
          sourcesEl.innerHTML = '<div class="empty">No sources yet.</div>';
          return;
        }}
        sourcesEl.innerHTML = `<ol>${{sources.map((source) => `
          <li>
            <span class="source-title">${{escapeHtml(source.title || source.id || "Untitled source")}}</span>
            <div class="source-meta">
              score=${{escapeHtml(source.score ?? "n/a")}}
              | source=${{escapeHtml(source.source ?? "unknown")}}
              | type=${{escapeHtml(source.doc_type ?? "unknown")}}
            </div>
            <div>${{escapeHtml(source.snippet || "No snippet available.")}}</div>
          </li>
        `).join("")}}</ol>`;
      }}

      function renderRuntime(runtime) {{
        if (!runtime) {{
          runtimeEl.innerHTML = '<div class="empty">No runtime snapshot yet.</div>';
          return;
        }}
        const checks = runtime.readiness?.checks ?? {{}};
        const checkLines = Object.entries(checks).map(([name, check]) =>
          `<li><strong>${{escapeHtml(name)}}</strong>: ${{escapeHtml(check?.status ?? "unknown")}}</li>`
        ).join("");
        runtimeEl.innerHTML = `
          <div class="kpis">
            <div class="pill"><strong>Status:</strong> ${{escapeHtml(runtime.readiness?.status ?? runtime.status ?? "unknown")}}</div>
            <div class="pill"><strong>Model:</strong> ${{escapeHtml(runtime.config?.constitutional_model ?? "unknown")}}</div>
            <div class="pill"><strong>Collections:</strong> ${{escapeHtml((runtime.collections || []).length)}}</div>
          </div>
          <ul>${{checkLines || "<li>No readiness checks available.</li>"}}</ul>
        `;
      }}

      function renderProject(project) {{
        if (!project) {{
          projectEl.innerHTML = '<div class="empty">No project snapshot yet.</div>';
          return;
        }}
        const summary = listMarkup(project.architecture_summary, (item) =>
          `<li>${{escapeHtml(item)}}</li>`
        );
        const nextSteps = listMarkup(project.next_steps, (item) =>
          `<li>${{escapeHtml(item)}}</li>`
        );
        const risks = listMarkup(project.risks, (item) =>
          `<li>${{escapeHtml(item)}}</li>`
        );
        projectEl.innerHTML = `
          <div class="kpis">
            <div class="pill"><strong>Docs:</strong> ${{escapeHtml((project.canonical_docs || []).length)}}</div>
            <div class="pill"><strong>Signals:</strong> ${{escapeHtml((project.frontend_signals || []).length)}}</div>
          </div>
          <h3>Architecture</h3>
          ${{summary}}
          <h3>Next steps</h3>
          ${{nextSteps}}
          <h3>Risks</h3>
          ${{risks}}
        `;
      }}

      function renderJob(toolOutput, toolMeta) {{
        const jobId = toolOutput?.job_id ?? toolMeta?.id ?? toolMeta?.job_id;
        if (!jobId && !toolMeta?.status) {{
          jobsEl.innerHTML = '<div class="empty">No job status yet.</div>';
          return;
        }}
        jobsEl.innerHTML = `
          <div class="kpis">
            <div class="pill"><strong>Job:</strong> ${{escapeHtml(jobId ?? "n/a")}}</div>
            <div class="pill"><strong>Status:</strong> ${{escapeHtml(toolOutput?.status ?? toolMeta?.status ?? "unknown")}}</div>
            <div class="pill"><strong>Operation:</strong> ${{escapeHtml(toolOutput?.operation ?? toolMeta?.operation ?? "n/a")}}</div>
          </div>
          <pre>${{escapeHtml(JSON.stringify(toolMeta ?? {{}}, null, 2))}}</pre>
        `;
      }}

      function applyToolResult(toolResult) {{
        latestToolOutput = toolResult?.structuredContent ?? null;
        latestToolMeta = toolResult?._meta ?? null;

        currentView = latestToolOutput?.view ?? latestToolMeta?.ui?.defaultView ?? currentView;
        const answer =
          latestToolOutput?.answer
          ?? latestToolOutput?.architecture_summary?.join("\\n")
          ?? latestToolMeta?.project?.architecture_summary?.join("\\n")
          ?? "No narrative content returned yet.";

        const kpis = [
          ["View", currentView],
          ["Evidence", latestToolOutput?.evidence_level],
          ["Sources", latestToolOutput?.source_count ?? latestToolMeta?.sources?.length],
          ["Mode", latestToolOutput?.mode],
          ["Model", latestToolMeta?.runtime?.config?.constitutional_model ?? latestToolOutput?.constitutional_model],
          ["Runtime", latestToolOutput?.runtime_status ?? latestToolMeta?.runtime?.readiness?.status],
        ];

        renderKpis(kpis);
        answerEl.textContent = answer;
        renderSources(latestToolMeta?.sources);
        renderRuntime(latestToolMeta?.runtime ?? (latestToolOutput?.runtime_status ? {{
          readiness: {{ status: latestToolOutput.runtime_status }},
          config: {{ constitutional_model: latestToolOutput.constitutional_model }},
          collections: [],
        }} : null));
        renderProject(latestToolMeta?.project ?? (latestToolOutput?.next_steps ? {{
          architecture_summary: latestToolOutput.architecture_summary ?? [],
          next_steps: latestToolOutput.next_steps ?? [],
          risks: [],
          canonical_docs: [],
          frontend_signals: [],
        }} : null));
        renderJob(latestToolOutput, latestToolMeta);
        metaEl.textContent = JSON.stringify(latestToolMeta ?? null, null, 2);
      }}

      function rpcRequest(method, params) {{
        return new Promise((resolve, reject) => {{
          const id = ++rpcId;
          const handleMessage = (event) => {{
            if (event.source !== window.parent) return;
            const message = event.data;
            if (!message || message.jsonrpc !== "2.0" || message.id !== id) return;
            window.removeEventListener("message", handleMessage);
            if (message.error) {{
              reject(message.error);
            }} else {{
              resolve(message.result);
            }}
          }};
          window.addEventListener("message", handleMessage, {{ passive: true }});
          window.parent.postMessage({{ jsonrpc: "2.0", id, method, params }}, "*");
        }});
      }}

      async function callTool(name, args) {{
        if (window.openai?.callTool) {{
          return window.openai.callTool(name, args);
        }}
        return rpcRequest("tools/call", {{ name, arguments: args }});
      }}

      async function refreshCurrentView() {{
        statusEl.textContent = "Calling tools/call via bridge…";
        try {{
          let result;
          if (currentView === "query" && (latestToolInput?.question || window.openai?.toolInput?.question)) {{
            const question = latestToolInput?.question ?? window.openai?.toolInput?.question;
            result = await callTool("render_query_report", {{
              question,
              mode: latestToolInput?.mode ?? window.openai?.toolInput?.mode ?? "auto",
              retrieval_strategy:
                latestToolInput?.retrieval_strategy
                ?? window.openai?.toolInput?.retrieval_strategy
                ?? "adaptive",
              use_agent: latestToolInput?.use_agent ?? window.openai?.toolInput?.use_agent ?? false,
            }});
          }} else {{
            result = await callTool("render_operator_dashboard", {{}});
          }}
          statusEl.textContent = "Received tools/call result.";
          applyToolResult(result);
        }} catch (error) {{
          statusEl.textContent = `tools/call failed: ${{JSON.stringify(error)}}`;
        }}
      }}

      window.addEventListener("message", (event) => {{
        if (event.source !== window.parent) return;
        const message = event.data;
        if (!message || message.jsonrpc !== "2.0") return;

        if (message.method === "ui/notifications/tool-input") {{
          latestToolInput = message.params ?? null;
          return;
        }}

        if (message.method === "ui/notifications/tool-result") {{
          statusEl.textContent = "Received ui/notifications/tool-result";
          applyToolResult(message.params ?? null);
        }}
      }}, {{ passive: true }});

      refreshButton.addEventListener("click", refreshCurrentView);
      expandButton.addEventListener("click", async () => {{
        if (!window.openai?.requestDisplayMode) return;
        await window.openai.requestDisplayMode({{ mode: "fullscreen" }});
      }});

      if (window.openai?.toolInput) {{
        latestToolInput = window.openai.toolInput;
      }}
      if (window.openai?.toolOutput || window.openai?.toolResponseMetadata) {{
        applyToolResult({{
          structuredContent: window.openai.toolOutput ?? null,
          _meta: window.openai.toolResponseMetadata ?? null,
        }});
      }}
    </script>
  </body>
</html>
"""
