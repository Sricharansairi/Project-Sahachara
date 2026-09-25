//! hwnd.rs — Window enumeration, multi-monitor mapping, and DPI-aware coordinate normalization
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MonitorInfo {
    pub id: u32,
    pub name: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub scale_factor: f32, // e.g. 1.0, 1.25, 1.5, 2.0
    pub is_primary: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WindowMetadata {
    pub hwnd: usize,
    pub title: String,
    pub process_name: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub monitor_id: u32,
    pub is_focused: bool,
}

impl WindowMetadata {
    /// Calculate DPI-normalized dimensions given the monitor's scale factor.
    /// At 150% DPI (scale_factor = 1.5), physical pixels = logical pixels * 1.5.
    pub fn physical_bounds(&self, scale_factor: f32) -> (i32, i32, u32, u32) {
        let phys_x = (self.x as f32 * scale_factor).round() as i32;
        let phys_y = (self.y as f32 * scale_factor).round() as i32;
        let phys_w = (self.width as f32 * scale_factor).round() as u32;
        let phys_h = (self.height as f32 * scale_factor).round() as u32;
        (phys_x, phys_y, phys_w, phys_h)
    }

    /// Normalize captured physical pixels back to standard logical coordinates.
    pub fn logical_bounds(&self, scale_factor: f32) -> (i32, i32, u32, u32) {
        let log_x = (self.x as f32 / scale_factor).round() as i32;
        let log_y = (self.y as f32 / scale_factor).round() as i32;
        let log_w = (self.width as f32 / scale_factor).round() as u32;
        let log_h = (self.height as f32 / scale_factor).round() as u32;
        (log_x, log_y, log_w, log_h)
    }
}

pub struct WindowManager {
    monitors: Vec<MonitorInfo>,
    windows: Vec<WindowMetadata>,
}

impl WindowManager {
    pub fn new() -> Self {
        Self {
            monitors: Vec::new(),
            windows: Vec::new(),
        }
    }

    /// Provide mock multi-monitor setup for deterministic testing
    pub fn with_mock_displays(mut self) -> Self {
        self.monitors = vec![
            MonitorInfo {
                id: 1,
                name: r"\\.\DISPLAY1".to_string(),
                x: 0,
                y: 0,
                width: 1920,
                height: 1080,
                scale_factor: 1.0,
                is_primary: true,
            },
            MonitorInfo {
                id: 2,
                name: r"\\.\DISPLAY2".to_string(),
                x: 1920,
                y: 0,
                width: 2560,
                height: 1440,
                scale_factor: 1.5,
                is_primary: false,
            },
        ];

        self.windows = vec![
            WindowMetadata {
                hwnd: 1001,
                title: "Visual Studio Code - Project Sahachara".to_string(),
                process_name: "Code.exe".to_string(),
                x: 100,
                y: 100,
                width: 1200,
                height: 800,
                monitor_id: 1,
                is_focused: true,
            },
            WindowMetadata {
                hwnd: 2002,
                title: "Microsoft Edge - Research Paper".to_string(),
                process_name: "msedge.exe".to_string(),
                x: 2020,
                y: 50,
                width: 1920,
                height: 1080,
                monitor_id: 2,
                is_focused: false,
            },
        ];

        self
    }

    pub fn get_monitors(&self) -> &[MonitorInfo] {
        &self.monitors
    }

    pub fn get_windows(&self) -> &[WindowMetadata] {
        &self.windows
    }

    pub fn get_focused_window(&self) -> Option<&WindowMetadata> {
        self.windows.iter().find(|w| w.is_focused)
    }

    pub fn get_window_by_hwnd(&self, hwnd: usize) -> Option<&WindowMetadata> {
        self.windows.iter().find(|w| w.hwnd == hwnd)
    }

    pub fn get_monitor_for_window(&self, window: &WindowMetadata) -> Option<&MonitorInfo> {
        self.monitors.iter().find(|m| m.id == window.monitor_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dpi_aware_normalization() {
        let win = WindowMetadata {
            hwnd: 5050,
            title: "Test App".to_string(),
            process_name: "app.exe".to_string(),
            x: 200,
            y: 100,
            width: 1000,
            height: 600,
            monitor_id: 1,
            is_focused: true,
        };

        // 150% DPI scaling (scale_factor = 1.5)
        let (phys_x, phys_y, phys_w, phys_h) = win.physical_bounds(1.5);
        assert_eq!(phys_x, 300);
        assert_eq!(phys_y, 150);
        assert_eq!(phys_w, 1500);
        assert_eq!(phys_h, 900);
    }

    #[test]
    fn test_multi_monitor_window_selection() {
        let mgr = WindowManager::new().with_mock_displays();
        assert_eq!(mgr.get_monitors().len(), 2);

        // Secondary monitor window
        let edge_win = mgr.get_window_by_hwnd(2002).expect("Edge window should exist");
        assert_eq!(edge_win.monitor_id, 2);
        
        let mon2 = mgr.get_monitor_for_window(edge_win).expect("Monitor 2 should be found");
        assert_eq!(mon2.id, 2);
        assert_eq!(mon2.scale_factor, 1.5);
        assert!(!mon2.is_primary);
    }
}
