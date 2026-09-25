import React, { useEffect, useRef } from "react";

interface ThinkingOrbProps {
  state: string;
  audioLevel: number;
  size?: number;
  onClick?: () => void;
}

interface Particle {
  x: number;
  y: number;
  z: number;
  angle: number;
  radius: number;
  speed: number;
  size: number;
  hue: number;
  alpha: number;
}

export const ThinkingOrb: React.FC<ThinkingOrbProps> = ({
  state,
  audioLevel,
  size = 220,
  onClick,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animFrameRef = useRef<number>(0);
  const timeRef = useRef<number>(0);
  const smoothAudioRef = useRef<number>(0);
  const particlesRef = useRef<Particle[]>([]);

  // Initialize stardust particles
  useEffect(() => {
    const count = 45;
    const particles: Particle[] = [];
    for (let i = 0; i < count; i++) {
      particles.push({
        x: 0,
        y: 0,
        z: Math.random() * 2 - 1,
        angle: Math.random() * Math.PI * 2,
        radius: 35 + Math.random() * 60,
        speed: (0.008 + Math.random() * 0.015) * (Math.random() > 0.5 ? 1 : -1),
        size: 1 + Math.random() * 2.2,
        hue: 200 + Math.random() * 80,
        alpha: 0.3 + Math.random() * 0.7,
      });
    }
    particlesRef.current = particles;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // High DPI scaling
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const isIdle = state.includes("IdleSleep");
    const isListening = state.includes("ActiveListening") || state.includes("UserSpeaking");
    const isThinking = state.includes("DeepProcessing");
    const isSpeaking = state.includes("AgentSpeaking");
    const isKeepAlive = state.includes("ConversationalKeepAlive");

    let isRunning = true;

    const render = () => {
      if (!isRunning) return;

      // Smooth audio smoothing filter
      smoothAudioRef.current += (audioLevel - smoothAudioRef.current) * 0.25;
      const smoothAudio = smoothAudioRef.current;

      // Time step varies with state
      let speedMultiplier = 1.0;
      if (isThinking) speedMultiplier = 2.6; // High energy thinking vortex
      else if (isSpeaking) speedMultiplier = 1.8;
      else if (isListening) speedMultiplier = 1.4;
      else if (isIdle) speedMultiplier = 0.6; // Peaceful idle breathing

      timeRef.current += 0.02 * speedMultiplier;
      const t = timeRef.current;

      const cx = size / 2;
      const cy = size / 2;
      const baseRadius = size * 0.26;

      ctx.clearRect(0, 0, size, size);

      // ─── 1. AMBIENT BACKGROUND GLOW (Corona Bloom) ───────────────────
      const glowRadius = size * 0.46 * (1 + smoothAudio * 0.35);
      const ambientGlow = ctx.createRadialGradient(cx, cy, baseRadius * 0.4, cx, cy, glowRadius);

      if (isThinking) {
        // Multi-chromatic iridescent thinking bloom (Gemini Cyan / Indigo / Amber)
        ambientGlow.addColorStop(0, "rgba(99, 102, 241, 0.45)");
        ambientGlow.addColorStop(0.35, "rgba(56, 189, 248, 0.3)");
        ambientGlow.addColorStop(0.7, "rgba(236, 72, 153, 0.2)");
        ambientGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      } else if (isListening || state.includes("UserSpeaking")) {
        // Energetic reactive Cyan / Emerald
        ambientGlow.addColorStop(0, "rgba(34, 211, 238, 0.48)");
        ambientGlow.addColorStop(0.4, "rgba(52, 211, 153, 0.32)");
        ambientGlow.addColorStop(0.8, "rgba(14, 165, 233, 0.15)");
        ambientGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      } else if (isSpeaking) {
        // Luminous Purple / Violet vocal harmonics
        ambientGlow.addColorStop(0, "rgba(168, 85, 247, 0.5)");
        ambientGlow.addColorStop(0.5, "rgba(129, 140, 248, 0.25)");
        ambientGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      } else if (isKeepAlive) {
        // Warm Amber / Sapphire standby
        ambientGlow.addColorStop(0, "rgba(251, 191, 36, 0.35)");
        ambientGlow.addColorStop(0.5, "rgba(56, 189, 248, 0.2)");
        ambientGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      } else {
        // Pure Obsidian Deep Violet breathing
        const breathe = Math.sin(t * 0.8) * 0.08;
        ambientGlow.addColorStop(0, `rgba(79, 70, 229, ${0.22 + breathe})`);
        ambientGlow.addColorStop(0.5, "rgba(30, 27, 75, 0.15)");
        ambientGlow.addColorStop(1, "rgba(0, 0, 0, 0)");
      }

      ctx.fillStyle = ambientGlow;
      ctx.beginPath();
      ctx.arc(cx, cy, glowRadius, 0, Math.PI * 2);
      ctx.fill();

      // ─── 2. STARDUST QUANTUM PARTICLES (Orbiting Core) ───────────────
      ctx.save();
      const particles = particlesRef.current;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.angle += p.speed * speedMultiplier;
        p.z += Math.sin(t + i) * 0.01;
        if (p.z > 1) p.z = -1;
        if (p.z < -1) p.z = 1;

        const scale = (p.z + 2) / 3;
        const currentRadius = p.radius * (1 + smoothAudio * 0.5);
        const px = cx + Math.cos(p.angle) * currentRadius;
        const py = cy + Math.sin(p.angle) * currentRadius * 0.82; // slight 3D perspective slant

        ctx.fillStyle = `hsla(${p.hue + (isThinking ? t * 40 : 0)}, 90%, 75%, ${p.alpha * scale})`;
        ctx.beginPath();
        ctx.arc(px, py, p.size * scale, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      // ─── 3. MULTI-LAYERED CHROMATIC ENERGY STRANDS (The Fluid Orb) ──
      ctx.save();
      ctx.globalCompositeOperation = "lighter"; // Additive luminescence

      const waveLayers = isThinking
        ? [
            { color: "rgba(56, 189, 248, 0.75)", freq: 4, speed: 1.3, amp: 14, phase: 0 },
            { color: "rgba(168, 85, 247, 0.75)", freq: 5, speed: -1.7, amp: 16, phase: 1.2 },
            { color: "rgba(236, 72, 153, 0.65)", freq: 3, speed: 2.1, amp: 12, phase: 2.4 },
            { color: "rgba(251, 191, 36, 0.55)", freq: 6, speed: -0.9, amp: 10, phase: 3.8 },
          ]
        : isListening || isSpeaking
        ? [
            { color: "rgba(34, 211, 238, 0.8)", freq: 4, speed: 1.2, amp: 10 + smoothAudio * 35, phase: 0 },
            { color: "rgba(99, 102, 241, 0.7)", freq: 5, speed: -1.4, amp: 12 + smoothAudio * 30, phase: 1.5 },
            { color: "rgba(168, 85, 247, 0.6)", freq: 3, speed: 1.8, amp: 8 + smoothAudio * 25, phase: 3.0 },
          ]
        : [
            // Idle — subtle, elegant harmonic contours
            { color: "rgba(99, 102, 241, 0.4)", freq: 3, speed: 0.7, amp: 6, phase: 0 },
            { color: "rgba(56, 189, 248, 0.35)", freq: 4, speed: -0.9, amp: 5, phase: 1.8 },
            { color: "rgba(168, 85, 247, 0.3)", freq: 2, speed: 1.1, amp: 4, phase: 3.2 },
          ];

      waveLayers.forEach((layer) => {
        ctx.beginPath();
        const steps = 90;
        for (let i = 0; i <= steps; i++) {
          const theta = (i / steps) * Math.PI * 2;
          const harmonic =
            Math.sin(theta * layer.freq + t * layer.speed + layer.phase) * layer.amp +
            Math.cos(theta * (layer.freq - 1) - t * 0.8) * (layer.amp * 0.4);

          const r = baseRadius + harmonic + (isThinking ? Math.sin(theta * 3 + t * 4) * 8 : 0);
          const x = cx + Math.cos(theta) * r;
          const y = cy + Math.sin(theta) * r;

          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();

        const grad = ctx.createRadialGradient(
          cx + Math.cos(t) * 12,
          cy + Math.sin(t) * 12,
          baseRadius * 0.2,
          cx,
          cy,
          baseRadius * 1.3
        );
        grad.addColorStop(0, layer.color);
        grad.addColorStop(1, "rgba(0, 0, 0, 0)");

        ctx.fillStyle = grad;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = layer.color;
        ctx.stroke();
      });

      ctx.restore();

      // ─── 4. INNER OPALESCENT GLASS CORE & SPECULAR LENS ──────────────
      ctx.save();
      const coreRadius = baseRadius * 0.75;
      const coreGrad = ctx.createRadialGradient(
        cx - coreRadius * 0.35,
        cy - coreRadius * 0.35,
        coreRadius * 0.05,
        cx,
        cy,
        coreRadius
      );

      if (isThinking) {
        coreGrad.addColorStop(0, "rgba(255, 255, 255, 0.85)");
        coreGrad.addColorStop(0.3, "rgba(147, 197, 253, 0.6)");
        coreGrad.addColorStop(0.7, "rgba(129, 140, 248, 0.35)");
        coreGrad.addColorStop(1, "rgba(15, 15, 26, 0.85)");
      } else if (isListening) {
        coreGrad.addColorStop(0, "rgba(255, 255, 255, 0.9)");
        coreGrad.addColorStop(0.3, "rgba(103, 232, 249, 0.65)");
        coreGrad.addColorStop(0.8, "rgba(14, 116, 144, 0.4)");
        coreGrad.addColorStop(1, "rgba(8, 12, 22, 0.85)");
      } else {
        coreGrad.addColorStop(0, "rgba(255, 255, 255, 0.75)");
        coreGrad.addColorStop(0.25, "rgba(165, 180, 252, 0.45)");
        coreGrad.addColorStop(0.7, "rgba(49, 46, 129, 0.3)");
        coreGrad.addColorStop(1, "rgba(5, 5, 10, 0.92)");
      }

      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, coreRadius, 0, Math.PI * 2);
      ctx.fill();

      // Specular glass highlight reflection (top-left)
      const specX = cx - coreRadius * 0.42;
      const specY = cy - coreRadius * 0.42;
      const specGrad = ctx.createRadialGradient(specX, specY, 1, specX, specY, coreRadius * 0.45);
      specGrad.addColorStop(0, "rgba(255, 255, 255, 0.85)");
      specGrad.addColorStop(0.4, "rgba(255, 255, 255, 0.25)");
      specGrad.addColorStop(1, "rgba(255, 255, 255, 0)");

      ctx.fillStyle = specGrad;
      ctx.beginPath();
      ctx.ellipse(specX, specY, coreRadius * 0.35, coreRadius * 0.22, -Math.PI / 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      animFrameRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      isRunning = false;
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [state, audioLevel, size]);

  return (
    <div
      className="thinking-orb-container"
      onClick={onClick}
      style={{
        width: size,
        height: size,
        position: "relative",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          width: size,
          height: size,
          display: "block",
          filter: "drop-shadow(0 0 24px rgba(99, 102, 241, 0.25))",
        }}
      />
    </div>
  );
};
