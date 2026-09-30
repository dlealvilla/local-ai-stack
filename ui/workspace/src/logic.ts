export type Block = { kind: "text" | "code" | "heading"; text: string };

export function blocks(source: string): Block[] {
  const parts = source.split("```");
  const found: Block[] = [];
  parts.forEach((part, index) => {
    if (index % 2 === 1) {
      found.push({ kind: "code", text: part });
      return;
    }
    for (const line of part.split("\n")) {
      if (line.startsWith("# ")) found.push({ kind: "heading", text: line.slice(2) });
      else if (line.trim()) found.push({ kind: "text", text: line });
    }
  });
  return found;
}

export function conversationBody(modelId: string, title = "New chat") {
  return { title, model_id: modelId };
}

export function parseSse(chunk: string): { delta: string; done: boolean } {
  let delta = "";
  let done = false;
  for (const line of chunk.split("\n")) {
    if (!line.startsWith("data:")) continue;
    const text = line.slice(5).trim();
    try {
      const payload = JSON.parse(text) as { delta?: string; done?: boolean };
      if (typeof payload.delta === "string") delta += payload.delta;
      if (payload.done === true) done = true;
    } catch {
      done = done || text === "[DONE]";
    }
  }
  return { delta, done };
}
