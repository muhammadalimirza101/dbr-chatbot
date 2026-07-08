import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import type { Conversation, Customer } from "../api/types";

const LANGS = { en: "English", roman_urdu: "Roman Urdu", ur: "Urdu" } as const;

export default function Customers() {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Customer | null>(null);

  const { data: customers = [] } = useQuery({
    queryKey: ["customers", search],
    queryFn: () =>
      api.get<Customer[]>(
        `/customers${search.trim() ? `?search=${encodeURIComponent(search.trim())}` : ""}`,
      ),
  });

  return (
    <>
      <h1 className="page-title">
        Customers <span className="sub">{customers.length} shown</span>
      </h1>
      <div className="toolbar">
        <input
          className="input"
          placeholder="Search phone or name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 280 }}
        />
      </div>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Phone</th><th>Name</th><th>Language</th><th>Tags</th><th>Since</th><th></th>
            </tr>
          </thead>
          <tbody>
            {customers.map((customer) => (
              <tr key={customer.id}>
                <td className="mono">{customer.phone}</td>
                <td>{customer.name || <span className="dim">—</span>}</td>
                <td>{LANGS[customer.preferred_language]}</td>
                <td>
                  {customer.tags.map((tag) => (
                    <span className="badge gray" key={tag} style={{ marginRight: 4 }}>{tag}</span>
                  ))}
                </td>
                <td className="dim">{new Date(customer.created_at).toLocaleDateString("en-GB", { timeZone: "Asia/Karachi" })}</td>
                <td>
                  <button className="btn small" onClick={() => setSelected(customer)}>Profile</button>
                </td>
              </tr>
            ))}
            {customers.length === 0 && (
              <tr><td colSpan={6} className="empty">No customers found</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {selected && (
        <CustomerDrawer customer={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}

function CustomerDrawer({ customer, onClose }: { customer: Customer; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(customer.name ?? "");
  const [language, setLanguage] = useState(customer.preferred_language);
  const [tags, setTags] = useState(customer.tags.join(", "));

  const { data: conversations = [] } = useQuery({
    queryKey: ["customer-conversations", customer.id],
    queryFn: () => api.get<Conversation[]>(`/customers/${customer.id}/conversations`),
  });

  const save = useMutation({
    mutationFn: () =>
      api.patch<Customer>(`/customers/${customer.id}`, {
        name: name || null,
        preferred_language: language,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean)
          .slice(0, 20),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      onClose();
    },
  });

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">
        <h2>
          {customer.name || customer.phone} <span className="badge gray mono">{customer.phone}</span>
        </h2>
        <div className="field">
          <label>Name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
        </div>
        <div className="field">
          <label>Preferred language</label>
          <select className="select" value={language} onChange={(e) => setLanguage(e.target.value as Customer["preferred_language"])}>
            {Object.entries(LANGS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Tags (comma-separated)</label>
          <input className="input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="vip, wedding-2026" />
        </div>
        <button className="btn primary" onClick={() => save.mutate()} disabled={save.isPending}>
          Save profile
        </button>
        {save.isError && <p className="error-text">Save failed.</p>}

        <div className="field" style={{ marginTop: 22 }}>
          <label>Conversation history</label>
          {conversations.map((c) => (
            <div key={c.id} className="card pad" style={{ marginBottom: 8, fontSize: 13 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong>#{c.id}</strong>
                <span className={`badge ${c.status === "open" ? "green" : "gray"}`}>{c.status}</span>
              </div>
              <span className="dim">
                {c.flagged_high_value && "🔥 high value · "}
                last activity {c.last_message_at ? new Date(c.last_message_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" }) : "—"}
              </span>
            </div>
          ))}
          {conversations.length === 0 && <span className="dim">No conversations</span>}
        </div>
        <button className="btn" onClick={onClose}>Close</button>
      </div>
    </>
  );
}
