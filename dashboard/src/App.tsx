import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Login from "./auth/Login";
import Layout from "./components/Layout";
import Analytics from "./pages/Analytics";
import Conversations from "./pages/Conversations";
import Customers from "./pages/Customers";
import KnowledgeBase from "./pages/KnowledgeBase";
import Leads from "./pages/Leads";
import Settings from "./pages/Settings";
import { useLiveEvents } from "./ws";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, retry: 1 } },
});

function Protected() {
  const { user, loading } = useAuth();
  useLiveEvents(user !== null);
  if (loading) return <div className="empty">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/conversations" replace />} />
        <Route path="/conversations" element={<Conversations />} />
        <Route path="/leads" element={<Leads />} />
        <Route path="/customers" element={<Customers />} />
        {user.role === "admin" && (
          <>
            <Route path="/kb" element={<KnowledgeBase />} />
            <Route path="/settings" element={<Settings />} />
          </>
        )}
        <Route path="/analytics" element={<Analytics />} />
        <Route path="*" element={<Navigate to="/conversations" replace />} />
      </Routes>
    </Layout>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/*" element={<Protected />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
