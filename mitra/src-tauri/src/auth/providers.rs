//! providers.rs — OAuth 2.0 provider configurations (Google, Microsoft 365, Apple ID)
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OAuthProvider {
    Google,
    Microsoft365,
    Apple,
}

impl OAuthProvider {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Google => "google",
            Self::Microsoft365 => "microsoft365",
            Self::Apple => "apple",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderConfig {
    pub provider: OAuthProvider,
    pub auth_endpoint: String,
    pub token_endpoint: String,
    pub userinfo_endpoint: String,
    pub client_id: String,
    pub redirect_uri: String,
    pub scopes: Vec<String>,
}

impl ProviderConfig {
    pub fn for_provider(provider: OAuthProvider) -> Self {
        match provider {
            OAuthProvider::Google => Self {
                provider,
                auth_endpoint: "https://accounts.google.com/o/oauth2/v2/auth".to_string(),
                token_endpoint: "https://oauth2.googleapis.com/token".to_string(),
                userinfo_endpoint: "https://www.googleapis.com/oauth2/v3/userinfo".to_string(),
                client_id: "sahachara-desktop-client.apps.googleusercontent.com".to_string(),
                redirect_uri: "http://127.0.0.1:43821/auth/callback".to_string(),
                scopes: vec![
                    "openid".to_string(),
                    "email".to_string(),
                    "profile".to_string(),
                    "https://www.googleapis.com/auth/calendar.events.readonly".to_string(),
                    "https://www.googleapis.com/auth/gmail.readonly".to_string(),
                ],
            },
            OAuthProvider::Microsoft365 => Self {
                provider,
                auth_endpoint: "https://login.microsoftonline.com/common/oauth2/v2.0/authorize".to_string(),
                token_endpoint: "https://login.microsoftonline.com/common/oauth2/v2.0/token".to_string(),
                userinfo_endpoint: "https://graph.microsoftonline.com/v1.0/me".to_string(),
                client_id: "sahachara-ms365-client-id".to_string(),
                redirect_uri: "http://127.0.0.1:43821/auth/callback".to_string(),
                scopes: vec![
                    "openid".to_string(),
                    "offline_access".to_string(),
                    "User.Read".to_string(),
                    "Calendars.ReadWrite".to_string(),
                    "Mail.ReadWrite".to_string(),
                ],
            },
            OAuthProvider::Apple => Self {
                provider,
                auth_endpoint: "https://appleid.apple.com/auth/authorize".to_string(),
                token_endpoint: "https://appleid.apple.com/auth/token".to_string(),
                userinfo_endpoint: "https://appleid.apple.com/auth/userinfo".to_string(),
                client_id: "com.project-sahachara.mitra.auth".to_string(),
                redirect_uri: "sahachara://auth/callback".to_string(),
                scopes: vec!["name".to_string(), "email".to_string()],
            },
        }
    }

    /// Construct authorization URL with PKCE challenge, state, and scopes
    pub fn build_auth_url(&self, code_challenge: &str, state: &str) -> String {
        let scopes = self.scopes.join(" ");
        let encoded_scopes = urlencoding::encode(&scopes);
        let encoded_redirect = urlencoding::encode(&self.redirect_uri);
        
        format!(
            "{}?response_type=code&client_id={}&redirect_uri={}&scope={}&code_challenge={}&code_challenge_method=S256&state={}",
            self.auth_endpoint,
            self.client_id,
            encoded_redirect,
            encoded_scopes,
            code_challenge,
            state
        )
    }
}

// Simple minimal urlencoding helper if not using urlencoding crate
mod urlencoding {
    pub fn encode(s: &str) -> String {
        let mut result = String::with_capacity(s.len());
        for b in s.bytes() {
            match b {
                b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                    result.push(b as char);
                }
                _ => {
                    result.push_str(&format!("%{:02X}", b));
                }
            }
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_provider_configs() {
        let google = ProviderConfig::for_provider(OAuthProvider::Google);
        assert!(google.auth_endpoint.contains("accounts.google.com"));
        assert!(google.scopes.contains(&"openid".to_string()));

        let ms = ProviderConfig::for_provider(OAuthProvider::Microsoft365);
        assert!(ms.token_endpoint.contains("microsoftonline.com"));
        assert!(ms.scopes.contains(&"User.Read".to_string()));

        let apple = ProviderConfig::for_provider(OAuthProvider::Apple);
        assert!(apple.auth_endpoint.contains("appleid.apple.com"));
    }

    #[test]
    fn test_build_auth_url() {
        let google = ProviderConfig::for_provider(OAuthProvider::Google);
        let url = google.build_auth_url("mock_challenge_123", "mock_state_456");
        assert!(url.contains("code_challenge=mock_challenge_123"));
        assert!(url.contains("code_challenge_method=S256"));
        assert!(url.contains("state=mock_state_456"));
    }
}
