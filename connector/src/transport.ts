/**
 * Provider-agnostic WhatsApp transport interface.
 *
 * The rest of the system (backend, this service's HTTP layer) depends ONLY
 * on these types. The Baileys implementation lives behind this interface so
 * it can be replaced by the official WhatsApp Business Cloud API without
 * touching anything else. Baileys types must never appear outside its
 * implementation module.
 */

export type InboundContentType = "text" | "voice" | "image" | "pdf" | "location";

export interface InboundMessage {
  /** Customer phone in E.164 without "+", e.g. "923001234567" */
  phone: string;
  contentType: InboundContentType;
  text?: string;
  /** Raw media bytes (voice/image) forwarded to the backend for processing */
  mediaBase64?: string;
  mediaMimeType?: string;
  /** Provider message id, for dedup */
  providerMessageId: string;
  timestamp: string; // ISO 8601 UTC
}

export interface OutboundText {
  kind: "text";
  phone: string;
  text: string;
}

export interface OutboundMedia {
  kind: "media";
  phone: string;
  /** Backend media_assets id — the connector never accepts file paths */
  mediaId: string;
  mediaType: "image" | "pdf";
  caption?: string;
}

export interface OutboundLocation {
  kind: "location";
  phone: string;
  latitude: number;
  longitude: number;
  name?: string;
}

export type OutboundMessage = OutboundText | OutboundMedia | OutboundLocation;

export interface WhatsAppTransport {
  /** Connect / pair and start listening. Resolves once ready. */
  start(): Promise<void>;
  stop(): Promise<void>;
  sendMessage(message: OutboundText): Promise<void>;
  sendMedia(message: OutboundMedia | OutboundLocation): Promise<void>;
  onMessageReceived(handler: (message: InboundMessage) => Promise<void>): void;
  isConnected(): boolean;
}
