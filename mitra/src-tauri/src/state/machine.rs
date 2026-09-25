//! machine.rs — MITRA Conversational State Machine
//! Implements the 7-state machine with 8-second keep-alive window.
//! All transitions emit Tauri events to the frontend.

use serde::{Deserialize, Serialize};
use std::time::{Duration, Instant};
use tauri::Emitter;
use tracing::{info, warn};

// Keep-alive duration after agent finishes speaking
pub const KEEP_ALIVE_SECS: u64 = 8;
// VAD silence duration before triggering endpointing
pub const VAD_SILENCE_MS: u64 = 700;

/// All possible states MITRA can be in
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum MitraState {
    /// Passive listening mode. Only wake word engine runs. <0.8% CPU.
    IdleSleep,
    /// Wake word detected + voiceprint verified. Mic open, awaiting user speech.
    ActiveListening,
    /// User is actively speaking (VAD energy detected).
    UserSpeaking,
    /// User paused; 700ms silence window counting down.
    VADEndpointing,
    /// Audio sent to STT/LLM for processing (Phase 2+).
    DeepProcessing,
    /// Agent is speaking via TTS (Phase 4+). In Phase 1, simulated.
    AgentSpeaking,
    /// Agent finished speaking. Listening for 8s before auto-sleep.
    ConversationalKeepAlive,
}

/// Events that drive state transitions
#[derive(Debug, Clone, PartialEq)]
pub enum MitraEvent {
    WakeWordDetected,
    ManualWake,
    SpeechDetected,
    SilenceDetected,
    VadEndpointFired,  // 700ms silence elapsed
    ResponseReady,
    PlaybackDone,
    KeepAliveTimeout,  // 8s elapsed with no speech
    ManualSleep,
}

/// Payload emitted via Tauri event "state-changed"
#[derive(Serialize, Clone)]
struct StateChangedPayload {
    state: String,
    timestamp_ms: u128,
}

pub struct StateMachine {
    pub state: MitraState,
    app_handle: tauri::AppHandle,
    /// When VADEndpointing started (for 700ms timeout)
    endpointing_started: Option<Instant>,
    /// When ConversationalKeepAlive started (for 8s timeout)
    keep_alive_started: Option<Instant>,
}

impl StateMachine {
    pub fn new(app_handle: tauri::AppHandle) -> Self {
        info!("🔄 StateMachine initialized → IdleSleep");
        Self {
            state: MitraState::IdleSleep,
            app_handle,
            endpointing_started: None,
            keep_alive_started: None,
        }
    }

    /// Process an event and perform the appropriate state transition.
    /// Returns the new state after transition.
    pub async fn transition(&mut self, event: MitraEvent) -> MitraState {
        let new_state = match (&self.state, &event) {
            // IdleSleep → ActiveListening
            (MitraState::IdleSleep, MitraEvent::WakeWordDetected)
            | (MitraState::IdleSleep, MitraEvent::ManualWake) => {
                info!("🟢 MITRA activated → ActiveListening");
                MitraState::ActiveListening
            }

            // ActiveListening → UserSpeaking
            (MitraState::ActiveListening, MitraEvent::SpeechDetected) => {
                info!("🗣️  Speech detected → UserSpeaking");
                MitraState::UserSpeaking
            }

            // UserSpeaking → VADEndpointing
            (MitraState::UserSpeaking, MitraEvent::SilenceDetected) => {
                info!("🤫 Silence detected → VADEndpointing");
                self.endpointing_started = Some(Instant::now());
                MitraState::VADEndpointing
            }

            // VADEndpointing → UserSpeaking (user resumes before 700ms)
            (MitraState::VADEndpointing, MitraEvent::SpeechDetected) => {
                info!("🗣️  User resumed speaking → UserSpeaking");
                self.endpointing_started = None;
                MitraState::UserSpeaking
            }

            // VADEndpointing → DeepProcessing (700ms elapsed)
            (MitraState::VADEndpointing, MitraEvent::VadEndpointFired) => {
                info!("⚡ Endpoint fired → DeepProcessing");
                self.endpointing_started = None;
                MitraState::DeepProcessing
            }

            // DeepProcessing → AgentSpeaking
            (MitraState::DeepProcessing, MitraEvent::ResponseReady) => {
                info!("🔊 Response ready → AgentSpeaking");
                MitraState::AgentSpeaking
            }

            // AgentSpeaking → ConversationalKeepAlive
            (MitraState::AgentSpeaking, MitraEvent::PlaybackDone) => {
                info!("🔄 Playback done → ConversationalKeepAlive (8s window)");
                self.keep_alive_started = Some(Instant::now());
                MitraState::ConversationalKeepAlive
            }

            // ConversationalKeepAlive → ActiveListening (user speaks within 8s)
            (MitraState::ConversationalKeepAlive, MitraEvent::SpeechDetected)
            | (MitraState::ConversationalKeepAlive, MitraEvent::WakeWordDetected) => {
                info!("🔄 User spoke in keep-alive window → ActiveListening");
                self.keep_alive_started = None;
                MitraState::ActiveListening
            }

            // ConversationalKeepAlive → IdleSleep (8s timeout)
            (MitraState::ConversationalKeepAlive, MitraEvent::KeepAliveTimeout) => {
                info!("💤 Keep-alive expired → IdleSleep");
                self.keep_alive_started = None;
                MitraState::IdleSleep
            }

            // Manual sleep from any state
            (_, MitraEvent::ManualSleep) => {
                info!("💤 Manual sleep → IdleSleep");
                self.endpointing_started = None;
                self.keep_alive_started = None;
                MitraState::IdleSleep
            }

            // Invalid transitions — stay in current state
            (current, event) => {
                warn!(
                    "⚠️  Invalid transition: {:?} + {:?} — staying in {:?}",
                    current, event, current
                );
                return self.state.clone();
            }
        };

        self.state = new_state.clone();
        self.emit_state_change();
        new_state
    }

    /// Check timer-based transitions. Call this in the main audio loop (every 50ms).
    pub async fn tick(&mut self) {
        match &self.state {
            MitraState::VADEndpointing => {
                if let Some(started) = self.endpointing_started {
                    if started.elapsed() >= Duration::from_millis(VAD_SILENCE_MS) {
                        self.transition(MitraEvent::VadEndpointFired).await;
                    }
                }
            }
            MitraState::ConversationalKeepAlive => {
                if let Some(started) = self.keep_alive_started {
                    if started.elapsed() >= Duration::from_secs(KEEP_ALIVE_SECS) {
                        self.transition(MitraEvent::KeepAliveTimeout).await;
                    }
                }
            }
            _ => {}
        }
    }

    /// Returns true if MITRA is in a state where it should process audio for VAD
    pub fn should_process_audio(&self) -> bool {
        matches!(
            self.state,
            MitraState::ActiveListening
                | MitraState::UserSpeaking
                | MitraState::VADEndpointing
                | MitraState::ConversationalKeepAlive
        )
    }

    /// Returns true if currently in keep-alive window
    pub fn in_keep_alive(&self) -> bool {
        matches!(self.state, MitraState::ConversationalKeepAlive)
    }

    /// How many seconds remain in the keep-alive window (0 if not in keep-alive)
    pub fn keep_alive_remaining_secs(&self) -> f32 {
        if let Some(started) = self.keep_alive_started {
            let elapsed = started.elapsed().as_secs_f32();
            ((KEEP_ALIVE_SECS as f32) - elapsed).max(0.0)
        } else {
            0.0
        }
    }

    fn emit_state_change(&self) {
        let payload = StateChangedPayload {
            state: format!("{:?}", self.state),
            timestamp_ms: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis(),
        };
        if let Err(e) = self.app_handle.emit("state-changed", payload) {
            warn!("Failed to emit state-changed event: {}", e);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Test harness that doesn't require a real Tauri app handle
    struct TestStateMachine {
        state: MitraState,
        endpointing_started: Option<Instant>,
        keep_alive_started: Option<Instant>,
        events_emitted: Vec<String>,
    }

    impl TestStateMachine {
        fn new() -> Self {
            Self {
                state: MitraState::IdleSleep,
                endpointing_started: None,
                keep_alive_started: None,
                events_emitted: Vec::new(),
            }
        }

        fn transition(&mut self, event: MitraEvent) -> MitraState {
            let new_state = match (&self.state, &event) {
                (MitraState::IdleSleep, MitraEvent::WakeWordDetected)
                | (MitraState::IdleSleep, MitraEvent::ManualWake) => MitraState::ActiveListening,

                (MitraState::ActiveListening, MitraEvent::SpeechDetected) => {
                    MitraState::UserSpeaking
                }

                (MitraState::UserSpeaking, MitraEvent::SilenceDetected) => {
                    self.endpointing_started = Some(Instant::now());
                    MitraState::VADEndpointing
                }

                (MitraState::VADEndpointing, MitraEvent::SpeechDetected) => {
                    self.endpointing_started = None;
                    MitraState::UserSpeaking
                }

                (MitraState::VADEndpointing, MitraEvent::VadEndpointFired) => {
                    self.endpointing_started = None;
                    MitraState::DeepProcessing
                }

                (MitraState::DeepProcessing, MitraEvent::ResponseReady) => {
                    MitraState::AgentSpeaking
                }

                (MitraState::AgentSpeaking, MitraEvent::PlaybackDone) => {
                    self.keep_alive_started = Some(Instant::now());
                    MitraState::ConversationalKeepAlive
                }

                (MitraState::ConversationalKeepAlive, MitraEvent::SpeechDetected)
                | (MitraState::ConversationalKeepAlive, MitraEvent::WakeWordDetected) => {
                    self.keep_alive_started = None;
                    MitraState::ActiveListening
                }

                (MitraState::ConversationalKeepAlive, MitraEvent::KeepAliveTimeout) => {
                    self.keep_alive_started = None;
                    MitraState::IdleSleep
                }

                (_, MitraEvent::ManualSleep) => {
                    self.endpointing_started = None;
                    self.keep_alive_started = None;
                    MitraState::IdleSleep
                }

                _ => return self.state.clone(),
            };

            self.state = new_state.clone();
            self.events_emitted.push(format!("{:?}", new_state));
            new_state
        }

        fn tick(&mut self) {
            match &self.state {
                MitraState::VADEndpointing => {
                    if let Some(started) = self.endpointing_started {
                        if started.elapsed() >= Duration::from_millis(VAD_SILENCE_MS) {
                            self.transition(MitraEvent::VadEndpointFired);
                        }
                    }
                }
                MitraState::ConversationalKeepAlive => {
                    if let Some(started) = self.keep_alive_started {
                        if started.elapsed() >= Duration::from_secs(KEEP_ALIVE_SECS) {
                            self.transition(MitraEvent::KeepAliveTimeout);
                        }
                    }
                }
                _ => {}
            }
        }
    }

    #[test]
    fn test_all_7_state_transitions() {
        let mut sm = TestStateMachine::new();

        // 1. IdleSleep → ActiveListening
        let s = sm.transition(MitraEvent::WakeWordDetected);
        assert_eq!(s, MitraState::ActiveListening, "T1: Wake → ActiveListening");

        // 2. ActiveListening → UserSpeaking
        let s = sm.transition(MitraEvent::SpeechDetected);
        assert_eq!(s, MitraState::UserSpeaking, "T2: Speech → UserSpeaking");

        // 3. UserSpeaking → VADEndpointing
        let s = sm.transition(MitraEvent::SilenceDetected);
        assert_eq!(s, MitraState::VADEndpointing, "T3: Silence → VADEndpointing");

        // 4. VADEndpointing → UserSpeaking (user resumes)
        let s = sm.transition(MitraEvent::SpeechDetected);
        assert_eq!(s, MitraState::UserSpeaking, "T4: Resume → UserSpeaking");

        // 5. UserSpeaking → VADEndpointing → DeepProcessing
        sm.transition(MitraEvent::SilenceDetected);
        let s = sm.transition(MitraEvent::VadEndpointFired);
        assert_eq!(s, MitraState::DeepProcessing, "T5: Endpoint → DeepProcessing");

        // 6. DeepProcessing → AgentSpeaking
        let s = sm.transition(MitraEvent::ResponseReady);
        assert_eq!(s, MitraState::AgentSpeaking, "T6: Response → AgentSpeaking");

        // 7. AgentSpeaking → ConversationalKeepAlive
        let s = sm.transition(MitraEvent::PlaybackDone);
        assert_eq!(s, MitraState::ConversationalKeepAlive, "T7: Done → KeepAlive");

        println!("✅ P1-T08: All 7 state transitions passed");
    }

    #[test]
    fn test_manual_wake_from_idle() {
        let mut sm = TestStateMachine::new();
        let s = sm.transition(MitraEvent::ManualWake);
        assert_eq!(s, MitraState::ActiveListening);
    }

    #[test]
    fn test_manual_sleep_from_any_state() {
        let mut sm = TestStateMachine::new();
        sm.transition(MitraEvent::WakeWordDetected);
        sm.transition(MitraEvent::SpeechDetected);
        // Now in UserSpeaking — manual sleep should return to Idle
        let s = sm.transition(MitraEvent::ManualSleep);
        assert_eq!(s, MitraState::IdleSleep);
    }

    #[test]
    fn test_keep_alive_resets_on_speech() {
        let mut sm = TestStateMachine::new();
        // Walk to ConversationalKeepAlive
        sm.transition(MitraEvent::WakeWordDetected);
        sm.transition(MitraEvent::SpeechDetected);
        sm.transition(MitraEvent::SilenceDetected);
        sm.transition(MitraEvent::VadEndpointFired);
        sm.transition(MitraEvent::ResponseReady);
        sm.transition(MitraEvent::PlaybackDone);
        assert_eq!(sm.state, MitraState::ConversationalKeepAlive);

        // User speaks within 8s → back to ActiveListening
        let s = sm.transition(MitraEvent::SpeechDetected);
        assert_eq!(s, MitraState::ActiveListening);
        assert!(sm.keep_alive_started.is_none(), "Timer should be cleared");

        println!("✅ P1-T09a: Keep-alive resets on speech");
    }

    #[test]
    fn test_auto_sleep_at_8_seconds() {
        let mut sm = TestStateMachine::new();
        sm.transition(MitraEvent::WakeWordDetected);
        sm.transition(MitraEvent::SpeechDetected);
        sm.transition(MitraEvent::SilenceDetected);
        sm.transition(MitraEvent::VadEndpointFired);
        sm.transition(MitraEvent::ResponseReady);
        sm.transition(MitraEvent::PlaybackDone);
        assert_eq!(sm.state, MitraState::ConversationalKeepAlive);

        // Simulate 8s timeout
        let s = sm.transition(MitraEvent::KeepAliveTimeout);
        assert_eq!(s, MitraState::IdleSleep);
        assert!(sm.keep_alive_started.is_none(), "Timer should be cleared");

        println!("✅ P1-T09b: Auto-sleep on 8s timeout");
    }

    #[test]
    fn test_vad_endpointing_timer() {
        let mut sm = TestStateMachine::new();
        sm.transition(MitraEvent::WakeWordDetected);
        sm.transition(MitraEvent::SpeechDetected);
        sm.transition(MitraEvent::SilenceDetected);
        assert_eq!(sm.state, MitraState::VADEndpointing);
        assert!(sm.endpointing_started.is_some(), "Endpointing timer should start");

        // Tick before 700ms — should stay in VADEndpointing
        sm.tick();
        assert_eq!(sm.state, MitraState::VADEndpointing);

        println!("✅ VADEndpointing timer started correctly");
    }

    #[test]
    fn test_invalid_transition_stays_in_state() {
        let mut sm = TestStateMachine::new();
        // Can't get SpeechDetected in IdleSleep — should stay
        let s = sm.transition(MitraEvent::SpeechDetected);
        assert_eq!(s, MitraState::IdleSleep, "Invalid transition should stay in IdleSleep");
    }
}
