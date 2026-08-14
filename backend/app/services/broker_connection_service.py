"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : broker_connection_service.py

Purpose :
Broker Connection Manager.

Current Stage:
CP-006 – File 4

Overview
--------
This service sits between the Credential Vault and all broker
implementations.

The service never communicates directly with MT5, MT4, cTrader,
Binance or any other SDK.

Instead it depends only on the BrokerAdapter interface.

Why?

This is called the Strategy Pattern.

Changing broker adapters should NEVER require changing this
connection service.

The connection service simply asks:

    "Which adapter should I use?"

and then talks only through the common interface.
====================================================================
"""

from __future__ import annotations

from typing import Dict

from app.core.logging import configure_logging
from app.services.broker_adapter_interface import BrokerAdapter
from app.services.credential_vault_service import CredentialVaultService


class BrokerConnectionService:
    """
    Manages broker sessions for all connected accounts.

    Sessions are cached so the application does not repeatedly
    reconnect to the same broker.

    Cache Structure
    ---------------
        {
            account_id: BrokerAdapter
        }
    """

    def __init__(
        self,
        vault: CredentialVaultService,
    ) -> None:

        self.logger = configure_logging()

        self._vault = vault

        self._sessions: Dict[str, BrokerAdapter] = {}

    # ---------------------------------------------------------

    def _create_adapter(
        self,
        broker_name: str,
    ) -> BrokerAdapter:
        """
        Create the correct adapter.

        At this checkpoint only MT5 is supported.

        The concrete MT5 adapter will be implemented in the
        next checkpoint.
        """

        broker = broker_name.strip().upper()

        if broker in (
            "MT5",
            "METATRADER5",
            "METATRADER 5",
        ):
            from app.services.adapters.mt5_adapter import (
                MT5Adapter,
            )

            return MT5Adapter()

        raise ValueError(
            f"Unsupported broker: {broker_name}"
        )

    # ---------------------------------------------------------

    async def connect_account(
        self,
        account_id: str,
    ) -> bool:
        """
        Connect a broker account.

        Flow
        ----
        1. Read credentials from vault.
        2. Verify execution permission.
        3. Create broker adapter.
        4. Connect.
        5. Cache the session.
        """

        credentials = await self._vault.get_credentials_by_account(
            account_id
        )

        if credentials is None:
            raise KeyError(
                f"Unknown account: {account_id}"
            )

        if not credentials["execution_enabled"]:
            raise PermissionError(
                "Execution is disabled for this account."
            )

        adapter = self._create_adapter(
            credentials["broker_name"]
        )

        connected = await adapter.connect(credentials)

        if connected:

            self._sessions[account_id] = adapter

            self.logger.info(
                "Connected account %s",
                account_id,
            )

        return connected

    # ---------------------------------------------------------

    async def disconnect_account(
        self,
        account_id: str,
    ) -> bool:

        adapter = self._sessions.get(account_id)

        if adapter is None:
            return False

        success = await adapter.disconnect()

        if success:

            self._sessions.pop(
                account_id,
                None,
            )

            self.logger.info(
                "Disconnected account %s",
                account_id,
            )

        return success

    # ---------------------------------------------------------

    async def get_session(
        self,
        account_id: str,
    ) -> BrokerAdapter | None:
        """
        Return the cached broker session.
        """

        return self._sessions.get(account_id)

    # ---------------------------------------------------------

    async def is_connected(
        self,
        account_id: str,
    ) -> bool:

        adapter = self._sessions.get(account_id)

        if adapter is None:
            return False

        return await adapter.is_connected()

    # ---------------------------------------------------------

    async def reconnect_account(
        self,
        account_id: str,
    ) -> bool:
        """
        Automatic reconnect.

        This implementation simply disconnects and reconnects.

        Future versions may implement retry policies,
        exponential backoff and health monitoring.
        """

        await self.disconnect_account(
            account_id
        )

        return await self.connect_account(
            account_id
        )
