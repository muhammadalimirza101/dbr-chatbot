import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { MediaAsset, Role, UserAdmin } from "../api/types";
import { useAuth } from "../auth/AuthContext";

export default function Settings() {
  return (
    <>
      <h1 className="page-title">Settings</h1>
      <ConnectorStatus />
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", alignItems: "start" }}>
        <UsersPanel />
        <MediaPanel />
      </div>
    </>
  );
}

function ConnectorStatus() {
  const { data } = useQuery({
    queryKey: ["connector-status"],
    queryFn: () => api.get<{ connected: boolean }>("/analytics/connector-status"),
    refetchInterval: 20_000,
  });
  return (
    <div className="card pad" style={{ marginBottom: 14 }}>
      <div className="row">
        <strong>WhatsApp connector</strong>
        {data?.connected ? (
          <span className="badge green">connected</span>
        ) : (
          <span className="badge red">disconnected</span>
        )}
        {!data?.connected && (
          <span className="dim">
            Start the connector (npm run dev in connector/) and pair via QR if needed.
          </span>
        )}
      </div>
    </div>
  );
}

function UsersPanel() {
  const queryClient = useQueryClient();
  const { user: me } = useAuth();
  const [showAdd, setShowAdd] = useState(false);

  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserAdmin[]>("/users"),
  });

  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) =>
      api.patch<UserAdmin>(`/users/${id}`, patch),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <div className="card pad">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
        <h2 style={{ fontSize: 15 }}>Staff accounts</h2>
        <button className="btn small primary" onClick={() => setShowAdd(true)}>+ Add user</button>
      </div>
      <table className="table">
        <thead>
          <tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>{user.full_name}{user.id === me?.id && <span className="dim"> (you)</span>}</td>
              <td className="dim">{user.email}</td>
              <td>
                <select
                  className="select"
                  value={user.role}
                  disabled={user.id === me?.id}
                  onChange={(e) =>
                    update.mutate({ id: user.id, patch: { role: e.target.value } })
                  }
                >
                  <option value="admin">admin</option>
                  <option value="agent">agent</option>
                </select>
              </td>
              <td>
                {user.is_active
                  ? <span className="badge green">active</span>
                  : <span className="badge gray">disabled</span>}
              </td>
              <td>
                <button
                  className="btn small"
                  disabled={user.id === me?.id}
                  onClick={() =>
                    update.mutate({ id: user.id, patch: { is_active: !user.is_active } })
                  }
                >
                  {user.is_active ? "Disable" : "Enable"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {showAdd && <AddUserModal onClose={() => setShowAdd(false)} />}
    </div>
  );
}

function AddUserModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("agent");

  const create = useMutation({
    mutationFn: () =>
      api.post<UserAdmin>("/users", { email, full_name: fullName, password, role }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
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
        <h2>Add staff user</h2>
        <div className="field">
          <label>Full name</label>
          <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} required maxLength={120} />
        </div>
        <div className="field">
          <label>Email</label>
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label>Temporary password (min 10 chars — ask them to change it)</label>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={10} maxLength={128} />
        </div>
        <div className="field">
          <label>Role</label>
          <select className="select" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="agent">agent — conversations & leads</option>
            <option value="admin">admin — everything</option>
          </select>
        </div>
        {create.isError && <p className="error-text">Could not create user (email in use?).</p>}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={create.isPending}>Create</button>
        </div>
      </form>
    </>
  );
}

const PURPOSES = [
  { id: "room_photo", label: "Room photo" },
  { id: "rate_card", label: "Rate card (PDF)" },
  { id: "location", label: "Location" },
  { id: "other", label: "Other" },
] as const;

function MediaPanel() {
  const queryClient = useQueryClient();
  const [purpose, setPurpose] = useState<MediaAsset["purpose"]>("room_photo");
  const [error, setError] = useState<string | null>(null);

  const { data: assets = [] } = useQuery({
    queryKey: ["media"],
    queryFn: () => api.get<MediaAsset[]>("/media"),
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload<MediaAsset>(`/media?purpose=${purpose}`, form);
    },
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["media"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Upload failed"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/media/${id}`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["media"] }),
  });

  return (
    <div className="card pad">
      <h2 style={{ fontSize: 15, marginBottom: 10 }}>Media library</h2>
      <div className="row" style={{ marginBottom: 12 }}>
        <select className="select" value={purpose} onChange={(e) => setPurpose(e.target.value as MediaAsset["purpose"])}>
          {PURPOSES.map((p) => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
        <label className="btn primary" style={{ margin: 0 }}>
          Upload…
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,application/pdf"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {error && <p className="error-text">{error}</p>}
      <table className="table">
        <thead>
          <tr><th>File</th><th>Type</th><th>Purpose</th><th>Size</th><th></th></tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr key={asset.id}>
              <td>{asset.original_name}</td>
              <td className="dim">{asset.mime_type}</td>
              <td><span className="badge blue">{asset.purpose}</span></td>
              <td className="mono">{(asset.size_bytes / 1024).toFixed(0)} KB</td>
              <td>
                <button
                  className="btn small danger"
                  onClick={() => {
                    if (confirm("Delete this media asset?")) remove.mutate(asset.id);
                  }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
          {assets.length === 0 && (
            <tr><td colSpan={5} className="empty">No media yet — upload room photos and the rate card</td></tr>
          )}
        </tbody>
      </table>
      <p className="dim" style={{ fontSize: 12 }}>
        JPEG/PNG/WebP/PDF only, max 10 MB. Files are validated server-side and stored by id.
      </p>
    </div>
  );
}
