/**
 * Internal HTTP API for the backend — bound to 127.0.0.1 only and protected
 * by the shared secret header (timing-safe comparison). No business logic:
 * it validates transport-level shape and hands off to the transport.
 */

import { createHash, timingSafeEqual } from "node:crypto";
import express, { type NextFunction, type Request, type Response } from "express";

import type { ConnectorConfig } from "./config.js";
import type {
  OutboundLocation,
  OutboundMedia,
  OutboundText,
  WhatsAppTransport,
} from "./transport.js";

const SECRET_HEADER = "x-connector-secret";

function secretsMatch(provided: string, expected: string): boolean {
  // hash both to fixed length so timingSafeEqual never throws on length
  const a = createHash("sha256").update(provided).digest();
  const b = createHash("sha256").update(expected).digest();
  return timingSafeEqual(a, b);
}

const isNonEmptyString = (v: unknown): v is string =>
  typeof v === "string" && v.trim().length > 0;

/** Transport-level shape check only — content policy lives in the backend. */
function parseOutbound(body: unknown): OutboundText | OutboundMedia | OutboundLocation | null {
  if (typeof body !== "object" || body === null) return null;
  const b = body as Record<string, unknown>;
  if (!isNonEmptyString(b.phone)) return null;

  switch (b.kind) {
    case "text":
      return isNonEmptyString(b.text) && b.text.length <= 8000
        ? { kind: "text", phone: b.phone, text: b.text }
        : null;
    case "media":
      return isNonEmptyString(b.mediaId) &&
        (b.mediaType === "image" || b.mediaType === "pdf") &&
        (b.caption === undefined || (typeof b.caption === "string" && b.caption.length <= 1000))
        ? {
            kind: "media",
            phone: b.phone,
            mediaId: b.mediaId,
            mediaType: b.mediaType,
            caption: b.caption as string | undefined,
          }
        : null;
    case "location":
      return typeof b.latitude === "number" &&
        typeof b.longitude === "number" &&
        Math.abs(b.latitude) <= 90 &&
        Math.abs(b.longitude) <= 180
        ? {
            kind: "location",
            phone: b.phone,
            latitude: b.latitude,
            longitude: b.longitude,
            name: isNonEmptyString(b.name) ? b.name : undefined,
          }
        : null;
    default:
      return null;
  }
}

export function createServer(config: ConnectorConfig, transport: WhatsAppTransport) {
  const app = express();
  app.disable("x-powered-by");
  app.use(express.json({ limit: "64kb" })); // media travels by id, not payload

  // unauthenticated liveness probe for platform health checks — status only
  app.get("/healthz", (_req: Request, res: Response) => {
    res.json({ ok: true });
  });

  app.use((req: Request, res: Response, next: NextFunction) => {
    const provided = req.header(SECRET_HEADER);
    if (!provided || !secretsMatch(provided, config.sharedSecret)) {
      res.status(401).json({ error: "unauthorized" });
      return;
    }
    next();
  });

  app.get("/status", (_req: Request, res: Response) => {
    res.json({ connected: transport.isConnected() });
  });

  app.post("/send", async (req: Request, res: Response) => {
    const message = parseOutbound(req.body);
    if (!message) {
      res.status(422).json({ error: "invalid outbound message" });
      return;
    }
    if (!transport.isConnected()) {
      res.status(503).json({ error: "whatsapp not connected" });
      return;
    }
    try {
      if (message.kind === "text") {
        await transport.sendMessage(message);
      } else {
        await transport.sendMedia(message);
      }
      res.json({ sent: true });
    } catch (error) {
      console.error("send failed:", error instanceof Error ? error.message : error);
      res.status(502).json({ error: "send failed" });
    }
  });

  return app;
}
