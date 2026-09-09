#!/usr/bin/env python3
"""CLI entry point.

Usage:
    python cli.py analyze <url> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

load_dotenv()

from app.analyzer import analyze_url  # noqa: E402
from app.models import CategoryResult, Report  # noqa: E402
from app.scraper import FetchError  # noqa: E402

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

GRADE_COLORS = {"A": "green", "B": "green", "C": "yellow", "D": "orange3", "F": "red"}


def render_json(report: Report) -> None:
    print(report.model_dump_json(indent=2))


def render_rich(report: Report) -> None:
    console = Console()
    console.print(Panel.fit(
        f"[bold]{report.final_url}[/bold]\n"
        f"Overall: [bold {GRADE_COLORS[report.overall_grade]}]{report.overall_score}/100 "
        f"({report.overall_grade})[/bold {GRADE_COLORS[report.overall_grade]}]  "
        f"|  GEO scoring via: {report.llm_provider}",
        title="Web Vitals & Search Visibility Report",
    ))

    if report.content_warning:
        console.print(Panel(report.content_warning, title="⚠ Content Warning", border_style="bold yellow"))

    for result in (report.seo, report.aeo, report.geo):
        console.print(_category_table(result))

    console.print(Panel(
        "\n".join(f"{i+1}. {action}" for i, action in enumerate(report.top_actions)) or "No high-priority issues found.",
        title="Top Actions -- Do These First",
        border_style="bold cyan",
    ))


def _category_table(result: CategoryResult) -> Table:
    color = GRADE_COLORS[result.grade]
    table = Table(
        title=f"{result.category}  --  {result.score}/100 ({result.grade})",
        title_style=f"bold {color}",
        show_lines=False,
    )
    table.add_column("✓", width=3)
    table.add_column("Check")
    table.add_column("Detail", overflow="fold")
    for f in result.findings:
        mark = "[green]✓[/green]" if f.passed else "[red]✗[/red]"
        table.add_row(mark, f.check, f.detail)
    return table


def render_plain(report: Report) -> None:
    print(f"{report.final_url}")
    print(f"Overall: {report.overall_score}/100 ({report.overall_grade})  |  GEO scoring via: {report.llm_provider}\n")
    if report.content_warning:
        print(f"WARNING: {report.content_warning}\n")
    for result in (report.seo, report.aeo, report.geo):
        print(f"== {result.category}: {result.score}/100 ({result.grade}) ==")
        for f in result.findings:
            mark = "PASS" if f.passed else "FAIL"
            print(f"  [{mark}] {f.check} -- {f.detail}")
        print()
    print("Top Actions:")
    for i, action in enumerate(report.top_actions, 1):
        print(f"  {i}. {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-powered SEO/AEO/GEO visibility analyzer")
    parser.add_argument("command", choices=["analyze"])
    parser.add_argument("url", help="Target URL to analyze")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of a formatted report")
    args = parser.parse_args()

    try:
        report = analyze_url(args.url)
    except FetchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        render_json(report)
    elif HAS_RICH:
        render_rich(report)
    else:
        render_plain(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
