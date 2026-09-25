import { create } from "zustand";

export type MitraStateType =
  | "IdleSleep"
  | "Waking"
  | "ActiveListening"
  | "DeepProcessing"
  | "AgentSpeaking"
  | "ConversationalKeepAlive"
  | "Error";

export interface ActionCardData {
  actionId: string;
  actionType: "draft_email" | "create_calendar" | "trigger_n8n" | "jira_ticket";
  title: string;
  description: string;
  details?: Record<string, any>;
  expiresAt: number; // timestamp ms
  status: "pending_approval" | "in_undo_window" | "committed" | "rolled_back";
}

export interface CommitmentData {
  id: string;
  party: string;
  description: string;
  dueDate: string;
  direction: "outbound" | "inbound";
  status: "pending" | "resolved" | "snoozed";
}

export interface MeetingDossierData {
  eventId: string;
  title: string;
  attendees: string[];
  bullets: string[];
  generatedAt: string;
}

export interface ClipboardData {
  type: "table" | "code" | "url" | "raw_text";
  rawText: string;
  formattedTable?: string;
  summaryBullets?: string[];
  jsonData?: any;
}

interface MitraStore {
  // Core state
  mitraState: MitraStateType;
  audioLevel: number;
  aecActive: boolean;
  transcript: string;
  isBackendLive: boolean;

  // Active cards
  activeAction: ActionCardData | null;
  dossier: MeetingDossierData | null;
  commitments: CommitmentData[];
  clipboardData: ClipboardData | null;

  // Actions
  setMitraState: (state: MitraStateType) => void;
  setAudioLevel: (level: number) => void;
  setAecActive: (active: boolean) => void;
  setTranscript: (text: string) => void;
  setIsBackendLive: (live: boolean) => void;
  setActiveAction: (action: ActionCardData | null) => void;
  setDossier: (dossier: MeetingDossierData | null) => void;
  setCommitments: (commitments: CommitmentData[]) => void;
  setClipboardData: (data: ClipboardData | null) => void;
  rollbackAction: (actionId?: string) => Promise<boolean>;
  resolveCommitment: (id: string) => Promise<void>;
  snoozeCommitment: (id: string) => Promise<void>;
}

const BACKEND_URL = "http://127.0.0.1:8766";

export const useMitraStore = create<MitraStore>((set, get) => ({
  mitraState: "IdleSleep",
  audioLevel: 0,
  aecActive: false,
  transcript: "",
  isBackendLive: false,

  activeAction: null,
  dossier: null,
  commitments: [],
  clipboardData: null,

  setMitraState: (mitraState) => set({ mitraState }),
  setAudioLevel: (audioLevel) => set({ audioLevel }),
  setAecActive: (aecActive) => set({ aecActive }),
  setTranscript: (transcript) => set({ transcript }),
  setIsBackendLive: (isBackendLive) => set({ isBackendLive }),
  setActiveAction: (activeAction) => set({ activeAction }),
  setDossier: (dossier) => set({ dossier }),
  setCommitments: (commitments) => set({ commitments }),
  setClipboardData: (clipboardData) => set({ clipboardData }),

  rollbackAction: async (actionId) => {
    const targetId = actionId || get().activeAction?.actionId;
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/intelligence/undo/rollback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_id: targetId }),
      });
      const data = await res.json();
      if (data.status === "rolled_back") {
        set((state) => ({
          activeAction: state.activeAction
            ? { ...state.activeAction, status: "rolled_back" }
            : null,
        }));
        setTimeout(() => set({ activeAction: null }), 2500);
        return true;
      }
      return false;
    } catch {
      // Local fallback
      set((state) => ({
        activeAction: state.activeAction
          ? { ...state.activeAction, status: "rolled_back" }
          : null,
      }));
      setTimeout(() => set({ activeAction: null }), 2500);
      return true;
    }
  },

  resolveCommitment: async (id: string) => {
    try {
      await fetch(`${BACKEND_URL}/api/v1/intelligence/ghost-radar/resolve/${id}`, {
        method: "POST",
      });
    } catch {
      // Offline fallback
    }
    set((state) => ({
      commitments: state.commitments.filter((c) => c.id !== id),
    }));
  },

  snoozeCommitment: async (id: string) => {
    try {
      await fetch(`${BACKEND_URL}/api/v1/intelligence/ghost-radar/snooze/${id}?minutes=120`, {
        method: "POST",
      });
    } catch {
      // Offline fallback
    }
    set((state) => ({
      commitments: state.commitments.map((c) =>
        c.id === id ? { ...c, status: "snoozed" as const } : c
      ),
    }));
  },
}));
