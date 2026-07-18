/**
 * Connector configuration, loaded from the repo-root .env.
 * Fails fast on anything missing — no silent fallbacks for secrets.
 */

import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import dotenv from "dotenv";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
dotenv.config({ path: path.join(repoRoot, ".env") });

function required(name: string): string {
  const value = process.env[name];
  if (!value || value.trim() === "") {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value.trim();
}

export interface ConnectorConfig {
  sessionDir: string;
  sharedSecret: string;
  backendUrl: string;
  /** Port for the internal HTTP server (PaaS platforms inject PORT) */
  port: number;
  /** Bind address. 127.0.0.1 locally; set CONNECTOR_HOST=0.0.0.0 on a PaaS
   * where the backend reaches this service over the platform network —
   * every request still requires the shared secret. */
  host: string;
}

export function loadConfig(): ConnectorConfig {
  const sessionDir = required("WHATSAPP_SESSION_DIR");
  if (path.resolve(sessionDir).startsWith(repoRoot)) {
    throw new Error(
      "WHATSAPP_SESSION_DIR must be OUTSIDE the repository — session files grant full control of the WhatsApp account",
    );
  }
  if (!existsSync(sessionDir)) {
    // 0o700: owner-only. POSIX perms are a no-op on Windows (NTFS ACLs apply);
    // the dir lives under the user profile, which is owner-restricted by default.
    mkdirSync(sessionDir, { recursive: true, mode: 0o700 });
  }
  return {
    sessionDir,
    sharedSecret: required("CONNECTOR_SHARED_SECRET"),
    backendUrl: (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, ""),
    port: Number(process.env.PORT ?? process.env.CONNECTOR_PORT ?? 3001),
    host: process.env.CONNECTOR_HOST ?? "127.0.0.1",
  };
}
