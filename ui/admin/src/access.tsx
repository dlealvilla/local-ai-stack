import { useEffect, useState } from "react";

type Check = { name: string; status: string; text: string };
type Provider = { provider_id: string; issuer: string; audience: string; enabled: boolean; state: string };
type Server = { server_id: string; display_name: string; endpoint: string };

async function post(body: object) {
  const response = await fetch("/v1/people", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await response.json()) as { outcome: string; message: string; body: Record<string, unknown> };
}

export function Identity() {
  const [rows, setRows] = useState<Provider[]>([]);
  const [issuer, setIssuer] = useState("");
  const [audience, setAudience] = useState("rukan");
  const [discovery, setDiscovery] = useState("");
  const [notice, setNotice] = useState("");

  async function reload() {
    const document = await post({ action: "list_providers" });
    setRows((document.body.providers as Provider[]) ?? []);
  }
  useEffect(() => { void reload(); }, []);

  return (
    <section className="card">
      <h2>Identity provider</h2>
      <p className="muted">The stored row is what Workspace and the gateway load. A change applies after restart.</p>
      <ul>{rows.map((row) => <li key={row.provider_id}>{row.provider_id} · {row.issuer} · {row.enabled ? "enabled" : "disabled"}</li>)}</ul>
      <form className="stack" onSubmit={(event) => {
        event.preventDefault();
        void post({
          action: "save_provider",
          provider_id: "primary",
          label: "Enterprise IdP",
          issuer,
          audience,
          discovery_url: discovery,
          enabled: true,
        }).then((document) => { setNotice(document.message); void reload(); });
      }}>
        <input aria-label="Issuer" value={issuer} onChange={(event) => setIssuer(event.target.value)} placeholder="https://idp.example/realms/rukan" />
        <input aria-label="Audience" value={audience} onChange={(event) => setAudience(event.target.value)} />
        <input aria-label="Discovery URL" value={discovery} onChange={(event) => setDiscovery(event.target.value)} placeholder="https://idp.example/.well-known/openid-configuration" />
        <button type="submit">Save provider</button>
      </form>
      {notice ? <p>{notice}</p> : null}
    </section>
  );
}

export function WorkspaceAccess() {
  const [checks, setChecks] = useState<Check[]>([]);
  const [outcome, setOutcome] = useState("");
  useEffect(() => {
    void post({ action: "preflight" }).then((document) => {
      setOutcome(String(document.body.outcome ?? ""));
      setChecks((document.body.checks as Check[]) ?? []);
    });
  }, []);
  return (
    <section className="card">
      <h2>Workspace</h2>
      <p>The default employee client is Rukan Workspace. LibreChat is an optional fallback and is not required.</p>
      <p className="status">Preflight {outcome || "checking"}</p>
      <ul>{checks.map((item) => <li key={item.name}>{item.name}: {item.status} — {item.text}</li>)}</ul>
    </section>
  );
}

export function McpCatalog() {
  const [rows, setRows] = useState<Server[]>([]);
  const [name, setName] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [notice, setNotice] = useState("");
  async function reload() {
    const document = await post({ action: "list_mcp" });
    setRows((document.body.servers as Server[]) ?? []);
  }
  useEffect(() => { void reload(); }, []);
  return (
    <section className="card">
      <h2>MCP catalog</h2>
      <p className="muted">Only an approved endpoint can be called. Employees do not add servers unless Connect is allowed.</p>
      <ul>{rows.map((row) => <li key={row.server_id}>{row.display_name} · {row.endpoint}</li>)}</ul>
      <form className="stack" onSubmit={(event) => {
        event.preventDefault();
        void post({
          action: "approve_mcp",
          server_id: name.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "server",
          display_name: name,
          endpoint,
        }).then((document) => { setNotice(document.message); void reload(); });
      }}>
        <input aria-label="Server name" value={name} onChange={(event) => setName(event.target.value)} />
        <input aria-label="Endpoint" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://mcp.example/rpc" />
        <button type="submit">Approve server</button>
      </form>
      {notice ? <p>{notice}</p> : null}
    </section>
  );
}
