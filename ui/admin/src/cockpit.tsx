import { useEffect, useState } from "react";
import { formatBytes, readinessHero, type Summary } from "./logic";

type UsageBody = {
  range?: string;
  summary?: {
    requests: number;
    succeeded: number;
    failed: number;
    input_tokens_total: string;
    output_tokens_total: string;
    average_latency_ms: string;
    input_sample_count: number;
    output_sample_count: number;
    latency_sample_count: number;
  };
  groups?: {
    model_identity: string;
    macropath: string;
    purpose: string;
    outcome: string;
    requests: number;
    output_tokens_total: string;
    average_latency_ms: string;
  }[];
};

type LibraryCard = {
  identity: string;
  kind: string;
  family: string;
  generation: string;
  variant: string;
  display_name: string;
  lifecycle: string;
  running: string;
  quantization: string;
};

type Monitoring = {
  enabled: boolean;
  endpoint: string;
  key_id: string;
  credential_status: string;
  cadence_profile: string;
  cadence_seconds: number;
  phase_seconds: number;
  next_report_at: string;
  last_success_at: string;
  queued: number;
  last_error: string;
  categories: string[];
  exclusions: string[];
  deployment_settings: string;
  deployment_settings_reason: string;
};

async function readJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(path);
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function CockpitOverview({ summary, open }: { summary: Summary; open: (page: string) => void }) {
  const body = summary.body;
  const host = formatBytes(body.host.safe_host_bytes);
  const accel = formatBytes(body.host.safe_accelerator_bytes);
  const [usage, setUsage] = useState<UsageBody | null>(null);
  const [monitoring, setMonitoring] = useState<Monitoring | null>(null);
  const [activity, setActivity] = useState<{ action: string; occurred_at: string; outcome: string }[]>([]);
  useEffect(() => {
    void readJson<{ body: UsageBody }>("/v1/usage?range=24h").then((document) => setUsage(document?.body ?? null));
    void readJson<{ body: Monitoring }>("/v1/monitoring").then((document) => setMonitoring(document?.body ?? null));
    void readJson<{ body: { rows: { action: string; occurred_at: string; outcome: string }[] } }>("/v1/activity").then(
      (document) => setActivity(document?.body.rows?.slice(-5) ?? []),
    );
  }, []);
  const facts = usage?.summary;
  return (
    <section>
      <h1 className="hero">{readinessHero(body.chain.basis, body.chain.contradictory, body.witness.verdict)}</h1>
      <p className="muted">This is the stored deployment chain. It is not a live health score.</p>
      <article className="card model-card">
        <p className="muted">Active model</p>
        <h2>{body.chain.model_identity}</h2>
        <p>{body.chain.macropath} · {body.chain.instance_state}</p>
        <p>Qualification {body.chain.qualification_outcome}</p>
      </article>
      <section className="grid">
        <article className="card">
          <h2>Usage, last 24h</h2>
          <p>Requests {facts?.requests ?? "not_recorded"}</p>
          <p>Output tokens {facts?.output_tokens_total ?? "not_recorded"}</p>
          <p>Input tokens {facts?.input_tokens_total ?? "not_recorded"}</p>
          <p>Average latency {facts?.average_latency_ms ?? "not_recorded"} ms ({facts?.latency_sample_count ?? 0} samples)</p>
          <p className="muted">Operator tests and acceptance probes stay separate in Analytics.</p>
        </article>
        <article className="card">
          <h2>Capacity</h2>
          <p>SAFE host memory {host.shown}</p>
          <p>SAFE accelerator memory {accel.shown}</p>
          <p className="muted">Reserved by the current plan when a reservation exists: {body.chain.reservation_state}. Utilization is not measured.</p>
        </article>
        <article className="card">
          <h2>Monitoring</h2>
          <p>{monitoring?.enabled ? "Reporting enabled" : "Reporting disabled"}</p>
          <p>Last success {monitoring?.last_success_at ?? "not_recorded"}</p>
          <p>Next report {monitoring?.next_report_at ?? "not_scheduled"}</p>
          <p>Queued {monitoring?.queued ?? 0}</p>
          <p>{monitoring?.last_error || "No upload error recorded"}</p>
        </article>
      </section>
      <h2>Recent activity</h2>
      {activity.length === 0 ? <p>No exportable activity yet.</p> : (
        <ul>{activity.map((row) => <li key={`${row.occurred_at}-${row.action}`}>{row.occurred_at} · {row.action} · {row.outcome}</li>)}</ul>
      )}
      <p>
        <button type="button" onClick={() => open("Inference")}>Test inference</button>{" "}
        <button type="button" onClick={() => open("Models")}>Browse models</button>{" "}
        <button type="button" onClick={() => open("Deployment")}>View deployment</button>{" "}
        <button type="button" onClick={() => open("Settings")}>Monitoring settings</button>
      </p>
    </section>
  );
}

export function ModelLibrary() {
  const [cards, setCards] = useState<LibraryCard[]>([]);
  const [running, setRunning] = useState<string[]>([]);
  useEffect(() => {
    void readJson<{ body: { cards: LibraryCard[]; collections: { running: string[] } } }>("/v1/models/library").then((document) => {
      setCards(document?.body.cards ?? []);
      setRunning(document?.body.collections.running ?? []);
    });
  }, []);
  const families = new Map<string, LibraryCard[]>();
  for (const card of cards) {
    const family = card.family === "not_recorded" ? "Family not recorded" : card.family;
    families.set(family, [...(families.get(family) ?? []), card]);
  }
  return (
    <section>
      <h1>Models</h1>
      <p className="muted">Each card is one artifact or digest. Cards are not merged.</p>
      <p>Running now: {running.length === 0 ? "none" : running.join(", ")}</p>
      {[...families.entries()].map(([family, members]) => (
        <section key={family}>
          <h2>{family}</h2>
          <div className="row">
            {members.map((card) => (
              <article className="card model-card" key={`${card.kind}-${card.identity}`}>
                <h3>{card.display_name}</h3>
                <p>{card.generation === "not_recorded" ? "Generation not recorded" : card.generation}</p>
                <p>{card.variant === "not_recorded" ? "Variant not recorded" : card.variant}</p>
                <p><span className="badge">{card.lifecycle}</span>{card.running === "true" ? <span className="badge">Running</span> : null}</p>
                <details>
                  <summary>Exact identity</summary>
                  <p>{card.kind}</p>
                  <p>{card.identity}</p>
                  <p>Quantization {card.quantization}</p>
                </details>
              </article>
            ))}
          </div>
        </section>
      ))}
      {cards.length === 0 ? <p>No stored models yet. Inspect, import, or acquire from the forms below when those operations are attached.</p> : null}
    </section>
  );
}

export function UsageAnalytics() {
  const [span, setSpan] = useState("24h");
  const [usage, setUsage] = useState<UsageBody | null>(null);
  useEffect(() => {
    void readJson<{ body: UsageBody }>(`/v1/usage?range=${span}`).then((document) => setUsage(document?.body ?? null));
  }, [span]);
  const facts = usage?.summary;
  return (
    <section>
      <h1>Analytics</h1>
      <p>
        {["24h", "7d", "30d", "all"].map((item) => (
          <button key={item} type="button" aria-current={span === item ? "page" : undefined} onClick={() => setSpan(item)}>{item}</button>
        ))}
      </p>
      <section className="grid">
        <article className="card"><h2>Requests</h2><p>{facts?.requests ?? 0}</p><p>Succeeded {facts?.succeeded ?? 0} · Failed {facts?.failed ?? 0}</p></article>
        <article className="card"><h2>Tokens</h2><p>Input {facts?.input_tokens_total ?? "not_recorded"} ({facts?.input_sample_count ?? 0} samples)</p><p>Output {facts?.output_tokens_total ?? "not_recorded"} ({facts?.output_sample_count ?? 0} samples)</p></article>
        <article className="card"><h2>Latency</h2><p>{facts?.average_latency_ms ?? "not_recorded"} ms average</p><p>{facts?.latency_sample_count ?? 0} samples. This is not TTFT.</p></article>
      </section>
      <table>
        <thead><tr><th>Model</th><th>Runtime</th><th>Purpose</th><th>Outcome</th><th>Requests</th><th>Output tokens</th><th>Average latency</th></tr></thead>
        <tbody>
          {(usage?.groups ?? []).map((row) => (
            <tr key={`${row.model_identity}-${row.purpose}-${row.outcome}`}>
              <td>{row.model_identity}</td><td>{row.macropath}</td><td>{row.purpose}</td><td>{row.outcome}</td>
              <td>{row.requests}</td><td>{row.output_tokens_total}</td><td>{row.average_latency_ms}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function Activity() {
  const [rows, setRows] = useState<{ occurred_at: string; action: string; outcome: string; actor_origin: string; subject: string }[]>([]);
  useEffect(() => {
    void readJson<{ body: { rows: typeof rows } }>("/v1/activity").then((document) => setRows(document?.body.rows ?? []));
  }, []);
  return (
    <section>
      <h1>Activity</h1>
      <p className="muted">Source names the local actor. There is no person identity yet.</p>
      <table>
        <thead><tr><th>When</th><th>Action</th><th>Outcome</th><th>Source</th><th>Subject</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.occurred_at}-${row.action}-${row.subject}`}>
              <td>{row.occurred_at}</td><td>{row.action}</td><td>{row.outcome}</td><td>{row.actor_origin}</td><td>{row.subject}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function MonitoringSettings() {
  const [state, setState] = useState<Monitoring | null>(null);
  const [endpoint, setEndpoint] = useState("");
  const [keyId, setKeyId] = useState("");
  const [secret, setSecret] = useState("");
  const [profile, setProfile] = useState("development");
  const [cadence, setCadence] = useState(120);
  const [enabled, setEnabled] = useState(false);
  const [localTest, setLocalTest] = useState(false);
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState("");
  async function reload() {
    const document = await readJson<{ body: Monitoring }>("/v1/monitoring");
    if (!document) return;
    setState(document.body);
    setEndpoint(document.body.endpoint);
    setProfile(document.body.cadence_profile || "development");
    setCadence(document.body.cadence_seconds || 120);
    setEnabled(document.body.enabled);
    if (document.body.key_id !== "not_configured") setKeyId(document.body.key_id);
  }
  useEffect(() => { void reload(); }, []);
  async function save() {
    const response = await fetch("/v1/monitoring", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        endpoint,
        key_id: keyId,
        secret,
        profile,
        custom_seconds: profile === "custom" ? cadence : undefined,
        enabled,
        local_test: localTest,
      }),
    });
    const document = (await response.json()) as { reason: string };
    setSecret("");
    setNotice(document.reason);
    await reload();
  }
  return (
    <section>
      <h1>Settings</h1>
      <h2>Monitoring and privacy</h2>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <label>Reporting <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /></label>
        <label>Endpoint <input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} /></label>
        <label>Key id <input value={keyId} onChange={(event) => setKeyId(event.target.value)} /></label>
        <label>Secret, entered once <input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} autoComplete="off" /></label>
        <p className="banner">Development reporting cadence — every 2 minutes. Production remains every 6 hours.</p>
        <label>Profile
          <select value={profile} onChange={(event) => setProfile(event.target.value)}>
            <option value="development">Development — every 2 minutes</option>
            <option value="production">Production — every 6 hours</option>
            <option value="custom">Custom</option>
          </select>
        </label>
        {profile === "custom" ? <label>Custom seconds <input type="number" min={60} max={86400} value={cadence} onChange={(event) => setCadence(Number(event.target.value))} /></label> : null}
        <p>Current interval {state?.cadence_seconds ?? 120} seconds. Stable phase {state?.phase_seconds ?? 0} seconds.</p>
        <label>Loopback test HTTP <input type="checkbox" checked={localTest} onChange={(event) => setLocalTest(event.target.checked)} /></label>
        <button type="submit">Save monitoring</button>
      </form>
      <p>Credential {state?.credential_status} · key {state?.key_id}</p>
      <p>Next report {state?.next_report_at} · queued {state?.queued ?? 0}</p>
      <p>Last success {state?.last_success_at}</p>
      <h3>Sent</h3>
      <ul>{(state?.categories ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
      <h3>Never sent</h3>
      <ul>{(state?.exclusions ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
      <p>
        <button type="button" onClick={() => void readJson("/v1/monitoring/preview").then((document) => setPreview(JSON.stringify(document, null, 2)))}>Preview next report</button>{" "}
        <button type="button" onClick={() => void fetch("/v1/monitoring/test", { method: "POST", body: "{}" }).then(() => reload())}>Send test report now</button>
      </p>
      {preview ? <pre>{preview}</pre> : null}
      <h2>Deployment settings</h2>
      <p>{state?.deployment_settings_reason}</p>
      <p className="muted">Context, concurrency, placement, and reserve stay visible on Deployment and System. They are not edited here.</p>
      {notice ? <p>{notice}</p> : null}
    </section>
  );
}

type Person = { user_id: string; display_name: string; email_display: string; status: string };
type Team = { team_id: string; name: string; status: string };

export function People() {
  const [users, setUsers] = useState<Person[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [team, setTeam] = useState("");
  const [notice, setNotice] = useState("");
  async function reload() {
    const document = await readJson<{ body: { users: Person[]; teams: Team[]; banner: string } }>("/v1/people");
    setUsers(document?.body.users ?? []);
    setTeams(document?.body.teams ?? []);
    setNotice(document?.body.banner ?? "");
  }
  useEffect(() => { void reload(); }, []);
  async function post(body: object) {
    await fetch("/v1/people", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    await reload();
  }
  return (
    <section>
      <h1>People</h1>
      <p className="banner">{notice || "Employee login and chat endpoint are not enabled yet. Access settings here prepare future provisioning."}</p>
      <p>{users.filter((item) => item.status === "active").length} active users · {teams.length} teams</p>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void post({ action: "create_user", email, display_name: name }); }}>
        <label>Name <input value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>Email <input value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <button type="submit">Add user</button>
      </form>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void post({ action: "create_team", name: team, description: "" }); }}>
        <label>Team <input value={team} onChange={(event) => setTeam(event.target.value)} /></label>
        <button type="submit">Add team</button>
      </form>
      <h2>Users</h2>
      <table>
        <thead><tr><th>Name</th><th>Email</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.user_id}>
              <td>{user.display_name}</td>
              <td>{user.email_display}</td>
              <td>{user.status}</td>
              <td>
                <button type="button" onClick={() => void post({ action: "set_status", user_id: user.user_id, status: user.status === "active" ? "suspended" : "active" })}>Suspend or reactivate</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Teams</h2>
      <ul>{teams.map((item) => <li key={item.team_id}>{item.name} · {item.status}</li>)}</ul>
      <p className="muted">Configured — enforcement begins when the employee gateway is enabled. This directory is not sent to Command Center.</p>
    </section>
  );
}
