import type { Event, NewEvent } from '@agentigram/protocol';
import { NewEventSchema } from '@agentigram/protocol';
import type { Cursor } from './cursor-store.js';

const MAX_BATCH = 100;
const RETRY_MS = 2_000;

type BridgeLog = {
  info(obj: object, msg?: string): void;
  warn(obj: object, msg?: string): void;
};

/** One-way relay from the local authority room into the hosted dashboard room. */
export class CoordinatorBridge {
  private readonly queue: Event[] = [];
  private running = false;
  private stopped = false;

  constructor(
    private readonly options: {
      url: string;
      roomId: string;
      secret: string;
      cursor: Cursor;
      log: BridgeLog;
    },
  ) {}

  get lastLocalSeq(): number {
    return this.options.cursor.get();
  }

  enqueue(events: Event[]): void {
    const seen = new Set(this.queue.map((event) => event.id));
    for (const event of events) {
      if (event.seq > this.lastLocalSeq && !seen.has(event.id)) this.queue.push(event);
    }
    this.queue.sort((left, right) => left.seq - right.seq);
    void this.drain();
  }

  stop(): void {
    this.stopped = true;
  }

  private async drain(): Promise<void> {
    if (this.running || this.stopped) return;
    this.running = true;
    try {
      while (this.queue.length > 0 && !this.stopped) {
        const batch = this.queue.slice(0, MAX_BATCH);
        try {
          await this.send(batch);
          this.queue.splice(0, batch.length);
          this.options.cursor.set(batch.at(-1)?.seq ?? this.lastLocalSeq);
        } catch (error) {
          this.options.log.warn(
            { err: error instanceof Error ? error.message : String(error), queued: this.queue.length },
            'hosted coordinator relay failed; retrying',
          );
          await new Promise((resolve) => setTimeout(resolve, RETRY_MS));
        }
      }
    } finally {
      this.running = false;
    }
  }

  private async send(events: Event[]): Promise<void> {
    const body: NewEvent[] = events.map(({ seq: _seq, ts: _ts, ...event }) =>
      NewEventSchema.parse(event),
    );
    const response = await fetch(
      `${this.options.url.replace(/\/+$/, '')}/room/${encodeURIComponent(this.options.roomId)}/bridge`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.options.secret}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(10_000),
      },
    );
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 300);
      throw new Error(`HTTP ${response.status}: ${detail}`);
    }
    this.options.log.info({ count: events.length }, 'relayed local room events to hosted coordinator');
  }
}
