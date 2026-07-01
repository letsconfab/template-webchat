"""Local Presidio-based redaction and fail-closed projection persistence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.diagnostics import AdminProjection


PROJECTION_VERSION = 1


@dataclass(frozen=True)
class ProjectionValue:
    status: str
    text: str | None
    version: int


class LocalRedactor:
    """Structured recognizers plus English spaCy named-entity recognition."""

    def __init__(self) -> None:
        self._analyzer: AnalyzerEngine | None = None
        self._anonymizer: AnonymizerEngine | None = None

    def _engines(self) -> tuple[AnalyzerEngine, AnonymizerEngine]:
        if self._analyzer is None:
            provider = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [
                        {"lang_code": "en", "model_name": "en_core_web_sm"}
                    ],
                }
            )
            self._analyzer = AnalyzerEngine(
                nlp_engine=provider.create_engine(),
                supported_languages=["en"],
            )
            self._anonymizer = AnonymizerEngine()
        return self._analyzer, self._anonymizer

    def redact(self, text: str) -> str:
        analyzer, anonymizer = self._engines()
        findings = analyzer.analyze(text=text, language="en")
        return anonymizer.anonymize(text=text, analyzer_results=findings).text


redactor = LocalRedactor()


async def project_text(
    db: AsyncSession,
    *,
    content_type: str,
    content_id: int,
    source_field: str,
    raw_text: str | None,
) -> AdminProjection:
    result = await db.execute(
        select(AdminProjection).where(
            AdminProjection.content_type == content_type,
            AdminProjection.content_id == content_id,
            AdminProjection.source_field == source_field,
            AdminProjection.version == PROJECTION_VERSION,
        )
    )
    projection = result.scalar_one_or_none()
    if projection is None:
        projection = AdminProjection(
            content_type=content_type,
            content_id=content_id,
            source_field=source_field,
            version=PROJECTION_VERSION,
            status="pending",
        )
        db.add(projection)

    try:
        projection.redacted_text = await asyncio.to_thread(
            redactor.redact,
            raw_text or "",
        )
        projection.status = "succeeded"
        projection.safe_error_category = None
    except Exception:
        projection.redacted_text = None
        projection.status = "failed"
        projection.safe_error_category = "redactor_unavailable"
    await db.flush()
    return projection


async def get_projection(
    db: AsyncSession,
    *,
    content_type: str,
    content_id: int,
    source_field: str,
) -> ProjectionValue:
    result = await db.execute(
        select(AdminProjection).where(
            AdminProjection.content_type == content_type,
            AdminProjection.content_id == content_id,
            AdminProjection.source_field == source_field,
            AdminProjection.version == PROJECTION_VERSION,
        )
    )
    projection = result.scalar_one_or_none()
    if projection is None or projection.status != "succeeded":
        return ProjectionValue(
            status=projection.status if projection else "pending",
            text=None,
            version=PROJECTION_VERSION,
        )
    return ProjectionValue(
        status="succeeded",
        text=projection.redacted_text,
        version=projection.version,
    )


def mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    visible = local[:1]
    return f"{visible}{'*' * max(3, len(local) - 1)}@{domain}"
