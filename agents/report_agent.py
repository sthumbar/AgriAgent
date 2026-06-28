"""Report Agent — generates markdown summary, PDF report, and final JSON."""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import google.generativeai as genai
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from tools.pdf_tool import generate_pdf_report

logger = logging.getLogger(__name__)

_SKILL_PATH = Path(__file__).parent.parent / "skills" / "report.md"
_REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "./reports"))


def _load_skill() -> str:
    """Load the report skill prompt from the markdown file."""
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

    logger.warning("Could not parse JSON from report response; using fallback")
    return {
        "report_title": "Crop Health Analysis Report",
        "executive_summary": "Analysis complete. See detailed recommendations.",
        "analysis_narrative": text[:500],
        "action_plan": [
            {"priority": 1, "action": "Review recommendations", "timeline": "Immediately", "urgency": "High"}
        ],
        "risk_summary": "Please consult an agronomist.",
        "key_metrics": {},
        "disclaimer": "AI-generated; verify with a certified agronomist.",
    }


# ── ADK tool functions ───────────────────────────────────────────────────────

def generate_markdown_summary(analysis_data_json: str) -> str:
    """
    Generate a Markdown-formatted summary from the combined analysis data.

    Args:
        analysis_data_json: JSON string containing vision_result, recommendations,
                            report_summary, and timestamp.

    Returns:
        Markdown string summarising the full analysis.
    """
    try:
        data = json.loads(analysis_data_json)
    except json.JSONDecodeError:
        return "# Error\nCould not parse analysis data."

    vision = data.get("vision_result", {})
    recs = data.get("recommendations", {})
    summary = data.get("report_summary", {})
    timestamp = data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    crop = vision.get("crop", "Unknown")
    disease = vision.get("disease", "Unknown")
    confidence = vision.get("confidence", 0)
    urgency = recs.get("urgency", "Medium")
    fertilizer_primary = recs.get("fertilizer", {}).get("primary", "N/A")
    irrigation_freq = recs.get("irrigation", {}).get("frequency", "N/A")
    exec_summary = summary.get("executive_summary", "Analysis complete.")

    md_lines = [
        f"# 🌿 Crop Health Analysis Report",
        f"**Generated:** {timestamp}",
        "",
        "---",
        "",
        "## Executive Summary",
        exec_summary,
        "",
        "## Key Findings",
        "",
        f"| Parameter | Value |",
        f"|-----------|-------|",
        f"| **Crop Identified** | {crop} |",
        f"| **Disease / Condition** | {disease} |",
        f"| **Confidence** | {confidence}% |",
        f"| **Severity** | {vision.get('severity', 'N/A')} |",
        f"| **Urgency** | {urgency} |",
        "",
        "## Recommendations Summary",
        "",
        f"- **Fertilizer:** {fertilizer_primary}",
        f"- **Irrigation:** {irrigation_freq}",
        f"- **Yield Impact if Untreated:** {recs.get('estimated_yield_impact', 'Unknown')}",
        "",
    ]

    treatment_steps = recs.get("treatment_steps", [])
    if treatment_steps:
        md_lines.append("## Treatment Steps")
        for step in treatment_steps:
            md_lines.append(f"1. {step}")
        md_lines.append("")

    prevention = recs.get("prevention", [])
    if prevention:
        md_lines.append("## Prevention")
        for item in prevention:
            md_lines.append(f"- {item}")
        md_lines.append("")

    organics = recs.get("organic_alternatives", [])
    if organics:
        md_lines.append("## Organic Alternatives")
        for item in organics:
            md_lines.append(f"- {item}")
        md_lines.append("")

    action_plan = summary.get("action_plan", [])
    if action_plan:
        md_lines.append("## Prioritised Action Plan")
        for item in action_plan:
            md_lines.append(
                f"{item.get('priority', '')}. **[{item.get('urgency', '')}]** "
                f"{item.get('action', '')} _(by {item.get('timeline', 'ASAP')})_"
            )
        md_lines.append("")

    disclaimer = summary.get("disclaimer", "Verify with a certified agronomist.")
    md_lines += [
        "---",
        f"> ⚠️ *{disclaimer}*",
        "",
        "*Generated by Agri AI Assistant*",
    ]

    return "\n".join(md_lines)


def create_report_files(analysis_data_json: str) -> str:
    """
    Create the PDF and markdown report files from the combined analysis data.

    Args:
        analysis_data_json: JSON string containing all analysis results.

    Returns:
        JSON string with keys: pdf_path, markdown_path, json_path, timestamp.
    """
    logger.info("Report tool: generating report files")

    try:
        data = json.loads(analysis_data_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Could not parse analysis data: {exc}"})

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    crop_slug = re.sub(r"[^a-z0-9]", "_", data.get("vision_result", {}).get("crop", "unknown").lower())
    base_name = f"agri_report_{crop_slug}_{timestamp}"

    data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    pdf_path = str(_REPORTS_DIR / f"{base_name}.pdf")
    md_path = str(_REPORTS_DIR / f"{base_name}.md")
    json_path = str(_REPORTS_DIR / f"{base_name}.json")

    generate_pdf_report(data, pdf_path)
    logger.info("PDF saved: %s", pdf_path)

    markdown_content = generate_markdown_summary(analysis_data_json)
    Path(md_path).write_text(markdown_content, encoding="utf-8")
    logger.info("Markdown saved: %s", md_path)

    Path(json_path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("JSON saved: %s", json_path)

    return json.dumps({
        "pdf_path": pdf_path,
        "markdown_path": md_path,
        "json_path": json_path,
        "timestamp": data["timestamp"],
    })


# ── ADK Agent ────────────────────────────────────────────────────────────────

def build_report_agent() -> Agent:
    """Construct and return the Report ADK Agent."""
    skill_prompt = _load_skill()

    return Agent(
        name="report_agent",
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        description=(
            "Synthesises all analysis results into a professional report. "
            "Generates an executive summary, action plan, risk assessment, markdown document, "
            "and a formatted PDF report."
        ),
        instruction=skill_prompt,
        tools=[create_report_files, generate_markdown_summary],
    )


# ── High-level runner ────────────────────────────────────────────────────────

class ReportAgent:
    """
    Wrapper that runs the Report ADK Agent and returns paths to generated files.

    Usage::

        agent = ReportAgent()
        result = await agent.run(combined_data_dict)
    """

    def __init__(self) -> None:
        self._agent = build_report_agent()
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=self._agent,
            app_name="agri_ai",
            session_service=self._session_service,
        )

    async def _generate_report_summary(self, combined_data: Dict[str, Any]) -> Dict[str, Any]:
        """Use Gemini to generate the structured report summary."""
        skill_prompt = _load_skill()

        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            system_instruction=skill_prompt,
        )

        user_message = (
            "Generate the report summary JSON from this analysis data:\n\n"
            + json.dumps(combined_data, indent=2)
        )

        response = model.generate_content(
            user_message,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=1200,
            ),
        )
        return _extract_json(response.text)

    async def run(self, combined_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate the report summary, PDF, markdown, and JSON files.

        Args:
            combined_data: Dict with vision_result, recommendations, and rag_context.

        Returns:
            Dict with report_summary, pdf_path, markdown_path, json_path, timestamp.
        """
        report_summary = await self._generate_report_summary(combined_data)
        combined_data["report_summary"] = report_summary
        combined_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        paths_json = create_report_files(json.dumps(combined_data))
        paths = json.loads(paths_json)

        return {
            "report_summary": report_summary,
            **paths,
        }
