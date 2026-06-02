export interface ParsedSseEvent {
  data: string;
  event?: string;
  id?: string;
  retry?: number;
}

interface PendingSseEvent {
  data: string[];
  event?: string;
  id?: string;
  retry?: number;
}

const createPendingEvent = (): PendingSseEvent => ({ data: [] });

export class SseParser {
  private buffer = "";
  private pending = createPendingEvent();

  push(chunk: string): ParsedSseEvent[] {
    this.buffer += chunk;
    const events: ParsedSseEvent[] = [];
    let boundary = findEventBoundary(this.buffer);

    while (boundary) {
      const block = this.buffer.slice(0, boundary.index);
      this.buffer = this.buffer.slice(boundary.end);
      const event = this.parseBlock(block);
      if (event) events.push(event);
      boundary = findEventBoundary(this.buffer);
    }

    return events;
  }

  flush(): ParsedSseEvent[] {
    if (!this.buffer.trim()) {
      this.buffer = "";
      return [];
    }
    const event = this.parseBlock(this.buffer);
    this.buffer = "";
    return event ? [event] : [];
  }

  private parseBlock(block: string): ParsedSseEvent | null {
    const lines = block.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
    for (const line of lines) {
      this.parseLine(line);
    }
    return this.dispatchPending();
  }

  private parseLine(line: string): void {
    if (line === "" || line.startsWith(":")) return;

    const separatorIndex = line.indexOf(":");
    const rawField = separatorIndex === -1 ? line : line.slice(0, separatorIndex);
    let value = separatorIndex === -1 ? "" : line.slice(separatorIndex + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    switch (rawField) {
      case "data":
        this.pending.data.push(value);
        break;
      case "event":
        this.pending.event = value;
        break;
      case "id":
        this.pending.id = value;
        break;
      case "retry": {
        const retry = Number(value);
        if (Number.isInteger(retry) && retry >= 0) {
          this.pending.retry = retry;
        }
        break;
      }
    }
  }

  private dispatchPending(): ParsedSseEvent | null {
    if (this.pending.data.length === 0) {
      this.pending = createPendingEvent();
      return null;
    }

    const event: ParsedSseEvent = {
      data: this.pending.data.join("\n"),
    };
    if (this.pending.event !== undefined) event.event = this.pending.event;
    if (this.pending.id !== undefined) event.id = this.pending.id;
    if (this.pending.retry !== undefined) event.retry = this.pending.retry;

    this.pending = createPendingEvent();
    return event;
  }
}

function findEventBoundary(buffer: string): { index: number; end: number } | null {
  const match = /\r\n\r\n|\n\n|\r\r/.exec(buffer);
  if (!match || match.index === undefined) return null;
  return {
    index: match.index,
    end: match.index + match[0].length,
  };
}
