import React, { useEffect, useRef } from "react";
import { motion } from "framer-motion";

interface GeminiThinkingOrbProps {
  state: string;
  audioLevel?: number;
  size?: number;
  onClick?: () => void;
}

interface OrbNode {
  baseX: number;
  baseY: number;
  radius: number;
  color: string;
  angle: number;
  speed: number;
  distFactor: number;
}

export const GeminiThinkingOrb: React.FC<GeminiThinkingOrbProps> = ({
  state,
  audioLevel = 0,
  size = 200,
  onClick,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animRef = useRef<number>(0);
  const timeRef = useRef<number>(0);
  const audioSmoothRef = useRef<number>(0);

  const isIdle = state.includes("IdleSleep");
  const isListening = state.includes("ActiveListening") || state.includes("UserSpeaking") || state.includes("Waking");
  const isThinking = state.includes("DeepProcessing") || state.includes("Thinking");
  const isSpeaking = state.includes("AgentSpeaking") || state.includes("Speaking");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    // 4 Gemini energy nodes
    const nodes: OrbNode[] = [
      { baseX: 0, baseY: 0, radius: 46, color: "rgba(56, 189, 248, 0.85)", angle: 0, speed: 0.022, distFactor: 24 },       // Cyan
      { baseX: 0, baseY: 0, radius: 52, color: "rgba(99, 102, 241, 0.82)", angle: Math.PI / 2, speed: 0.018, distFactor: 28 }, // Indigo
      { baseX: 0, baseY: 0, radius: 48, color: "rgba(168, 85, 247, 0.82)", angle: Math.PI, speed: 0.025, distFactor: 22 },     // Purple
      { baseX: 0, baseY: 0, radius: 44, color: "rgba(37, 99, 235, 0.80)", angle: Math.PI * 1.5, speed: 0.019, distFactor: 26 }, // Blue
    ];

    let running = true;

    const render = () => {
      if (!running) return;

      audioSmoothRef.current += (audioLevel - audioSmoothRef.current) * 0.22;
      const smoothAudio = audioSmoothRef.current;

      // Speed and scale multipliers based on state
      let speedMult = 1.0;
      let expandMult = 1.0;
      let glowIntensity = 1.0;

      if (isThinking) {
        speedMult = 2.4;
        expandMult = 1.15;
        glowIntensity = 1.4;
      } else if (isListening) {
        speedMult = 1.5;
        expandMult = 1.0 + smoothAudio * 0.45;
        glowIntensity = 1.1 + smoothAudio * 0.5;
      } else if (isSpeaking) {
        speedMult = 1.8;
        expandMult = 1.08 + Math.sin(timeRef.current * 8) * 0.06;
        glowIntensity = 1.25;
      } else {
        // Idle
        speedMult = 0.6;
        expandMult = 0.92;
        glowIntensity = 0.75;
      }

      timeRef.current += 0.016 * speedMult;
      const t = timeRef.current;

      ctx.clearRect(0, 0, size, size);

      const cx = size / 2;
      const cy = size / 2;

      // Draw background ambient glow
      const bgGrad = ctx.createRadialGradient(cx, cy, 10, cx, cy, size * 0.45);
      bgGrad.addColorStop(0, `rgba(79, 70, 229, ${0.18 * glowIntensity})`);
      bgGrad.addColorStop(0.5, `rgba(56, 189, 248, ${0.08 * glowIntensity})`);
      bgGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, size, size);

      // Save before blend mode
      ctx.save();
      ctx.globalCompositeOperation = "screen";

      // Render orbiting fluid nodes
      nodes.forEach((node, i) => {
        const currentAngle = node.angle + t * node.speed * (i % 2 === 0 ? 1 : -1);
        const dist = (node.distFactor + Math.sin(t * 1.5 + i) * 8) * expandMult;

        const x = cx + Math.cos(currentAngle) * dist;
        const y = cy + Math.sin(currentAngle) * dist;
        const r = node.radius * expandMult * (0.95 + Math.sin(t * 2 + i) * 0.08);

        const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
        grad.addColorStop(0, node.color);
        grad.addColorStop(0.55, node.color.replace(/[\d\.]+\)$/, "0.45)"));
        grad.addColorStop(1, "rgba(0, 0, 0, 0)");

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      });

      // Central core highlight
      const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 32 * expandMult);
      coreGrad.addColorStop(0, `rgba(255, 255, 255, ${0.5 * glowIntensity})`);
      coreGrad.addColorStop(0.4, `rgba(147, 197, 253, ${0.35 * glowIntensity})`);
      coreGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, 32 * expandMult, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();

      animRef.current = requestAnimationFrame(render);
    };

    animRef.current = requestAnimationFrame(render);

    return () => {
      running = false;
      cancelAnimationFrame(animRef.current);
    };
  }, [size, isThinking, isListening, isSpeaking, isIdle, audioLevel]);

  return (
    <div
      onClick={onClick}
      style={{
        width: size,
        height: size,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          width: size,
          height: size,
          filter: "blur(18px)",
          transform: "scale(1.08)",
        }}
      />
      {/* Crisp optical center dot for precision */}
      <motion.div
        animate={{
          scale: isThinking ? [1, 1.25, 1] : isListening ? 1 + audioLevel * 0.4 : 1,
          opacity: isIdle ? 0.35 : 0.85,
        }}
        transition={{
          repeat: isThinking ? Infinity : 0,
          duration: isThinking ? 1.5 : 0.2,
          ease: "easeInOut",
        }}
        style={{
          position: "absolute",
          width: 8,
          height: 8,
          borderRadius: "50%",
          backgroundColor: "#ffffff",
          boxShadow: "0 0 12px rgba(255, 255, 255, 0.9)",
          pointerEvents: "none",
        }}
      />
    </div>
  );
};
