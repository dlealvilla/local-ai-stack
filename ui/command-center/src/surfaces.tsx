import { useEffect, useState } from "react";

type Envelope<T> = { body: T; reason: string };

async function readJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(path);
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function Portfolio() {
  const [body, setBody] = useState<Record<string, number | string | boolean> | null>(null);
  useEffect(() => {
    void readJson<Envelope<Record<string, number | string | boolean>>>("/v1/portfolio").then((document) => setBody(document?.body ?? null));
  }, []);
  return (
    <section>
      <h1>Deployment portfolio</h1>
      <p className="banner">Report age is not online, offline, or healthy.</p>
      <section className="grid">
        <article className="card"><h2>Known deployments</h2><p>{body?.deployments ?? "not_recorded"}</p></article>
        <article className="card"><h2>Reports, 24h</h2><p>{body?.reports_24h ?? "not_recorded"}</p></article>
        <article className="card"><h2>Reports, 7d</h2><p>{body?.reports_7d ?? "not_recorded"}</p></article>
        <article className="card"><h2>Inside cadence</h2><p>{body?.within_cadence ?? "not_recorded"}</p></article>
        <article className="card"><h2>Later than scheduled</h2><p>{body?.later_than_scheduled ?? "not_recorded"}</p></article>
        <article className="card"><h2>Reported requests</h2><p>{body?.requests ?? "not_recorded"}</p></article>
        <article className="card"><h2>Rejected reports</h2><p>{body?.rejected_reports ?? "not_recorded"}</p></article>
      </section>
    </section>
  );
}

export function ModelLandscape() {
  const [models, setModels] = useState<Record<string, string | number>[]>([]);
  useEffect(() => {
    void readJson<Envelope<{ models: Record<string, string | number>[] }>>("/v1/landscape").then((document) => setModels(document?.body.models ?? []));
  }, []);
  return (
    <section>
      <h1>Model landscape</h1>
      <p className="muted">Usage across imported reports. This is not a marketplace.</p>
      <div className="row">
        {models.map((item) => (
          <article className="card model-card" key={String(item.model_identity)}>
            <h2>{String(item.model_identity)}</h2>
            <p>Deployments {item.deployments}</p>
            <p>Requests {item.requests}</p>
            <p>Output tokens {item.output_tokens}</p>
            <p>Failures {item.failures}</p>
          </article>
        ))}
      </div>
      {models.length === 0 ? <p>No reported model usage yet.</p> : null}
    </section>
  );
}

export function Reporting() {
  const [body, setBody] = useState<{
    accepted: number;
    rejected: number;
    gaps: number;
    recent: { report_id: string; install_id: string; sequence: number; triggers: string; gap: string; key_id: string; received_at: string }[];
    rejection_reasons: { reason: string; n: number }[];
    credentials: { key_id: string; install_id: string; status: string }[];
  } | null>(null);
  useEffect(() => {
    void readJson<Envelope<NonNullable<typeof body>>>("/v1/reporting").then((document) => setBody(document?.body ?? null));
  }, []);
  return (
    <section>
      <h1>Reporting intake</h1>
      <p>Accepted {body?.accepted ?? 0} · Rejected {body?.rejected ?? 0} · Gaps {body?.gaps ?? 0}</p>
      <h2>Credentials</h2>
      <ul>{(body?.credentials ?? []).map((item) => <li key={item.key_id}>{item.key_id} · {item.install_id} · {item.status}</li>)}</ul>
      <h2>Recent reports</h2>
      <table>
        <thead><tr><th>Received</th><th>Install</th><th>Sequence</th><th>Triggers</th><th>Gap</th><th>Key</th></tr></thead>
        <tbody>
          {(body?.recent ?? []).map((item) => (
            <tr key={item.report_id}><td>{item.received_at}</td><td>{item.install_id}</td><td>{item.sequence}</td><td>{item.triggers}</td><td>{item.gap}</td><td>{item.key_id}</td></tr>
          ))}
        </tbody>
      </table>
      <h2>Rejection reasons</h2>
      <ul>{(body?.rejection_reasons ?? []).map((item) => <li key={item.reason}>{item.reason} · {item.n}</li>)}</ul>
    </section>
  );
}

export function CommandSettings() {
  const [installId, setInstallId] = useState("");
  const [keyId, setKeyId] = useState("");
  const [label, setLabel] = useState("");
  const [notice, setNotice] = useState("");
  const [secret, setSecret] = useState("");
  async function act(action: string) {
    const response = await fetch("/v1/credentials", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action, install_id: installId, key_id: keyId }),
    });
    const document = (await response.json()) as { reason: string; body: { secret?: string; key_id?: string } };
    setNotice(document.reason);
    setSecret(document.body.secret ?? "");
    if (document.body.key_id) setKeyId(document.body.key_id);
  }
  return (
    <section>
      <h1>Command Center settings</h1>
      <p className="muted">Aliases stay on this machine. They are not sent back to the deployment.</p>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void fetch("/v1/aliases", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ install_id: installId, label }) }); }}>
        <label>Install id <input value={installId} onChange={(event) => setInstallId(event.target.value)} /></label>
        <label>Local alias <input value={label} onChange={(event) => setLabel(event.target.value)} /></label>
        <button type="submit">Save alias</button>
      </form>
      <h2>Upload credential</h2>
      <p>
        <button type="button" onClick={() => void act("issue")}>Issue key</button>{" "}
        <button type="button" onClick={() => void act("rotate")}>Rotate key</button>{" "}
        <button type="button" onClick={() => void act("revoke")}>Revoke key</button>
      </p>
      <label>Key id <input value={keyId} onChange={(event) => setKeyId(event.target.value)} /></label>
      {secret ? <p role="status">Secret shown once: {secret}</p> : null}
      {notice ? <p>{notice}</p> : null}
      <p className="muted">Intake listens only on its own write-only port. This UI stays on loopback.</p>
    </section>
  );
}
