import { DragDropContext, Draggable, Droppable, type DropResult } from "@hello-pangea/dnd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { InterestType, Lead, LeadStage, UserAdmin } from "../api/types";
import { useAuth } from "../auth/AuthContext";

const STAGES: { id: LeadStage; label: string }[] = [
  { id: "new", label: "New" },
  { id: "contacted", label: "Contacted" },
  { id: "qualified", label: "Qualified" },
  { id: "booking_sent", label: "Booking sent" },
  { id: "won", label: "Won" },
  { id: "lost", label: "Lost" },
];

const INTERESTS: InterestType[] = ["room", "event_wedding", "corporate", "day_trip", "other"];

const INTEREST_LABEL: Record<InterestType, string> = {
  room: "Room",
  event_wedding: "Wedding",
  corporate: "Corporate",
  day_trip: "Day trip",
  other: "Other",
};

function isOverdue(lead: Lead): boolean {
  return (
    !!lead.follow_up_at &&
    new Date(lead.follow_up_at) < new Date() &&
    lead.stage !== "won" &&
    lead.stage !== "lost"
  );
}

export default function Leads() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [view, setView] = useState<"board" | "overdue">("board");
  const [detail, setDetail] = useState<Lead | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  const { data: leads = [] } = useQuery({
    queryKey: ["leads"],
    queryFn: () => api.get<Lead[]>("/leads"),
    refetchInterval: 30_000,
  });
  const { data: agents = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserAdmin[]>("/users"),
    enabled: user?.role === "admin",
  });

  const byStage = useMemo(() => {
    const map = new Map<LeadStage, Lead[]>(STAGES.map((s) => [s.id, []]));
    for (const lead of leads) map.get(lead.stage)?.push(lead);
    return map;
  }, [leads]);

  const overdue = leads.filter(isOverdue);

  const move = useMutation({
    mutationFn: ({ id, stage }: { id: number; stage: LeadStage }) =>
      api.patch<Lead>(`/leads/${id}`, { stage }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["leads"] }),
  });

  function onDragEnd(result: DropResult) {
    if (!result.destination) return;
    const stage = result.destination.droppableId as LeadStage;
    const id = Number(result.draggableId);
    if (stage !== result.source.droppableId) move.mutate({ id, stage });
  }

  return (
    <>
      <h1 className="page-title">
        Leads
        <span className="sub">{leads.length} total</span>
        <div style={{ flex: 1 }} />
        <button className="btn" onClick={() => setView(view === "board" ? "overdue" : "board")}>
          {view === "board" ? `Overdue follow-ups (${overdue.length})` : "Back to board"}
        </button>
        <button className="btn primary" onClick={() => setShowAdd(true)}>
          + Add lead
        </button>
      </h1>

      {view === "overdue" ? (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Customer</th><th>Interest</th><th>Stage</th><th>Follow-up was due</th><th></th>
              </tr>
            </thead>
            <tbody>
              {overdue.map((lead) => (
                <tr key={lead.id}>
                  <td>{lead.customer_name || lead.customer_phone}</td>
                  <td>{INTEREST_LABEL[lead.interest_type]}</td>
                  <td><span className="badge blue">{lead.stage}</span></td>
                  <td className="mono">{new Date(lead.follow_up_at!).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })}</td>
                  <td><button className="btn small" onClick={() => setDetail(lead)}>Open</button></td>
                </tr>
              ))}
              {overdue.length === 0 && (
                <tr><td colSpan={5} className="empty">Nothing overdue 🎉</td></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <DragDropContext onDragEnd={onDragEnd}>
          <div className="kanban">
            {STAGES.map((stage) => (
              <Droppable droppableId={stage.id} key={stage.id}>
                {(provided) => (
                  <div className="kanban-col" ref={provided.innerRef} {...provided.droppableProps}>
                    <h3>
                      {stage.label}
                      <span>{byStage.get(stage.id)?.length ?? 0}</span>
                    </h3>
                    {byStage.get(stage.id)?.map((lead, index) => (
                      <Draggable draggableId={String(lead.id)} index={index} key={lead.id}>
                        {(drag) => (
                          <div
                            className={`lead-card ${isOverdue(lead) ? "overdue" : ""}`}
                            ref={drag.innerRef}
                            {...drag.draggableProps}
                            {...drag.dragHandleProps}
                            onClick={() => setDetail(lead)}
                          >
                            <div className="who">{lead.customer_name || lead.customer_phone}</div>
                            <div className="meta">
                              <span className="badge gray">{INTEREST_LABEL[lead.interest_type]}</span>
                              <span className="badge gray">{lead.source}</span>
                              {isOverdue(lead) && <span className="badge red">overdue</span>}
                            </div>
                          </div>
                        )}
                      </Draggable>
                    ))}
                    {provided.placeholder}
                  </div>
                )}
              </Droppable>
            ))}
          </div>
        </DragDropContext>
      )}

      {detail && (
        <LeadDrawer
          lead={detail}
          agents={agents}
          onClose={() => setDetail(null)}
        />
      )}
      {showAdd && <AddLeadModal onClose={() => setShowAdd(false)} />}
    </>
  );
}

function LeadDrawer({
  lead,
  agents,
  onClose,
}: {
  lead: Lead;
  agents: UserAdmin[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [followUp, setFollowUp] = useState(
    lead.follow_up_at ? lead.follow_up_at.slice(0, 16) : "",
  );

  const update = useMutation({
    mutationFn: (patch: Record<string, unknown>) =>
      api.patch<Lead>(`/leads/${lead.id}`, patch),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["leads"] }),
  });

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">
        <h2>
          {lead.customer_name || lead.customer_phone}{" "}
          <span className="badge gray">{lead.source}</span>
        </h2>
        <div className="field">
          <label>Phone</label>
          <div className="mono">{lead.customer_phone}</div>
        </div>
        {lead.ai_summary && (
          <div className="field">
            <label>AI summary</label>
            <div className="card pad" style={{ fontSize: 13 }}>{lead.ai_summary}</div>
          </div>
        )}
        <div className="field">
          <label>Details</label>
          <div className="card pad" style={{ fontSize: 12.5 }}>
            {Object.entries(lead.details).length === 0 && <span className="dim">none</span>}
            {Object.entries(lead.details).map(([key, value]) => (
              <div key={key}>
                <strong>{key}:</strong> {String(value)}
              </div>
            ))}
          </div>
        </div>
        <div className="field">
          <label>Stage</label>
          <select
            className="select"
            value={lead.stage}
            onChange={(e) => update.mutate({ stage: e.target.value })}
          >
            {STAGES.map((s) => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Assigned agent</label>
          <select
            className="select"
            value={lead.assigned_agent_id ?? ""}
            onChange={(e) =>
              update.mutate({
                assigned_agent_id: e.target.value ? Number(e.target.value) : null,
              })
            }
          >
            <option value="">Unassigned</option>
            {agents
              .filter((a) => a.is_active)
              .map((a) => (
                <option key={a.id} value={a.id}>{a.full_name}</option>
              ))}
          </select>
        </div>
        <div className="field">
          <label>Follow-up (PKT)</label>
          <div className="row">
            <input
              className="input"
              type="datetime-local"
              value={followUp}
              onChange={(e) => setFollowUp(e.target.value)}
            />
            <button
              className="btn small"
              onClick={() =>
                update.mutate({
                  follow_up_at: followUp ? new Date(followUp).toISOString() : null,
                })
              }
            >
              Save
            </button>
          </div>
        </div>
        {lead.conversation_id && (
          <p className="dim" style={{ fontSize: 12 }}>
            Linked conversation #{lead.conversation_id} — open it from the Conversations page.
          </p>
        )}
        <button className="btn" onClick={onClose} style={{ marginTop: 8 }}>Close</button>
      </div>
    </>
  );
}

function AddLeadModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [interest, setInterest] = useState<InterestType>("room");
  const [notes, setNotes] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api.post<Lead>("/leads", {
        phone: phone.replace(/\D/g, ""),
        customer_name: name || null,
        interest_type: interest,
        details: notes ? { notes } : {},
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["leads"] });
      onClose();
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <>
      <div className="modal-overlay" onClick={onClose} />
      <form className="modal" onSubmit={onSubmit}>
        <h2>Add lead</h2>
        <div className="field">
          <label>WhatsApp number (digits only, e.g. 92300…)</label>
          <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)}
            pattern="\d{8,15}" required />
        </div>
        <div className="field">
          <label>Customer name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
        </div>
        <div className="field">
          <label>Interest</label>
          <select className="select" value={interest} onChange={(e) => setInterest(e.target.value as InterestType)}>
            {INTERESTS.map((i) => (
              <option key={i} value={i}>{INTEREST_LABEL[i]}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Notes</label>
          <textarea className="textarea" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} />
        </div>
        {create.isError && <p className="error-text">Could not create lead.</p>}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={create.isPending}>Create</button>
        </div>
      </form>
    </>
  );
}
