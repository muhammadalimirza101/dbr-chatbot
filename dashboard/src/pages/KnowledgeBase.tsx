import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { KBEntry, Unanswered } from "../api/types";

export default function KnowledgeBase() {
  const [tab, setTab] = useState<"kb" | "unanswered">("kb");
  return (
    <>
      <h1 className="page-title">Knowledge Base</h1>
      <div className="tabs">
        <button className={tab === "kb" ? "active" : ""} onClick={() => setTab("kb")}>
          Entries
        </button>
        <button
          className={tab === "unanswered" ? "active" : ""}
          onClick={() => setTab("unanswered")}
        >
          Unanswered questions
        </button>
      </div>
      {tab === "kb" ? <Entries /> : <UnansweredQueue />}
    </>
  );
}

function Entries() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<KBEntry | "new" | null>(null);

  const { data: entries = [] } = useQuery({
    queryKey: ["kb"],
    queryFn: () => api.get<KBEntry[]>("/kb"),
  });

  const toggle = useMutation({
    mutationFn: (id: number) => api.patch<KBEntry>(`/kb/${id}/toggle`, {}),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["kb"] }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/kb/${id}`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["kb"] }),
  });

  return (
    <>
      <div className="toolbar">
        <span className="dim">{entries.length} entries — embeddings are generated automatically on save</span>
        <div style={{ flex: 1 }} />
        <button className="btn primary" onClick={() => setEditing("new")}>+ Add entry</button>
      </div>
      <div className="card">
        <table className="table">
          <thead>
            <tr><th>Question</th><th>Answer</th><th>Category</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} style={{ opacity: entry.is_active ? 1 : 0.55 }}>
                <td style={{ maxWidth: 280 }}>{entry.question}</td>
                <td style={{ maxWidth: 380 }} className="dim">
                  {entry.answer.length > 160 ? `${entry.answer.slice(0, 160)}…` : entry.answer}
                </td>
                <td><span className="badge blue">{entry.category}</span></td>
                <td>
                  {entry.is_active
                    ? <span className="badge green">active</span>
                    : <span className="badge gray">off</span>}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="btn small" onClick={() => setEditing(entry)}>Edit</button>{" "}
                  <button className="btn small" onClick={() => toggle.mutate(entry.id)}>
                    {entry.is_active ? "Disable" : "Enable"}
                  </button>{" "}
                  <button
                    className="btn small danger"
                    onClick={() => {
                      if (confirm("Delete this KB entry permanently?")) remove.mutate(entry.id);
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr><td colSpan={5} className="empty">No entries yet — add resort FAQs here</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && (
        <EntryModal
          entry={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

function EntryModal({ entry, onClose }: { entry: KBEntry | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState(entry?.question ?? "");
  const [answer, setAnswer] = useState(entry?.answer ?? "");
  const [category, setCategory] = useState(entry?.category ?? "");

  const save = useMutation({
    mutationFn: () =>
      entry
        ? api.put<KBEntry>(`/kb/${entry.id}`, { question, answer, category })
        : api.post<KBEntry>("/kb", { question, answer, category }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kb"] });
      onClose();
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <>
      <div className="modal-overlay" onClick={onClose} />
      <form className="modal" onSubmit={onSubmit}>
        <h2>{entry ? "Edit entry" : "New KB entry"}</h2>
        <div className="field">
          <label>Customer question</label>
          <textarea className="textarea" value={question} onChange={(e) => setQuestion(e.target.value)}
            required minLength={3} maxLength={2000} />
        </div>
        <div className="field">
          <label>Answer the bot should give</label>
          <textarea className="textarea" style={{ minHeight: 120 }} value={answer}
            onChange={(e) => setAnswer(e.target.value)} required maxLength={8000} />
        </div>
        <div className="field">
          <label>Category</label>
          <input className="input" value={category} onChange={(e) => setCategory(e.target.value)}
            placeholder="rooms / dining / transport / events / activities" required minLength={2} maxLength={50} />
        </div>
        {save.isError && <p className="error-text">Save failed.</p>}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={save.isPending}>
            {save.isPending ? "Saving + embedding…" : "Save"}
          </button>
        </div>
      </form>
    </>
  );
}

function UnansweredQueue() {
  const queryClient = useQueryClient();
  const [converting, setConverting] = useState<Unanswered | null>(null);

  const { data: questions = [] } = useQuery({
    queryKey: ["unanswered"],
    queryFn: () => api.get<Unanswered[]>("/kb/unanswered"),
  });

  const resolve = useMutation({
    mutationFn: (id: number) => api.post(`/kb/unanswered/${id}/resolve`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["unanswered"] }),
  });

  return (
    <>
      <div className="card">
        <table className="table">
          <thead>
            <tr><th>Customer asked</th><th>Best match</th><th>When</th><th></th></tr>
          </thead>
          <tbody>
            {questions.map((q) => (
              <tr key={q.id}>
                <td style={{ maxWidth: 420 }}>{q.question_text}</td>
                <td className="mono">{(q.best_similarity_score * 100).toFixed(0)}%</td>
                <td className="dim">
                  {new Date(q.created_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="btn small primary" onClick={() => setConverting(q)}>
                    Convert to KB
                  </button>{" "}
                  <button className="btn small" onClick={() => resolve.mutate(q.id)}>Dismiss</button>
                </td>
              </tr>
            ))}
            {questions.length === 0 && (
              <tr><td colSpan={4} className="empty">Queue is empty — the bot had answers for everything</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {converting && (
        <ConvertModal question={converting} onClose={() => setConverting(null)} />
      )}
    </>
  );
}

function ConvertModal({ question, onClose }: { question: Unanswered; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [q, setQ] = useState(question.question_text);
  const [answer, setAnswer] = useState("");
  const [category, setCategory] = useState("");

  const convert = useMutation({
    mutationFn: () =>
      api.post(`/kb/unanswered/${question.id}/convert`, { question: q, answer, category }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["unanswered"] });
      queryClient.invalidateQueries({ queryKey: ["kb"] });
      onClose();
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    convert.mutate();
  }

  return (
    <>
      <div className="modal-overlay" onClick={onClose} />
      <form className="modal" onSubmit={onSubmit}>
        <h2>Convert to KB entry</h2>
        <div className="field">
          <label>Question</label>
          <textarea className="textarea" value={q} onChange={(e) => setQ(e.target.value)} required minLength={3} />
        </div>
        <div className="field">
          <label>Answer</label>
          <textarea className="textarea" style={{ minHeight: 120 }} value={answer}
            onChange={(e) => setAnswer(e.target.value)} required
            placeholder="Write the answer the bot should give from now on" />
        </div>
        <div className="field">
          <label>Category</label>
          <input className="input" value={category} onChange={(e) => setCategory(e.target.value)} required minLength={2} maxLength={50} />
        </div>
        {convert.isError && <p className="error-text">Convert failed.</p>}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={convert.isPending}>
            {convert.isPending ? "Converting…" : "Create entry"}
          </button>
        </div>
      </form>
    </>
  );
}
