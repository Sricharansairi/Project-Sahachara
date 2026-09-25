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
  RotateCcw,
  Volume2,
  Calendar,
} from "lucide-react";

import { ThinkingOrbGemini } from "./components/ThinkingOrbGemini";
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
  const [isSimulatingAudio, setIsSimulatingAudio] = useState<boolean>(false);

  // Keyboard shortcut Ctrl+Z / Cmd+Z for 10-Second Undo Buffer
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        rollbackAction();
      }
      if (e.key === "Escape") {
        setShowSettings(false);
        setShowConsentModal(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [rollbackAction]);

  // Audio simulation loop for local browser testing & visual inspection
  useEffect(() => {
    if (!isSimulatingAudio) return;
    const interval = setInterval(() => {
      const simulated = Math.abs(Math.sin(Date.now() / 150)) * 0.75 + Math.random() * 0.25;
      setAudioLevel(simulated);
    }, 50);
    return () => clearInterval(interval);
  }, [isSimulatingAudio, setAudioLevel]);

  // Initial Tauri check and seed sample interactive items for preview
  useEffect(() => {
    invoke<boolean>("is_voiceprint_enrolled")
      .then((enrolled) => {
        if (!enrolled) {
          setShowConsentModal(true);
        }
      })
      .catch(() => {
        // Browser preview fallback: seed sample cards for hackathon inspection
        setTimeout(() => {
          setActiveAction({
            actionId: "act_sample_01",
            actionType: "draft_email",
            title: "Draft Reply to Sarah Chen",
            description: "Confirmed Q3 design system review and attached Thinking Orb specifications.",
            expiresAt: Date.now() + 10000,
            status: "in_undo_window",
          });

          setDossier({
            eventId: "evt_001",
            title: "Project Sahachara Design & Engineering Sync",
            attendees: ["sarah.chen@company.com", "mitra.agent@internal"],
            bullets: [
              "Present rareformlabs Thinking Orbs integration with 9-state physics.",
              "Review pure black OLED glassmorphic Dynamic Island layout.",
              "Validate sub-400ms end-to-end voice round-trip latency targets.",
            ],
            generatedAt: new Date().toISOString(),
          });

          setCommitments([
            {
              id: "com_01",
              party: "alex@company.com",
              description: "Send pitch deck with live thinking orb demo by Friday 4 PM",
              dueDate: new Date(Date.now() + 86400000).toISOString(),
              direction: "outbound",
              status: "pending",
            },
          ]);

          setClipboardData({
            type: "table",
            rawText: "Feature,Status,Latency\nThinking Orbs,Complete,60 FPS\nNVIDIA NIM,Verified,0.37s\nUndo Buffer,Active,10.0s",
            formattedTable:
              "| Feature | Status | Latency |\n| :--- | :--- | :--- |\n| Thinking Orbs | Complete | 60 FPS |\n| NVIDIA NIM | Verified | 0.37s |\n| Undo Buffer | Active | 10.0s |",
            summaryBullets: [
              "Thinking Orbs running smoothly at 60 FPS on 2D canvas.",
              "NVIDIA Fast Brain Nemotron-3 TTFT verified at 0.37s.",
              "10-Second Undo Buffer active with Ctrl+Z rollback.",
            ],
          });
        }, 800);
      });
  }, [setActiveAction, setDossier, setCommitments, setClipboardData]);

  // Listen to Tauri Core events
  useEffect(() => {
    const unlisteners: Array<() => void> = [];

    listen<{ state: string }>("state-changed", (e) => {
      setMitraState(e.payload.state as MitraStateType);
      setRecentLog(`State: ${e.payload.state}`);
    })
      .then((u) => unlisteners.push(u))
      .catch(() => {});

    listen<{ level: number }>("audio-level-update", (e) => {
      if (!isSimulatingAudio) {
        setAudioLevel(Math.min(e.payload.level * 20, 1));
      }
    })
      .then((u) => unlisteners.push(u))
      .catch(() => {});

    listen<{ phrase: string; score: number }>("wake-word-detected", (e) => {
      setMitraState("ActiveListening");
      setRecentLog(`Wake Word: ${e.payload.phrase} (${Math.round(e.payload.score * 100)}%)`);
    })
      .then((u) => unlisteners.push(u))
      .catch(() => {});

    return () => unlisteners.forEach((u) => u());
  }, [setMitraState, setAudioLevel, isSimulatingAudio]);

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
      return { label: "Solving", color: "text-purple-400 bg-purple-500/10 border-purple-500/20" };
    }
    if (
      mitraState.includes("ActiveListening") ||
      mitraState.includes("UserSpeaking") ||
      mitraState.includes("Waking")
    ) {
      return { label: "Listening", color: "text-sky-400 bg-sky-500/10 border-sky-500/20" };
    }
    if (mitraState.includes("AgentSpeaking") || mitraState.includes("Speaking")) {
      return { label: "Speaking", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" };
    }
    return { label: "Standby", color: "text-neutral-400 bg-white/5 border-white/10" };
  };

  const badge = getStateBadge();

  // Demo Trigger Helpers
  const triggerSampleUndo = () => {
    setActiveAction({
      actionId: `act_${Date.now()}`,
      actionType: "draft_email",
      title: "Schedule Meeting with Sarah",
      description: "Friday at 3:00 PM (Google Meet invite prepared)",
      expiresAt: Date.now() + 10000,
      status: "in_undo_window",
    });
    setRecentLog("Action Staged: 10s Undo Window");
  };

  return (
    <div className="w-screen h-screen bg-black text-white flex flex-col items-center justify-center p-4 selection:bg-indigo-500/30 font-sans overflow-hidden">
      {/* ─── DYNAMIC FLOATING PILL CONTAINER (DYNAMIC ISLAND) ─────────── */}
      <motion.div
        layout
        transition={{ type: "spring", stiffness: 380, damping: 32 }}
        className="w-[410px] max-w-[95vw] max-h-[92vh] overflow-y-auto overflow-x-hidden bg-neutral-950/90 border border-white/10 rounded-[32px] p-5 shadow-[0_0_60px_rgba(0,0,0,0.95)] backdrop-blur-3xl relative flex flex-col items-center custom-scrollbar"
      >
        {/* Subtle Gemini top ambient illumination beam */}
        <div className="absolute top-0 left-1/4 right-1/4 h-[1px] bg-gradient-to-r from-transparent via-sky-400/40 to-transparent" />

        {/* Phase 3 & 6 Privacy Ring Indicator */}
        <div
          data-testid="privacy-ring-indicator"
          className={`privacy-ring absolute inset-0 rounded-[32px] pointer-events-none transition-opacity duration-300 ${
            !isMuted && mitraState !== "IdleSleep"
              ? "ring-2 ring-[#10b981] opacity-100 shadow-[0_0_24px_#10b981]"
              : "opacity-0"
          }`}
        />

        {/* ─── TOP CONTROL BAR ────────────────────────────────────────── */}
        <div className="w-full flex items-center justify-between mb-2 px-1 z-10">
          {/* Logo & Brand */}
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-indigo-500 via-sky-400 to-purple-500 flex items-center justify-center shadow-lg shadow-sky-500/25">
              <Sparkles size={13} className="text-white" />
            </div>
            <div className="flex flex-col">
              <span className="text-[11px] font-bold tracking-wider text-white font-mono uppercase leading-tight">
                MITRA
              </span>
              <span className="text-[8px] text-neutral-400 font-mono tracking-tight">
                Sahachara AI
              </span>
            </div>
          </div>

          {/* State Indicator */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold tracking-wider uppercase border transition-all ${badge.color}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
            <span>{badge.label}</span>
          </div>

          {/* Top Action Icons */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => setIsSimulatingAudio(!isSimulatingAudio)}
              className={`w-7 h-7 rounded-full flex items-center justify-center transition-colors border ${
                isSimulatingAudio
                  ? "bg-sky-500/20 text-sky-400 border-sky-500/30"
                  : "bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white border-white/5"
              }`}
              title={isSimulatingAudio ? "Stop Audio Simulation" : "Simulate Live Speech"}
            >
              <Volume2 size={13} />
            </button>
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
              className={`w-7 h-7 rounded-full flex items-center justify-center transition-colors border ${
                showSettings
                  ? "bg-white/20 text-white border-white/30"
                  : "bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white border-white/5"
              }`}
              title="Settings & Showcase"
            >
              <SlidersHorizontal size={13} />
            </button>
          </div>
        </div>

        {/* ─── CENTER STAGE: GEMINI THINKING ORB ──────────────────────── */}
        <div className="py-1 relative flex flex-col items-center justify-center">
          <ThinkingOrbGemini
            state={mitraState}
            audioLevel={audioLevel}
            size={175}
            onClick={toggleWakeListening}
            onStateSelect={(s) => setRecentLog(`Orb State: ${s}`)}
          />

          {/* Minimal Prompt Cue Below Orb */}
          <div className="mt-1 text-[11px] text-neutral-400 font-medium tracking-wide flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400/80" />
            <span className="truncate max-w-[280px]">{recentLog}</span>
          </div>
        </div>

        {/* ─── ACTIVE ACTION CARDS LAYER ───────────────────────────────── */}
        <div className="w-full space-y-2.5 mt-3">
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

        {/* ─── SETTINGS & HACKATHON DEMO DRAWER ───────────────────────── */}
        <AnimatePresence>
          {showSettings && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="w-full mt-3 pt-3 border-t border-white/10 text-xs text-neutral-400 space-y-3"
            >
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-semibold text-neutral-300">Hackathon Interactive Demos</span>
                <span className="text-[10px] text-sky-400 font-mono">1-Click Test</span>
              </div>

              {/* Demo Quick Launch Buttons */}
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  onClick={triggerSampleUndo}
                  className="py-1.5 px-2 bg-white/5 hover:bg-white/10 text-neutral-300 rounded-xl border border-white/5 flex items-center justify-center gap-1.5 transition-colors text-[10px]"
                >
                  <RotateCcw size={11} className="text-amber-400" />
                  <span>10s Undo Buffer</span>
                </button>
                <button
                  onClick={() => {
                    setDossier({
                      eventId: `evt_${Date.now()}`,
                      title: "Product Roadmap Review",
                      attendees: ["ceo@company.com", "lead-designer@company.com"],
                      bullets: [
                        "Final signoff on Gemini Thinking Orbs UI aesthetics.",
                        "Live demo of sub-400ms voice pipeline response.",
                        "Review n8n workflow triggers for Slack & Jira.",
                      ],
                      generatedAt: new Date().toISOString(),
                    });
                    setRecentLog("Pre-Meeting Dossier Generated");
                  }}
                  className="py-1.5 px-2 bg-white/5 hover:bg-white/10 text-neutral-300 rounded-xl border border-white/5 flex items-center justify-center gap-1.5 transition-colors text-[10px]"
                >
                  <Calendar size={11} className="text-sky-400" />
                  <span>Meeting Dossier</span>
                </button>
              </div>

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
                <span>Thinking Orb Source</span>
                <span className="text-[10px] text-sky-400 font-mono">
                  rareformlabs/thinking-orbs
                </span>
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
                  className="w-full py-1.5 bg-gradient-to-r from-sky-500/20 to-indigo-500/20 hover:from-sky-500/30 hover:to-indigo-500/30 text-sky-300 rounded-xl border border-sky-500/30 flex items-center justify-center gap-1.5 transition-colors text-[11px]"
                >
                  <RefreshCw size={11} />
                  <span>Toggle Wake / Standby</span>
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* ─── PERMISSION CONSENT MODAL ─────────────────────────────────── */}
      <PermissionConsentModal
        isOpen={showConsentModal}
        onClose={() => setShowConsentModal(false)}
        onPermissionsUpdated={() => setShowConsentModal(false)}
      />
    </div>
  );
}
