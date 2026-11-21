from __future__ import annotations

import asyncio
from dataclasses import replace
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings
from .research.loop import run_research
from .search.chain import build_chain
from .store import save_run

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Indagar — deep research from the command line.",
)
console = Console()


def _version() -> str:
    try:
        return package_version("indagar")
    except PackageNotFoundError:
        return "0.1.0"


def _settings_or_exit() -> Settings:
    return Settings.from_env()


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(_version())


@app.command()
def doctor() -> None:
    """Show configured search and LLM providers and the current budgets."""
    settings = _settings_or_exit()
    configured = settings.configured_search_providers()

    console.print("[bold]Indagar doctor[/bold]")
    console.print(f"Search order: {', '.join(settings.search_order)}")
    console.print(f"Configured search: {', '.join(configured) or 'none'}")
    console.print(f"LLM providers: {', '.join(settings.llm_providers()) or 'none'}")
    console.print(
        f"Budgets: sources={settings.max_sources}, "
        f"seconds={settings.max_seconds}, search_limit={settings.search_limit}"
    )
    if not configured:
        console.print(
            "[yellow]No search provider configured. Set FIRECRAWL_URL, "
            "BRAVE_API_KEY, SERPER_API_KEY, or SEARXNG_URL.[/yellow]"
        )


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(8, "--limit", "-n", min=1, max=20),
) -> None:
    """Run the configured search chain and print the results."""
    settings = _settings_or_exit()
    chain = build_chain(settings)
    if not chain.providers:
        console.print("[red]No search provider configured.[/red]")
        raise typer.Exit(1)

    try:
        outcome = asyncio.run(chain.search(query, limit=limit))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        console.print(f"[red]Search failed: {exc}[/red]")
        raise typer.Exit(1) from exc

    table = Table(title=f"Search: {query}", show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Title", overflow="fold")
    table.add_column("Domain", style="cyan")
    table.add_column("Provider", style="green")
    for index, source in enumerate(outcome.sources, start=1):
        table.add_row(str(index), source.title, source.domain, source.provider)
    console.print(table)

    for attempt in outcome.attempts:
        detail = f" — {attempt.error}" if attempt.error else ""
        console.print(
            f"[dim]{attempt.provider}: {attempt.status} "
            f"({attempt.count}, {attempt.latency_ms}ms){detail}[/dim]"
        )
    if not outcome.sources:
        console.print("[yellow]No results.[/yellow]")


@app.command()
def research(
    question: str = typer.Argument(..., help="Question or topic to research"),
    max_sources: int = typer.Option(0, "--max-sources", min=0, help="0 uses INDAGAR_MAX_SOURCES"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Markdown output path"),
) -> None:
    """Plan sub-questions, search, and write a source dossier."""
    settings = _settings_or_exit()
    if max_sources:
        settings = replace(settings, max_sources=max_sources)

    try:
        run = asyncio.run(run_research(question, settings))
    except (RuntimeError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(f"[bold]Plan[/bold] ({len(run.plan.sub_questions)} sub-questions)")
    for index, sub_question in enumerate(run.plan.sub_questions, start=1):
        console.print(f"  {index}. {sub_question.question}")

    table = Table(title=f"Sources: {len(run.sources)}")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Title", overflow="fold")
    table.add_column("Domain", style="cyan")
    table.add_column("Provider", style="green")
    for index, source in enumerate(run.sources, start=1):
        table.add_row(str(index), source.title, source.domain, source.provider)
    console.print(table)

    json_path, markdown_path = save_run(run, out=out)
    console.print(f"Run record: {json_path}")
    console.print(f"Dossier: {markdown_path}")


def main() -> None:
    app()


__all__ = ["app", "main"]
