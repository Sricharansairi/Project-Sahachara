import React, { useEffect, useRef } from "react";

interface AudioVisualizerProps {
  level: number;
  isActive: boolean;
  barCount?: number;
  height?: number;
}

export const AudioVisualizer: React.FC<AudioVisualizerProps> = ({
  level,
  isActive,
  barCount = 24,
  height = 36,
}) => {
  const barsRef = useRef<number[]>(new Array(barCount).fill(0.08));
  const animRef = useRef<number>(0);

  useEffect(() => {
    let running = true;
    const render = () => {
      if (!running) return;

      const bars = barsRef.current;
      for (let i = 0; i < barCount; i++) {
        const centerDist = 1 - Math.abs(i - barCount / 2) / (barCount / 2);
        const target = isActive
          ? Math.max(0.1, level * (0.4 + centerDist * 0.8) + Math.sin(Date.now() * 0.008 + i * 0.4) * 0.12 * level)
          : 0.08 + Math.sin(Date.now() * 0.002 + i * 0.25) * 0.03;

        bars[i] += (target - bars[i]) * 0.3;
      }

      animRef.current = requestAnimationFrame(render);
    };

    render();
    return () => {
      running = false;
      cancelAnimationFrame(animRef.current);
    };
  }, [level, isActive, barCount]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 3,
        height,
        padding: "0 8px",
      }}
    >
      {barsRef.current.map((bar, i) => {
        const centerDist = 1 - Math.abs(i - barCount / 2) / (barCount / 2);
        const clamped = Math.min(Math.max(bar, 0.08), 1);
        const h = Math.round(clamped * height);

        return (
          <div
            key={i}
            style={{
              width: 3,
              height: `${Math.max(h, 3)}px`,
              borderRadius: 3,
              background: isActive
                ? `linear-gradient(180deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%)`
                : "rgba(255, 255, 255, 0.12)",
              boxShadow: isActive && clamped > 0.3
                ? `0 0 ${8 * centerDist}px rgba(56, 189, 248, 0.6)`
                : "none",
              transition: "height 40ms ease",
            }}
          />
        );
      })}
    </div>
  );
};
