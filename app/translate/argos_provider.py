from __future__ import annotations

import logging

from app.translate.base import Translator

logger = logging.getLogger(__name__)


class ArgosTranslator(Translator):
    """Offline Argos Translate. Language packages download on first use."""

    def translate(self, text, source_lang, target_lang, context) -> str:
        del context
        translation = self._translation(source_lang, target_lang)
        return (translation.translate(text) or "").strip()

    def _translation(self, source_lang: str, target_lang: str):
        import argostranslate.package
        import argostranslate.translate

        def lookup():
            languages = argostranslate.translate.get_installed_languages()
            source = next((item for item in languages if item.code == source_lang), None)
            target = next((item for item in languages if item.code == target_lang), None)
            if source is None or target is None:
                return None
            return source.get_translation(target)

        found = lookup()
        if found is not None:
            return found
        logger.info("Downloading Argos package %s -> %s", source_lang, target_lang)
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
        package = next(
            (
                item
                for item in available
                if item.from_code == source_lang and item.to_code == target_lang
            ),
            None,
        )
        if package is None:
            raise RuntimeError(
                f"No offline Argos package is available for {source_lang} -> {target_lang}."
            )
        archive = package.download()
        argostranslate.package.install_from_path(archive)
        found = lookup()
        if found is None:
            raise RuntimeError(
                f"Argos package {source_lang} -> {target_lang} could not be loaded."
            )
        return found
