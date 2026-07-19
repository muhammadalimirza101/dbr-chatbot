/**
 * Connector entrypoint: transport only, zero business logic.
 * Inbound WhatsApp -> POST backend webhook; backend -> POST /send here.
 *
 * Session storage: WA_AUTH_STORE=postgres keeps the Baileys session in the
 * database (via the backend) so restarts/redeploys reconnect without a QR.
 * Default is local files (WHATSAPP_SESSION_DIR).
 */

import { useMultiFileAuthState } from "baileys";

import { usePostgresAuthState, type AuthProvider } from "./authState.js";
import { BaileysTransport } from "./baileys.js";
import { BackendClient } from "./backendClient.js";
import { loadConfig } from "./config.js";
import { createServer } from "./server.js";

async function main(): Promise<void> {
  const config = loadConfig();
  const backend = new BackendClient(config);

  const authProvider: () => Promise<AuthProvider> =
    config.authStore === "postgres"
      ? () => usePostgresAuthState(backend)
      : () => useMultiFileAuthState(config.sessionDir);

  if (config.resetSession && config.authStore === "postgres") {
    await backend.authClear();
    console.log(
      "WA_RESET_SESSION: stored session wiped — scan the new QR, then REMOVE " +
        "the WA_RESET_SESSION env var so future restarts keep the session.",
    );
  }

  // logged out (e.g. unlinked from the phone, or switching numbers):
  // wipe stale session material and exit — the platform restarts us and a
  // fresh QR prints for pairing.
  const onLoggedOut = async () => {
    if (config.authStore === "postgres") {
      try {
        await backend.authClear();
        console.log("stored session cleared after logout");
      } catch (error) {
        console.error(
          "could not clear stored session:",
          error instanceof Error ? error.message : error,
        );
      }
    }
    console.log("restarting for fresh pairing…");
    process.exit(1);
  };

  const transport = new BaileysTransport(
    config,
    (mediaId) => backend.fetchMedia(mediaId),
    authProvider,
    onLoggedOut,
  );

  transport.onMessageReceived((message) => backend.forwardInbound(message));

  const app = createServer(config, transport);
  // 127.0.0.1 locally; 0.0.0.0 only on a PaaS (see CONNECTOR_HOST in config)
  app.listen(config.port, config.host, () => {
    console.log(`connector internal API on ${config.host}:${config.port}`);
  });

  await transport.start();

  for (const signal of ["SIGINT", "SIGTERM"] as const) {
    process.on(signal, () => {
      void transport.stop().finally(() => process.exit(0));
    });
  }
}

main().catch((error) => {
  console.error("fatal:", error instanceof Error ? error.message : error);
  process.exit(1);
});
