import secrets

import pytest

import config
from app import validate_startup_security
from scripts.generate_secrets import generate_all_secrets
from services.security.auth_service import hash_password, verify_password_hash


def test_production_startup_security_rejects_empty_secret(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)
    monkeypatch.setattr(config, 'SECRET_KEY', '')
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', hash_password('secure_password_2026'))
    monkeypatch.setattr(config, 'GRPC_API_KEY', 'valid_grpc_api_key_12345')

    with pytest.raises(SystemExit) as exc:
        validate_startup_security()
    assert exc.value.code == 1


def test_production_startup_security_rejects_short_secret(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)
    monkeypatch.setattr(config, 'SECRET_KEY', 'short_secret_key_123')
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', hash_password('secure_password_2026'))
    monkeypatch.setattr(config, 'GRPC_API_KEY', 'valid_grpc_api_key_12345')

    with pytest.raises(SystemExit) as exc:
        validate_startup_security()
    assert exc.value.code == 1


def test_production_startup_security_rejects_insecure_default_secret(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)
    monkeypatch.setattr(config, 'SECRET_KEY', 'kvit-secret-key-production-change-in-prod')
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', hash_password('secure_password_2026'))
    monkeypatch.setattr(config, 'GRPC_API_KEY', 'valid_grpc_api_key_12345')

    with pytest.raises(SystemExit) as exc:
        validate_startup_security()
    assert exc.value.code == 1


def test_production_startup_security_rejects_default_admin_hash(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)
    monkeypatch.setattr(config, 'SECRET_KEY', secrets.token_hex(32))
    # Old default hash for admin123
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', 'pbkdf2_sha256$600000$c39a69e0d844f92023de12de1d2f2c54$63ad158940b48e73648c4d9d2d88099f7e0897529040f53c88ffcae75935daa5')
    monkeypatch.setattr(config, 'GRPC_API_KEY', 'valid_grpc_api_key_12345')

    with pytest.raises(SystemExit) as exc:
        validate_startup_security()
    assert exc.value.code == 1


def test_production_startup_security_rejects_invalid_hash_format(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)
    monkeypatch.setattr(config, 'SECRET_KEY', secrets.token_hex(32))
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', 'plain_text_md5_hash_invalid')
    monkeypatch.setattr(config, 'GRPC_API_KEY', 'valid_grpc_api_key_12345')

    with pytest.raises(SystemExit) as exc:
        validate_startup_security()
    assert exc.value.code == 1


def test_production_startup_security_passes_with_valid_secrets(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', True)
    monkeypatch.setattr(config, 'SECRET_KEY', secrets.token_hex(32))
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', hash_password('StrongPassword2026!#$'))
    monkeypatch.setattr(config, 'GRPC_API_KEY', secrets.token_hex(16))

    # Should not raise SystemExit
    validate_startup_security()


def test_development_startup_security_auto_fallbacks(monkeypatch):
    monkeypatch.setattr(config, 'IS_PRODUCTION', False)
    monkeypatch.setattr(config, 'SECRET_KEY', '')
    monkeypatch.setattr(config, 'ADMIN_PASSWORD_HASH', '')
    monkeypatch.setattr(config, 'GRPC_API_KEY', '')

    validate_startup_security()
    assert len(config.SECRET_KEY) >= 32
    assert config.ADMIN_PASSWORD_HASH.startswith('pbkdf2_sha256$')
    assert bool(config.GRPC_API_KEY)


def test_generate_secrets_utility():
    secret_key, grpc_api_key, raw_pass, admin_hash = generate_all_secrets("CustomAdminPass_2026!")
    assert len(secret_key) == 64
    assert len(grpc_api_key) == 64
    assert raw_pass == "CustomAdminPass_2026!"
    assert admin_hash.startswith("pbkdf2_sha256$600000$")
    assert verify_password_hash("CustomAdminPass_2026!", admin_hash) is True
    assert verify_password_hash("WrongPass", admin_hash) is False
