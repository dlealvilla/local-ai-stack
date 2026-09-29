import { useEffect, useState } from "react";
import type { SupportSnapshot } from "../../shared/snapshot";
import { cadenceLabel, cadenceText, filterRows, history, reportAge, snapshotAge, type DeploymentRow } from "./query";
import { CommandSettings, ModelLandscape, Portfolio, Reporting } from "./surfaces";

const PAGES = ["Overview", "Deployments", "Detail", "Analytics", "Models", "Reporting", "Settings", "Import"] as const;
type Page = (typeof PAGES)[number];

type Status = {
  last_refresh: string;
  last_imported: number;
  last_rejected: number;
  live_claim: boolean;
};

type DetailBody = {
  snapshots: SupportSnapshot[];
  events: { event_id: string; event_type: string; occurred_at: string; outcome: string; block_id: string }[];
  inferences: { proof_id: string; outcome: string; completion_tokens: string; failure: string; model_identity: string }[];
  reports?: { report_id: string; sequence: number; received_at: string; generated_at: string; triggers: string; gap: string; key_id: string }[];
};

export function App() {
  const [page, setPage] = useState<Page>("Overview");
  const [rows, setRows] = useState<DeploymentRow[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [selected, setSelected] = useState("");
  const [snapshotId, setSnapshotId] = useState("");
  const [detail, setDetail] = useState<DetailBody | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function reload() {
    const statusResponse = await fetch("/v1/status");
    const statusDocument = await statusResponse.json();
    setStatus(statusDocument.body);
    const listResponse = await fetch("/v1/deployments");
    const listDocument = await listResponse.json();
    setRows(listDocument.body.deployments);
  }

  useEffect(() => {
    void reload().catch(() => setError("Rukan Command Center service is not reachable."));
  }, []);

  async function refresh() {
    setError("");
    const response = await fetch("/v1/refresh", { method: "POST" });
    const document = await response.json();
    setNotice(
      `imported ${document.body.imported}, skipped ${document.body.skipped}, rejected ${document.body.rejected}`,
    );
    await reload();
  }

  async function open(installId: string) {
    setSelected(installId);
    setSnapshotId("");
    const response = await fetch(`/v1/deployments/${encodeURIComponent(installId)}`);
    const document = await response.json();
    setDetail(document.body);
    setPage("Detail");
  }

  const snapshots = detail ? history(detail.snapshots) : [];
  const snapshot = snapshots.find((item) => item.snapshot_id === snapshotId) ?? snapshots[0] ?? null;

  return (
    <>
      <header>
        <strong>Rukan Command Center</strong>
        <button type="button" onClick={() => void refresh()}>
          Refresh deployments
        </button>
        <nav aria-label="Command sections">
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
        <p className="banner">Imported evidence — not live deployment status</p>
        {status ? (
          <p className="muted">
            Service loopback. Last refresh {status.last_refresh}. Imported {status.last_imported}. Rejected{" "}
            {status.last_rejected}.
          </p>
        ) : null}
        {notice ? <p role="status">{notice}</p> : null}
        {error ? <p role="alert">{error}</p> : null}
        {page === "Overview" ? <Portfolio /> : null}
        {page === "Deployments" ? (
          <Deployments rows={rows} query={query} onQuery={setQuery} onOpen={(installId) => void open(installId)} />
        ) : null}
        {page === "Detail" ? (
          <>
            <Detail snapshot={snapshot} snapshots={snapshots} reports={detail?.reports ?? []} onSelect={setSnapshotId} />
            <InferenceFacts rows={detail?.inferences ?? []} />
            <Support snapshot={snapshot} events={detail?.events ?? []} />
          </>
        ) : null}
        {page === "Analytics" ? <Analytics /> : null}
        {page === "Models" ? <ModelLandscape /> : null}
        {page === "Reporting" ? <Reporting /> : null}
        {page === "Import" ? (
          <Import
            rows={rows}
            onRemove={async (installId) => {
              await fetch(`/v1/deployments/${encodeURIComponent(installId)}`, { method: "DELETE" });
              await reload();
            }}
          />
        ) : null}
        {page === "Settings" ? <CommandSettings /> : null}
      </main>
    </>
  );
}

function Deployments({
  rows,
  query,
  onQuery,
  onOpen,
}: {
  rows: DeploymentRow[];
  query: string;
  onQuery: (value: string) => void;
  onOpen: (installId: string) => void;
}) {
  const visible = filterRows(rows, query);
  return (
    <section>
      <h1>Imported deployments</h1>
      <p>
        <label>
          Search{" "}
          <input aria-label="Search deployments" value={query} onChange={(event) => onQuery(event.target.value)} />
        </label>
      </p>
      {rows.length === 0 ? <p>No imported deployments.</p> : null}
      {rows.length > 0 && visible.length === 0 ? <p>No deployments match that search.</p> : null}
      {visible.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Install identity</th>
              <th>Rukan version</th>
              <th>OS / accelerator</th>
              <th>Macropath</th>
              <th>Model</th>
              <th>Witness</th>
              <th>Snapshots</th>
              <th>Cadence</th>
              <th>Last report</th>
              <th>Report age</th>
              <th>Cadence</th>
              <th>Evidence exported</th>
              <th>Snapshot age</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.install_id}>
                <td>
                  <button type="button" onClick={() => onOpen(item.install_id)}>
                    {item.install_id}
                  </button>
                </td>
                <td>{item.version}</td>
                <td>
                  {item.os_family} / {item.accelerator_summary}
                </td>
                <td>{item.macropath}</td>
                <td>{item.model_identity}</td>
                <td>{item.witness_verdict}</td>
                <td>{item.snapshot_count}</td>
                <td>{cadenceText(item.cadence_profile, item.cadence_seconds)}</td>
                <td>{item.last_report_received_at ?? "not_recorded"}</td>
                <td>{reportAge(item.last_report_received_at, Date.now())}</td>
                <td>{cadenceLabel(item.last_report_received_at, Date.now(), item.cadence_seconds)}</td>
                <td>{item.latest_exported_at}</td>
                <td>{snapshotAge(item.latest_exported_at, Date.now())}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}

function Detail({
  snapshot,
  snapshots,
  reports,
  onSelect,
}: {
  snapshot: SupportSnapshot | null;
  snapshots: SupportSnapshot[];
  reports: { report_id: string; sequence: number; received_at: string; generated_at: string; triggers: string; gap: string; key_id: string }[];
  onSelect: (snapshotId: string) => void;
}) {
  if (!snapshot) return <p>Select an imported deployment.</p>;
  return (
    <section>
      <h1>Deployment detail</h1>
      <p className="banner">Imported evidence — not live deployment status</p>
      <h2>Reports</h2>
      {reports.length === 0 ? <p>No operational reports for this deployment.</p> : (
        <table>
          <thead><tr><th>Received</th><th>Generated</th><th>Sequence</th><th>Triggers</th><th>Gap</th><th>Key</th></tr></thead>
          <tbody>{reports.map((item) => <tr key={item.report_id}><td>{item.received_at}</td><td>{item.generated_at}</td><td>{item.sequence}</td><td>{item.triggers}</td><td>{item.gap}</td><td>{item.key_id}</td></tr>)}</tbody>
        </table>
      )}
      {snapshots.length > 1 ? (
        <p>
          <label>
            Snapshot history{" "}
            <select
              aria-label="Snapshot history"
              value={snapshot.snapshot_id}
              onChange={(event) => onSelect(event.target.value)}
            >
              {snapshots.map((item) => (
                <option key={item.snapshot_id} value={item.snapshot_id}>
                  {item.exported_at} · {item.version} · {item.witness_verdict} · {item.macropath}
                </option>
              ))}
            </select>
          </label>
        </p>
      ) : null}
      <section className="grid">
      <article className="card">
        <h2>Identity and version</h2>
        <p>Install {snapshot.install_id}</p>
        <p>Created {snapshot.install_created_at}</p>
        <p>
          Rukan {snapshot.version} build {snapshot.build_id}
        </p>
        <p>Commit {snapshot.source_commit}</p>
      </article>
      <article className="card">
        <h2>Hardware and capacity</h2>
        <p>
          {snapshot.os_family} {snapshot.architecture}
        </p>
        <p>{snapshot.accelerator_summary}</p>
        <p>SAFE host {snapshot.safe_host_bytes}</p>
        <p>SAFE accelerator {snapshot.safe_accelerator_bytes}</p>
        <p>Capacity observed {snapshot.capacity_observed_at}</p>
      </article>
      <article className="card">
        <h2>Execution, model, and Witness</h2>
        <p>Macropath {snapshot.macropath}</p>
        <p>Generation {snapshot.foundation_generation_id}</p>
        <p>
          Model {snapshot.model_identity} ({snapshot.model_identity_kind})
        </p>
        <p>
          Qualification {snapshot.qualification_id} {snapshot.qualification_outcome}
        </p>
        <p>
          Witness {snapshot.witness_verdict}: {snapshot.witness_reason}
        </p>
        <p>{snapshot.physical_register}</p>
        <p>{snapshot.pending_coverage}</p>
        <p>Snapshot {snapshot.snapshot_id}</p>
        <p>Exported {snapshot.exported_at}</p>
      </article>
      </section>
    </section>
  );
}

function InferenceFacts({
  rows,
}: {
  rows: { proof_id: string; outcome: string; completion_tokens: string; failure: string; model_identity: string }[];
}) {
  return (
    <section>
      <h2>Inference facts</h2>
      <p className="muted">Persisted proofs only. Input tokens, TTFT, queue time, and latency are not recorded.</p>
      {rows.length === 0 ? <p>No imported inference proofs.</p> : null}
      {rows.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Proof</th>
              <th>Model</th>
              <th>Outcome</th>
              <th>Completion tokens</th>
              <th>Failure</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.proof_id}>
                <td>{row.proof_id}</td>
                <td>{row.model_identity}</td>
                <td>{row.outcome}</td>
                <td>{row.completion_tokens}</td>
                <td>{row.failure}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}

function Support({
  snapshot,
  events,
}: {
  snapshot: SupportSnapshot | null;
  events: { event_id: string; event_type: string; occurred_at: string; outcome: string }[];
}) {
  if (!snapshot && events.length === 0) return <p>Select an imported deployment.</p>;
  const rows = events.length > 0 ? events : snapshot?.support_events ?? [];
  return (
    <section>
      <h1>Support evidence</h1>
      <p className="muted">Structured operational envelopes. Payloads and customer content are omitted.</p>
      {rows.length === 0 ? <p>No exportable operational events in this snapshot.</p> : null}
      {rows.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Event</th>
              <th>Outcome</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((event) => (
              <tr key={`${event.occurred_at}:${event.event_type}`}>
                <td>{event.occurred_at}</td>
                <td>{event.event_type}</td>
                <td>{event.outcome}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}

function Analytics() {
  const [body, setBody] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    void fetch("/v1/analytics")
      .then((response) => response.json())
      .then((document) => setBody(document.body));
  }, []);
  if (!body) return <p>Loading imported analytics.</p>;
  return (
    <section>
      <h1>Imported analytics</h1>
      <p className="banner">Imported evidence — not live deployment status</p>
      <pre>{JSON.stringify(body, null, 2)}</pre>
    </section>
  );
}

function Import({
  rows,
  onRemove,
}: {
  rows: DeploymentRow[];
  onRemove: (installId: string) => Promise<void>;
}) {
  return (
    <section>
      <h1>Inbox</h1>
      <p>
        Place a support snapshot JSON file or an analytics bundle JSONL file in the Command Center inbox,
        then use Refresh deployments. Files are not uploaded by the browser.
      </p>
      <ul>
        {rows.map((row) => (
          <li key={row.install_id}>
            {row.install_id}{" "}
            <button type="button" onClick={() => void onRemove(row.install_id)}>
              Remove local copy
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Settings() {
  return (
    <section>
      <h1>Settings</h1>
      <p>This Command Center runs on the business operator PC.</p>
      <p>SQLite is the durable store. The browser is not.</p>
      <p>There is no remote execution authority and no fleet connection.</p>
      <p>Transfer from a deployment is manual: export a bundle, copy it into the inbox, then refresh.</p>
    </section>
  );
}
