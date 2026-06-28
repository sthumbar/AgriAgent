"""Audio output tool — converts analysis results into spoken farmer-friendly summaries."""

import io
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "English": "en",
    "Hindi (हिंदी)": "hi",
    "Marathi (मराठी)": "mr",
    "Telugu (తెలుగు)": "te",
    "Tamil (தமிழ்)": "ta",
    "Kannada (ಕನ್ನಡ)": "kn",
    "Bengali (বাংলা)": "bn",
    "Gujarati (ગુજરાતી)": "gu",
}

_URGENCY_ADVICE = {
    "low":      "You have some time, but please act within the next two weeks.",
    "medium":   "Please act within the next few days.",
    "high":     "This is urgent. Please act within 24 to 48 hours.",
    "critical": "This is very serious. Act immediately today.",
}


def _build_english_summary(result: Dict[str, Any]) -> str:
    """Build a simple, spoken-word English summary from the analysis result."""
    vision = result.get("vision_result", {})
    recs = result.get("recommendations", {})

    crop = vision.get("crop", "Unknown crop")
    disease = vision.get("disease", "Unknown condition")
    severity = vision.get("severity", "").lower() or "moderate"
    confidence = int(vision.get("confidence", 0))
    urgency = recs.get("urgency", "Medium").lower()

    treatment_steps = recs.get("treatment_steps", [])
    steps_text = ""
    if treatment_steps:
        ordinals = ["First", "Second", "Third"]
        parts = [f"{ordinals[i]}, {step}" for i, step in enumerate(treatment_steps[:3])]
        steps_text = " ".join(parts)

    urgency_advice = _URGENCY_ADVICE.get(urgency, _URGENCY_ADVICE["medium"])

    if disease.lower() in ("healthy", "none", "no disease"):
        condition_line = f"Good news! Your {crop} crop looks healthy."
    else:
        condition_line = (
            f"Your {crop} crop has been identified with {disease}. "
            f"The severity is {severity}."
        )

    lines = [
        "Hello farmer. Here is your crop health report.",
        condition_line,
        f"The AI confidence in this diagnosis is {confidence} percent.",
        urgency_advice,
    ]
    if steps_text:
        lines.append(f"Recommended action:{steps_text}.")

    fertilizer = recs.get("fertilizer", {})
    if fertilizer.get("primary"):
        lines.append(
            f"For fertilizer, use {fertilizer['primary']} "
            f"at a rate of {fertilizer.get('application_rate', 'as directed')}."
        )

    lines.append("For more details, please read the full report on screen or ask someone to help you.")
    lines.append("Thank you. Good luck with your harvest.")

    return " ".join(lines)


def _translate_with_gemini(english_text: str, target_language: str) -> str:
    """Translate the summary to the target language using Gemini."""
    try:
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not set; returning English fallback")
            return english_text

        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        model = genai.GenerativeModel(model_name)

        prompt = (
            f"Translate the following crop health report summary into {target_language}. "
            f"Keep the language very simple, clear, and suitable for a farmer with low literacy. "
            f"Do not add any extra text — only the translation.\n\n"
            f"{english_text}"
        )
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as exc:
        logger.error("Gemini translation failed: %s", exc)
        return english_text


def generate_audio_bytes(
    result: Dict[str, Any],
    language_name: str = "English",
) -> Optional[bytes]:
    """
    Generate spoken audio bytes from an analysis result dict.

    Args:
        result: The full pipeline result dict from OrchestratorAgent.run().
        language_name: Display name from SUPPORTED_LANGUAGES (e.g. "Hindi (हिंदी)").

    Returns:
        MP3 audio bytes, or None if TTS fails.
    """
    from gtts import gTTS

    lang_code = SUPPORTED_LANGUAGES.get(language_name, "en")
    english_summary = _build_english_summary(result)

    if lang_code == "en":
        spoken_text = english_summary
    else:
        spoken_text = _translate_with_gemini(english_summary, language_name.split(" ")[0])

    try:
        tts = gTTS(text=spoken_text, lang=lang_code, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception as exc:
        logger.error("gTTS generation failed (lang=%s): %s", lang_code, exc)
        return None
