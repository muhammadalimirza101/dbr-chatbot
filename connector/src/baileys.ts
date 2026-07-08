/**
 * Baileys v7 implementation of WhatsAppTransport (linked-device mode).
 *
 * THE ONLY FILE that may import Baileys. Everything Baileys-specific stays
 * behind the WhatsAppTransport interface so this module can be replaced by
 * the official WhatsApp Business Cloud API without touching anything else.
 */

import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  useMultiFileAuthState,
  type WAMessage,
} from "baileys";
import { Boom } from "@hapi/boom";
import pino from "pino";
import qrcode from "qrcode-terminal";

import type { ConnectorConfig } from "./config.js";
import { SendQueue } from "./queue.js";
import type {
  InboundMessage,
  OutboundLocation,
  OutboundMedia,
  OutboundText,
  WhatsAppTransport,
} from "./transport.js";

const MAX_INBOUND_MEDIA_BYTES = 16 * 1024 * 1024; // WhatsApp voice/images are far below this

// silent for payload safety: Baileys debug logs can include message content
const logger = pino({ level: "silent" });

type MediaFetcher = (mediaId: string) => Promise<{ bytes: Buffer; mimeType: string }>;

export class BaileysTransport implements WhatsAppTransport {
  private socket: ReturnType<typeof makeWASocket> | null = null;
  private connected = false;
  private stopping = false;
  private handler: ((message: InboundMessage) => Promise<void>) | null = null;
  private readonly queue = new SendQueue();

  constructor(
    private readonly config: ConnectorConfig,
    private readonly fetchMedia: MediaFetcher,
  ) {}

  onMessageReceived(handler: (message: InboundMessage) => Promise<void>): void {
    this.handler = handler;
  }

  isConnected(): boolean {
    return this.connected;
  }

  async start(): Promise<void> {
    const { state, saveCreds } = await useMultiFileAuthState(this.config.sessionDir);

    const socket = makeWASocket({
      auth: state,
      logger,
      markOnlineOnConnect: false, // keep the phone's own notifications working
      syncFullHistory: false,
    });
    this.socket = socket;

    socket.ev.on("creds.update", saveCreds);

    socket.ev.on("connection.update", (update) => {
      const { connection, lastDisconnect, qr } = update;
      if (qr) {
        console.log("\nScan this QR with WhatsApp (Linked devices > Link a device):\n");
        qrcode.generate(qr, { small: true });
      }
      if (connection === "open") {
        this.connected = true;
        console.log("WhatsApp connection established");
      }
      if (connection === "close") {
        this.connected = false;
        const statusCode = (lastDisconnect?.error as Boom | undefined)?.output?.statusCode;
        if (statusCode === DisconnectReason.loggedOut) {
          console.error(
            "Session logged out. Delete the session directory contents and re-pair.",
          );
          return;
        }
        if (!this.stopping) {
          console.log("Connection closed, reconnecting…");
          void this.start();
        }
      }
    });

    socket.ev.on("messages.upsert", ({ messages, type }) => {
      if (type !== "notify") return;
      for (const message of messages) {
        void this.handleInbound(message);
      }
    });
  }

  async stop(): Promise<void> {
    this.stopping = true;
    this.socket?.end(undefined);
    this.connected = false;
  }

  async sendMessage(message: OutboundText): Promise<void> {
    await this.queue.run(async () => {
      const jid = toJid(message.phone);
      await this.presenceTyping(jid);
      await this.mustSocket().sendMessage(jid, { text: message.text });
    });
  }

  async sendMedia(message: OutboundMedia | OutboundLocation): Promise<void> {
    await this.queue.run(async () => {
      const jid = toJid(message.phone);
      const socket = this.mustSocket();
      if (message.kind === "location") {
        await socket.sendMessage(jid, {
          location: {
            degreesLatitude: message.latitude,
            degreesLongitude: message.longitude,
            name: message.name,
          },
        });
        return;
      }
      const { bytes, mimeType } = await this.fetchMedia(message.mediaId);
      if (message.mediaType === "image") {
        await socket.sendMessage(jid, { image: bytes, caption: message.caption });
      } else {
        await socket.sendMessage(jid, {
          document: bytes,
          mimetype: mimeType,
          fileName: message.caption ?? "document.pdf",
        });
      }
    });
  }

  private mustSocket(): ReturnType<typeof makeWASocket> {
    if (!this.socket || !this.connected) {
      throw new Error("WhatsApp is not connected");
    }
    return this.socket;
  }

  /** Brief "typing…" presence so replies read as human. Best-effort. */
  private async presenceTyping(jid: string): Promise<void> {
    try {
      await this.socket?.sendPresenceUpdate("composing", jid);
      await new Promise((resolve) => setTimeout(resolve, 400));
      await this.socket?.sendPresenceUpdate("paused", jid);
    } catch {
      /* presence is cosmetic — never fail a send over it */
    }
  }

  private async handleInbound(message: WAMessage): Promise<void> {
    try {
      if (!this.handler) return;
      const messageId = message.key.id ?? "?";
      let jid = message.key.remoteJid;
      // WhatsApp LID privacy addressing: the chat arrives as <id>@lid and the
      // real phone jid travels in remoteJidAlt — use it, or we can't route
      const alt = (message.key as { remoteJidAlt?: string | null }).remoteJidAlt;
      if (jid?.endsWith("@lid") && alt?.endsWith("@s.whatsapp.net")) {
        jid = alt;
      }
      // transport scope: direct customer chats only — no groups, no status,
      // no own messages. Log every drop so silence is never a mystery.
      if (!jid || message.key.fromMe) {
        console.log(`inbound ${messageId}: ignored (own message)`);
        return;
      }
      if (!jid.endsWith("@s.whatsapp.net")) {
        const kind = jid.endsWith("@g.us") ? "group" : jid.split("@")[1] ?? "unknown";
        console.log(`inbound ${messageId}: ignored (${kind} chat, not a direct customer)`);
        return;
      }
      const content = message.message;
      if (!content) {
        console.log(`inbound ${messageId}: ignored (no content — receipt/protocol event)`);
        return;
      }

      const phone = jid.split("@")[0].split(":")[0];
      const providerMessageId = message.key.id ?? `${jid}:${message.messageTimestamp}`;
      const timestamp = new Date(Number(message.messageTimestamp) * 1000).toISOString();
      const base = { phone, providerMessageId, timestamp } as const;

      const text = content.conversation ?? content.extendedTextMessage?.text;
      if (text) {
        await this.handler({ ...base, contentType: "text", text });
        return;
      }

      const audio = content.audioMessage;
      if (audio) {
        const bytes = await this.download(message, Number(audio.fileLength ?? 0));
        if (!bytes) return;
        await this.handler({
          ...base,
          contentType: "voice",
          mediaBase64: bytes.toString("base64"),
          mediaMimeType: audio.mimetype ?? "audio/ogg; codecs=opus",
        });
        return;
      }

      const image = content.imageMessage;
      if (image) {
        const bytes = await this.download(message, Number(image.fileLength ?? 0));
        if (!bytes) return;
        await this.handler({
          ...base,
          contentType: "image",
          text: image.caption ?? undefined,
          mediaBase64: bytes.toString("base64"),
          mediaMimeType: image.mimetype ?? "image/jpeg",
        });
        return;
      }
      console.log(
        `inbound ${messageId}: ignored (unsupported type: ${Object.keys(content).join(",")})`,
      );
    } catch (error) {
      console.error(
        `failed to process inbound ${message.key?.id}:`,
        error instanceof Error ? error.message : error,
      );
    }
  }

  private async download(message: WAMessage, declaredSize: number): Promise<Buffer | null> {
    if (declaredSize > MAX_INBOUND_MEDIA_BYTES) {
      console.error(`inbound media ${message.key.id} exceeds size limit, skipping`);
      return null;
    }
    const socket = this.socket;
    if (!socket) return null;
    const buffer = (await downloadMediaMessage(message, "buffer", {}, {
      logger,
      reuploadRequest: socket.updateMediaMessage,
    })) as Buffer;
    if (buffer.length > MAX_INBOUND_MEDIA_BYTES) {
      console.error(`inbound media ${message.key.id} exceeds size limit, skipping`);
      return null;
    }
    return buffer;
  }
}

function toJid(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 8 || digits.length > 15) {
    throw new Error("invalid phone number");
  }
  return `${digits}@s.whatsapp.net`;
}
