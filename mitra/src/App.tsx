import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { motion, AnimatePresence } from "framer-motion";
import {
  Mic,
  SlidersHorizontal,
  Shield,
  Sparkles,
  MessageSquare,
  RefreshCw,
  Volume2,
} from "lucide-react";

import { GeminiVoiceMode } from "./components/GeminiVoiceMode";
import { GeminiChatView } from "./components/GeminiChatView";
import { PermissionConsentModal } from "./components/PermissionConsentModal";
import { useMitraStore, MitraStateType } from "./store/useMitraStore";

export type GeminiViewMode = "voice" | "chat";

export default function App() {
  const {
    mitraState,
    setMitraState,
    audioLevel,
    setAudioLevel,
    aecActive,
    setAecActive,
    transcript,
    setActiveAction,
    setDossier,
    setCommitments,
    setClipboardData,
    rollbackAction,
  } = useMitraStore();

  const [activeView, setActiveView] = useState<GeminiViewMode>("voice");
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const [showConsentModal, setShowConsentModal] = useState<boolean>(false);
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
        // Browser development preview: seed sample actions
        setTimeout(() => {
          setActiveAction({
            actionId: "act_sample_01",
            actionType: "draft_email",
            title: "Draft Reply to Sarah Chen",
            description: "Confirmed Friday sync at 3:00 PM and attached Q3 project milestone review.",
            expiresAt: Date.now() + 10000,
            status: "in_undo_window",
          });

          setDossier({
            eventId: "evt_001",
            title: "Sahachara Engineering & Design Sync",
            attendees: ["sarah.chen@company.com", "mitra.agent@internal"],
            bullets: [
              "Review minimal Google Gemini Voice & Desktop Chat layouts.",
              "Validate Thinking Orbs 2D canvas integration with 9 states.",
              "Sign off on sub-400ms end-to-end voice latency target.",
            ],
            generatedAt: new Date().toISOString(),
          });

          setCommitments([
            {
              id: "com_01",
              party: "alex@company.com",
              description: "Send pitch deck with Gemini Voice UI demo by Friday 4 PM",
              dueDate: new Date(Date.now() + 86400000).toISOString(),
              direction: "outbound",
              status: "pending",
            },
          ]);

          setClipboardData({
            type: "table",
            rawText: "Feature,Status,Latency\nVoice Live,Minimalist,60 FPS\nDesktop Chat,Complete,Instant\nUndo Buffer,Active,10.0s",
            formattedTable:
              "| Feature | Status | Latency |\n| :--- | :--- | :--- |\n| Voice Live | Minimalist | 60 FPS |\n| Desktop Chat | Complete | Instant |\n| Undo Buffer | Active | 10.0s |",
            summaryBullets: [
              "Voice Live mode running with clean 2D thinking orbs.",
              "Desktop Chat mode modeled after gemini.google.com.",
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

    listen<{ phrase: string; score: number }>("wake-word-detected", () => {
      setMitraState("ActiveListening");
      setActiveView("voice");
    })
      .then((u) => unlisteners.push(u))
      .catch(() => {});

    return () => unlisteners.forEach((u) => u());
  }, [setMitraState, setAudioLevel, isSimulatingAudio]);

  const toggleWakeListening = useCallback(() => {
    if (mitraState.includes("IdleSleep")) {
      invoke("manual_wake").catch(() => {});
      setMitraState("ActiveListening");
    } else {
      invoke("manual_sleep").catch(() => {});
      setMitraState("IdleSleep");
    }
  }, [mitraState, setMitraState]);

  return (
    <div className="w-screen h-screen bg-[#000000] text-[#f1f3f4] flex flex-col items-center justify-center p-4 selection:bg-[#8ab4f8]/30 font-sans overflow-hidden">
      {/* ─── MAIN DESKTOP CONTAINER (PURE BLACK OLED & GEMINI SURFACES) ─── */}
      <motion.div
        layout
        transition={{ type: "spring", stiffness: 400, damping: 30 }}
        className="w-[430px] max-w-[95vw] bg-[#000000] border border-white/[0.08] rounded-[28px] shadow-[0_16px_48px_rgba(0,0,0,0.9)] relative flex flex-col overflow-hidden"
      >
        {/* Subtle Green Privacy Border when Mic is Active */}
        <div
          data-testid="privacy-ring-indicator"
          className={`absolute inset-0 rounded-[28px] pointer-events-none transition-opacity duration-300 ${
            !isMuted && !mitraState.includes("IdleSleep")
              ? "ring-1 ring-[#34a853] opacity-100 shadow-[0_0_16px_rgba(52,168,83,0.3)]"
              : "opacity-0"
          }`}
        />

        {/* ─── TOP CONTROL BAR & SEGMENTED VIEW SWITCHER ───────────────── */}
        <div className="w-full flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-[#000000] z-20">
          {/* Logo & Assistant Identity */}
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-[#1e1f20] border border-white/[0.08] flex items-center justify-center text-[#8ab4f8]">
              <Sparkles size={13} />
            </div>
            <span className="text-xs font-semibold text-[#f1f3f4] tracking-wide font-mono uppercase">
              MITRA
            </span>
          </div>

          {/* Segmented Mode Switcher: Voice Live | Desktop Chat */}
          <div className="flex items-center bg-[#1e1f20] border border-white/[0.08] rounded-full p-0.5">
            <button
              onClick={() => setActiveView("voice")}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all ${
                activeView === "voice"
                  ? "bg-[#282a2c] text-[#8ab4f8] shadow-sm"
                  : "text-[#9aa0a6] hover:text-[#f1f3f4]"
              }`}
            >
              <Mic size={12} />
              <span>Voice</span>
            </button>
            <button
              onClick={() => setActiveView("chat")}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all ${
                activeView === "chat"
                  ? "bg-[#282a2c] text-[#8ab4f8] shadow-sm"
                  : "text-[#9aa0a6] hover:text-[#f1f3f4]"
              }`}
            >
              <MessageSquare size={12} />
              <span>Chat</span>
            </button>
          </div>

          {/* Actions & Settings */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => setIsSimulatingAudio(!isSimulatingAudio)}
              className={`w-7 h-7 rounded-full flex items-center justify-center border transition-colors ${
                isSimulatingAudio
                  ? "bg-[#8ab4f8]/20 text-[#8ab4f8] border-[#8ab4f8]/30"
                  : "bg-[#1e1f20] hover:bg-[#282a2c] text-[#9aa0a6] hover:text-[#f1f3f4] border-white/[0.08]"
              }`}
              title={isSimulatingAudio ? "Stop Audio Simulation" : "Simulate Live Speech"}
            >
              <Volume2 size={13} />
            </button>

            <button
              onClick={() => setShowConsentModal(true)}
              className="w-7 h-7 rounded-full bg-[#1e1f20] hover:bg-[#282a2c] text-[#9aa0a6] hover:text-[#f1f3f4] border border-white/[0.08] flex items-center justify-center transition-colors"
              title="Privacy & Consent"
            >
              <Shield size={13} />
            </button>

            <button
              onClick={() => setShowSettings(!showSettings)}
              className={`w-7 h-7 rounded-full flex items-center justify-center border transition-colors ${
                showSettings
                  ? "bg-[#282a2c] text-[#f1f3f4] border-white/[0.18]"
                  : "bg-[#1e1f20] hover:bg-[#282a2c] text-[#9aa0a6] hover:text-[#f1f3f4] border-white/[0.08]"
              }`}
              title="Settings"
            >
              <SlidersHorizontal size={13} />
            </button>
          </div>
        </div>

        {/* ─── MAIN CONTENT VIEW (VOICE LIVE vs DESKTOP CHAT) ───────────── */}
        <div className="w-full relative">
          <AnimatePresence mode="wait">
            {activeView === "voice" ? (
              <motion.div
                key="voice-mode"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.15 }}
                className="w-full"
              >
                <GeminiVoiceMode
                  mitraState={mitraState}
                  audioLevel={audioLevel}
                  transcript={transcript}
                  isMuted={isMuted}
                  onToggleMute={() => setIsMuted(!isMuted)}
                  onSwitchToChat={() => setActiveView("chat")}
                  onToggleWake={toggleWakeListening}
                />
              </motion.div>
            ) : (
              <motion.div
                key="chat-mode"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.15 }}
                className="w-full"
              >
                <GeminiChatView
                  onSwitchToVoice={() => setActiveView("voice")}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* ─── SETTINGS DRAWER (FOLDABLE, MINIMAL GOOGLE STYLE) ─────────── */}
        <AnimatePresence>
          {showSettings && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="w-full p-4 border-t border-white/[0.08] bg-[#131314] text-xs text-[#9aa0a6] space-y-3"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-[#f1f3f4]">Audio Echo Cancellation</span>
                <button
                  onClick={() => setAecActive(!aecActive)}
                  className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono border transition-colors ${
                    aecActive
                      ? "bg-[#34a853]/15 text-[#34a853] border-[#34a853]/30"
                      : "bg-white/[0.04] text-[#9aa0a6] border-white/[0.08]"
                  }`}
                >
                  {aecActive ? "Active" : "Off"}
                </button>
              </div>

              <div className="flex items-center justify-between">
                <span className="font-medium text-[#f1f3f4]">Zero-Cloud Voice Buffer</span>
                <span className="text-[10px] text-[#34a853] font-mono">Enclave Protected</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="font-medium text-[#f1f3f4]">Thinking Orb Engine</span>
                <span className="text-[10px] text-[#8ab4f8] font-mono">2D Canvas (rareformlabs)</span>
              </div>

              <div className="pt-2">
                <button
                  onClick={toggleWakeListening}
                  className="w-full py-2 bg-[#1e1f20] hover:bg-[#282a2c] text-[#f1f3f4] rounded-xl border border-white/[0.08] flex items-center justify-center gap-2 transition-colors text-xs"
                >
                  <RefreshCw size={12} />
                  <span>Toggle Wake / Standby State</span>
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
