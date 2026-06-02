import { describe, expect, test } from "vitest";
import { SseParser } from "./sseParser";

describe("SseParser", () => {
  test("parses CRLF-delimited multiline data with event id and retry fields", () => {
    const parser = new SseParser();

    const events = parser.push(
      [
        "id: 42",
        "event: metadata",
        "retry: 1500",
        'data: {"type":"metadata",',
        'data: "sources":[]}',
        "",
        "",
      ].join("\r\n"),
    );

    expect(events).toEqual([
      {
        data: '{"type":"metadata",\n"sources":[]}',
        event: "metadata",
        id: "42",
        retry: 1500,
      },
    ]);
  });

  test("ignores comments and waits for partial chunks before dispatching", () => {
    const parser = new SseParser();

    expect(parser.push(": keepalive\n\ndata: {\"type\"")).toEqual([]);
    expect(parser.push(":\"token\",\"content\":\"hej\"}\n\n")).toEqual([
      {
        data: '{"type":"token","content":"hej"}',
      },
    ]);
  });

  test("flushes an unterminated final event at EOF", () => {
    const parser = new SseParser();

    expect(parser.push('data: {"type":"done"}')).toEqual([]);
    expect(parser.flush()).toEqual([{ data: '{"type":"done"}' }]);
    expect(parser.flush()).toEqual([]);
  });
});
