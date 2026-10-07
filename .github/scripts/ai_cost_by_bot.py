#!/usr/bin/env python3
"""Rewrite the profile AI block so estimated cost is per model and per bot.

waka-readme-stats ranks ai_model_breakdown by lines written. Grok records
tokens and cost with zero lines, so that ranking prints Grok at 0%. WakaTime
already has ai_model_costs and per-editor ai_model_total_cost. This step runs
after the stats action and replaces the model rows from that payload.
"""

import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

STATS_URL = "https://api.wakatime.com/api/v1/users/current/stats/last_7_days"
ROW_LIMIT = 8


def row(name, text, percent):
    name = name[:25]
    text = text[:20]
    quart = round(max(0.0, min(100.0, percent)) / 4)
    bar = "█" * quart + "░" * (25 - quart)
    return f"{name}{' ' * (25 - len(name))}{text}{' ' * (20 - len(text))}{bar}   {percent:05.2f} %"


def ranked_rows(items, total):
    lines = []
    for name, cost in items[:ROW_LIMIT]:
        lines.append(row(name, f"${cost:,.2f}", round(cost / total * 100, 2)))
    return lines


def cost_body(data):
    total = float(data.get("ai_model_total_cost") or 0)
    if total <= 0:
        raise SystemExit("WakaTime returned no AI cost for this week")

    models = []
    for model in data.get("ai_model_breakdown") or []:
        cost = float(model.get("cost") or 0)
        if cost > 0:
            models.append((model.get("name") or "Unknown", cost))
    models.sort(key=lambda item: item[1], reverse=True)

    bots = []
    for editor in data.get("editors") or []:
        cost = float(editor.get("ai_model_total_cost") or 0)
        if cost > 0:
            bots.append((editor.get("name") or "Unknown", cost))
    bots.sort(key=lambda item: item[1], reverse=True)

    lines = ranked_rows(models, total)
    if bots:
        lines.append("")
        lines.append("💵 Estimated cost by bot:")
        lines.extend(ranked_rows(bots, total))
    return "\n".join(lines)


def rewrite(text, payload):
    data = payload["data"]
    category = next((item for item in data.get("categories") or [] if item.get("name") == "AI Coding"), None)
    if category is not None:
        text = re.sub(
            r"⏱ AI Coding Time: .+",
            f"⏱ AI Coding Time: {category['text']} ({category['percent']}%)",
            text,
            count=1,
        )

    ai_lines = int(data.get("ai_additions") or 0)
    human_lines = int(data.get("human_additions") or 0)
    written = ai_lines + human_lines
    ai_percent = round(ai_lines / written * 100, 2) if written else 0
    text = re.sub(
        r"✍️ [\d,]+ lines written by AI, [\d,]+ lines written by hand \([\d.]+% AI-written\)",
        f"✍️ {ai_lines:,} lines written by AI, {human_lines:,} lines written by hand ({ai_percent}% AI-written)",
        text,
        count=1,
    )
    text = re.sub(
        r"(🔤 )[\d,]+( Input Tokens, )[\d,]+( Output Tokens)",
        rf"\g<1>{int(data.get('ai_input_tokens') or 0):,}\g<2>{int(data.get('ai_output_tokens') or 0):,}\g<3>",
        text,
        count=1,
    )
    cost = float(data.get("ai_model_total_cost") or 0)
    text = re.sub(
        r"(💵 \$)[\d,.]+( Estimated AI Cost This Week)",
        rf"\g<1>{cost:.2f}\g<2>",
        text,
        count=1,
    )
    text = re.sub(
        r"🧠 [\d,]+ AI Sessions, [\d,]+ AI Prompts",
        f"🧠 {int(data.get('ai_sessions') or 0):,} AI Sessions, {int(data.get('ai_prompt_events_total') or 0):,} AI Prompts",
        text,
        count=1,
    )

    sessions = text.find("AI Sessions")
    insights = text.find("AI Coding Insights")
    if sessions < 0 or insights < 0 or insights < sessions:
        raise SystemExit("AI coding block markers not found")
    line_end = text.find("\n", sessions)
    insights_line = text.rfind("\n", 0, insights) + 1
    return text[: line_end + 1] + "\n" + cost_body(data) + "\n\n" + text[insights_line:]


def fetch_stats():
    key = os.environ.get("WAKATIME_API_KEY", "").strip()
    if not key:
        raise SystemExit("WAKATIME_API_KEY is not set")
    token = base64.b64encode(f"{key}:".encode()).decode()
    request = urllib.request.Request(STATS_URL, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} README.md")
    path = Path(sys.argv[1])
    updated = rewrite(path.read_text(), fetch_stats())
    path.write_text(updated)
    # Public profile numbers only. The API key never reaches stdout.
    start = updated.find("💵 Estimated cost by bot:")
    end = updated.find("AI Coding Insights", start)
    print(updated[start:end].rstrip())


if __name__ == "__main__":
    main()
