from __future__ import annotations

from app.config import AppConfig
from app.translate.argos_provider import ArgosTranslator
from app.translate.base import Translator
from app.translate.llm_provider import LlmTranslator
from app.translate.mock_provider import MockTranslator


def create_translator(config: AppConfig) -> Translator:
    provider = (config.translation.provider or "llm").strip().lower()
    if provider == "mock":
        return MockTranslator()
    if provider == "argos":
        return ArgosTranslator()
    return _llm(config)


def create_summarizer(config: AppConfig):
    """Summaries always go to the configured LLM, except in mock mode."""
    if (config.translation.provider or "").strip().lower() == "mock":
        return MockTranslator()
    return _llm(config)


def _llm(config: AppConfig) -> LlmTranslator:
    vendor = (config.translation.llm_vendor or "openai").strip().lower()
    if vendor == "anthropic":
        model = config.translation.anthropic_model
    else:
        vendor = "openai"
        model = config.translation.openai_model
    return LlmTranslator(vendor, model)
