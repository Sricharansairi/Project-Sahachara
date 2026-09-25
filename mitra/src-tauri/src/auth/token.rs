//! token.rs — OAuth 2.0 TokenBundle definition and lifecycle helpers
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TokenBundle {
    pub access_token: String,
    pub refresh_token: Option<String>,
    pub token_type: String,
    pub expires_at: i64, // Unix timestamp in seconds
    pub scopes: Vec<String>,
}

impl TokenBundle {
    pub fn new(
        access_token: String,
        refresh_token: Option<String>,
        expires_in_secs: i64,
        token_type: Option<String>,
        scopes: Vec<String>,
    ) -> Self {
        let now = chrono::Utc::now().timestamp();
        Self {
            access_token,
            refresh_token,
            token_type: token_type.unwrap_or_else(|| "Bearer".to_string()),
            expires_at: now + expires_in_secs,
            scopes,
        }
    }

    /// Check if the token is completely expired
    pub fn is_expired(&self) -> bool {
        let now = chrono::Utc::now().timestamp();
        now >= self.expires_at
    }

    /// Silent refresh rule: token needs refresh if less than 5 minutes (300s) remain
    pub fn needs_refresh(&self) -> bool {
        let now = chrono::Utc::now().timestamp();
        now + 300 >= self.expires_at
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_token_expiration() {
        let now = chrono::Utc::now().timestamp();
        
        // Active token: 1 hour remaining
        let active = TokenBundle {
            access_token: "tok_123".to_string(),
            refresh_token: Some("ref_123".to_string()),
            token_type: "Bearer".to_string(),
            expires_at: now + 3600,
            scopes: vec!["read".to_string()],
        };
        assert!(!active.is_expired());
        assert!(!active.needs_refresh());

        // Token needing silent refresh: 4 minutes (240s) remaining
        let soon_expiring = TokenBundle {
            access_token: "tok_123".to_string(),
            refresh_token: Some("ref_123".to_string()),
            token_type: "Bearer".to_string(),
            expires_at: now + 240,
            scopes: vec!["read".to_string()],
        };
        assert!(!soon_expiring.is_expired());
        assert!(soon_expiring.needs_refresh());

        // Completely expired token: expired 10 seconds ago
        let expired = TokenBundle {
            access_token: "tok_123".to_string(),
            refresh_token: Some("ref_123".to_string()),
            token_type: "Bearer".to_string(),
            expires_at: now - 10,
            scopes: vec!["read".to_string()],
        };
        assert!(expired.is_expired());
        assert!(expired.needs_refresh());
    }
}
