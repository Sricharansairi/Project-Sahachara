// MITRA Phase 4 — audio/aec.rs
//
// Acoustic Echo Cancellation (AEC) Gate
//
// Strategy: Hard-mute microphone input during TTS playback.
// This is the simplest, most reliable AEC approach for a single-user
// desktop assistant: we own the mic stream, so we simply gate it.
//
// Implementation:
//   - `AecGate` wraps an `Arc<AtomicBool>` that is shared with the audio
//     capture pipeline (ring_buffer writer and VAD tick loop).
//   - When TTS begins playing, `AecGate::activate()` sets the flag.
//   - The audio capture loop (capture.rs) checks the flag before each
//     ring-buffer write — if AEC active, samples are dropped (zeroed).
//   - When TTS finishes (or is interrupted), `AecGate::deactivate()` clears.
//   - Barge-in: a 200ms re-arm window is applied after TTS completes to
//     prevent Mitra's own trailing audio from triggering the wake word again.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use tracing::{debug, info};

/// Shared AEC gate flag (thread-safe, zero-cost reads).
#[derive(Clone)]
pub struct AecGate {
    /// `true` while TTS is playing — mic samples should be dropped.
    muted: Arc<AtomicBool>,
    /// Instant when TTS last finished — used for re-arm delay.
    last_tts_end: Arc<std::sync::Mutex<Option<Instant>>>,
    /// Milliseconds to delay before re-enabling mic after TTS stops.
    rearm_delay_ms: u64,
}

impl AecGate {
    /// Create a new AEC gate (mic live by default).
    pub fn new(rearm_delay_ms: u64) -> Self {
        Self {
            muted: Arc::new(AtomicBool::new(false)),
            last_tts_end: Arc::new(std::sync::Mutex::new(None)),
            rearm_delay_ms,
        }
    }

    /// Activate AEC: mute the microphone because TTS is starting.
    pub fn activate(&self) {
        self.muted.store(true, Ordering::Release);
        debug!("aec.gate_activated — mic muted for TTS playback");
    }

    /// Deactivate AEC: TTS has finished.
    /// Mic remains muted for `rearm_delay_ms` to absorb trailing echo.
    pub fn deactivate(&self) {
        {
            let mut end = self.last_tts_end.lock().unwrap();
            *end = Some(Instant::now());
        }
        // Don't immediately clear — re-arm timer will clear it
        let muted = Arc::clone(&self.muted);
        let delay = self.rearm_delay_ms;
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(delay));
            muted.store(false, Ordering::Release);
            info!("aec.gate_deactivated — mic re-armed after {}ms", delay);
        });
    }

    /// Query: should the current audio frame be silenced?
    /// Called from the audio capture hot path — must be very fast.
    #[inline(always)]
    pub fn is_muted(&self) -> bool {
        self.muted.load(Ordering::Acquire)
    }

    /// Barge-in detection: did the user start speaking during TTS?
    /// Returns true if VAD detected speech while gate was active.
    /// This is signalled externally (from VAD) via `signal_barge_in()`.
    pub fn signal_barge_in(&self) -> bool {
        // If mic is still muted and user spoke, we deactivate immediately
        if self.muted.load(Ordering::Acquire) {
            self.muted.store(false, Ordering::Release);
            info!("aec.barge_in_detected — TTS interrupted, mic re-armed immediately");
            true
        } else {
            false
        }
    }
}

impl Default for AecGate {
    fn default() -> Self {
        Self::new(200) // 200ms default re-arm delay
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;

    #[test]
    fn test_aec_gate_activate_deactivate() {
        let gate = AecGate::new(50); // short delay for tests
        assert!(!gate.is_muted(), "should start un-muted");

        gate.activate();
        assert!(gate.is_muted(), "should be muted after activate");

        gate.deactivate();
        // Still muted immediately (re-arm in background)
        assert!(gate.is_muted(), "should still be muted during re-arm delay");

        thread::sleep(Duration::from_millis(100)); // wait for re-arm
        assert!(!gate.is_muted(), "should be un-muted after re-arm delay");
    }

    #[test]
    fn test_barge_in_clears_immediately() {
        let gate = AecGate::new(500);
        gate.activate();
        assert!(gate.is_muted());

        let interrupted = gate.signal_barge_in();
        assert!(interrupted, "barge-in should return true when was muted");
        assert!(!gate.is_muted(), "barge-in should clear mute immediately");
    }

    #[test]
    fn test_no_barge_in_when_not_muted() {
        let gate = AecGate::new(200);
        // Gate not active
        let interrupted = gate.signal_barge_in();
        assert!(!interrupted, "barge-in should return false when mic was already live");
    }
}
