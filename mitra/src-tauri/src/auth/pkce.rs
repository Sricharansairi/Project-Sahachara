//! pkce.rs — OAuth 2.0 PKCE (RFC 7636) code verifier and challenge generator
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use rand::Rng;
use sha2::{Digest, Sha256};

pub struct PkcePair {
    pub verifier: String,
    pub challenge: String,
    pub method: &'static str,
}

impl PkcePair {
    /// Generate a new PKCE code_verifier (random 43-128 chars) and S256 code_challenge.
    pub fn generate() -> Self {
        let verifier = generate_verifier(64);
        let challenge = compute_challenge(&verifier);
        Self {
            verifier,
            challenge,
            method: "S256",
        }
    }
}

/// Generates a high-entropy cryptographic random string using URL-safe characters.
pub fn generate_verifier(len: usize) -> String {
    let len = len.clamp(43, 128);
    const CHARSET: &[u8] = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~";
    let mut rng = rand::thread_rng();
    (0..len)
        .map(|_| {
            let idx = rng.gen_range(0..CHARSET.len());
            CHARSET[idx] as char
        })
        .collect()
}

/// Computes code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier))) without padding.
pub fn compute_challenge(verifier: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(verifier.as_bytes());
    let hash = hasher.finalize();
    URL_SAFE_NO_PAD.encode(hash)
}

/// Verifies whether a given verifier produces the expected challenge.
pub fn verify_challenge(verifier: &str, challenge: &str) -> bool {
    compute_challenge(verifier) == challenge
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pkce_generation() {
        let pair = PkcePair::generate();
        assert!(pair.verifier.len() >= 43 && pair.verifier.len() <= 128);
        assert_eq!(pair.method, "S256");
        assert!(!pair.challenge.is_empty());
        assert!(!pair.challenge.contains('='));
        assert!(!pair.challenge.contains('+'));
        assert!(!pair.challenge.contains('/'));
        assert!(verify_challenge(&pair.verifier, &pair.challenge));
    }

    #[test]
    fn test_rfc7636_test_vector() {
        // RFC 7636 test vector
        let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        let expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";
        let challenge = compute_challenge(verifier);
        assert_eq!(challenge, expected_challenge);
        assert!(verify_challenge(verifier, expected_challenge));
    }
}
