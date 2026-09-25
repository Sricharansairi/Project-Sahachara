import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ThinkingOrb, OrbState } from "thinking-orbs";
import {
  Mic,
  MicOff,
  Eye,
  MessageSquare,
  Pause,
  Play,
} from "lucide-react";
import { mapMitraToOrbState, ALL_ORB_STATES } from "./ThinkingOrbGemini";

interface GeminiVoiceModeProps {
  mitraState: string;
  audioLevel: number;
  transcript: string;
  isMuted: boolean;
  onToggleMute: () => void;
  onSwitchToChat: () => void;
  onToggleWake: () => void;
}

export const GeminiVoiceMode: React.FC<GeminiVoiceModeProps> = ({
  mitraState,
  audioLevel,
  transcript,
  isMuted,
  onToggleMute,
  onSwitchToChat,
  onToggleWake,
}) => {
  const [smoothAudio, setSmoothAudio] = useState(0);
  const [screenGlanceActive, setScreenGlanceActive] = useState(false);
  const [selectedStateOverride, setSelectedStateOverride] = useState<OrbState | null>(null);
  const [showStateMenu, setShowStateMenu] = useState(false);

  // Smooth audio decay filter
  useEffect(() => {
    const interval = setInterval(() => {
      setSmoothAudio((prev) => prev + (audioLevel - prev) * 0.28);
    }, 30);
    return () => clearInterval(interval);
  }, [audioLevel]);

  const activeOrbState: OrbState = selectedStateOverride || mapMitraToOrbState(mitraState);
  const dynamicSpeed = Math.min(2.5, Math.max(0.8, 1.0 + smoothAudio * 2.2));

  const getStatusText = () => {
    if (isMuted) return "Microphone paused";
    if (mitraState.includes("DeepProcessing") || mitraState.includes("Thinking"))
      return "Thinking...";
    if (
      mitraState.includes("ActiveListening") ||
      mitraState.includes("UserSpeaking")
    )
      return "Listening...";
    if (mitraState.includes("AgentSpeaking") || mitraState.includes("Speaking"))
      return "Speaking...";
    if (mitraState.includes("ConversationalKeepAlive"))
      return "Listening for follow-up...";
    return "Say \"Hey Mitra\" or tap to speak";
  };

  return (
    <div className="w-full flex flex-col items-center justify-between min-h-[440px] px-3 py-2 text-[#f1f3f4] relative select-none">
      {/* ─── 1. TOP STATUS PILL ──────────────────────────────────────── */}
      <div className="flex items-center justify-between w-full px-2 z-10">
        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full transition-colors ${
              !isMuted && !mitraState.includes("IdleSleep")
                ? "bg-[#34a853] animate-pulse"
                : "bg-[#5f6368]"
            }`}
          />
          <span className="text-xs font-medium text-[#9aa0a6] tracking-wide">
            {getStatusText()}
          </span>
        </div>

        {/* State Override Selector Pill */}
        <div className="relative">
          <button
            onClick={() => setShowStateMenu(!showStateMenu)}
            className="px-2.5 py-1 rounded-full bg-[#1e1f20] hover:bg-[#282a2c] border border-white/[0.08] text-[10px] text-[#9aa0a6] hover:text-[#f1f3f4] transition-colors flex items-center gap-1.5"
            title="Switch Thinking Orb state preset"
          >
            <span>State:</span>
            <span className="text-[#8ab4f8] font-medium capitalize">{activeOrbState}</span>
          </button>

          {/* Expandable State Tray */}
          <AnimatePresence>
            {showStateMenu && (
              <motion.div
                initial={{ opacity: 0, scale: 0.94, y: 4 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.94, y: 4 }}
                className="absolute right-0 top-8 z-30 w-48 p-1.5 bg-[#1e1f20] border border-white/[0.1] rounded-2xl shadow-2xl flex flex-col gap-0.5"
              >
                {ALL_ORB_STATES.map((item) => (
                  <button
                    key={item.state}
                    onClick={() => {
                      setSelectedStateOverride(item.state);
                      setShowStateMenu(false);
                    }}
                    className={`w-full text-left px-2.5 py-1.5 rounded-lg text-[11px] flex items-center justify-between transition-colors ${
                      activeOrbState === item.state
                        ? "bg-white/[0.08] text-[#8ab4f8] font-medium"
                        : "text-[#9aa0a6] hover:text-[#f1f3f4] hover:bg-white/[0.04]"
                    }`}
                  >
                    <span className="capitalize">{item.state}</span>
                    <span className="text-[9px] text-[#5f6368] font-mono">{item.label}</span>
                  </button>
                ))}
                {selectedStateOverride && (
                  <button
                    onClick={() => {
                      setSelectedStateOverride(null);
                      setShowStateMenu(false);
                    }}
                    className="w-full text-center py-1 mt-1 border-t border-white/[0.06] text-[10px] text-[#8ab4f8] hover:underline"
                  >
                    Reset to Auto
                  </button>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* ─── 2. CENTER STAGE: DOTTED THINKING ORB (NO GRADIENTS) ──────── */}
      <div className="my-auto flex flex-col items-center justify-center py-4 relative">
        <motion.div
          animate={{
            scale: 1.0 + smoothAudio * 0.12,
          }}
          transition={{ type: "spring", stiffness: 350, damping: 24 }}
          onClick={onToggleWake}
          className="cursor-pointer relative flex items-center justify-center"
          title="Tap to speak"
        >
          {/* Subtle monochrome backing glow for visibility */}
          <div
            className="absolute rounded-full pointer-events-none transition-opacity duration-300"
            style={{
              width: 140,
              height: 140,
              background: "radial-gradient(circle, rgba(255, 255, 255, 0.05) 0%, transparent 70%)",
              opacity: isMuted ? 0.2 : 0.8 + smoothAudio * 0.4,
            }}
          />

          {/* Dotted Thinking Orb Component from rareformlabs/thinking-orbs */}
          <div
            style={{
              transform: "scale(2.4)",
              transformOrigin: "center center",
              width: 64,
              height: 64,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <ThinkingOrb
              state={activeOrbState}
              size={64}
              theme="dark"
              speed={dynamicSpeed}
            />
          </div>
        </motion.div>

        {/* ─── 3. MINIMALIST AUDIO EQUALIZER BARS (MONOCHROME/BLUE) ────── */}
        <div className="flex items-center justify-center gap-[3px] mt-6 h-5">
          {[...Array(14)].map((_, i) => {
            const h = Math.max(
              3,
              Math.sin((i / 14) * Math.PI) * (smoothAudio * 18 + 3) * (1 + (i % 2) * 0.2)
            );
            return (
              <motion.div
                key={i}
                className={`w-[2.5px] rounded-full transition-all duration-75 ${
                  smoothAudio > 0.05 ? "bg-[#8ab4f8]" : "bg-white/[0.15]"
                }`}
                style={{ height: `${Math.min(18, h)}px` }}
              />
            );
          })}
        </div>

        {/* ─── 4. LIVE SUBTITLE / TRANSCRIPT STREAM ───────────────────── */}
        <div className="mt-4 px-4 text-center max-w-[340px]">
          <p className="text-xs text-[#9aa0a6] font-normal leading-relaxed line-clamp-2">
            {transcript ? (
              <span className="text-[#f1f3f4] font-medium">"{transcript}"</span>
            ) : (
              <span>Listening for voice input...</span>
            )}
          </p>
        </div>
      </div>

      {/* ─── 5. FLOATING BOTTOM ACTION PILLS (MOBILE GEMINI LIVE STYLE) ── */}
      <div className="w-full flex items-center justify-center gap-3 pt-3 pb-1 border-t border-white/[0.06] z-10">
        {/* Mic Toggle Button */}
        <button
          onClick={onToggleMute}
          className={`w-11 h-11 rounded-full flex items-center justify-center border transition-all ${
            isMuted
              ? "bg-[#ea4335]/15 text-[#ea4335] border-[#ea4335]/30 hover:bg-[#ea4335]/25"
              : "bg-[#1e1f20] hover:bg-[#282a2c] text-[#f1f3f4] border-white/[0.08]"
          }`}
          title={isMuted ? "Unpause Microphone" : "Pause Microphone"}
        >
          {isMuted ? <MicOff size={18} /> : <Mic size={18} />}
        </button>

        {/* Screen Glance Toggle */}
        <button
          onClick={() => setScreenGlanceActive(!screenGlanceActive)}
          className={`w-11 h-11 rounded-full flex items-center justify-center border transition-all ${
            screenGlanceActive
              ? "bg-[#8ab4f8]/20 text-[#8ab4f8] border-[#8ab4f8]/40"
              : "bg-[#1e1f20] hover:bg-[#282a2c] text-[#9aa0a6] hover:text-[#f1f3f4] border-white/[0.08]"
          }`}
          title={screenGlanceActive ? "Screen Glance Active" : "Glance at Focused Window"}
        >
          <Eye size={18} />
        </button>

        {/* Manual Wake / Sleep Toggle */}
        <button
          onClick={onToggleWake}
          className="w-11 h-11 rounded-full bg-[#1e1f20] hover:bg-[#282a2c] text-[#9aa0a6] hover:text-[#f1f3f4] border border-white/[0.08] flex items-center justify-center transition-colors"
          title="Toggle Standby"
        >
          {mitraState.includes("IdleSleep") ? <Play size={17} /> : <Pause size={17} />}
        </button>

        {/* Switch to Desktop Chat Mode */}
        <button
          onClick={onSwitchToChat}
          className="w-11 h-11 rounded-full bg-[#1e1f20] hover:bg-[#282a2c] text-[#9aa0a6] hover:text-[#f1f3f4] border border-white/[0.08] flex items-center justify-center transition-colors"
          title="Switch to Desktop Chat View"
        >
          <MessageSquare size={17} />
        </button>
      </div>
    </div>
  );
};
