/**
 * Dashboard live updates: one websocket, authenticated by sending the JWT
 * as the first frame (never in the URL). Events invalidate the relevant
 * TanStack Query caches so every page stays live without page-specific
 * socket code.
 */

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getAccessToken, wsUrl } from "./api/client";

export function useLiveEvents(enabled: boolean): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!enabled) return;
    let socket: WebSocket | null = null;
    let closed = false;
    let retryMs = 1000;

    const connect = () => {
      socket = new WebSocket(wsUrl());
      socket.onopen = () => {
        retryMs = 1000;
        socket?.send(JSON.stringify({ token: getAccessToken() }));
      };
      socket.onmessage = (event) => {
        let data: { type?: string; conversation_id?: number };
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        switch (data.type) {
          case "message":
          case "transcription":
            queryClient.invalidateQueries({ queryKey: ["conversations"] });
            if (data.conversation_id) {
              queryClient.invalidateQueries({
                queryKey: ["messages", data.conversation_id],
              });
            }
            break;
          case "conversation_updated":
          case "handoff":
          case "high_value_flagged":
            queryClient.invalidateQueries({ queryKey: ["conversations"] });
            break;
          case "lead_created":
          case "lead_updated":
            queryClient.invalidateQueries({ queryKey: ["leads"] });
            break;
        }
      };
      socket.onclose = () => {
        if (closed) return;
        setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 2, 15000);
      };
    };

    connect();
    return () => {
      closed = true;
      socket?.close();
    };
  }, [enabled, queryClient]);
}
