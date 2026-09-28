import { useEffect, useState } from "react";
import { canSendInference, releaseBlocked, witnessClass, type Summary } from "./logic";

const PAGES = ["Overview", "Inference", "Models", "Deployment", "System"] as const;
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
          <Overview summary={summary} />
        ) : null}
        {!loading && summary?.outcome === "ok" && page === "Inference" ? (
          <Inference summary={summary} />
        ) : null}
        {!loading && summary?.outcome === "ok" && page === "Models" ? (
          <Models summary={summary} onChanged={() => void reload()} />
        ) : null}
        {!loading && summary?.outcome === "ok" && page === "Deployment" ? (
          <Deployment summary={summary} onChanged={() => void reload()} />
        ) : null}
        {!loading && summary?.outcome === "ok" && page === "System" ? (
          <System summary={summary} />
        ) : null}
      </main>
    </>
  );
}

function Overview({ summary }: { summary: Summary }) {
  const body = summary.body;
  return (
    <section className="grid">
      <Card title="Build" value={`${body.product_name} ${body.version}`} detail={body.build_id} />
      <Card
        title="Witness"
        value={body.witness.verdict}
        detail={body.witness.reason}
        status={witnessClass(body.witness.verdict)}
      />
      <Card title="Macropath" value={body.chain.macropath} detail={body.chain.basis} />
      <Card title="Model" value={body.chain.model_identity} detail={body.chain.model_identity_kind} />
      <Card title="Instance" value={body.chain.instance_state} detail={body.chain.instance_health} />
      <Card title="Reservation" value={body.chain.reservation_state} detail={body.chain.reservation_id} />
      <Card title="SAFE host bytes" value={body.host.safe_host_bytes} />
      <Card title="SAFE accelerator bytes" value={body.host.safe_accelerator_bytes} />
      <Card title="Physical coverage" value="PHYSICAL_PENDING" detail={body.pending_coverage} />
    </section>
  );
}

function Inference({ summary }: { summary: Summary }) {
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState("");
  const [outcome, setOutcome] = useState("");
  const enabled = canSendInference(summary);
  async function send() {
    const response = await fetch("/v1/inference", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt, max_tokens: 16 }),
    });
    const document = await response.json();
    setOutcome(document.outcome);
    setResult(
      document.outcome === "completed"
        ? `${document.body.text}\n\ntokens ${document.body.completion_tokens ?? "not reported"}`
        : document.reason,
    );
  }
  return (
    <section>
      <p className="muted">
        Operational test through the Rukan seam. The browser does not choose vLLM or Ollama.
        The reply is not stored.
      </p>
      <p>
        Model {summary.body.chain.model_identity} · {summary.body.chain.macropath}
      </p>
      <textarea aria-label="Prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
      <p>
        <button type="button" disabled={!enabled || !prompt.trim()} onClick={() => void send()}>
          Send
        </button>
      </p>
      {!enabled ? <p>No single authorised READY instance. The request will be refused.</p> : null}
      {outcome ? (
        <p className={`status ${witnessClass(outcome === "completed" ? "supported" : "failed")}`}>
          {outcome}
        </p>
      ) : null}
      {result ? <pre>{result}</pre> : null}
    </section>
  );
}

function Models({ summary, onChanged }: { summary: Summary; onChanged: () => void }) {
  const ops = summary.body.model_operations;
  return (
    <section>
      <h2>Stored identities</h2>
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
              <td>{item.kind}</td>
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
  return (
    <section>
      <ol>
        <li>Foundation {chain.foundation_generation_id}</li>
        <li>Model {chain.model_identity}</li>
        <li>Plan {chain.plan_id}</li>
        <li>Reservation {chain.reservation_id} ({chain.reservation_state})</li>
        <li>Instance {chain.instance_id} ({chain.instance_state})</li>
        <li>Proof {chain.proof_id} ({chain.proof_outcome})</li>
        <li>Witness {summary.body.witness.verdict}</li>
      </ol>
      <p className="muted">Chain basis: {chain.basis}. This is not a live badge.</p>
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
      {releaseBlocked(summary) ? <p>Stop before release.</p> : null}
      {message ? <p role="status">{message}</p> : null}
      <details>
        <summary>Evidence identifiers</summary>
        <p>Qualification {chain.qualification_id} ({chain.qualification_outcome})</p>
        <p>Witness {summary.body.witness.witness_id}</p>
      </details>
    </section>
  );
}

function System({ summary }: { summary: Summary }) {
  const host = summary.body.host;
  return (
    <section className="grid">
      <Card title="OS" value={host.os_family} detail={host.architecture} />
      <Card title="Memory evidence" value={host.memory_summary} />
      <Card title="Accelerators" value={host.accelerator_summary} />
      <Card title="Mounts" value={host.mount_summary} />
      <Card title="SAFE host" value={host.safe_host_bytes} detail={host.capacity_observed_at} />
      <Card title="Foundation readiness" value={summary.body.chain.basis} />
      <Card title="Qualification register" value={summary.body.physical_register} detail={summary.body.pending_coverage} />
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
  const [note, setNote] = useState(enabled ? "" : "This operation is not attached.");
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
      {!enabled ? <p>Acquire is not attached.</p> : null}
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
