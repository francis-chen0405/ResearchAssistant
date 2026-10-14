"""Compatibility API imports and factory; implementations have explicit owners.

Importing this module creates no controller, service manager or application. Legacy
ASGI ``app``/``runtime`` attributes are initialized together only when requested.
"""

from __future__ import annotations

from collections.abc import AsyncIterator as AsyncIterator
from collections.abc import Callable as Callable
from collections.abc import MutableMapping as MutableMapping
from contextlib import asynccontextmanager as asynccontextmanager
from decimal import Decimal as Decimal
from functools import cache
from pathlib import Path as Path
from threading import Lock
from typing import Literal as Literal
from typing import Protocol as Protocol
from urllib.parse import urlsplit as urlsplit
from uuid import UUID as UUID

import uvicorn
from fastapi import FastAPI as FastAPI
from fastapi import HTTPException as HTTPException
from fastapi import Query as Query
from fastapi import Request as Request
from fastapi.exceptions import RequestValidationError as RequestValidationError
from fastapi.middleware.cors import CORSMiddleware as CORSMiddleware
from fastapi.responses import JSONResponse as JSONResponse
from pydantic import Field as Field
from pydantic import SecretStr as SecretStr
from pydantic import ValidationError as ValidationError
from pydantic import field_validator as field_validator
from pydantic import model_validator as model_validator
from starlette.middleware.base import BaseHTTPMiddleware as BaseHTTPMiddleware
from starlette.middleware.base import RequestResponseEndpoint as RequestResponseEndpoint
from starlette.responses import Response as Response
from starlette.types import ASGIApp as ASGIApp

from researchassistant.agents.v2_deep_analysis import (
    V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY as V2_DEEP_ANALYSIS_BACKFILL_ARTIFACT_KEY,
)
from researchassistant.agents.v2_evidence_admission import (
    V2_EVIDENCE_ADMISSION_ARTIFACT_KEY as V2_EVIDENCE_ADMISSION_ARTIFACT_KEY,
)
from researchassistant.agents.v2_final_output import (
    V2_FINAL_OUTPUT_ARTIFACT_KEY as V2_FINAL_OUTPUT_ARTIFACT_KEY,
)
from researchassistant.agents.v2_final_output import (
    V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY as V2_FINAL_OUTPUT_LEGACY_ARTIFACT_KEY,
)
from researchassistant.agents.v2_final_output import (
    V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY as V2_FINAL_OUTPUT_PHASE13_ARTIFACT_KEY,
)
from researchassistant.agents.v2_post_analysis import (
    V2_POST_ANALYSIS_ASSESSMENT_POLICY as V2_POST_ANALYSIS_ASSESSMENT_POLICY,
)
from researchassistant.agents.v2_post_analysis import (
    V2PostAnalysisAssessment as V2PostAnalysisAssessment,
)
from researchassistant.agents.v2_post_analysis import (
    build_v2_post_analysis_assessment as build_v2_post_analysis_assessment,
)
from researchassistant.agents.v2_reviewer_ledger import (
    V2_REVIEWER_LEDGER_ARTIFACT_KEY as V2_REVIEWER_LEDGER_ARTIFACT_KEY,
)
from researchassistant.agents.v2_round_four import (
    V2_POST13_GAP_AFTER_ROUND_THREE_KEY as V2_POST13_GAP_AFTER_ROUND_THREE_KEY,
)
from researchassistant.agents.v2_round_four import (
    V2_POST13_ROUND_FOUR_GOVERNOR_KEY as V2_POST13_ROUND_FOUR_GOVERNOR_KEY,
)
from researchassistant.api.application import create_app as _assemble_app
from researchassistant.api.application_services.configuration import (
    _per_token_price as _per_token_price,
)
from researchassistant.api.application_services.configuration import (
    _saved_credential_names as _saved_credential_names,
)
from researchassistant.api.application_services.configuration import (
    _saved_setting_names as _saved_setting_names,
)
from researchassistant.api.application_services.configuration import (
    _selected_discovery_providers as _selected_discovery_providers,
)
from researchassistant.api.application_services.evidence_projection import (
    _build_research_status_display as _build_research_status_display,
)
from researchassistant.api.application_services.evidence_projection import (
    _build_shared_website_groups as _build_shared_website_groups,
)
from researchassistant.api.application_services.evidence_projection import (
    _build_source_budget_outcomes as _build_source_budget_outcomes,
)
from researchassistant.api.application_services.evidence_projection import (
    _build_v2_evidence_display as _build_v2_evidence_display,
)
from researchassistant.api.application_services.evidence_projection import (
    _source_budget_outcome as _source_budget_outcome,
)
from researchassistant.api.application_services.evidence_projection import (
    _source_context_notice as _source_context_notice,
)
from researchassistant.api.application_services.evidence_projection import (
    _validate_evidence_display_provenance as _validate_evidence_display_provenance,
)
from researchassistant.api.constants import API_HOST as API_HOST
from researchassistant.api.constants import API_PORT as API_PORT
from researchassistant.api.constants import API_VERSION as API_VERSION
from researchassistant.api.constants import CREDENTIAL_ACCESS_MESSAGE as CREDENTIAL_ACCESS_MESSAGE
from researchassistant.api.constants import LOOPBACK_HOSTS as LOOPBACK_HOSTS
from researchassistant.api.constants import WEB_ORIGINS as WEB_ORIGINS
from researchassistant.api.dependencies import ApiDependencies
from researchassistant.api.http_contracts import ApiHealth as ApiHealth
from researchassistant.api.http_contracts import CancelResponse as CancelResponse
from researchassistant.api.http_contracts import ConfigurationCheckInput as ConfigurationCheckInput
from researchassistant.api.http_contracts import ConfigurationResponse as ConfigurationResponse
from researchassistant.api.http_contracts import ConnectionCheckInput as ConnectionCheckInput
from researchassistant.api.http_contracts import CredentialSetupRequest as CredentialSetupRequest
from researchassistant.api.http_contracts import CredentialSetupResponse as CredentialSetupResponse
from researchassistant.api.http_contracts import HistoryResponse as HistoryResponse
from researchassistant.api.http_contracts import ResearchStartInput as ResearchStartInput
from researchassistant.api.http_contracts import RunLocator as RunLocator
from researchassistant.api.http_errors import _inspection_http_error as _inspection_http_error
from researchassistant.api.http_security import LoopbackGuardMiddleware as LoopbackGuardMiddleware
from researchassistant.api.inspection_contracts import V2EvidenceDisplay as V2EvidenceDisplay
from researchassistant.api.inspection_contracts import (
    V2EvidenceDisplayItem as V2EvidenceDisplayItem,
)
from researchassistant.api.inspection_contracts import (
    V2ResearchStatusDisplay as V2ResearchStatusDisplay,
)
from researchassistant.api.inspection_contracts import V2SharedWebsiteGroup as V2SharedWebsiteGroup
from researchassistant.api.inspection_contracts import (
    V2SourceBudgetOutcomeDisplay as V2SourceBudgetOutcomeDisplay,
)
from researchassistant.api.inspection_contracts import V2SourceTitleDisplay as V2SourceTitleDisplay
from researchassistant.api.live_lifecycle import LifecycleConflict as LifecycleConflict
from researchassistant.api.live_lifecycle import LifecycleCoordinator as LifecycleCoordinator
from researchassistant.api.live_service import DEFAULT_LIVE_DB as DEFAULT_LIVE_DB
from researchassistant.api.live_service import LiveHistoryItem as LiveHistoryItem
from researchassistant.api.live_service import LiveResearchController as LiveResearchController
from researchassistant.api.live_service import LiveRunRequest as LiveRunRequest
from researchassistant.api.live_service import LiveRunSnapshot as LiveRunSnapshot
from researchassistant.api.live_service import LiveStartResult as LiveStartResult
from researchassistant.api.live_service import ResearchTrail as ResearchTrail
from researchassistant.api.live_service import prepare_default_database as prepare_default_database
from researchassistant.api.provider_connections import ConnectionCheck as ConnectionCheck
from researchassistant.api.provider_connections import check_connection as check_connection
from researchassistant.api.runtime import ApiRuntime as ApiRuntime
from researchassistant.api.runtime import ControllerBoundary as ControllerBoundary
from researchassistant.api.runtime import ServiceBoundary as ServiceBoundary
from researchassistant.api.runtime import create_default_runtime as create_default_runtime
from researchassistant.api.security import redact_text as redact_text
from researchassistant.api.service_manager import ServiceDiagnostic as ServiceDiagnostic
from researchassistant.api.service_manager import WigoloServiceManager as WigoloServiceManager
from researchassistant.contracts.models import CandidateQuoteBlock as CandidateQuoteBlock
from researchassistant.contracts.models import DiscoveryProvider as DiscoveryProvider
from researchassistant.contracts.models import LedgerRecord as LedgerRecord
from researchassistant.contracts.models import ResearchControls as ResearchControls
from researchassistant.contracts.models import ResearchDirections as ResearchDirections
from researchassistant.contracts.models import ResearchMode as ResearchMode
from researchassistant.contracts.models import SourceSnapshot as SourceSnapshot
from researchassistant.contracts.models import StrictModel as StrictModel
from researchassistant.contracts.models import V2ClaimCoverageState as V2ClaimCoverageState
from researchassistant.contracts.models import (
    V2DeepAnalysisBackfillResult as V2DeepAnalysisBackfillResult,
)
from researchassistant.contracts.models import (
    V2DeepAnalysisSourceExecution as V2DeepAnalysisSourceExecution,
)
from researchassistant.contracts.models import (
    V2DeepAnalysisSourceExecutionState as V2DeepAnalysisSourceExecutionState,
)
from researchassistant.contracts.models import (
    V2EvidenceAdmissionBatchResult as V2EvidenceAdmissionBatchResult,
)
from researchassistant.contracts.models import (
    V2EvidenceAdmissionRecord as V2EvidenceAdmissionRecord,
)
from researchassistant.contracts.models import (
    V2EvidenceAnalystSourceResult as V2EvidenceAnalystSourceResult,
)
from researchassistant.contracts.models import V2EvidenceRelationship as V2EvidenceRelationship
from researchassistant.contracts.models import V2FinalResearchOutput as V2FinalResearchOutput
from researchassistant.contracts.models import V2GapAnalysisOutput as V2GapAnalysisOutput
from researchassistant.contracts.models import (
    V2ReviewerLedgerBatchResult as V2ReviewerLedgerBatchResult,
)
from researchassistant.contracts.models import (
    V2RoundFourGovernorDecision as V2RoundFourGovernorDecision,
)
from researchassistant.evidence.evidence_core import (
    parse_extracted_quote_block as parse_extracted_quote_block,
)
from researchassistant.evidence.evidence_core import (
    validate_snapshot_integrity as validate_snapshot_integrity,
)
from researchassistant.evidence.source_display import display_source_title as display_source_title
from researchassistant.evidence.study_lineage import StudyLineageNotice as StudyLineageNotice
from researchassistant.evidence.study_lineage import (
    build_study_lineage_notices as build_study_lineage_notices,
)
from researchassistant.platform_support.credential_store import (
    KeychainUnavailableError as KeychainUnavailableError,
)
from researchassistant.platform_support.credential_store import (
    ProviderCredentials as ProviderCredentials,
)
from researchassistant.platform_support.credential_store import (
    apply_credentials_to_environment as apply_credentials_to_environment,
)
from researchassistant.platform_support.credential_store import (
    load_saved_credentials_into_environment as load_saved_credentials_into_environment,
)
from researchassistant.platform_support.credential_store import (
    remove_credential as remove_credential,
)
from researchassistant.platform_support.credential_store import save_credentials as save_credentials
from researchassistant.platform_support.desktop_settings import (
    InterfaceSettings as InterfaceSettings,
)
from researchassistant.platform_support.desktop_settings import Preferences
from researchassistant.platform_support.desktop_settings import read_preferences as read_preferences
from researchassistant.platform_support.desktop_settings import (
    update_preferences as update_preferences,
)
from researchassistant.providers.model_choices import (
    CONFIGURABLE_PROFILE_ID as CONFIGURABLE_PROFILE_ID,
)
from researchassistant.providers.model_choices import DEFAULT_STAGE_MODELS as DEFAULT_STAGE_MODELS
from researchassistant.providers.model_choices import StageModelSelections as StageModelSelections
from researchassistant.providers.model_choices import model_options_payload as model_options_payload
from researchassistant.providers.model_profiles import CONFIGURABLE_PROFILE as CONFIGURABLE_PROFILE
from researchassistant.providers.model_profiles import STANDARD_PROFILE as STANDARD_PROFILE
from researchassistant.providers.model_profiles import ModelProfile as ModelProfile
from researchassistant.providers.model_profiles import ProfileId as ProfileId
from researchassistant.providers.model_profiles import profile_environment as profile_environment
from researchassistant.providers.v2_factory import (
    V2ProductionFactoryConfig as V2ProductionFactoryConfig,
)
from researchassistant.runtime.application_runtime import repository_identity as repository_identity
from researchassistant.storage.history_import import HistoryImportResult as HistoryImportResult
from researchassistant.storage.history_import import import_history as import_history
from researchassistant.storage.sqlite_policy import is_busy_error as is_busy_error
from researchassistant.storage.store import DatabaseCompatibilityError as DatabaseCompatibilityError
from researchassistant.storage.store import open_read_only_store as open_read_only_store
from researchassistant.storage.store import read_v2_artifact as read_v2_artifact


def _read_preferences() -> Preferences:
    return read_preferences()


def _update_preferences(*, interface: InterfaceSettings) -> Preferences:
    return update_preferences(interface=interface)


def _check_connection(
    name: str,
    environment: MutableMapping[str, str],
    *,
    model_profile: ProfileId,
    stage_models: StageModelSelections,
) -> ConnectionCheck:
    return check_connection(
        name, environment, model_profile=model_profile, stage_models=stage_models
    )


def _remove_credential(name: str) -> None:
    remove_credential(name)


def _import_history(source: Path) -> HistoryImportResult:
    return import_history(source)


def _prepare_default_database() -> Path:
    return prepare_default_database()


def create_app(
    runtime: ApiRuntime,
    *,
    load_keychain_on_start: bool,
    allowed_hosts: tuple[str, ...] = LOOPBACK_HOSTS,
    allowed_origins: tuple[str, ...] = WEB_ORIGINS,
    session_token: str | None = None,
) -> FastAPI:
    """Preserve the public factory and its historical replaceable I/O seams."""
    return _assemble_app(
        runtime,
        load_keychain_on_start=load_keychain_on_start,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
        session_token=session_token,
        dependencies=ApiDependencies(
            default_db_path=DEFAULT_LIVE_DB,
            prepare_default_database=_prepare_default_database,
            read_preferences=_read_preferences,
            update_preferences=_update_preferences,
            check_connection=_check_connection,
            remove_credential=_remove_credential,
            import_history=_import_history,
        ),
    )


_default_lock = Lock()


@cache
def _default_application() -> tuple[ApiRuntime, FastAPI]:
    default_runtime = create_default_runtime()
    return default_runtime, create_app(default_runtime, load_keychain_on_start=True)


def __getattr__(name: str) -> ApiRuntime | FastAPI:
    if name not in {"app", "runtime"}:
        raise AttributeError(name)
    with _default_lock:
        default_runtime, default_app = _default_application()
    return default_app if name == "app" else default_runtime


def main() -> None:
    with _default_lock:
        _, default_app = _default_application()
    uvicorn.run(default_app, host=API_HOST, port=API_PORT, log_level="warning")


if __name__ == "__main__":
    main()
