import { useMemo, useState } from "react";
import { emptyStore, importSnapshot, latest, removeDeployment, type CommandStore } from "../../shared/store";
import type { SupportSnapshot } from "../../shared/snapshot";
import { filterDeployments, history, snapshotAge } from "./query";

const PAGES = ["Deployments", "Detail", "Support", "Import", "Settings"] as const;
type Page = (typeof PAGES)[number];
const STORAGE_KEY = "rukan.command.store.v1";

export function App() {
  const [page, setPage] = useState<Page>("Deployments");
  const [store, setStore] = useState<CommandStore>(() => readStore());
  const [selected, setSelected] = useState<string>("");
  const [snapshotId, setSnapshotId] = useState<string>("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  function save(next: CommandStore) {
    setStore(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  const current = store.deployments.find((item) => item.installId === selected) ?? null;
  const snapshots = current ? history(current.snapshots) : [];
  const snapshot = snapshots.find((item) => item.snapshot_id === snapshotId) ?? snapshots[0] ?? null;

  return (
    <>
      <header>
        <strong>Rukan Command Center</strong>
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
        {error ? <p role="alert">{error}</p> : null}
        {page === "Deployments" ? (
          <Deployments
            store={store}
            query={query}
            onQuery={setQuery}
            onOpen={(installId) => {
              setSelected(installId);
              setSnapshotId("");
              setPage("Detail");
            }}
          />
        ) : null}
        {page === "Detail" ? (
          <Detail
            snapshot={snapshot}
            snapshots={snapshots}
            onSelect={setSnapshotId}
          />
        ) : null}
        {page === "Support" ? <Support snapshot={snapshot} /> : null}
        {page === "Import" ? (
          <Import
            onImported={(raw) => {
              try {
                const next = importSnapshot(store, raw);
                save(next);
                setError("");
                setPage("Deployments");
              } catch (exc) {
                setError(exc instanceof Error ? exc.message : "import failed");
              }
            }}
            onRemove={(installId) => save(removeDeployment(store, installId))}
            store={store}
          />
        ) : null}
        {page === "Settings" ? <Settings /> : null}
      </main>
    </>
  );
}

function Deployments({
  store,
  query,
  onQuery,
  onOpen,
}: {
  store: CommandStore;
  query: string;
  onQuery: (value: string) => void;
  onOpen: (installId: string) => void;
}) {
  const rows = filterDeployments(store, query);
  return (
    <section>
      <h1>Imported deployments</h1>
      <p>
        <label>
          Search{" "}
          <input
            aria-label="Search deployments"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
          />
        </label>
      </p>
      {store.deployments.length === 0 ? <p>No imported deployments.</p> : null}
      {store.deployments.length > 0 && rows.length === 0 ? <p>No deployments match that search.</p> : null}
      {rows.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Install identity</th>
              <th>Install created</th>
              <th>Rukan version</th>
              <th>OS / accelerator</th>
              <th>Macropath</th>
              <th>Model</th>
              <th>Witness</th>
              <th>Snapshots</th>
              <th>Evidence exported</th>
              <th>Snapshot age</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => {
              const snap = latest(item);
              return (
                <tr key={item.installId}>
                  <td>
                    <button type="button" onClick={() => onOpen(item.installId)}>
                      {item.installId}
                    </button>
                  </td>
                  <td>{snap.install_created_at}</td>
                  <td>{snap.version}</td>
                  <td>
                    {snap.os_family} / {snap.accelerator_summary}
                  </td>
                  <td>{snap.macropath}</td>
                  <td>{snap.model_identity}</td>
                  <td>{snap.witness_verdict}</td>
                  <td>{item.snapshots.length}</td>
                  <td>{snap.exported_at}</td>
                  <td>{snapshotAge(snap.exported_at, Date.now())}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}

function Detail({
  snapshot,
  snapshots,
  onSelect,
}: {
  snapshot: SupportSnapshot | null;
  snapshots: SupportSnapshot[];
  onSelect: (snapshotId: string) => void;
}) {
  if (!snapshot) return <p>Select an imported deployment.</p>;
  return (
    <section>
      <h1>Deployment detail</h1>
      <p className="banner">Imported evidence — not live deployment status</p>
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

function Support({ snapshot }: { snapshot: SupportSnapshot | null }) {
  if (!snapshot) return <p>Select an imported deployment.</p>;
  if (snapshot.support_events.length === 0) {
    return (
      <section>
        <h1>Support evidence</h1>
        <p>No exportable operational events in this snapshot.</p>
      </section>
    );
  }
  return (
    <section>
      <h1>Support evidence</h1>
      <p className="muted">Structured operational envelopes. Payloads and customer content are omitted.</p>
    <table>
      <thead>
        <tr>
          <th>When</th>
          <th>Event</th>
          <th>Outcome</th>
          <th>Privacy</th>
        </tr>
      </thead>
      <tbody>
        {snapshot.support_events.map((event) => (
          <tr key={`${event.occurred_at}:${event.event_type}`}>
            <td>{event.occurred_at}</td>
            <td>{event.event_type}</td>
            <td>{event.outcome}</td>
            <td>{event.privacy}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </section>
  );
}

function Import({
  store,
  onImported,
  onRemove,
}: {
  store: CommandStore;
  onImported: (raw: unknown) => void;
  onRemove: (installId: string) => void;
}) {
  const ids = useMemo(() => store.deployments.map((item) => item.installId), [store]);
  return (
    <section>
      <p>Import a Rukan deployment summary file from this PC. Nothing is uploaded.</p>
      <input
        aria-label="Snapshot file"
        type="file"
        accept="application/json"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (!file) return;
          void file.text().then((text) => {
            try {
              onImported(JSON.parse(text));
            } catch {
              onImported(null);
            }
          });
        }}
      />
      <ul>
        {ids.map((id) => (
          <li key={id}>
            {id}{" "}
            <button type="button" onClick={() => onRemove(id)}>
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
      <p>This Command Center runs on the business operator PC.</p>
      <p>It has no remote execution authority and no fleet connection.</p>
      <p>Imported files stay in this browser profile until removed.</p>
    </section>
  );
}

function readStore(): CommandStore {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return emptyStore();
  try {
    const parsed = JSON.parse(raw) as CommandStore;
    if (!Array.isArray(parsed.deployments)) return emptyStore();
    return parsed;
  } catch {
    return emptyStore();
  }
}
