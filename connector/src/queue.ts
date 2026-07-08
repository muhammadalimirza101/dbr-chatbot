/**
 * Sequential outbound queue with human-like pacing.
 *
 * Every send waits a random 1.5–4 s (reads as typing time to WhatsApp) and
 * sends are strictly serialized, which also acts as a global rate limit
 * (~15–40 msgs/min worst case) to reduce ban risk on the linked device.
 */

const MIN_DELAY_MS = 1500;
const MAX_DELAY_MS = 4000;

function randomDelay(): number {
  return MIN_DELAY_MS + Math.random() * (MAX_DELAY_MS - MIN_DELAY_MS);
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export class SendQueue {
  private chain: Promise<void> = Promise.resolve();

  /** Enqueue a send. Resolves/rejects with the underlying task's outcome. */
  run<T>(task: () => Promise<T>): Promise<T> {
    const result = this.chain.then(async () => {
      await sleep(randomDelay());
      return task();
    });
    // keep the chain alive even when a task fails
    this.chain = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }
}
