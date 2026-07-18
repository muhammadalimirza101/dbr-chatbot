/**
 * Connector entrypoint: transport only, zero business logic.
 * Inbound WhatsApp -> POST backend webhook; backend -> POST /send here.
 */

import { BaileysTransport } from "./baileys.js";
import { BackendClient } from "./backendClient.js";
import { loadConfig } from "./config.js";
import { createServer } from "./server.js";

async function main(): Promise<void> {
  const config = loadConfig();
  const backend = new BackendClient(config);
  const transport = new BaileysTransport(config, (mediaId) => backend.fetchMedia(mediaId));

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
