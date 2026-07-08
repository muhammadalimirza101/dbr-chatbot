import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Conversation, Message } from "../api/types";

const PKT = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Karachi",
  hour: "2-digit",
  minute: "2-digit",
  day: "2-digit",
  month: "short",
});

function fmt(ts: string | null): string {
  return ts ? PKT.format(new Date(ts)) : "";
}

export default function Conversations() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "needs_human" | "flagged">("all");
  const [search, setSearch] = useState("");

  const params = new URLSearchParams({ status: "open" });
  if (filter === "needs_human") params.set("needs_human", "true");
  if (filter === "flagged") params.set("flagged", "true");
  if (search.trim()) params.set("search", search.trim());

  const { data: conversations = [] } = useQuery({
    queryKey: ["conversations", filter, search],
    queryFn: () => api.get<Conversation[]>(`/conversations?${params}`),
    refetchInterval: 30_000,
  });

  const selected = conversations.find((c) => c.id === selectedId) ?? null;

  return (
    <>
      <h1 className="page-title">
        Live Conversations
        <span className="sub">{conversations.length} open</span>
      </h1>
      <div className="toolbar">
        <input
          className="input"
          placeholder="Search phone or name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="select"
          value={filter}
          onChange={(e) => setFilter(e.target.value as typeof filter)}
        >
          <option value="all">All open</option>
          <option value="needs_human">With human / needs agent</option>
          <option value="flagged">High value 🔥</option>
        </select>
      </div>
      <div className="convo-layout">
        <div className="card convo-list">
          {conversations.length === 0 && <div className="empty">No conversations yet</div>}
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`convo-item ${c.id === selectedId ? "selected" : ""}`}
              onClick={() => setSelectedId(c.id)}
            >
              <div className="top">
                <span className="name">
                  {c.customer_name || c.customer_phone}
                  {c.flagged_high_value && " 🔥"}
                </span>
                <span className="dim" style={{ fontSize: 11 }}>{fmt(c.last_message_at)}</span>
              </div>
              <div className="row" style={{ gap: 6 }}>
                {c.bot_active ? (
                  <span className="badge green">bot</span>
                ) : (
                  <span className="badge amber">human</span>
                )}
                <span className="preview">{c.last_message_preview}</span>
              </div>
            </div>
          ))}
        </div>
        {selected ? (
          <Thread conversation={selected} />
        ) : (
          <div className="card empty" style={{ display: "grid", placeItems: "center" }}>
            Select a conversation
          </div>
        )}
      </div>
    </>
  );
}

function Thread({ conversation }: { conversation: Conversation }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);

  const { data: messages = [] } = useQuery({
    queryKey: ["messages", conversation.id],
    queryFn: () => api.get<Message[]>(`/conversations/${conversation.id}/messages`),
    refetchInterval: 15_000,
  });

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [messages.length, conversation.id]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
    queryClient.invalidateQueries({ queryKey: ["messages", conversation.id] });
  };

  const takeover = useMutation({
    mutationFn: () => api.post(`/conversations/${conversation.id}/takeover`),
    onSettled: invalidate,
  });
  const returnToBot = useMutation({
    mutationFn: () => api.post(`/conversations/${conversation.id}/return-to-bot`),
    onSettled: invalidate,
  });
  const reply = useMutation({
    mutationFn: (text: string) =>
      api.post(`/conversations/${conversation.id}/reply`, { text }),
    onSuccess: () => setDraft(""),
    onSettled: invalidate,
  });

  function onSend(event: FormEvent) {
    event.preventDefault();
    if (draft.trim()) reply.mutate(draft.trim());
  }

  return (
    <div className="card thread">
      <div className="thread-head">
        <strong>{conversation.customer_name || conversation.customer_phone}</strong>
        <span className="dim">{conversation.customer_phone}</span>
        {conversation.flagged_high_value && <span className="badge red">high value</span>}
        {conversation.bot_active ? (
          <span className="badge green">bot active</span>
        ) : (
          <span className="badge amber">agent mode</span>
        )}
        <div className="spacer" style={{ flex: 1 }} />
        {conversation.bot_active ? (
          <button className="btn small" onClick={() => takeover.mutate()}>
            Take over
          </button>
        ) : (
          <button className="btn small" onClick={() => returnToBot.mutate()}>
            Return to bot
          </button>
        )}
      </div>
      <div className="thread-body" ref={bodyRef}>
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.direction}`}>
            {m.content_type === "voice" ? (
              <span className="voice">
                🎤 {m.transcription ? `"${m.transcription}"` : "(voice note, transcribing…)"}
              </span>
            ) : m.content_type === "image" ? (
              <span>🖼 {m.content_text || "(image)"}</span>
            ) : (
              m.content_text
            )}
            <span className="meta">
              {m.sender_type} · {fmt(m.created_at)}
            </span>
          </div>
        ))}
        {messages.length === 0 && <div className="empty">No messages</div>}
      </div>
      <form className="thread-foot" onSubmit={onSend}>
        <input
          className="input"
          placeholder={
            conversation.bot_active
              ? "Take over to reply as an agent…"
              : "Type a reply…"
          }
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={conversation.bot_active || reply.isPending}
          maxLength={8000}
        />
        <button
          className="btn primary"
          disabled={conversation.bot_active || reply.isPending || !draft.trim()}
        >
          Send
        </button>
      </form>
      {reply.isError && (
        <p className="error-text" style={{ padding: "0 12px 10px" }}>
          Send failed — is the WhatsApp connector running?
        </p>
      )}
    </div>
  );
}
