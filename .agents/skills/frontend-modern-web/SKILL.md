---
name: frontend-modern-web
description: >-
  Advanced React 19, TypeScript, and modern web application development skill.
  Guides Zustand state synchronization with Tauri IPC, low-latency SSE stream parsing,
  keyboard accessibility, responsive desktop layouts, and 60 FPS performance optimizations.
---

# Modern Frontend & Tauri Web Application Standards

This skill governs high-performance frontend engineering for MITRA.

## 1. React 19 & State Architecture
- **Zustand Store (`src/store/useMitraStore.ts`)**:
  - Single source of truth for MITRA state (`MitraState`, `voiceStatus`, `aecActive`, `activeCards`, `undoQueue`, `commitments`).
  - Decoupled from rendering: components subscribe only to the slices they consume.
- **Tauri IPC Event Listeners**:
  - Listen to backend events using `@tauri-apps/api/event`.
  - Unlisten cleanup hooks on unmount to prevent memory leaks.
- **Low-Latency SSE Streaming**:
  - Streaming words/tokens from `/api/v1/voice/pipeline/stream` or `/api/v1/chat/stream`.
  - Append tokens to the active transcript buffer without triggering full re-renders of unrelated components.

## 2. Keyboard & Accessibility (WCAG 2.1 AA)
- Global shortcut `Ctrl+Z` handles action rollback during the 10-second undo window.
- Full keyboard navigation: focus rings, `Tab` cycling inside action cards, `Escape` to collapse/dock.
- Screen reader announcements using `aria-live="polite"` for state transitions.

## 3. Performance & 60 FPS Target
- Avoid CSS filters on high-frequency animating elements (e.g. animate `opacity` and `transform` rather than `backdrop-filter`).
- Use CSS `will-change: transform` on floating pills during drag and snap operations.
- Zero layout shift: Fixed aspect-ratio containers and reserved slots for action cards.
