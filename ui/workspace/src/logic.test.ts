import { expect, test } from "vitest";
import { blocks, conversationBody, parseSse } from "./logic";

test("splits fenced code without treating it as markup", () => {
  const parts = blocks("Hello\n```\nprint(1)\n```\n");
  expect(parts.map((item) => item.kind)).toEqual(["text", "code"]);
  expect(parts[1].text).toContain("print(1)");
});

test("sends the selected model when a chat is created", () => {
  expect(conversationBody("mart_demo").model_id).toBe("mart_demo");
});

test("reads one streamed delta and the done marker", () => {
  const first = parseSse('data: {"delta":"Hi"}\n\n');
  const last = parseSse('data: {"done": true}\n\n');
  expect(first).toEqual({ delta: "Hi", done: false });
  expect(last.done).toBe(true);
});
