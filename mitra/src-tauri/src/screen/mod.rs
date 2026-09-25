pub mod capture;
pub mod hwnd;
pub mod privacy;

pub use capture::{CaptureError, CapturePayload, ScreenCaptureEngine};
pub use hwnd::{MonitorInfo, WindowManager, WindowMetadata};
pub use privacy::{PrivacyScanner, PrivacyScanResult};
