/**
 * Thin HTTP client for the FastAPI backend.
 *
 * - Forwards inbound WhatsApp messages to the webhook (shared-secret header),
 *   retrying with backoff so a backend restart doesn't drop messages.
 * - Fetches media bytes by id for outbound sends (the connector never
 *   receives file paths — only opaque media ids).
 *
 * Logging note: message content and phone numbers never go to logs —
 * only provider message ids.
 */

import type { ConnectorConfig } from "./config.js";
import type { InboundMessage } from "./transport.js";

const SECRET_HEADER = "x-connector-secret";
const FORWARD_ATTEMPTS = 3;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export class BackendClient {
  constructor(private readonly config: ConnectorConfig) {}

  async forwardInbound(message: InboundMessage): Promise<void> {
    for (let attempt = 1; attempt <= FORWARD_ATTEMPTS; attempt++) {
      try {
        const response = await fetch(`${this.config.backendUrl}/webhook/whatsapp`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            [SECRET_HEADER]: this.config.sharedSecret,
          },
          body: JSON.stringify(message),
          signal: AbortSignal.timeout(30_000),
        });
        if (response.ok) {
          console.log(
            `inbound ${message.providerMessageId} (${message.contentType}) → backend ok`,
          );
          return;
        }
        // 4xx = backend rejected it (bad payload/secret) — retrying won't help
        if (response.status >= 400 && response.status < 500) {
          console.error(
            `backend REJECTED inbound ${message.providerMessageId}: HTTP ${response.status}` +
              (response.status === 401 ? " — CONNECTOR_SHARED_SECRET mismatch?" : ""),
          );
          return;
        }
        throw new Error(`HTTP ${response.status}`);
      } catch (error) {
        if (attempt === FORWARD_ATTEMPTS) {
          console.error(
            `giving up forwarding inbound ${message.providerMessageId} after ${attempt} attempts:`,
            error instanceof Error ? error.message : error,
            `— is the backend running on ${this.config.backendUrl}?`,
          );
          return;
        }
        await sleep(1000 * 3 ** (attempt - 1)); // 1s, 3s
      }
    }
  }

  /** Download a media asset's bytes from the backend internal endpoint. */
  async fetchMedia(mediaId: string): Promise<{ bytes: Buffer; mimeType: string }> {
    const response = await fetch(
      `${this.config.backendUrl}/internal/media/${encodeURIComponent(mediaId)}`,
      {
        headers: { [SECRET_HEADER]: this.config.sharedSecret },
        signal: AbortSignal.timeout(30_000),
      },
    );
    if (!response.ok) {
      throw new Error(`media fetch failed: HTTP ${response.status}`);
    }
    return {
      bytes: Buffer.from(await response.arrayBuffer()),
      mimeType: response.headers.get("content-type") ?? "application/octet-stream",
    };
  }
}
