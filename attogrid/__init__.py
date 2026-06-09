"""AttoGrid (by ATTO Research) — 데이터센터 DWG 도면 읽기/번역/검증/이미지컷 코어 라이브러리."""
from .reader import read, Drawing
from .text import extract_texts, clean_mtext, classify_language, TextItem
from .validate import validate, load_rules, parse_electrical, Finding
from .translate import (
    translate_texts, load_glossary, mask, unmask,
    DeepLTranslator, ArgosTranslator, MockTranslator, TranslationCache,
)
from . import render

__version__ = "0.1.0"

__all__ = [
    "read", "Drawing",
    "extract_texts", "clean_mtext", "classify_language", "TextItem",
    "validate", "load_rules", "parse_electrical", "Finding",
    "translate_texts", "load_glossary", "mask", "unmask",
    "DeepLTranslator", "ArgosTranslator", "MockTranslator", "TranslationCache",
    "render",
]
