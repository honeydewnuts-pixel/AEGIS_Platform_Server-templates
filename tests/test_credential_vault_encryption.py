"""
Encryption roundtrip test for CredentialVaultService - the AES-GCM
encrypt/decrypt logic is pure and testable without a real DB connection
(DB calls are separately mocked/skipped here; this focuses on the crypto).
"""

import base64
import os

import pytest


@pytest.fixture
def vault_service():
    # AEGIS_MASTER_KEY must be set before the service can even construct.
    key = base64.b64encode(os.urandom(32)).decode()
    os.environ["AEGIS_MASTER_KEY"] = key
    from app.services.credential_vault_service import CredentialVaultService
    return CredentialVaultService()


class TestCredentialEncryption:

    def test_encrypt_decrypt_roundtrip(self, vault_service):
        plaintext = "MyBrokerPassword123!"
        encrypted = vault_service._encrypt(plaintext)
        decrypted = vault_service._decrypt(encrypted["nonce"], encrypted["ciphertext"])
        assert decrypted == plaintext

    def test_encrypting_same_plaintext_twice_gives_different_ciphertext(self, vault_service):
        # Nonce must be fresh each time - if it isn't, that's a serious
        # AES-GCM misuse (nonce reuse breaks the whole scheme).
        a = vault_service._encrypt("same-password")
        b = vault_service._encrypt("same-password")
        assert a["nonce"] != b["nonce"]
        assert a["ciphertext"] != b["ciphertext"]

    def test_missing_master_key_raises(self, monkeypatch):
        monkeypatch.delenv("AEGIS_MASTER_KEY", raising=False)
        from app.services.credential_vault_service import CredentialVaultService
        with pytest.raises(RuntimeError, match="AEGIS_MASTER_KEY"):
            CredentialVaultService()

    def test_wrong_length_master_key_raises(self, monkeypatch):
        monkeypatch.setenv("AEGIS_MASTER_KEY", base64.b64encode(b"too-short").decode())
        from app.services.credential_vault_service import CredentialVaultService
        with pytest.raises(RuntimeError, match="32 bytes"):
            CredentialVaultService()
