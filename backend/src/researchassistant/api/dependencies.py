"""Explicit I/O dependencies for application-local route factories."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from researchassistant.api.live_service import DEFAULT_LIVE_DB, prepare_default_database
from researchassistant.api.provider_connections import ConnectionCheck, check_connection
from researchassistant.platform_support.credential_store import remove_credential
from researchassistant.platform_support.desktop_settings import (
    Preferences,
    read_preferences,
    update_preferences,
)
from researchassistant.storage.history_import import HistoryImportResult, import_history


@dataclass(frozen=True)
class ApiDependencies:
    default_db_path: Path = DEFAULT_LIVE_DB
    prepare_default_database: Callable[[], Path] = prepare_default_database
    read_preferences: Callable[[], Preferences] = read_preferences
    update_preferences: Callable[..., Preferences] = update_preferences
    check_connection: Callable[..., ConnectionCheck] = check_connection
    remove_credential: Callable[[str], None] = remove_credential
    import_history: Callable[[Path], HistoryImportResult] = import_history
