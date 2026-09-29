import { useEffect, useState } from "react";
import { Activity, CockpitOverview, ModelLibrary, MonitoringSettings, UsageAnalytics } from "./cockpit";
import {
  canSendInference,
  formatBytes,
  modelKindLabel,
  releaseBlocked,
  usabilityLabel,
  witnessClass,
  type Summary,
} from "./logic";

const PAGES = ["Overview", "Models", "Deployment", "Inference", "Analytics", "Activity", "System", "Settings"] as const;
type Page = (typeof PAGES)[number];

export function App() {
  const [page, setPage] = useState<Page>("Overview");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function reload() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/v1/summary");
      const document = (await response.json()) as Summary;
      setSummary(document);
    } catch {
      setError("Rukan Admin could not read the loopback seam.");
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  return (
    <>
      <header>
        <strong>Rukan Admin</strong>
        <nav aria-label="Admin sections">
          {PAGES.map((item) => (
            <button
              key={item}
              type="button"
              aria-current={page === item ? "page" : undefined}
              onClick={() => setPage(item)}
            >
              {item}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {loading ? <p>Loading stored deployment evidence.</p> : null}
        {error ? <p role="alert">{error}</p> : null}
        {!loading && !error && summary?.outcome !== "ok" ? (
          <p role="alert">{summary?.reason ?? "The seam refused the summary."}</p>
        ) : null}
        {!loading && summary?.outcome === "ok" && page === "Overview" ? (
          <CockpitOverview summary={summary} open={(next) => {
            if ((PAGES as readonly string[]).includes(next)) setPage(next as Page);
          }} />
        ) : null}
        {!loading && summary?.outcome === "ok" && page === "Inference" ? (
          <Inference summary={summary} />
        ) : null}
        {!loading && summary?.outcome === "ok" && page === "Models" ? (
          <>
            <ModelLibrary />
            <Models summary={summary} onChanged={() => void reload()} />
          </>
        ) : null}
        {!loading && summary?.outcome === "ok" && page === "Deployment" ? (
          <Deployment summary={summary} onChanged={() => void reload()} />
        ) : null}
        {!loading && summary?.outcome === "ok" && page === "System" ? (
          <System summary={summary} />
        ) : null}
        {!loading && page === "Analytics" ? <><UsageAnalytics /><Analytics /></> : null}
        {!loading && page === "Activity" ? <Activity /> : null}
        {!loading && page === "Settings" ? <MonitoringSettings /> : null}
      </main>
    </>
  );
}

function Inference({ summary }: { summary: Summary }) {
  const [prompt, setPrompt] = useState("");
  const [maxTokens, setMaxTokens] = useState(16);
  const [result, setResult] = useState("");
  const [tokens, setTokens] = useState("");
  const [elapsed, setElapsed] = useState("");
  const [outcome, setOutcome] = useState("");
  const [busy, setBusy] = useState(false);
  const enabled = canSendInference(summary);
  async function send() {
    if (busy) return;
    setBusy(true);
    setOutcome("");
    setResult("");
    setTokens("");
    setElapsed("");
    try {
      const response = await fetch("/v1/inference", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt, max_tokens: maxTokens }),
      });
      const document = await response.json();
      setOutcome(document.outcome);
      if (document.outcome === "completed") {
        setResult(String(document.body.text ?? ""));
        const count = document.body.completion_tokens;
        setTokens(typeof count === "number" ? `${count} completion tokens` : "completion tokens not reported");
        const seconds = document.body.elapsed_seconds;
        setElapsed(typeof seconds === "number" ? `elapsed ${seconds}s` : "");
      } else {
        setResult(String(document.reason ?? "refused"));
      }
    } catch {
      setOutcome("failed");
      setResult("The loopback seam did not answer.");
    } finally {
      setBusy(false);
    }
  }
  function clear() {
    setPrompt("");
    setResult("");
    setTokens("");
    setElapsed("");
    setOutcome("");
  }
  return (
    <section>
      <h1>Inference test</h1>
      <p className="muted">
        Operational test through the Rukan seam. The browser does not choose vLLM or Ollama.
        The reply is not stored.
      </p>
      <p>
        Model {summary.body.chain.model_identity} · macropath {summary.body.chain.macropath}
      </p>
      <textarea aria-label="Prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
      <p>
        <label>
          Max tokens{" "}
          <input
            aria-label="Max tokens"
            type="number"
            min={1}
            max={64}
            value={maxTokens}
            onChange={(event) => setMaxTokens(Number(event.target.value))}
          />
        </label>
      </p>
      <p>
        <button type="button" disabled={!enabled || !prompt.trim() || busy || maxTokens < 1 || maxTokens > 64} onClick={() => void send()}>
          {busy ? "Sending" : "Send"}
        </button>{" "}
        <button type="button" onClick={clear} disabled={busy}>
          Clear
        </button>
      </p>
      {busy ? <p role="status">Request in progress.</p> : null}
      {!enabled ? <p>No single authorised READY instance. Send stays disabled.</p> : null}
      {outcome ? (
        <p className={`status ${witnessClass(outcome === "completed" ? "supported" : "failed")}`} role="status">
          {outcome}
        </p>
      ) : null}
      {result ? <pre>{result}</pre> : null}
      {tokens ? <p>{tokens}</p> : null}
      {elapsed ? <p>{elapsed}</p> : null}
    </section>
  );
}

function Models({ summary, onChanged }: { summary: Summary; onChanged: () => void }) {
  const ops = summary.body.model_operations;
  return (
    <section>
      <h1>Models</h1>
      <p className="muted">Warehouse artifacts and provider digests stay separate. This is not a marketplace.</p>
      {summary.body.models.length === 0 ? <p>No stored model identity.</p> : null}
      <table>
        <thead>
          <tr>
            <th>Identity</th>
            <th>Kind</th>
            <th>Revision or outcome</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {summary.body.models.map((item) => (
            <tr key={`${item.kind}:${item.identity}`}>
              <td>{item.identity}</td>
              <td>{modelKindLabel(item.kind)}</td>
              <td>{item.revision}</td>
              <td>{item.lifecycle}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ModelForm
        title="Inspect local metadata"
        enabled={ops.inspect_local}
        pathLabel
        onSubmit={async (fields) => postModel("/v1/models/inspect", fields, onChanged)}
      />
      <ModelForm
        title="Import into the warehouse"
        enabled={ops.import_local}
        pathLabel
        onSubmit={async (fields) => postModel("/v1/models/import", fields, onChanged)}
      />
      <HubForm enabled={ops.acquire_hub} onChanged={onChanged} />
    </section>
  );
}

function Deployment({ summary, onChanged }: { summary: Summary; onChanged: () => void }) {
  const chain = summary.body.chain;
  const [message, setMessage] = useState("");
  const life = summary.body.lifecycle;
  async function act(path: string) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    });
    const document = await response.json();
    setMessage(`${document.outcome}: ${document.reason}`);
    onChanged();
  }
  const steps = [
    ["Foundation", "The execution foundation that was selected.", chain.foundation_generation_id],
    ["Model", modelKindLabel(chain.model_identity_kind), chain.model_identity],
    ["Plan", "The desired deployment. It does not reserve or start.", chain.plan_id],
    ["Reservation", `Hold is ${chain.reservation_state}. Stop does not release it.`, chain.reservation_id],
    ["Instance", `Serving state is ${chain.instance_state}.`, chain.instance_id],
    ["Inference evidence", `Proof outcome is ${chain.proof_outcome}.`, chain.proof_id],
    ["Witness", summary.body.witness.reason, summary.body.witness.verdict],
  ] as const;
  return (
    <section>
      <h1>Deployment journey</h1>
      <p className="muted">{usabilityLabel(chain.basis, chain.contradictory)}</p>
      <ol>
        {steps.map(([title, meaning, value]) => (
          <li key={title}>
            <strong>{title}</strong>
            <p>{meaning}</p>
            <p>{value}</p>
            <details>
              <summary>Technical detail</summary>
              <p>{value}</p>
            </details>
          </li>
        ))}
      </ol>
      <p>
        <button type="button" disabled={!life.stop_attached} onClick={() => void act("/v1/lifecycle/stop")}>
          Stop
        </button>{" "}
        <button
          type="button"
          disabled={!life.release_attached || releaseBlocked(summary)}
          onClick={() => void act("/v1/lifecycle/release")}
        >
          Release
        </button>
      </p>
      {releaseBlocked(summary) ? <p>Stop before release. The reservation stays held.</p> : null}
      {!life.stop_attached ? <p>Stop is not attached to the serving lifecycle.</p> : null}
      {message ? <p role="status">{message}</p> : null}
      <details>
        <summary>Qualification</summary>
        <p>
          {chain.qualification_id} · {chain.qualification_outcome}
        </p>
      </details>
    </section>
  );
}

function System({ summary }: { summary: Summary }) {
  const host = summary.body.host;
  const safeHost = formatBytes(host.safe_host_bytes);
  const safeAccel = formatBytes(host.safe_accelerator_bytes);
  return (
    <section>
      <h1>System</h1>
      <h2>Observed hardware</h2>
      <section className="grid">
        <Card title="OS" value={host.os_family} detail={host.architecture} />
        <Card title="Memory evidence" value={host.memory_summary} />
        <Card title="Accelerators" value={host.accelerator_summary} />
        <Card title="Mounts" value={host.mount_summary} />
      </section>
      <h2>SAFE capacity</h2>
      <p className="muted">Planning ceilings. Not current utilisation.</p>
      <section className="grid">
        <Card title="SAFE host memory" value={safeHost.shown} detail={`${safeHost.exact} · observed ${host.capacity_observed_at}`} />
        <Card title="SAFE accelerator memory" value={safeAccel.shown} detail={safeAccel.exact} />
        <Card title="Physical qualification" value={summary.body.physical_register} detail={summary.body.pending_coverage} />
      </section>
    </section>
  );
}

function Analytics() {
  const [body, setBody] = useState<Record<string, unknown> | null>(null);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    void fetch("/v1/analytics")
      .then((response) => response.json())
      .then((document) => setBody(document.body))
      .catch(() => setFailed("Local analytics could not be read."));
  }, []);
  if (failed) return <p role="alert">{failed}</p>;
  if (!body) return <p>Loading local analytics.</p>;
  const missing = Array.isArray(body.missing) ? body.missing : [];
  return (
    <section>
      <h1>Local analytics</h1>
      <p className="muted">Facts from this deployment's journal and proofs. Not a vendor export.</p>
      <section className="grid">
        <article className="card">
          <p className="muted">Inference proofs</p>
          <p>{String(body.inference_proof_count ?? "not_recorded")}</p>
        </article>
        <article className="card">
          <p className="muted">Proven</p>
          <p>{String(body.inference_proven ?? "not_recorded")}</p>
        </article>
        <article className="card">
          <p className="muted">Failed</p>
          <p>{String(body.inference_failed ?? "not_recorded")}</p>
        </article>
        <article className="card">
          <p className="muted">Reported completion tokens</p>
          <p>{String(body.completion_tokens_reported ?? "not_recorded")}</p>
        </article>
      </section>
      <h2>Not recorded</h2>
      <ul>
        {missing.map((item) => (
          <li key={String(item)}>{String(item)}</li>
        ))}
      </ul>
      <h2>Recent events</h2>
      <pre>{JSON.stringify(body.timeline ?? [], null, 2)}</pre>
    </section>
  );
}

function Card({
  title,
  value,
  detail,
  status,
}: {
  title: string;
  value: string;
  detail?: string;
  status?: string;
}) {
  return (
    <article className="card">
      <p className="muted">{title}</p>
      <p className={status ? `status ${status}` : undefined}>{value}</p>
      {detail ? <p className="muted">{detail}</p> : null}
    </article>
  );
}

function ModelForm({
  title,
  enabled,
  pathLabel,
  onSubmit,
}: {
  title: string;
  enabled: boolean;
  pathLabel?: boolean;
  onSubmit: (fields: { source_path: string; label: string }) => Promise<void>;
}) {
  const [source, setSource] = useState("");
  const [label, setLabel] = useState("");
  const [note, setNote] = useState(
    enabled ? "" : "Unavailable. This operation is not attached to the loopback process.",
  );
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit({ source_path: source, label }).then(() => setNote("Submitted."));
      }}
    >
      <h3>{title}</h3>
      {pathLabel ? (
        <p>
          <label>
            Directory{" "}
            <input aria-label={`${title} directory`} value={source} onChange={(event) => setSource(event.target.value)} />
          </label>
        </p>
      ) : null}
      <p>
        <label>
          Label{" "}
          <input aria-label={`${title} label`} value={label} onChange={(event) => setLabel(event.target.value)} />
        </label>
      </p>
      <button type="submit" disabled={!enabled}>
        Run
      </button>
      {note ? <p>{note}</p> : null}
    </form>
  );
}

function HubForm({ enabled, onChanged }: { enabled: boolean; onChanged: () => void }) {
  const [repository, setRepository] = useState("");
  const [revision, setRevision] = useState("");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void postModel("/v1/models/acquire", { repository, revision }, onChanged);
      }}
    >
      <h3>Acquire one hub revision</h3>
      <p className="muted">Not a marketplace. One repository and revision.</p>
      <p>
        <label>
          Repository <input aria-label="Repository" value={repository} onChange={(event) => setRepository(event.target.value)} />
        </label>
      </p>
      <p>
        <label>
          Revision <input aria-label="Revision" value={revision} onChange={(event) => setRevision(event.target.value)} />
        </label>
      </p>
      <button type="submit" disabled={!enabled}>
        Acquire
      </button>
      {!enabled ? <p>Unavailable. Acquire is not attached to the loopback process.</p> : null}
    </form>
  );
}

async function postModel(path: string, body: object, onChanged: () => void) {
  await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  onChanged();
}
