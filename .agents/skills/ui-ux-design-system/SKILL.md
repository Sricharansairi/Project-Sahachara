---
name: ui-ux-design-system
description: >-
  World-class UI/UX design system and interaction design skill.
  Guides the implementation of pure black OLED (#000000) glassmorphic interfaces,
  Dynamic Island state morphing, publication-grade Framer Motion animations,
  accessible contrast ratios, and micro-interactions.
---

# UI/UX Design System & Ambient Interface Engineering

This skill defines the design tokens, visual architecture, motion grammar, and interaction design standards for Project Sahachara (MITRA).

## 1. Visual Aesthetics & Philosophy
- **Pure Black OLED Canvas**: Background is `#000000` to maximize contrast, conserve energy on OLED/Mini-LED displays, and create the illusion that the UI floats natively on the desktop.
- **Glassmorphic Depth Layers**:
  - `Surface Level 0`: Background `#000000`.
  - `Surface Level 1` (Collapsed Pill): `rgba(18, 18, 18, 0.72)` with `backdrop-filter: blur(24px)` and `border: 1px solid rgba(255, 255, 255, 0.08)`.
  - `Surface Level 2` (Expanded Action Cards): `rgba(24, 24, 28, 0.85)` with `backdrop-filter: blur(32px)` and subtle linear border gradient `linear-gradient(135deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.02) 100%)`.
  - `Surface Level 3` (Modals / Overlays): `rgba(30, 30, 36, 0.95)` with high blur `blur(40px)`.

## 2. Dynamic Island State Grammar (7 States)
MITRA's floating pill dynamically reflects the state machine with fluid transitions:
1. **PassiveIdle**: Collapsed 180×40px, subtle breathing ambient pulse (`opacity: 0.8 -> 1.0` every 4s).
2. **Waking**: Expands slightly + bright neon emerald ring pulse (`#10B981`, `box-shadow: 0 0 20px rgba(16, 185, 129, 0.4)`).
3. **Listening**: Dynamic live soundwave bars animated using real-time audio energy.
4. **Thinking / Reasoning**: Glowing shimmer gradient sweep (`linear-gradient(90deg, #6366F1, #8B5CF6, #EC4899)`).
5. **Speaking**: Symmetrical voice frequency visualizer + audio waveform bars responding to TTS chunks.
6. **ExecutingTool**: Expands into action card layout with live countdown bar (10s Undo buffer).
7. **Error / Blocked**: Gentle amber/rose ring alert (`#F43F5E`) with clean explanatory toast.

## 3. Motion & Animation Physics (Framer Motion)
- **Spring Physics for Expansions**:
  ```ts
  const springTransition = {
    type: "spring",
    stiffness: 400,
    damping: 30,
    mass: 0.8,
  };
  ```
- **Never jump layouts**: Always use layout animations (`layout` prop on `motion.div`) to prevent layout shifts.
- **Micro-Interactions**:
  - Hover: `whileHover={{ scale: 1.02, y: -1 }}`
  - Tap / Press: `whileTap={{ scale: 0.97 }}`
  - Cards Entrance: `initial={{ opacity: 0, scale: 0.94, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }}`
  - Exit: `exit={{ opacity: 0, scale: 0.96, y: -4 }}`

## 4. Typography Hierarchy
- **Primary / Body Font**: `Inter`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `Roboto`, sans-serif.
- **Headings / Accents**: `Outfit`, sans-serif.
- **Numbers / Metrics / Timers**: Tabular numbers (`font-variant-numeric: tabular-nums`) so countdown clocks don't jitter.

## 5. Action Card Standards
- **10-Second Undo Bar**: Live reactive progress bar shrinking from 100% to 0% over 10.0 seconds with prominent `Undo (Ctrl+Z)` button.
- **Ghost Radar Commitment Card**: Badges for `Outbound` (Cyan) and `Inbound` (Amber), 1-click `Snooze` and `Resolve`.
- **Pre-Meeting Dossier Card**: Calendar time indicator, attendee chips, 3 synthesized bullet points.
- **Clipboard Augmenter**: Quick action pills with subtle glowing borders.
