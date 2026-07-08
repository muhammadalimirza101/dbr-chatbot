export type Role = "admin" | "agent";
export type LeadStage = "new" | "contacted" | "qualified" | "booking_sent" | "won" | "lost";
export type InterestType = "room" | "event_wedding" | "corporate" | "day_trip" | "other";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
}

export interface UserAdmin extends User {
  is_active: boolean;
  created_at: string;
}

export interface Conversation {
  id: number;
  customer_id: number;
  customer_phone: string;
  customer_name: string | null;
  bot_active: boolean;
  assigned_agent_id: number | null;
  status: "open" | "closed";
  flagged_high_value: boolean;
  last_message_at: string | null;
  last_message_preview?: string | null;
}

export interface Message {
  id: number;
  conversation_id: number;
  direction: "inbound" | "outbound";
  sender_type: "customer" | "bot" | "agent";
  content_type: "text" | "voice" | "image" | "pdf" | "location";
  content_text: string | null;
  transcription: string | null;
  media_id: number | null;
  tokens_used: number | null;
  created_at: string;
}

export interface Lead {
  id: number;
  customer_id: number;
  customer_phone: string | null;
  customer_name: string | null;
  conversation_id: number | null;
  source: "bot" | "manual";
  interest_type: InterestType;
  stage: LeadStage;
  details: Record<string, unknown>;
  ai_summary: string | null;
  assigned_agent_id: number | null;
  follow_up_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Customer {
  id: number;
  phone: string;
  name: string | null;
  preferred_language: "en" | "roman_urdu" | "ur";
  tags: string[];
  created_at: string;
}

export interface KBEntry {
  id: number;
  question: string;
  answer: string;
  category: string;
  is_active: boolean;
  has_embedding: boolean;
  created_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface Unanswered {
  id: number;
  conversation_id: number;
  question_text: string;
  best_similarity_score: number;
  resolved: boolean;
  created_at: string;
}

export interface MediaAsset {
  id: number;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  purpose: "room_photo" | "rate_card" | "location" | "other";
  created_at: string;
}

export interface AnalyticsOverview {
  conversations_per_day: { date: string; count: number }[];
  token_spend_per_day: { date: string; tokens: number }[];
  cache_hit_rate: number | null;
  route_counts: Record<string, number>;
  leads_by_stage: Record<LeadStage, number>;
  lead_conversion_rate: number | null;
  avg_first_response_seconds: number | null;
  busiest_hours_utc: { hour: number; count: number }[];
}
