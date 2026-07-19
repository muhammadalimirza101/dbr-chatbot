/**
 * Baileys auth state stored in Postgres, via the backend's shared-secret
 * /internal/wa-auth endpoints (the connector never talks to the DB
 * directly). Restarts and redeploys reconnect silently — no QR re-scan.
 *
 * Mirrors Baileys' useMultiFileAuthState contract: BufferJSON
 * (de)serialization and the app-state-sync-key proto special case.
 */

import {
  BufferJSON,
  initAuthCreds,
  proto,
  type AuthenticationCreds,
  type AuthenticationState,
  type SignalDataTypeMap,
} from "baileys";

import type { BackendClient } from "./backendClient.js";

const CREDS_KEY = "creds";

function serialize(value: unknown): string {
  return JSON.stringify(value, BufferJSON.replacer);
}

function deserialize(raw: string): unknown {
  return JSON.parse(raw, BufferJSON.reviver);
}

export interface AuthProvider {
  state: AuthenticationState;
  saveCreds: () => Promise<void>;
}

export async function usePostgresAuthState(
  backend: BackendClient,
): Promise<AuthProvider> {
  const stored = (await backend.authGet([CREDS_KEY]))[CREDS_KEY];
  const creds: AuthenticationCreds = stored
    ? (deserialize(stored) as AuthenticationCreds)
    : initAuthCreds();
  if (!stored) {
    console.log("no stored WhatsApp session — pairing required (QR will print)");
  } else {
    console.log("restored WhatsApp session from database");
  }

  return {
    state: {
      creds,
      keys: {
        get: async <T extends keyof SignalDataTypeMap>(
          type: T,
          ids: string[],
        ): Promise<{ [id: string]: SignalDataTypeMap[T] }> => {
          const rows = await backend.authGet(ids.map((id) => `${type}-${id}`));
          const data: { [id: string]: SignalDataTypeMap[T] } = {};
          for (const id of ids) {
            const raw = rows[`${type}-${id}`];
            if (raw === null || raw === undefined) continue;
            let value = deserialize(raw);
            if (type === "app-state-sync-key" && value) {
              value = proto.Message.AppStateSyncKeyData.fromObject(value);
            }
            data[id] = value as SignalDataTypeMap[T];
          }
          return data;
        },
        set: async (data): Promise<void> => {
          const values: Record<string, string | null> = {};
          for (const category of Object.keys(data) as (keyof SignalDataTypeMap)[]) {
            const entries = data[category];
            if (!entries) continue;
            for (const id of Object.keys(entries)) {
              const value = entries[id];
              values[`${category}-${id}`] = value ? serialize(value) : null;
            }
          }
          if (Object.keys(values).length > 0) {
            await backend.authSet(values);
          }
        },
      },
    },
    saveCreds: async () => {
      await backend.authSet({ [CREDS_KEY]: serialize(creds) });
    },
  };
}
