import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ThinkingOrb, OrbState } from "thinking-orbs";
import { Orbit } from "lucide-react";

export type OrbDisplayMode = "hybrid" | "dotted" | "fluid";

interface ThinkingOrbGeminiProps {
  state: string;
  audioLevel?: number;
  size?: number;
  onClick?: () => void;
  onStateSelect?: (state: OrbState) => void;
}

/**
 * Maps MITRA's conversational state machine to thinking-orbs states
 */
export function mapMitraToOrbState(mitraState: string): OrbState {
  if (mitraState.includes("IdleSleep")) return "breathing";
  if (mitraState.includes("Waking")) return "shaping";
  if (
    mitraState.includes("ActiveListening") ||
    mitraState.includes("UserSpeaking")
  ) {
    return "listening";
  }
  if (
    mitraState.includes("DeepProcessing") ||
    mitraState.includes("Thinking")
  ) {
    return "solving";
  }
  if (mitraState.includes("AgentSpeaking") || mitraState.includes("Speaking")) {
    return "composing";
  }
  if (mitraState.includes("ConversationalKeepAlive")) return "connecting";
  if (mitraState.includes("Searching") || mitraState.includes("Rag")) {
    return "searching";
  }
  return "working";
}

export const ALL_ORB_STATES: { state: OrbState; label: string; desc: string }[] = [
  { state: "listening", label: "Listening", desc: "Waveform rolls through rings" },
  { state: "solving", label: "Solving", desc: "Scrambled bands click into place" },
  { state: "searching", label: "Searching", desc: "Scan meridian sweeps dotted globe" },
  { state: "composing", label: "Composing", desc: "Flowing multi-band sash" },
  { state: "working", label: "Working", desc: "Particles on tilted orbits" },
  { state: "weaving", label: "Weaving", desc: "Three strands plait around sphere" },
  { state: "connecting", label: "Connecting", desc: "Constellation wiring itself" },
  { state: "shaping", label: "Shaping", desc: "Morphing geometric outline" },
  { state: "breathing", label: "Breathing", desc: "Peaceful ambient morphing ring" },
];

export const ThinkingOrbGemini: React.FC<ThinkingOrbGeminiProps> = ({
  state,
  audioLevel = 0,
  size = 180,
  onClick,
  onStateSelect,
}) => {
  const [displayMode, setDisplayMode] = useState<OrbDisplayMode>("hybrid");
  const [manualState, setManualState] = useState<OrbState | null>(null);
  const [showStatePicker, setShowStatePicker] = useState<boolean>(false);

  // Active state is either manual override or derived from MITRA state machine
  const activeOrbState: OrbState = manualState || mapMitraToOrbState(state);

  // Smooth audio smoothing
  const [smoothAudio, setSmoothAudio] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => {
      setSmoothAudio((prev) => prev + (audioLevel - prev) * 0.3);
    }, 30);
    return () => clearInterval(interval);
  }, [audioLevel]);

  // Audio-reactive dynamic speed multiplier
  const dynamicSpeed = Math.min(
    3.0,
    Math.max(0.8, 1.0 + smoothAudio * 2.8 + (activeOrbState === "solving" ? 0.4 : 0))
  );

  // Handle manual selection
  const handleSelectState = (s: OrbState) => {
    setManualState(s);
    if (onStateSelect) onStateSelect(s);
  };

  const resetToAutoState = () => {
    setManualState(null);
  };

  return (
    <div className="relative flex flex-col items-center justify-center select-none">
      {/* ─── 1. MODE & OVERRIDE CONTROLS (Top Floating Pill) ─────────────── */}
      <div className="flex items-center gap-1.5 mb-2 z-20">
        <div className="bg-black/60 backdrop-blur-md border border-white/10 rounded-full p-0.5 flex items-center shadow-lg">
          <button
            onClick={() => setDisplayMode("hybrid")}
            className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-all ${
              displayMode === "hybrid"
                ? "bg-gradient-to-r from-sky-500/30 to-indigo-500/30 text-sky-300 border border-sky-500/30 shadow-sm"
                : "text-neutral-400 hover:text-white"
            }`}
            title="Hybrid: Dotted Orb + Gemini Ambient Aura"
          >
            Hybrid
          </button>
          <button
            onClick={() => setDisplayMode("dotted")}
            className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-all ${
              displayMode === "dotted"
                ? "bg-white/15 text-white border border-white/20 shadow-sm"
                : "text-neutral-400 hover:text-white"
            }`}
            title="Dotted: Pure Thinking Orb (rareformlabs.github.io/thinking-orbs)"
          >
            Dotted
          </button>
          <button
            onClick={() => setDisplayMode("fluid")}
            className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-all ${
              displayMode === "fluid"
                ? "bg-gradient-to-r from-indigo-500/30 to-purple-500/30 text-purple-300 border border-purple-500/30 shadow-sm"
                : "text-neutral-400 hover:text-white"
            }`}
            title="Fluid: Fluid Quantum Energy"
          >
            Fluid
          </button>
        </div>

        {/* State Picker Button */}
        <button
          onClick={() => setShowStatePicker(!showStatePicker)}
          className={`px-2 py-1 rounded-full text-[10px] font-medium border flex items-center gap-1 transition-all ${
            manualState
              ? "bg-sky-500/20 text-sky-300 border-sky-500/30"
              : "bg-white/5 text-neutral-400 hover:text-white border-white/10"
          }`}
          title="Browse All 9 Thinking Orb States"
        >
          <Orbit size={11} className={manualState ? "text-sky-400 animate-spin" : ""} />
          <span>{activeOrbState}</span>
        </button>

        {manualState && (
          <button
            onClick={resetToAutoState}
            className="px-1.5 py-0.5 rounded-full text-[9px] bg-white/10 hover:bg-white/20 text-neutral-300 transition-colors"
            title="Return to auto state detection"
          >
            Auto
          </button>
        )}
      </div>

      {/* ─── 2. EXPANDABLE 9-STATE SELECTOR TRAY ─────────────────────────── */}
      <AnimatePresence>
        {showStatePicker && (
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: -6 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="absolute top-8 z-30 w-[340px] max-w-[90vw] p-2 bg-neutral-950/95 backdrop-blur-2xl border border-white/15 rounded-2xl shadow-2xl flex flex-wrap gap-1.5 justify-center"
          >
            {ALL_ORB_STATES.map((item) => (
              <button
                key={item.state}
                onClick={() => {
                  handleSelectState(item.state);
                  setShowStatePicker(false);
                }}
                className={`px-2.5 py-1 rounded-xl text-[10px] font-medium flex items-center gap-1.5 transition-all ${
                  activeOrbState === item.state
                    ? "bg-gradient-to-r from-sky-500 to-indigo-600 text-white shadow-md shadow-indigo-500/30"
                    : "bg-white/5 hover:bg-white/10 text-neutral-300 hover:text-white border border-white/5"
                }`}
                title={item.desc}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    activeOrbState === item.state
                      ? "bg-white animate-pulse"
                      : "bg-neutral-500"
                  }`}
                />
                <span>{item.label}</span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ─── 3. CENTER ORB STAGE ────────────────────────────────────────── */}
      <div
        onClick={onClick}
        className="relative flex items-center justify-center cursor-pointer group"
        style={{ width: size, height: size }}
      >
        {/* Ambient Gemini Outer Glow (Active in Hybrid and Fluid modes) */}
        {(displayMode === "hybrid" || displayMode === "fluid") && (
          <div
            className="absolute inset-0 rounded-full pointer-events-none transition-all duration-300"
            style={{
              background: `radial-gradient(circle, rgba(56, 189, 248, ${
                0.22 + smoothAudio * 0.4
              }) 0%, rgba(99, 102, 241, ${
                0.18 + smoothAudio * 0.3
              }) 35%, rgba(168, 85, 247, ${
                0.12 + smoothAudio * 0.2
              }) 60%, transparent 75%)`,
              filter: `blur(${20 + smoothAudio * 12}px)`,
              transform: `scale(${1.05 + smoothAudio * 0.28})`,
            }}
          />
        )}

        {/* Ethereal Floating Nebula Rings (Hybrid & Fluid) */}
        {displayMode !== "dotted" && (
          <>
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 22 / dynamicSpeed, ease: "linear" }}
              className="absolute w-[140px] h-[140px] rounded-full pointer-events-none border border-sky-400/20 opacity-60"
              style={{
                boxShadow: "0 0 25px rgba(56, 189, 248, 0.25) inset",
                transform: `scale(${1.0 + smoothAudio * 0.15})`,
              }}
            />
            <motion.div
              animate={{ rotate: -360 }}
              transition={{ repeat: Infinity, duration: 18 / dynamicSpeed, ease: "linear" }}
              className="absolute w-[115px] h-[115px] rounded-full pointer-events-none border border-purple-500/25 opacity-70"
              style={{
                boxShadow: "0 0 20px rgba(168, 85, 247, 0.25) inset",
              }}
            />
          </>
        )}

        {/* ─── DOTTED THINKING ORB (From https://rareformlabs.github.io/thinking-orbs) ─── */}
        {(displayMode === "hybrid" || displayMode === "dotted") && (
          <motion.div
            layout
            animate={{
              scale: 1.0 + smoothAudio * 0.18,
            }}
            transition={{ type: "spring", stiffness: 350, damping: 25 }}
            className="relative z-10 flex items-center justify-center"
            style={{
              filter:
                displayMode === "hybrid"
                  ? "drop-shadow(0 0 14px rgba(56, 189, 248, 0.6)) drop-shadow(0 0 28px rgba(99, 102, 241, 0.35))"
                  : "drop-shadow(0 0 6px rgba(255, 255, 255, 0.35))",
            }}
          >
            {/* The authentic ThinkingOrb component scaled to crisp avatar view */}
            <div
              style={{
                transform: "scale(2.2)",
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
        )}

        {/* ─── FLUID QUANTUM ENERGY NODES (For Fluid Mode) ─── */}
        {displayMode === "fluid" && (
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ repeat: Infinity, duration: 14 / dynamicSpeed, ease: "linear" }}
            className="relative z-10 w-28 h-28 flex items-center justify-center"
          >
            <div className="absolute w-12 h-12 rounded-full bg-sky-400/80 blur-sm translate-x-4 shadow-[0_0_20px_#38bdf8]" />
            <div className="absolute w-14 h-14 rounded-full bg-indigo-500/80 blur-sm -translate-x-4 shadow-[0_0_20px_#6366f1]" />
            <div className="absolute w-10 h-10 rounded-full bg-purple-500/80 blur-sm translate-y-4 shadow-[0_0_20px_#a855f7]" />
            <div className="absolute w-11 h-11 rounded-full bg-blue-600/80 blur-sm -translate-y-4 shadow-[0_0_20px_#2563eb]" />
          </motion.div>
        )}

        {/* Interactive hover ripple cue */}
        <div className="absolute inset-0 rounded-full group-hover:ring-1 group-hover:ring-sky-400/30 transition-all pointer-events-none" />
      </div>

      {/* ─── 4. SOUNDWAVE FREQUENCY VISUALIZER ───────────────────────────── */}
      <div className="flex items-center justify-center gap-0.5 mt-2 h-4">
        {[...Array(16)].map((_, i) => {
          const waveHeight = Math.max(
            3,
            Math.sin((i / 16) * Math.PI) * (smoothAudio * 20 + 4) * (1 + (i % 3) * 0.15)
          );
          return (
            <motion.div
              key={i}
              className="w-1 rounded-full bg-gradient-to-t from-sky-400 via-indigo-400 to-purple-400"
              style={{
                height: `${Math.min(16, waveHeight)}px`,
                opacity: 0.35 + (waveHeight / 16) * 0.65,
              }}
              transition={{ ease: "easeOut", duration: 0.05 }}
            />
          );
        })}
      </div>
    </div>
  );
};
