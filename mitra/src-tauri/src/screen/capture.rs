//! capture.rs — On-demand shutter-gated screen capture engine
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tracing::{info, warn};

use super::hwnd::WindowManager;
use super::privacy::PrivacyScanner;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapturePayload {
    pub window_hwnd: usize,
    pub title: String,
    pub width: u32,
    pub height: u32,
    pub dpi_scale: f32,
    pub format: String,
    pub quality: u8,
    pub privacy_redactions: usize,
    pub timestamp: i64,
    pub data_bytes: Vec<u8>,
}

#[derive(Debug, thiserror::Error)]
pub enum CaptureError {
    #[error("Screen capture rejected: Passive idle state active. Capture is strictly on-demand.")]
    PassiveIdleBlocked,
    #[error("No focused window found for capture")]
    NoFocusedWindow,
    #[error("Capture failed: {0}")]
    CaptureFailed(String),
}

pub struct ScreenCaptureEngine {
    window_manager: Arc<WindowManager>,
    shutter_active: Arc<AtomicBool>,
}

impl ScreenCaptureEngine {
    pub fn new(window_manager: Arc<WindowManager>) -> Self {
        Self {
            window_manager,
            shutter_active: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Set whether on-demand shutter is active (triggered by "look at my screen")
    pub fn set_on_demand_shutter(&self, active: bool) {
        self.shutter_active.store(active, Ordering::SeqCst);
        if active {
            info!("📸 Screen capture shutter OPENED (on-demand request)");
        } else {
            info!("🔒 Screen capture shutter CLOSED (idle protection)");
        }
    }

    pub fn is_shutter_active(&self) -> bool {
        self.shutter_active.load(Ordering::SeqCst)
    }

    /// Captures the focused window. STRICTLY BLOCKED if shutter is inactive.
    pub fn capture_focused_window(&self, mock_ocr_text: Option<&str>) -> Result<CapturePayload, CaptureError> {
        // Enforce privacy invariant: NO capture in passive idle state
        if !self.is_shutter_active() {
            warn!("🛑 Blocked passive screen capture attempt while shutter is closed");
            return Err(CaptureError::PassiveIdleBlocked);
        }

        let focused = self.window_manager.get_focused_window()
            .ok_or(CaptureError::NoFocusedWindow)?;

        let monitor = self.window_manager.get_monitor_for_window(focused)
            .cloned()
            .unwrap_or(super::hwnd::MonitorInfo {
                id: 1,
                name: "DEFAULT".to_string(),
                x: 0,
                y: 0,
                width: 1920,
                height: 1080,
                scale_factor: 1.0,
                is_primary: true,
            });

        let (_phys_x, _phys_y, phys_w, phys_h) = focused.physical_bounds(monitor.scale_factor);

        // Privacy scan on any accompanying OCR text
        let mut redaction_count = 0;
        if let Some(text) = mock_ocr_text {
            let scan = PrivacyScanner::mask_sensitive_text(text);
            redaction_count = scan.redacting_count;
        }

        // Generate WebP frame representation (quality 75)
        // 4 bytes per pixel dummy frame or compressed image
        let dummy_frame_size = (phys_w * phys_h).min(1024 * 1024) as usize;
        let mut frame_data = vec![0x89; dummy_frame_size]; // mock compressed data
        if frame_data.len() > 12 {
            // WebP RIFF header signature
            frame_data[0..4].copy_from_slice(b"RIFF");
            frame_data[8..12].copy_from_slice(b"WEBP");
        }

        let payload = CapturePayload {
            window_hwnd: focused.hwnd,
            title: focused.title.clone(),
            width: phys_w,
            height: phys_h,
            dpi_scale: monitor.scale_factor,
            format: "image/webp".to_string(),
            quality: 75,
            privacy_redactions: redaction_count,
            timestamp: chrono::Utc::now().timestamp_millis(),
            data_bytes: frame_data,
        };

        info!(
            "🖼️ Captured window HWND={} '{}' ({}x{} @ {:.0}% DPI, quality={})",
            focused.hwnd,
            focused.title,
            payload.width,
            payload.height,
            payload.dpi_scale * 100.0,
            payload.quality
        );

        Ok(payload)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_passive_idle_blocks_capture() {
        let win_mgr = Arc::new(WindowManager::new().with_mock_displays());
        let engine = ScreenCaptureEngine::new(win_mgr);

        // Initially shutter is closed (idle state)
        assert!(!engine.is_shutter_active());

        // Attempt capture -> must fail with PassiveIdleBlocked
        let err = engine.capture_focused_window(None).unwrap_err();
        match err {
            CaptureError::PassiveIdleBlocked => {}
            _ => panic!("Expected PassiveIdleBlocked error, got {:?}", err),
        }
    }

    #[test]
    fn test_on_demand_capture_succeeds_with_dpi_and_quality() {
        let win_mgr = Arc::new(WindowManager::new().with_mock_displays());
        let engine = ScreenCaptureEngine::new(win_mgr);

        // Open shutter (user said "look at my screen")
        engine.set_on_demand_shutter(true);
        assert!(engine.is_shutter_active());

        let payload = engine.capture_focused_window(Some("Payment card: 4532-1234-5678-9012")).unwrap();
        assert_eq!(payload.format, "image/webp");
        assert_eq!(payload.quality, 75);
        assert_eq!(payload.privacy_redactions, 1);
        assert_eq!(payload.window_hwnd, 1001); // Focused window HWND
        assert_eq!(&payload.data_bytes[0..4], b"RIFF");
        assert_eq!(&payload.data_bytes[8..12], b"WEBP");

        // Close shutter
        engine.set_on_demand_shutter(false);
        assert!(engine.capture_focused_window(None).is_err());
    }
}
