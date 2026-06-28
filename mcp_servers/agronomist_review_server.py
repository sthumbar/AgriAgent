#!/usr/bin/env python3
"""
Agronomist Review MCP Server

Exposes the review queue as MCP tools over stdio so any MCP client
(Claude Code, ADK MCPToolset, curl, etc.) can submit and manage reviews.

Run standalone:
    python mcp_servers/agronomist_review_server.py

Connect from Google ADK via MCPToolset:
    MCPToolset(StdioServerParameters(
        command="python",
        args=["mcp_servers/agronomist_review_server.py"],
    ))
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from tools.review_tool import (
    submit_for_review,
    get_review_status,
    get_full_analysis,
    add_expert_note,
    list_pending_reviews,
    list_all_reviews,
)

server = Server("agronomist-review")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="submit_for_review",
            description=(
                "Submit a low-confidence crop analysis to the agronomist review queue. "
                "Returns a review_id to track status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Filesystem path to the crop image",
                    },
                    "analysis_json": {
                        "type": "string",
                        "description": "Full pipeline result dict serialised as a JSON string",
                    },
                },
                "required": ["image_path", "analysis_json"],
            },
        ),
        types.Tool(
            name="get_review_status",
            description="Check the current status (pending / approved / rejected) of a review.",
            inputSchema={
                "type": "object",
                "properties": {
                    "review_id": {"type": "string", "description": "ID returned by submit_for_review"},
                },
                "required": ["review_id"],
            },
        ),
        types.Tool(
            name="add_expert_note",
            description=(
                "Record an agronomist decision on a pending review. "
                "Optionally supply corrected crop / disease names."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "review_id":         {"type": "string"},
                    "note":              {"type": "string", "description": "Expert observations"},
                    "action":            {
                        "type": "string",
                        "enum": ["approved", "rejected", "needs_more_info"],
                    },
                    "reviewer":          {"type": "string", "description": "Reviewer name or ID"},
                    "corrected_crop":    {"type": "string", "description": "Override AI crop name"},
                    "corrected_disease": {"type": "string", "description": "Override AI disease name"},
                },
                "required": ["review_id", "note", "action"],
            },
        ),
        types.Tool(
            name="get_full_analysis",
            description="Return the complete stored analysis JSON for a review (used to resume the pipeline after approval).",
            inputSchema={
                "type": "object",
                "properties": {
                    "review_id": {"type": "string"},
                },
                "required": ["review_id"],
            },
        ),
        types.Tool(
            name="list_pending_reviews",
            description="List all analyses currently awaiting agronomist review.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="list_all_reviews",
            description="List all reviews regardless of status (most recent first).",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max rows to return (default 50)"},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "submit_for_review":
            analysis = json.loads(arguments["analysis_json"])
            review_id = submit_for_review(arguments["image_path"], analysis)
            result = {
                "review_id": review_id,
                "status": "pending",
                "message": "Queued for agronomist review. Pipeline paused until approved.",
            }

        elif name == "get_review_status":
            result = get_review_status(arguments["review_id"])

        elif name == "add_expert_note":
            result = add_expert_note(
                review_id=arguments["review_id"],
                note=arguments["note"],
                action=arguments["action"],
                reviewer=arguments.get("reviewer", "agronomist"),
                corrected_crop=arguments.get("corrected_crop", ""),
                corrected_disease=arguments.get("corrected_disease", ""),
            )

        elif name == "get_full_analysis":
            result = get_full_analysis(arguments["review_id"])

        elif name == "list_pending_reviews":
            reviews = list_pending_reviews()
            result = {"count": len(reviews), "reviews": reviews}

        elif name == "list_all_reviews":
            reviews = list_all_reviews(limit=arguments.get("limit", 50))
            result = {"count": len(reviews), "reviews": reviews}

        else:
            result = {"error": f"Unknown tool: {name!r}"}

    except Exception as exc:
        result = {"error": str(exc)}

    return [types.TextContent(type="text", text=json.dumps(result, default=str, indent=2))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
