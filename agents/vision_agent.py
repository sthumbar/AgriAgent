"""Vision Agent — identifies crop and detects disease from an image."""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict

import google.generativeai as genai
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from tools.image_tool import ImageProcessingError, load_and_process_image

logger = logging.getLogger(__name__)

_SKILL_PATH = Path(__file__).parent.parent / "skills" / "identify_crop.md"


def _load_skill() -> str:
    """Load the vision skill prompt from the markdown file."""
    if not _SKILL_PATH.exists():
        raise FileNotFoundError(f"Skill file not found: {_SKILL_PATH}")
    return _SKILL_PATH.read_text(encoding="utf-8")


def _extract_json(text: str) -> Dict[str, Any]:
    """
    Extract and parse a JSON object from the model's response text.

    Falls back to a structured error dict if parsing fails.
    """
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from vision response; returning raw text")
    return {
        "crop": "Unknown",
        "disease": "Unknown",
        "confidence": 0,
        "severity": "Unknown",
        "affected_parts": [],
        "additional_notes": text[:500],
    }


# ── ADK tool function ────────────────────────────────────────────────────────

def analyze_crop_image(image_path: str) -> str:
    """
    Analyze a crop image using Gemini Vision to identify the crop and any diseases.

    This tool loads the image from disk, encodes it as JPEG, and sends it to
    the Gemini Vision model along with the specialist system prompt.

    Args:
        image_path: Filesystem path to the crop image (jpg, jpeg, png, bmp, webp).

    Returns:
        JSON string containing crop name, disease, confidence, severity,
        affected_parts, and additional_notes.
    """
    logger.info("Vision tool: analysing image '%s'", image_path)

    try:
        img_data = load_and_process_image(image_path)
    except (FileNotFoundError, ImageProcessingError) as exc:
        logger.error("Image processing failed: %s", exc)
        return json.dumps({
            "crop": "Unknown",
            "disease": "Unknown",
            "confidence": 0,
            "severity": "None",
            "affected_parts": [],
            "additional_notes": f"Image error: {exc}",
        })

    skill_prompt = _load_skill()

    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel(
        model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        system_instruction=skill_prompt,
    )

    image_part = {
        "mime_type": img_data["mime_type"],
        "data": img_data["base64_data"],
    }

    response = model.generate_content(
        [
            "Analyse this crop image and return the JSON as specified in your instructions.",
            image_part,
        ],
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=512,
        ),
    )

    result = _extract_json(response.text)
    logger.info(
        "Vision result: crop=%s, disease=%s, confidence=%s",
        result.get("crop"),
        result.get("disease"),
        result.get("confidence"),
    )
    return json.dumps(result)


# ── ADK Agent ────────────────────────────────────────────────────────────────

def build_vision_agent() -> Agent:
    """Construct and return the Vision ADK Agent."""
    skill_prompt = _load_skill()

    return Agent(
        name="vision_agent",
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        description=(
            "Analyses crop images to identify the plant species and detect diseases "
            "using Gemini Vision. Returns structured JSON with crop, disease, confidence, "
            "severity, affected parts, and observational notes."
        ),
        instruction=skill_prompt,
        tools=[analyze_crop_image],
    )


# ── High-level runner ────────────────────────────────────────────────────────

class VisionAgent:
    """
    Wrapper that runs the Vision ADK Agent and returns a parsed result dict.

    Usage::

        agent = VisionAgent()
        result = await agent.run("/path/to/crop.jpg")
    """

    def __init__(self) -> None:
        self._agent = build_vision_agent()
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=self._agent,
            app_name="agri_ai",
            session_service=self._session_service,
        )

    async def run(self, image_path: str) -> Dict[str, Any]:
        """
        Run the vision agent on the given image path.

        Returns a dict with keys: crop, disease, confidence, severity,
        affected_parts, additional_notes.
        """
        session = await self._session_service.create_session(
            app_name="agri_ai",
            user_id="vision_user",
        )

        message = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=(
                        f"Please analyse the crop image at path: {image_path}\n"
                        "Call the analyze_crop_image tool and return the JSON result."
                    )
                )
            ],
        )

        final_text = ""
        async for event in self._runner.run_async(
            user_id="vision_user",
            session_id=session.id,
            new_message=message,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if part.text:
                        final_text += part.text

        if final_text:
            return _extract_json(final_text)

        # Direct fallback: call the tool function directly without ADK routing
        logger.warning("ADK routing returned no text; falling back to direct tool call")
        raw_json = analyze_crop_image(image_path)
        return json.loads(raw_json)
