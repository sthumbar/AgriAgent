"""Recommendation Agent — generates fertilizer, irrigation, and treatment advice using RAG."""

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

from tools.rag_tool import retrieve_agricultural_knowledge

logger = logging.getLogger(__name__)

_SKILL_PATH = Path(__file__).parent.parent / "skills" / "recommendations.md"


def _load_skill() -> str:
    """Load the recommendations skill prompt from the markdown file."""
    if not _SKILL_PATH.exists():
        raise FileNotFoundError(f"Skill file not found: {_SKILL_PATH}")
    return _SKILL_PATH.read_text(encoding="utf-8")


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract and parse a JSON object from the model's response text."""
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from recommendation response")
    return {
        "disease_explanation": text[:300],
        "fertilizer": {"primary": "Balanced NPK 19-19-19", "notes": "Consult local agronomist"},
        "irrigation": {"frequency": "As needed", "notes": "Monitor soil moisture"},
        "treatment_steps": ["Consult a local agronomist for specific treatment"],
        "prevention": ["Practice crop rotation", "Monitor fields regularly"],
        "organic_alternatives": ["Neem oil spray"],
        "urgency": "Medium",
        "estimated_yield_impact": "Unknown",
    }


# ── ADK tool function ────────────────────────────────────────────────────────

def get_crop_recommendations(crop_name: str, disease_name: str) -> str:
    """
    Generate comprehensive agricultural recommendations for the identified crop and disease.

    Retrieves relevant knowledge from the vector store (RAG) and uses Gemini to produce
    fertilizer, irrigation, treatment, prevention, and organic alternative recommendations.

    Args:
        crop_name: The name of the identified crop (e.g., "Tomato", "Wheat").
        disease_name: The disease or condition detected (e.g., "Early Blight", "Healthy").

    Returns:
        JSON string with fertilizer, irrigation, treatment_steps, prevention,
        organic_alternatives, urgency, and estimated_yield_impact.
    """
    logger.info("Recommendation tool: crop=%s, disease=%s", crop_name, disease_name)

    rag_query = f"{crop_name} {disease_name} treatment fertilizer irrigation"
    rag_context = retrieve_agricultural_knowledge(rag_query)

    if rag_context:
        logger.info("RAG context retrieved (%d chars)", len(rag_context))
    else:
        logger.warning("No RAG context available; using general agronomic knowledge")

    skill_prompt = _load_skill()

    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel(
        model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        system_instruction=skill_prompt,
    )

    user_message = (
        f"Crop: {crop_name}\n"
        f"Disease/Condition: {disease_name}\n\n"
        f"Retrieved Agricultural Knowledge:\n{rag_context or 'Not available — use general expertise.'}\n\n"
        "Generate comprehensive recommendations following the JSON format in your instructions."
    )

    response = model.generate_content(
        user_message,
        generation_config=genai.GenerationConfig(
            temperature=0.2,
            max_output_tokens=1500,
        ),
    )

    result = _extract_json(response.text)
    logger.info(
        "Recommendations generated: urgency=%s, fertilizer=%s",
        result.get("urgency"),
        result.get("fertilizer", {}).get("primary", "N/A"),
    )
    return json.dumps(result)


# ── ADK Agent ────────────────────────────────────────────────────────────────

def build_recommendation_agent() -> Agent:
    """Construct and return the Recommendation ADK Agent."""
    skill_prompt = _load_skill()

    return Agent(
        name="recommendation_agent",
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        description=(
            "Provides evidence-based agricultural recommendations including fertilizer programme, "
            "irrigation schedule, disease treatment steps, prevention strategies, and organic "
            "alternatives. Uses RAG to retrieve relevant knowledge from agricultural literature."
        ),
        instruction=skill_prompt,
        tools=[get_crop_recommendations, retrieve_agricultural_knowledge],
    )


# ── High-level runner ────────────────────────────────────────────────────────

class RecommendationAgent:
    """
    Wrapper that runs the Recommendation ADK Agent and returns a parsed result dict.

    Usage::

        agent = RecommendationAgent()
        result = await agent.run("Tomato", "Early Blight")
    """

    def __init__(self) -> None:
        self._agent = build_recommendation_agent()
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=self._agent,
            app_name="agri_ai",
            session_service=self._session_service,
        )

    async def run(self, crop_name: str, disease_name: str) -> Dict[str, Any]:
        """
        Run the recommendation agent for the given crop and disease.

        Returns a dict with fertilizer, irrigation, treatment_steps, prevention,
        organic_alternatives, urgency, and estimated_yield_impact.
        """
        session = await self._session_service.create_session(
            app_name="agri_ai",
            user_id="rec_user",
        )

        message = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=(
                        f"Generate recommendations for crop '{crop_name}' "
                        f"with disease/condition '{disease_name}'. "
                        "Call the get_crop_recommendations tool and return the JSON result."
                    )
                )
            ],
        )

        final_text = ""
        async for event in self._runner.run_async(
            user_id="rec_user",
            session_id=session.id,
            new_message=message,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if part.text:
                        final_text += part.text

        if final_text:
            return _extract_json(final_text)

        logger.warning("ADK routing returned no text; falling back to direct tool call")
        raw_json = get_crop_recommendations(crop_name, disease_name)
        return json.loads(raw_json)
