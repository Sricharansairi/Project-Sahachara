import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { motion, AnimatePresence } from "framer-motion";
import {
  Mic,
  MicOff,
  SlidersHorizontal,
  Shield,
  Sparkles,
  RefreshCw,
} from "lucide-react";

import { GeminiThinkingOrb } from "./components/GeminiThinkingOrb";
import {
  UndoActionCard,
  MeetingDossierCard,
  GhostRadarCard,
  ClipboardAugmenterCard,
} from "./components/ActionCards";
import { PermissionConsentModal } from "./components/PermissionConsentModal";
import { useMitraStore, MitraStateType } from "./store/useMitraStore";

export default function App() {
  const {
    mitraState,
    setMitraState,
    audioLevel,
    setAudioLevel,
    aecActive,
    setAecActive,
    activeAction,
    setActiveAction,
    dossier,
    setDossier,
    commitments,
    setCommitments,
    clipboardData,
    setClipboardData,
    rollbackAction,
  } = useMitraStore();

  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const [showConsentModal, setShowConsentModal] = useState<boolean>(false);
  const [recentLog, setRecentLog] = useState<string>("Core Engine Online");

  // Keyboard shortcut Ctrl+Z for 10-Second Undo Buffer
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        rollbackAction();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [rollbackAction]);

  // Initial Tauri check and mock seed if running in browser
  useEffect(() => {
    invoke<boolean>("is_voiceprint_enrolled")
      .then((enrolled) => {
        if (!enrolled) {
          setShowConsentModal(true);
        }
      })
      .catch(() => {
        // Browser development preview: seed sample action and dossier for verification
        setTimeout(() => {
          setActiveAction({
            actionId: "act_sample_01",
            actionType: "draft_email",
            title: "Draft Reply to John Smith",
            description: "Reviewed Q3 report and sent feedback for Friday's sprint review.",
            expiresAt: Date.now() + 10000,
            status: "in_undo_window",
          });

          setDossier({
            eventId: "evt_001",
            title: "Sahachara Product Sync with Sarah",
            attendees: ["sarah.chen@example.com", "user@example.com"],
            bullets: [
              "Align on Project Sahachara beta release milestones.",
              "Review Sarah Chen's Figma Dynamic Island design specs.",
              "Sign off on voice pipeline latency targets (P50 < 400ms).",
            ],
            generatedAt: new Date().toISOString(),
          });

          setCommitments([
            {
              id: "com_01",
              party: "alex@company.com",
              description: "Send updated pitch deck by Friday afternoon",
              dueDate: new Date(Date.now() + 86400000).toISOString(),
              direction: "outbound",
              status: "pending",
            },
          ]);
        }, 1200);
      });
  }, [setActiveAction, setDossier, setCommitments]);

  // Listen to Tauri Core events
  useEffect(() => {
    const unlisteners: Array<() => void> = [];

    listen<{ state: string }>("state-changed", (e) => {
      setMitraState(e.payload.state as MitraStateType);
      setRecentLog(`State: ${e.payload.state}`);
    }).then((u) => unlisteners.push(u)).catch(() => {});

    listen<{ level: number }>("audio-level-update", (e) => {
      setAudioLevel(Math.min(e.payload.level * 20, 1));
    }).then((u) => unlisteners.push(u)).catch(() => {});

    listen<{ phrase: string; score: number }>("wake-word-detected", (e) => {
      setMitraState("ActiveListening");
      setRecentLog(`Wake Word: ${e.payload.phrase} (${Math.round(e.payload.score * 100)}%)`);
    }).then((u) => unlisteners.push(u)).catch(() => {});

    return () => unlisteners.forEach((u) => u());
  }, [setMitraState, setAudioLevel]);

  const toggleWakeListening = useCallback(() => {
    if (mitraState.includes("IdleSleep")) {
      invoke("manual_wake").catch(() => {});
      setMitraState("ActiveListening");
      setRecentLog("Manual Wake: Listening");
    } else {
      invoke("manual_sleep").catch(() => {});
      setMitraState("IdleSleep");
      setRecentLog("Manual Sleep: Standby");
    }
  }, [mitraState, setMitraState]);

  const getStateBadge = () => {
    if (mitraState.includes("DeepProcessing") || mitraState.includes("Thinking")) {
      return { label: "Thinking", color: "text-purple-400 bg-purple-500/10 border-purple-500/20" };
    }
    if (mitraState.includes("ActiveListening") || mitraState.includes("UserSpeaking") || mitraState.includes("Waking")) {
      return { label: "Listening", color: "text-sky-400 bg-sky-500/10 border-sky-500/20" };
    }
    if (mitraState.includes("AgentSpeaking") || mitraState.includes("Speaking")) {
      return { label: "Speaking", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" };
    }
    return { label: "Standby", color: "text-neutral-400 bg-white/5 border-white/10" };
  };

  const badge = getStateBadge();

  return (
    <div className="w-screen h-screen bg-black text-white flex flex-col items-center justify-center p-4 selection:bg-indigo-500/30 font-sans">
      {/* Dynamic Floating Pill Container */}
      <motion.div
        layout
        transition={{ type: "spring", stiffness: 380, damping: 32 }}
        className="w-[390px] max-w-[95vw] bg-neutral-950/95 border border-white/10 rounded-[32px] p-5 shadow-[0_0_50px_rgba(0,0,0,0.9)] backdrop-blur-3xl relative overflow-hidden flex flex-col items-center"
      >
        {/* Subtle Gemini top ambient illumination beam */}
        <div className="absolute top-0 left-1/4 right-1/4 h-[1px] bg-gradient-to-r from-transparent via-sky-400/30 to-transparent" />

        {/* Phase 3 & 6 Privacy Ring Indicator */}
        <div
          data-testid="privacy-ring-indicator"
          className={`privacy-ring absolute inset-0 rounded-[32px] pointer-events-none transition-opacity duration-300 ${
            !isMuted && mitraState !== "IdleSleep"
              ? "ring-2 ring-[#10b981] opacity-100 shadow-[0_0_20px_#10b981]"
              : "opacity-0"
          }`}
        />

        {/* Top Control Bar */}
        <div className="w-full flex items-center justify-between mb-3 px-1">
          {/* Logo & Brand */}
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-indigo-500 via-sky-400 to-purple-500 flex items-center justify-center shadow-lg shadow-sky-500/20">
              <Sparkles size={13} className="text-white" />
            </div>
            <span className="text-xs font-bold tracking-wider text-white font-mono uppercase">
              MITRA
            </span>
          </div>

          {/* State Indicator */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold tracking-wider uppercase border transition-all ${badge.color}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
            <span>{badge.label}</span>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => setIsMuted(!isMuted)}
              className="w-7 h-7 rounded-full bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white flex items-center justify-center transition-colors border border-white/5"
              title={isMuted ? "Unmute Mic" : "Mute Mic"}
            >
              {isMuted ? <MicOff size={13} className="text-rose-400" /> : <Mic size={13} />}
            </button>
            <button
              onClick={() => setShowConsentModal(true)}
              className="w-7 h-7 rounded-full bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white flex items-center justify-center transition-colors border border-white/5"
              title="Permissions & Privacy"
            >
              <Shield size={13} />
            </button>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="w-7 h-7 rounded-full bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white flex items-center justify-center transition-colors border border-white/5"
              title="Settings"
            >
              <SlidersHorizontal size={13} />
            </button>
          </div>
        </div>

        {/* Center Stage — Gemini Thinking Orb */}
        <div className="py-2 relative flex flex-col items-center justify-center">
          <GeminiThinkingOrb
            state={mitraState}
            audioLevel={audioLevel}
            size={180}
            onClick={toggleWakeListening}
          />

          {/* Minimal prompt cue below orb */}
          <div className="mt-1 text-[11px] text-neutral-400 font-medium tracking-wide flex items-center gap-1.5">
            <span>{recentLog}</span>
          </div>
        </div>

        {/* Real-time Audio Level Meter (minimalist line) */}
        <div className="w-48 h-0.5 bg-white/10 rounded-full mt-2 mb-4 overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-sky-400 to-indigo-500"
            style={{ width: `${Math.max(8, audioLevel * 100)}%` }}
            transition={{ ease: "easeOut", duration: 0.08 }}
          />
        </div>

        {/* Active Action Cards Layer */}
        <div className="w-full space-y-2.5">
          <AnimatePresence>
            {/* Tier-1 Approval & 10s Undo Card */}
            {activeAction && (
              <UndoActionCard
                key={activeAction.actionId}
                action={activeAction}
                onApprove={() => {
                  setActiveAction({
                    ...activeAction,
                    status: "in_undo_window",
                    expiresAt: Date.now() + 10000,
                  });
                }}
                onReject={() => setActiveAction(null)}
              />
            )}

            {/* Pre-Meeting Briefing Card */}
            {dossier && (
              <MeetingDossierCard
                key={dossier.eventId}
                dossier={dossier}
                onDismiss={() => setDossier(null)}
              />
            )}

            {/* Ghost Radar Commitments */}
            {commitments.map((com) => (
              <GhostRadarCard key={com.id} commitment={com} />
            ))}

            {/* Clipboard Augmenter */}
            {clipboardData && (
              <ClipboardAugmenterCard
                key="clipboard-card"
                data={clipboardData}
                onFormatTable={() => {
                  setRecentLog("Formatted Markdown Table");
                  setClipboardData(null);
                }}
                onSummarize={() => {
                  setRecentLog("Summarized to Bullets");
                  setClipboardData(null);
                }}
                onDismiss={() => setClipboardData(null)}
              />
            )}
          </AnimatePresence>
        </div>

        {/* Settings Drawer (Foldable) */}
        <AnimatePresence>
          {showSettings && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="w-full mt-4 pt-3 border-t border-white/10 text-xs text-neutral-400 space-y-3"
            >
              <div className="flex items-center justify-between">
                <span>Acoustic Echo Cancellation</span>
                <button
                  onClick={() => setAecActive(!aecActive)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                    aecActive
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      : "bg-white/5 text-neutral-400 border-white/10"
                  }`}
                >
                  {aecActive ? "Enabled" : "Disabled"}
                </button>
              </div>

              <div className="flex items-center justify-between">
                <span>Zero-Knowledge Privacy</span>
                <div className="flex items-center gap-1 text-[10px] text-emerald-400 font-mono">
                  <Shield size={11} />
                  <span>Enclave Active</span>
                </div>
              </div>

              <div className="pt-1 flex items-center justify-between">
                <button
                  onClick={toggleWakeListening}
                  className="w-full py-1.5 bg-white/5 hover:bg-white/10 text-neutral-300 rounded-xl border border-white/5 flex items-center justify-center gap-1.5 transition-colors text-[11px]"
                >
                  <RefreshCw size={11} />
                  <span>Cycle Wake State</span>
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Permission Consent Modal */}
      <PermissionConsentModal
        isOpen={showConsentModal}
        onClose={() => setShowConsentModal(false)}
        onPermissionsUpdated={() => setShowConsentModal(false)}
      />
    </div>
  );
}
