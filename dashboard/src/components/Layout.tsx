import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const NAV = [
  { to: "/conversations", label: "Conversations", icon: "💬" },
  { to: "/leads", label: "Leads", icon: "📋" },
  { to: "/customers", label: "Customers", icon: "👤" },
  { to: "/analytics", label: "Analytics", icon: "📈" },
];

const ADMIN_NAV = [
  { to: "/kb", label: "Knowledge Base", icon: "📚" },
  { to: "/settings", label: "Settings", icon: "⚙️" },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const items = user?.role === "admin" ? [...NAV, ...ADMIN_NAV] : NAV;
  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">
          DBR Dashboard
          <small>Destination Beach Resort</small>
        </div>
        {items.map((item) => (
          <NavLink key={item.to} to={item.to}>
            <span aria-hidden>{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
        <div className="spacer" />
        <div className="userbox">
          <strong>{user?.full_name}</strong>
          {user?.role}
          <button onClick={logout}>Sign out</button>
        </div>
      </nav>
      <main className="main">{children}</main>
    </div>
  );
}
