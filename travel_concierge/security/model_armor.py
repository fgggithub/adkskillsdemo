"""
Model Armor Security Module.
Provides multi-layered defense against Prompt Injection, Hate Speech, Harassment,
and Criminal / Illicit activity requests before LLM invocation.
Adheres to Google Cloud Model Armor standards and AXI methodology.
"""
import re
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List

from travel_concierge.telemetry.tracer import get_tracer

logger = logging.getLogger("travel_concierge.security.model_armor")
tracer = get_tracer("travel_concierge.security.model_armor")


class ModelArmorViolationError(PermissionError):
    """Raised when Model Armor detects malicious, abusive, or injection input."""
    def __init__(self, category: str, details: str):
        super().__init__(f"403 Forbidden [Model Armor]: {category} policy violation detected. {details}")
        self.category = category
        self.details = details


@dataclass
class InspectionResult:
    is_safe: bool
    category: Optional[str] = None
    confidence: float = 0.0
    reason: Optional[str] = None
    sanitized_text: Optional[str] = None


class ModelArmor:
    """
    Enterprise Model Armor guardrail engine.
    Scans prompts and model inputs for:
    1. Prompt Injection (Jailbreaks, system instruction leaks, instruction override tokens).
    2. Hate Speech & Harassment (Defamatory, degrading, or discriminatory patterns).
    3. Criminal & Illicit Activities (Fraud, identity theft, credit card skimming, exploit crafting).
    """

    PROMPT_INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|directions|prompts)", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(?:an?\s+)?(?:unrestricted|jailbroken|dan|evil|hacker)", re.IGNORECASE),
        re.compile(r"system\s+prompt\s+(?:override|bypass|leak|reveal)", re.IGNORECASE),
        re.compile(r"disregard\s+(?:any\s+)?guardrails", re.IGNORECASE),
        re.compile(r"print\s+(?:your\s+)?(?:initial|original|hidden)\s+(?:system\s+)?prompt", re.IGNORECASE),
        re.compile(r"mode\s*:\s*unrestricted", re.IGNORECASE),
        re.compile(r"bypass\s+safety\s+filter", re.IGNORECASE),
        re.compile(r"\[SYSTEM_PROMPT_OVERRIDE\]", re.IGNORECASE),
    ]

    HATE_SPEECH_PATTERNS = [
        re.compile(r"\b(?:hate|kill|exterminate|disgusting|vermin|subhuman)\s+(?:all\s+)?(?:immigrants|jews|muslims|minorities|refugees|foreigners)\b", re.IGNORECASE),
        re.compile(r"\b(?:discriminate\s+against|exclude)\s+(?:ethnic\s+)?(?:minorities|immigrants|foreigners|refugees)\b", re.IGNORECASE),
        re.compile(r"\bgo\s+back\s+to\s+your\s+country\b", re.IGNORECASE),
        re.compile(r"\bwhite\s+supremacy\b", re.IGNORECASE),
        re.compile(r"\bethnic\s+cleansing\b", re.IGNORECASE),
    ]

    CRIMINAL_ACTIVITY_PATTERNS = [
        re.compile(r"\b(?:steal|fake|forge|hack|counterfeit|launder)\s+(?:credit\s+cards?|passports?|identit(?:y|ies)|bank\s+accounts?|money)\b", re.IGNORECASE),
        re.compile(r"\b(?:bypass|crack|hack)\s+(?:hotel\s+)?(?:keycards?|payment\s+gateway|stripe|auth|room\s+locks?)\b", re.IGNORECASE),
        re.compile(r"\b(?:how\s+to\s+make\s+a\s+bomb|synthesize\s+explosives|illegal\s+weapons)\b", re.IGNORECASE),
        re.compile(r"\bcredit\s+card\s+fraud\b", re.IGNORECASE),
    ]

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode

    def inspect_prompt(self, prompt: str) -> InspectionResult:
        """
        Inspects text input across all security criteria.
        Returns InspectionResult with safety verdict and details.
        """
        with tracer.start_as_current_span("model_armor_inspect") as span:
            span.set_attribute("security.scanner", "ModelArmor")
            span.set_attribute("security.input_length", len(prompt))

            # 1. Prompt Injection Scan
            for pat in self.PROMPT_INJECTION_PATTERNS:
                if pat.search(prompt):
                    matched = pat.pattern
                    span.set_attribute("security.violation", "prompt_injection")
                    span.set_attribute("security.pattern_matched", matched)
                    logger.warning(f"[Model Armor] Prompt Injection blocked: '{prompt[:60]}...' matched {matched}")
                    return InspectionResult(
                        is_safe=False,
                        category="prompt_injection",
                        confidence=0.98,
                        reason="Prompt injection / system override heuristic triggered.",
                    )

            # 2. Hate Speech Scan
            for pat in self.HATE_SPEECH_PATTERNS:
                if pat.search(prompt):
                    span.set_attribute("security.violation", "hate_speech")
                    logger.warning(f"[Model Armor] Hate Speech blocked: '{prompt[:60]}...'")
                    return InspectionResult(
                        is_safe=False,
                        category="hate_speech",
                        confidence=0.95,
                        reason="Hate speech or discriminatory language detected.",
                    )

            # 3. Criminal Activity Scan
            for pat in self.CRIMINAL_ACTIVITY_PATTERNS:
                if pat.search(prompt):
                    span.set_attribute("security.violation", "criminal_activity")
                    logger.warning(f"[Model Armor] Criminal Activity blocked: '{prompt[:60]}...'")
                    return InspectionResult(
                        is_safe=False,
                        category="criminal_activity",
                        confidence=0.96,
                        reason="Illicit or criminal activity solicitation detected.",
                    )

            span.set_attribute("security.violation", "none")
            span.set_attribute("security.status", "CLEAN")
            return InspectionResult(is_safe=True, category="clean", confidence=1.0, sanitized_text=prompt)

    def guard(self, prompt: str) -> str:
        """
        Guards input, raising ModelArmorViolationError if input is unsafe.
        Returns the prompt if clean.
        """
        result = self.inspect_prompt(prompt)
        if not result.is_safe:
            raise ModelArmorViolationError(category=result.category or "unknown", details=result.reason or "Policy violation")
        return prompt


# Global default scanner instance
default_model_armor = ModelArmor()


def guard_prompt(prompt: str) -> str:
    """Convenience helper function to run default Model Armor guardrail."""
    return default_model_armor.guard(prompt)
