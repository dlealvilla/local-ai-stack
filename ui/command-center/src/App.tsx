import { useMemo, useState } from "react";
import { emptyStore, importSnapshot, latest, removeDeployment, type CommandStore } from "../../shared/store";
import type { SupportSnapshot } from "../../shared/snapshot";

const PAGES = ["Deployments", "Detail", "Support", "Import", "Settings"] as const;
type Page = (typeof PAGES)[number];
const STORAGE_KEY = "rukan.command.store.v1";

export function App() {
  const [page, setPage] = useState<Page>("Deployments");
  const [store, setStore] = useState<CommandStore>(() => readStore());
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState("");

  function save(next: CommandStore) {
    setStore(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  const current = store.deployments.find((item) => item.installId === selected) ?? null;
  const snapshot = current ? latest(current) : null;

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
        <p className="banner">Imported evidence only. Not live, online, offline, or currently healthy.</p>
        {error ? <p role="alert">{error}</p> : null}
        {page === "Deployments" ? (
          <Deployments
            store={store}
            onOpen={(installId) => {
              setSelected(installId);
              setPage("Detail");
            }}
          />
        ) : null}
        {page === "Detail" ? <Detail snapshot={snapshot} /> : null}
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
  onOpen,
}: {
  store: CommandStore;
  onOpen: (installId: string) => void;
}) {
  if (store.deployments.length === 0) return <p>No imported deployments.</p>;
  return (
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
          <th>Exported at</th>
        </tr>
      </thead>
      <tbody>
        {store.deployments.map((item) => {
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
              <td>{snap.exported_at}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Detail({ snapshot }: { snapshot: SupportSnapshot | null }) {
  if (!snapshot) return <p>Select an imported deployment.</p>;
  return (
    <section className="grid">
      <article className="card">
        <p>Install {snapshot.install_id}</p>
        <p>Created {snapshot.install_created_at}</p>
        <p>
          Rukan {snapshot.version} build {snapshot.build_id}
        </p>
        <p>Commit {snapshot.source_commit}</p>
      </article>
      <article className="card">
        <p>
          {snapshot.os_family} {snapshot.architecture}
        </p>
        <p>{snapshot.accelerator_summary}</p>
        <p>SAFE host {snapshot.safe_host_bytes}</p>
        <p>SAFE accelerator {snapshot.safe_accelerator_bytes}</p>
        <p>Capacity observed {snapshot.capacity_observed_at}</p>
      </article>
      <article className="card">
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
  );
}

function Support({ snapshot }: { snapshot: SupportSnapshot | null }) {
  if (!snapshot) return <p>Select an imported deployment.</p>;
  if (snapshot.support_events.length === 0) {
    return <p>No exportable operational events in this snapshot.</p>;
  }
  return (
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
