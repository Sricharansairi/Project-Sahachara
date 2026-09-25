//! privacy.rs — Privacy scanner and masking engine for screen OCR & image transmission
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::sync::OnceLock;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PrivacyScanResult {
    pub text: String,
    pub redacting_count: usize,
    pub detected_categories: Vec<String>,
}

static CC_REGEX: OnceLock<Regex> = OnceLock::new();
static SSN_REGEX: OnceLock<Regex> = OnceLock::new();
static SECRET_REGEX: OnceLock<Regex> = OnceLock::new();

fn get_cc_regex() -> &'static Regex {
    CC_REGEX.get_or_init(|| {
        // Matches standard 13-19 digit credit cards with hyphens, spaces, or contiguous
        Regex::new(r"\b(?:\d{4}[ -]?){3}\d{4}\b").expect("Valid CC regex")
    })
}

fn get_ssn_regex() -> &'static Regex {
    SSN_REGEX.get_or_init(|| {
        Regex::new(r"\b\d{3}-\d{2}-\d{4}\b").expect("Valid SSN regex")
    })
}

fn get_secret_regex() -> &'static Regex {
    SECRET_REGEX.get_or_init(|| {
        Regex::new(r"(?i)\b(password|passwd|secret|api_key|token)\s*[:=]\s*([^\s,;]+)").expect("Valid secret regex")
    })
}

pub struct PrivacyScanner;

impl PrivacyScanner {
    /// Mask sensitive strings within text content before transmitting to backend LLM
    pub fn mask_sensitive_text(input: &str) -> PrivacyScanResult {
        let mut text = input.to_string();
        let mut count = 0;
        let mut categories = Vec::new();

        // 1. Credit Cards
        let cc_re = get_cc_regex();
        if cc_re.is_match(&text) {
            categories.push("CREDIT_CARD".to_string());
            let masked = cc_re.replace_all(&text, |caps: &regex::Captures| {
                count += 1;
                let full = caps.get(0).unwrap().as_str();
                let last4 = &full[full.len().saturating_sub(4)..];
                format!("****-****-****-{}", last4)
            });
            text = masked.into_owned();
        }

        // 2. SSN
        let ssn_re = get_ssn_regex();
        if ssn_re.is_match(&text) {
            categories.push("SSN".to_string());
            let masked = ssn_re.replace_all(&text, |_caps: &regex::Captures| {
                count += 1;
                "***-**-****".to_string()
            });
            text = masked.into_owned();
        }

        // 3. Secrets
        let secret_re = get_secret_regex();
        if secret_re.is_match(&text) {
            categories.push("AUTH_SECRET".to_string());
            let masked = secret_re.replace_all(&text, |caps: &regex::Captures| {
                count += 1;
                let key = caps.get(1).unwrap().as_str();
                format!("{}: [MASKED]", key)
            });
            text = masked.into_owned();
        }

        PrivacyScanResult {
            text,
            redacting_count: count,
            detected_categories: categories,
        }
    }

    /// Redact a rectangular region in an RGBA image buffer (fill with solid black)
    pub fn redact_image_region(
        buffer: &mut [u8],
        stride_bytes: usize,
        x: u32,
        y: u32,
        w: u32,
        h: u32,
    ) {
        for row in y..(y + h) {
            let row_start = (row as usize) * stride_bytes;
            for col in x..(x + w) {
                let px = row_start + (col as usize) * 4;
                if px + 3 < buffer.len() {
                    buffer[px] = 0;     // R
                    buffer[px + 1] = 0; // G
                    buffer[px + 2] = 0; // B
                    buffer[px + 3] = 255; // A
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_credit_card_masking() {
        let input = "Payment details: Card 4532-1234-5678-9012 for user.";
        let res = PrivacyScanner::mask_sensitive_text(input);
        assert_eq!(res.redacting_count, 1);
        assert!(res.detected_categories.contains(&"CREDIT_CARD".to_string()));
        assert_eq!(res.text, "Payment details: Card ****-****-****-9012 for user.");
    }

    #[test]
    fn test_ssn_masking() {
        let input = "Employee SSN: 123-45-6789 verified.";
        let res = PrivacyScanner::mask_sensitive_text(input);
        assert_eq!(res.redacting_count, 1);
        assert_eq!(res.text, "Employee SSN: ***-**-**** verified.");
    }

    #[test]
    fn test_secret_masking() {
        let input = "Config has api_key: sk-proj-1234567890abcdef and password: supersecretpassword";
        let res = PrivacyScanner::mask_sensitive_text(input);
        assert!(res.detected_categories.contains(&"AUTH_SECRET".to_string()));
        assert!(!res.text.contains("supersecretpassword"));
        assert!(!res.text.contains("sk-proj-1234567890abcdef"));
        assert!(res.text.contains("api_key: [MASKED]"));
    }
}
