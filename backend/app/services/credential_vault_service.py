"""
====================================================================
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : credential_vault_service.py

Enterprise Broker Credential Vault - AES-256-GCM encryption for
trading_password/investor_password, backed by Postgres via SQLAlchemy
(async). Previously SQLite-file-backed; moved to Postgres so this
works correctly across multiple API instances/replicas, not just one.
====================================================================
"""

from __future__ import annotations

import base64
import os
import secrets
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import configure_logging
from app.db.base import async_session_factory
from app.db.models import Credential


class CredentialVaultService:

    def __init__(self) -> None:
        self.logger = configure_logging(__name__)

        key = os.getenv("AEGIS_MASTER_KEY")
        if key is None:
            raise RuntimeError(
                "AEGIS_MASTER_KEY environment variable is missing. "
                "Generate one with security.generate_secret_key() "
                "(base64, must decode to 32 bytes)."
            )

        self._master_key = base64.b64decode(key)
        if len(self._master_key) != 32:
            raise RuntimeError("AEGIS_MASTER_KEY must decode to exactly 32 bytes.")

        self._aes = AESGCM(self._master_key)

    # ---------------------------------------------------------
    # Encryption helpers
    # ---------------------------------------------------------

    def _encrypt(self, plaintext: str) -> dict[str, str]:
        nonce = secrets.token_bytes(12)
        ciphertext = self._aes.encrypt(nonce, plaintext.encode("utf-8"), None)
        return {
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }

    def _decrypt(self, nonce: str, ciphertext: str) -> str:
        plain = self._aes.decrypt(base64.b64decode(nonce), base64.b64decode(ciphertext), None)
        return plain.decode()

    # ---------------------------------------------------------

    async def save_credentials(
        self,
        *,
        credential_id: str,
        broker_name: str,
        server: str,
        account_id: str,
        trading_password: str,
        investor_password: str | None,
        execution_enabled: bool,
    ) -> None:
        trading_enc = self._encrypt(trading_password)
        investor_enc = self._encrypt(investor_password) if investor_password else None
        now = datetime.now(timezone.utc)

        async with async_session_factory() as session:
            stmt = pg_insert(Credential).values(
                credential_id=credential_id,
                broker_name=broker_name,
                server=server,
                account_id=account_id,
                trading_nonce=trading_enc["nonce"],
                trading_ciphertext=trading_enc["ciphertext"],
                investor_nonce=investor_enc["nonce"] if investor_enc else None,
                investor_ciphertext=investor_enc["ciphertext"] if investor_enc else None,
                execution_enabled=execution_enabled,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["credential_id"],
                set_={
                    "broker_name": broker_name,
                    "server": server,
                    "account_id": account_id,
                    "trading_nonce": trading_enc["nonce"],
                    "trading_ciphertext": trading_enc["ciphertext"],
                    "investor_nonce": investor_enc["nonce"] if investor_enc else None,
                    "investor_ciphertext": investor_enc["ciphertext"] if investor_enc else None,
                    "execution_enabled": execution_enabled,
                    "updated_at": now,
                },
            )
            await session.execute(stmt)
            await session.commit()

        self.logger.info("Credential stored for account %s", account_id)

    # ---------------------------------------------------------

    def _row_to_dict(self, row: Credential, include_secrets: bool) -> dict[str, Any]:
        base = {
            "broker_name": row.broker_name,
            "server": row.server,
            "account_id": row.account_id,
            "execution_enabled": row.execution_enabled,
        }
        if not include_secrets or not base["execution_enabled"]:
            return base

        base["trading_password"] = self._decrypt(row.trading_nonce, row.trading_ciphertext)
        if row.investor_nonce:
            base["investor_password"] = self._decrypt(row.investor_nonce, row.investor_ciphertext)
        return base

    async def get_credentials(self, credential_id: str) -> dict[str, Any]:
        async with async_session_factory() as session:
            row = await session.get(Credential, credential_id)

        if row is None:
            raise KeyError("Credential not found.")

        self.logger.info("Credential accessed: %s", credential_id)
        return self._row_to_dict(row, include_secrets=True)

    async def get_credentials_by_account(self, account_id: str) -> dict[str, Any] | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Credential).where(Credential.account_id == account_id).limit(1)
            )
            row = result.scalar_one_or_none()

        if row is None:
            return None

        self.logger.info("Credential accessed by account_id: %s", account_id)
        return self._row_to_dict(row, include_secrets=True)

    # ---------------------------------------------------------

    async def rotate_credentials(self, credential_id: str, new_password: str) -> None:
        encrypted = self._encrypt(new_password)
        now = datetime.now(timezone.utc)

        async with async_session_factory() as session:
            row = await session.get(Credential, credential_id)
            if row is None:
                raise KeyError("Credential not found.")
            row.trading_nonce = encrypted["nonce"]
            row.trading_ciphertext = encrypted["ciphertext"]
            row.updated_at = now
            await session.commit()

        self.logger.info("Credential rotated: %s", credential_id)

    # ---------------------------------------------------------

    async def delete_credentials(self, credential_id: str) -> None:
        async with async_session_factory() as session:
            row = await session.get(Credential, credential_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

        self.logger.info("Credential deleted: %s", credential_id)
