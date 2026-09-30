import { useEffect, useState } from "react";
import { blocks, conversationBody, parseSse } from "./logic";

type Me = { user_id: string; csrf: string };
type Conversation = { conversation_id: string; title: string; model_id: string; agent_id: string };
type Message = { role: string; content: string; input_tokens?: string; output_tokens?: string };
type Model = { id: string; tool_calling?: string };
type Agent = { agent_id: string; display_name: string; model_id: string };
type Usage = { requests?: number; input_tokens?: string; output_tokens?: string; total_tokens?: string };

const PAGES = ["Chat", "Usage", "Connections", "Tools", "Agents"] as const;
type Page = (typeof PAGES)[number];

async function api(path: string, csrf: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (csrf) headers.set("X-Rukan-CSRF", csrf);
  if (init.body) headers.set("content-type", "application/json");
  const response = await fetch(path, { ...init, headers, credentials: "include" });
  const kind = response.headers.get("content-type") ?? "";
  if (!kind.includes("application/json")) return { response, body: null };
  return { response, body: (await response.json()) as Record<string, unknown> };
}

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [page, setPage] = useState<Page>("Chat");
  const [error, setError] = useState("");

  useEffect(() => {
    void fetch("/api/workspace/v1/me", { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return;
        setMe((await response.json()) as Me);
      })
      .catch(() => setError("Rukan Workspace could not reach this server."));
  }, []);

  if (!me) {
    return (
      <main>
        <h1 className="hero">Rukan Workspace</h1>
        <p>Sign in with your organisation account. Chat stays on this Rukan server.</p>
        {error ? <p className="banner">{error}</p> : null}
        <p><a href="/api/workspace/v1/login">Sign in</a></p>
      </main>
    );
  }

  return (
    <>
      <header>
        <strong>Rukan Workspace</strong>
        <nav>
          {PAGES.map((item) => (
            <button key={item} type="button" aria-current={page === item ? "page" : undefined} onClick={() => setPage(item)}>{item}</button>
          ))}
        </nav>
        <button type="button" onClick={() => {
          void api("/api/workspace/v1/logout", me.csrf, { method: "POST" }).then(() => setMe(null));
        }}>Sign out</button>
      </header>
      <main>
        {error ? <p className="banner">{error}</p> : null}
        {page === "Chat" ? <Chat csrf={me.csrf} onError={setError} /> : null}
        {page === "Usage" ? <UsagePanel csrf={me.csrf} /> : null}
        {page === "Connections" ? <Connections csrf={me.csrf} /> : null}
        {page === "Tools" ? <Tools csrf={me.csrf} /> : null}
        {page === "Agents" ? <Agents csrf={me.csrf} /> : null}
      </main>
    </>
  );
}

function Chat({ csrf, onError }: { csrf: string; onError: (text: string) => void }) {
  const [rows, setRows] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [title, setTitle] = useState("New chat");
  const [models, setModels] = useState<Model[]>([]);
  const [modelId, setModelId] = useState("");
  const [busy, setBusy] = useState(false);
  const [stop, setStop] = useState<AbortController | null>(null);

  async function reload() {
    const result = await api("/api/workspace/v1/conversations", csrf);
    setRows((result.body?.conversations as Conversation[]) ?? []);
  }
  useEffect(() => {
    void reload();
    void api("/api/workspace/v1/models", csrf).then((result) => {
      const data = (result.body?.data as Model[]) ?? [];
      setModels(data);
      if (data[0]) setModelId(data[0].id);
    });
  }, []);

  async function open(id: string) {
    setCurrent(id);
    const result = await api(`/api/workspace/v1/conversations/${id}`, csrf);
    setMessages((result.body?.messages as Message[]) ?? []);
    setTitle(String(result.body?.title ?? "New chat"));
  }

  async function create() {
    const result = await api("/api/workspace/v1/conversations", csrf, {
      method: "POST",
      body: JSON.stringify(conversationBody(modelId)),
    });
    const id = String(result.body?.conversation_id ?? "");
    await reload();
    if (id) await open(id);
  }

  async function send(text: string) {
    if (!current || !text.trim()) return;
    setMessages((items) => [...items, { role: "user", content: text }]);
    setDraft("");
    setBusy(true);
    const controller = new AbortController();
    setStop(controller);
    let assistant = "";
    try {
      const response = await fetch(`/api/workspace/v1/conversations/${current}/messages`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json", "X-Rukan-CSRF": csrf },
        body: JSON.stringify({ content: text }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        const failed = await response.json().catch(() => ({ error: "upstream_failure" }));
        onError(String(failed.error ?? "upstream_failure"));
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const step = await reader.read();
        if (step.done) break;
        buffer += decoder.decode(step.value, { stream: true });
        const parsed = parseSse(buffer);
        buffer = "";
        if (parsed.delta) {
          assistant += parsed.delta;
          const snapshot = assistant;
          setMessages((items) => {
            const next = [...items];
            const last = next.at(-1);
            if (last?.role === "assistant") next[next.length - 1] = { role: "assistant", content: snapshot };
            else next.push({ role: "assistant", content: snapshot });
            return next;
          });
        }
      }
    } catch (exc) {
      if (!(exc instanceof DOMException && exc.name === "AbortError")) onError("upstream_failure");
    } finally {
      setBusy(false);
      setStop(null);
      await open(current);
    }
  }

  return (
    <div className="grid">
      <section className="card">
        <label>Model
          <select aria-label="Model" value={modelId} onChange={(event) => setModelId(event.target.value)}>
            {models.map((model) => <option key={model.id} value={model.id}>{model.id}</option>)}
          </select>
        </label>
        <button type="button" onClick={() => void create()}>New chat</button>
        <ul>
          {rows.map((row) => (
            <li key={row.conversation_id}>
              <button type="button" onClick={() => void open(row.conversation_id)}>{row.title}</button>
            </li>
          ))}
        </ul>
      </section>
      <section className="card">
        <form className="stack" onSubmit={(event) => {
          event.preventDefault();
          void api(`/api/workspace/v1/conversations/${current}/title`, csrf, {
            method: "POST",
            body: JSON.stringify({ title }),
          }).then(() => reload());
        }}>
          <input aria-label="Title" value={title} onChange={(event) => setTitle(event.target.value)} />
          <button type="submit" disabled={!current}>Rename</button>
        </form>
        {messages.map((message, index) => (
          <article key={`${message.role}-${index}`}>
            <p className="muted">{message.role}</p>
            {blocks(message.content).map((block, blockIndex) => (
              block.kind === "code"
                ? <pre key={blockIndex}><code>{block.text}</code></pre>
                : block.kind === "heading"
                  ? <h3 key={blockIndex}>{block.text}</h3>
                  : <p key={blockIndex}>{block.text}</p>
            ))}
            {message.input_tokens ? <p className="muted">tokens {message.input_tokens} / {message.output_tokens}</p> : null}
            <button type="button" onClick={() => void navigator.clipboard.writeText(message.content)}>Copy</button>
          </article>
        ))}
        <form className="stack" onSubmit={(event) => { event.preventDefault(); void send(draft); }}>
          <textarea aria-label="Message" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(draft);
            }
          }} />
          <button type="submit" disabled={!current || busy}>Send</button>
        </form>
        <button type="button" disabled={!busy} onClick={() => {
          stop?.abort();
          void api(`/api/workspace/v1/conversations/${current}/stop`, csrf, { method: "POST", body: "{}" });
        }}>Stop</button>
        <button type="button" disabled={!current || busy} onClick={() => {
          void fetch(`/api/workspace/v1/conversations/${current}/regenerate`, {
            method: "POST",
            credentials: "include",
            headers: { "content-type": "application/json", "X-Rukan-CSRF": csrf },
            body: "{}",
          }).then((response) => response.text()).then(() => open(current));
        }}>Regenerate</button>
        <button type="button" disabled={!current} onClick={() => {
          void api(`/api/workspace/v1/conversations/${current}/archive`, csrf, { method: "POST", body: "{}" }).then(() => { setCurrent(""); setMessages([]); void reload(); });
        }}>Delete</button>
      </section>
    </div>
  );
}

function UsagePanel({ csrf }: { csrf: string }) {
  const [period, setPeriod] = useState("all");
  const [usage, setUsage] = useState<Usage>({});
  useEffect(() => {
    void api(`/api/workspace/v1/usage?period=${period}`, csrf).then((result) => setUsage((result.body ?? {}) as Usage));
  }, [csrf, period]);
  return (
    <section className="card">
      <h2>My usage</h2>
      <nav>
        {["24h", "7d", "30d", "all"].map((item) => (
          <button key={item} type="button" aria-current={period === item ? "page" : undefined} onClick={() => setPeriod(item)}>{item}</button>
        ))}
      </nav>
      <p>Requests {String(usage.requests ?? "not recorded")}</p>
      <p>Total tokens {String(usage.total_tokens ?? "not recorded")}</p>
      <p>Input tokens {String(usage.input_tokens ?? "not recorded")}</p>
      <p>Output tokens {String(usage.output_tokens ?? "not recorded")}</p>
    </section>
  );
}

function Connections({ csrf }: { csrf: string }) {
  const [secret, setSecret] = useState("");
  const [keyId, setKeyId] = useState("");
  return (
    <section className="card">
      <h2>Connections</h2>
      <p>OpenAI-compatible base URL is this server’s <code>/v1</code>. The secret is shown once.</p>
      <button type="button" onClick={() => {
        void api("/api/workspace/v1/credentials", csrf, { method: "POST", body: JSON.stringify({ label: "workspace" }) })
          .then((result) => {
            setSecret(String(result.body?.secret ?? ""));
            setKeyId(String(result.body?.key_id ?? ""));
          });
      }}>Create credential</button>
      {secret ? <p>Secret {secret}</p> : null}
      <button type="button" disabled={!keyId} onClick={() => {
        void api("/api/workspace/v1/credentials/revoke", csrf, { method: "POST", body: JSON.stringify({ key_id: keyId }) })
          .then(() => { setSecret(""); setKeyId(""); });
      }}>Revoke</button>
    </section>
  );
}

function Tools({ csrf }: { csrf: string }) {
  const [rows, setRows] = useState<Array<{ server_id: string; display_name: string }>>([]);
  const [result, setResult] = useState("");
  useEffect(() => {
    void api("/api/workspace/v1/tools", csrf).then((document) => {
      setRows((document.body?.servers as Array<{ server_id: string; display_name: string }>) ?? []);
    });
  }, [csrf]);
  return (
    <section className="card">
      <h2>Tools</h2>
      <ul>
        {rows.map((row) => (
          <li key={row.server_id}>
            {String(row.display_name || row.server_id)}
            <button type="button" onClick={() => {
              const name = (row as { tools?: string[] }).tools?.[0] ?? "ping";
              void api(`/api/workspace/v1/tools/${row.server_id}/call`, csrf, {
                method: "POST",
                body: JSON.stringify({ name }),
              }).then((document) => setResult(JSON.stringify(document.body)));
            }}>Call</button>
          </li>
        ))}
      </ul>
      {result ? <pre>{result}</pre> : null}
    </section>
  );
}

function Agents({ csrf }: { csrf: string }) {
  const [rows, setRows] = useState<Agent[]>([]);
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [modelId, setModelId] = useState("");
  const [tools, setTools] = useState("");
  const [editing, setEditing] = useState("");
  async function reload() {
    const document = await api("/api/workspace/v1/agents", csrf);
    setRows((document.body?.agents as Agent[]) ?? []);
  }
  useEffect(() => { void reload(); }, []);
  return (
    <section className="card">
      <h2>Agents</h2>
      <ul>
        {rows.map((row) => (
          <li key={row.agent_id}>
            {row.display_name}
            <button type="button" onClick={() => { setEditing(row.agent_id); setName(row.display_name); }}>Edit</button>
            <button type="button" onClick={() => {
              void api("/api/workspace/v1/conversations", csrf, {
                method: "POST",
                body: JSON.stringify({ title: row.display_name, agent_id: row.agent_id, model_id: row.model_id }),
              });
            }}>Chat</button>
            <button type="button" onClick={() => {
              void api(`/api/workspace/v1/agents/${row.agent_id}/archive`, csrf, { method: "POST", body: "{}" }).then(() => reload());
            }}>Archive</button>
          </li>
        ))}
      </ul>
      <form className="stack" onSubmit={(event) => {
        event.preventDefault();
        const path = editing ? `/api/workspace/v1/agents/${editing}/revise` : "/api/workspace/v1/agents";
        void api(path, csrf, {
          method: "POST",
          body: JSON.stringify({ display_name: name, instructions, model_id: modelId, tool_refs: tools }),
        }).then(() => { setName(""); setInstructions(""); setEditing(""); void reload(); });
      }}>
        <input aria-label="Agent name" value={name} onChange={(event) => setName(event.target.value)} />
        <input aria-label="Agent model" value={modelId} onChange={(event) => setModelId(event.target.value)} placeholder="model id" />
        <input aria-label="Agent tools" value={tools} onChange={(event) => setTools(event.target.value)} placeholder="server/tool" />
        <textarea aria-label="Instructions" value={instructions} onChange={(event) => setInstructions(event.target.value)} />
        <button type="submit">Save agent</button>
      </form>
    </section>
  );
}
