"""Orchestrator Agent — coordinates the full crop analysis pipeline."""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.vision_agent import VisionAgent, analyze_crop_image
from agents.recommendation_agent import RecommendationAgent, get_crop_recommendations
from agents.report_agent import ReportAgent, create_report_files
from tools.rag_tool import retrieve_agricultural_knowledge
from tools.review_tool import is_low_confidence, submit_for_review

logger = logging.getLogger(__name__)


def build_orchestrator_agent() -> Agent:
    """
    Build the top-level orchestrator ADK Agent.

    The orchestrator has access to all sub-agent tools and coordinates
    the full analysis pipeline: vision → recommendations → report.
    """
    instruction = """
You are the Agri AI Orchestrator. Your job is to coordinate a multi-step crop health analysis
pipeline whenever a farmer provides a crop image path.

Follow these steps IN ORDER:

1. **Vision Analysis**: Call `analyze_crop_image` with the image path to identify the crop
   and detect any diseases. Record the crop name and disease name from the result.

2. **RAG Knowledge Retrieval**: Call `retrieve_agricultural_knowledge` with a query like
   "<crop_name> <disease_name> treatment fertilizer irrigation" to get relevant knowledge.

3. **Recommendations**: Call `get_crop_recommendations` with the crop name and disease name
   to generate fertilizer, irrigation, and treatment recommendations.

4. **Report Generation**: Combine all results into a JSON string and call `create_report_files`
   to generate the PDF and markdown reports.

5. **Final Response**: Return a complete JSON summary with all results and report paths.

Always complete all 4 steps before responding. Never skip a step.
The final response must be a valid JSON object containing:
- vision_result (from step 1)
- rag_context (from step 2)
- recommendations (from step 3)
- report_paths (from step 4)
- timestamp
"""

    return Agent(
        name="agri_orchestrator",
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        description=(
            "Top-level coordinator for the Agri AI analysis pipeline. "
            "Directs Vision, Recommendation, and Report agents in sequence to produce "
            "a comprehensive crop health analysis with PDF report."
        ),
        instruction=instruction,
        tools=[
            analyze_crop_image,
            retrieve_agricultural_knowledge,
            get_crop_recommendations,
            create_report_files,
        ],
    )


class OrchestratorAgent:
    """
    High-level orchestrator that coordinates the full four-agent pipeline.

    This class manages sequencing and data flow between:
      1. VisionAgent  — image analysis
      2. RecommendationAgent — RAG-backed recommendations
      3. ReportAgent  — PDF and markdown report generation

    It also exposes the orchestrator as a standalone ADK Agent for
    command-line and API usage via ``build_orchestrator_agent()``.

    Usage::

        orchestrator = OrchestratorAgent()
        result = await orchestrator.run("/path/to/crop.jpg")
    """

    def __init__(self) -> None:
        self._vision_agent = VisionAgent()
        self._recommendation_agent = RecommendationAgent()
        self._report_agent = ReportAgent()

    # ── Core pipeline ────────────────────────────────────────────────────────

    async def run(
        self,
        image_path: str,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute the complete crop analysis pipeline.

        Args:
            image_path: Path to the uploaded crop image.
            progress_callback: Optional callable(step: str, pct: int) for UI progress.

        Returns:
            Dict containing:
              - vision_result
              - rag_context
              - recommendations
              - report_summary
              - pdf_path
              - markdown_path
              - json_path
              - timestamp
              - success (bool)
              - error (str | None)
        """
        start_time = datetime.now()
        result: Dict[str, Any] = {
            "image_path": image_path,
            "timestamp": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "success": False,
            "error": None,
        }

        try:
            # ── Step 1: Vision Analysis ──────────────────────────────────────
            logger.info("Pipeline step 1/3: vision analysis")
            if progress_callback:
                progress_callback("Analysing image with Gemini Vision...", 20)

            vision_result = await self._vision_agent.run(image_path)
            result["vision_result"] = vision_result

            crop_name: str = vision_result.get("crop", "Unknown")
            disease_name: str = vision_result.get("disease", "Unknown")
            confidence: int = int(vision_result.get("confidence", 100))
            logger.info("Vision: crop=%s, disease=%s, confidence=%d%%", crop_name, disease_name, confidence)

            # ── HITL Gate: low-confidence → queue for agronomist review ──────
            if is_low_confidence(confidence):
                review_id = submit_for_review(image_path, {"vision_result": vision_result})
                logger.warning(
                    "Low confidence (%d%%) — flagged for agronomist review (id=%s)",
                    confidence, review_id,
                )
                result.update({
                    "success": False,
                    "requires_review": True,
                    "review_id": review_id,
                    "review_message": (
                        f"AI confidence is {confidence}% (threshold: "
                        f"{os.getenv('LOW_CONFIDENCE_THRESHOLD', '60')}%). "
                        "Analysis queued for agronomist review before recommendations are generated."
                    ),
                })
                return result

            # ── Step 2: RAG Retrieval ────────────────────────────────────────
            logger.info("Pipeline step 2/3: RAG retrieval + recommendations")
            if progress_callback:
                progress_callback("Retrieving agricultural knowledge (RAG)...", 45)

            rag_query = f"{crop_name} {disease_name} treatment fertilizer irrigation management"
            from tools.rag_tool import get_retriever
            retriever = get_retriever()
            rag_context = retriever.retrieve_as_context(rag_query)
            result["rag_context"] = rag_context

            # ── Step 3: Recommendations ──────────────────────────────────────
            if progress_callback:
                progress_callback("Generating recommendations...", 65)

            recommendations = await self._recommendation_agent.run(crop_name, disease_name)
            result["recommendations"] = recommendations

            # ── Step 4: Report Generation ────────────────────────────────────
            logger.info("Pipeline step 3/3: report generation")
            if progress_callback:
                progress_callback("Generating PDF report...", 85)

            report_result = await self._report_agent.run({
                "vision_result": vision_result,
                "recommendations": recommendations,
                "rag_context": rag_context,
            })

            result.update(report_result)
            result["success"] = True

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info("Pipeline completed in %.1fs", elapsed)
            result["elapsed_seconds"] = round(elapsed, 1)

            if progress_callback:
                progress_callback("Analysis complete!", 100)

        except Exception as exc:
            logger.error("Pipeline failed: %s", exc, exc_info=True)
            result["success"] = False
            result["error"] = str(exc)

        return result

    # ── Post-approval resume ─────────────────────────────────────────────────

    async def run_from_vision_result(
        self,
        vision_result: Dict[str, Any],
        image_path: str = "",
        progress_callback=None,
    ) -> Dict[str, Any]:
        """
        Resume the pipeline from an already-confirmed vision result.
        Called after an agronomist approves a low-confidence review.
        Skips vision; runs RAG → Recommendations → Report.
        """
        start_time = datetime.now()
        result: Dict[str, Any] = {
            "image_path": image_path,
            "timestamp": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "vision_result": vision_result,
            "success": False,
            "error": None,
        }

        try:
            crop_name = vision_result.get("crop", "Unknown")
            disease_name = vision_result.get("disease", "Unknown")

            if progress_callback:
                progress_callback("Retrieving agricultural knowledge (RAG)...", 30)

            rag_query = f"{crop_name} {disease_name} treatment fertilizer irrigation management"
            from tools.rag_tool import get_retriever
            rag_context = get_retriever().retrieve_as_context(rag_query)
            result["rag_context"] = rag_context

            if progress_callback:
                progress_callback("Generating recommendations...", 60)

            recommendations = await self._recommendation_agent.run(crop_name, disease_name)
            result["recommendations"] = recommendations

            if progress_callback:
                progress_callback("Generating PDF report...", 85)

            report_result = await self._report_agent.run({
                "vision_result": vision_result,
                "recommendations": recommendations,
                "rag_context": rag_context,
            })
            result.update(report_result)
            result["success"] = True
            result["elapsed_seconds"] = round((datetime.now() - start_time).total_seconds(), 1)

            if progress_callback:
                progress_callback("Analysis complete!", 100)

        except Exception as exc:
            logger.error("Post-approval pipeline failed: %s", exc, exc_info=True)
            result["error"] = str(exc)

        return result

    # ── Synchronous wrapper ──────────────────────────────────────────────────

    def run_sync(
        self,
        image_path: str,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous wrapper around ``run()`` for non-async callers (e.g. Streamlit).
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.run(image_path, progress_callback),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self.run(image_path, progress_callback))
        except RuntimeError:
            return asyncio.run(self.run(image_path, progress_callback))

    def run_from_vision_result_sync(
        self,
        vision_result: Dict[str, Any],
        image_path: str = "",
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper around run_from_vision_result() for Streamlit."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.run_from_vision_result(vision_result, image_path, progress_callback),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.run_from_vision_result(vision_result, image_path, progress_callback)
                )
        except RuntimeError:
            return asyncio.run(
                self.run_from_vision_result(vision_result, image_path, progress_callback)
            )
