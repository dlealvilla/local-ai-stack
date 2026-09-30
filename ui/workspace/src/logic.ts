export type Block = { kind: "text" | "code"; text: string };

export function blocks(source: string): Block[] {
  return source.split("```").map((text, index) => ({
    kind: index % 2 === 1 ? "code" : "text",
    text,
  }));
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
