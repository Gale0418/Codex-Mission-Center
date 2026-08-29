use mission_center_publish::{ScopeError, scope_digest_checked, validate_scope};

#[test]
fn scope_rejects_escape_absolute_url_and_duplicates() {
    assert!(matches!(
        validate_scope(&["../secret"]),
        Err(ScopeError::InvalidLocator(_))
    ));
    assert!(matches!(
        validate_scope(&["https://example.invalid/a"]),
        Err(ScopeError::InvalidLocator(_))
    ));
    assert!(matches!(
        validate_scope(&["a.md", "a.md"]),
        Err(ScopeError::Duplicate(_))
    ));
    assert!(scope_digest_checked(&[("a.md", b"a")]).is_ok());
}
