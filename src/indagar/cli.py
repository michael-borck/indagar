from __future__ import annotations

import asyncio
from dataclasses import replace
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Settings
from .estimate import cost_for_tokens, estimate_run
from .llm.base import LLM_ROLES, LLMError
from .llm.factory import build_llm, build_llms
from .research.deep import run_deep_research
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
        return __version__


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
    selected = settings.selected_llm_provider()
    if selected:
        models = ", ".join(
            f"{role}={settings.llm_model_for(role) or 'unset'}" for role in LLM_ROLES
        )
        console.print(f"LLM provider: {selected}")
        console.print(f"LLM models: {models}")
        if not any(settings.llm_model_for(role) for role in LLM_ROLES):
            console.print(
                "[yellow]Set INDAGAR_LLM_MODEL or a role-specific model to use the LLM.[/yellow]"
            )
    else:
        console.print("LLM provider: none")
        console.print(
            "[dim]Set ANTHROPIC_API_KEY or OPENAI_API_KEY/OPENAI_BASE_URL to "
            "enable LLM commands.[/dim]"
        )
    console.print(
        f"Budgets: sources={settings.max_sources}, "
        f"seconds={settings.max_seconds}, search_limit={settings.search_limit}, "
        f"depth={settings.max_depth}, retries={settings.llm_max_retries}, "
        f"min_interval={settings.llm_min_interval}s, "
        f"llm_max_tokens={settings.llm_max_tokens}"
    )
    if not configured:
        console.print(
            "[yellow]No search provider configured. Set FIRECRAWL_URL, "
            "BRAVE_API_KEY, SERPER_API_KEY, or SEARXNG_URL.[/yellow]"
        )


@app.command("llm")
def llm_prompt(
    prompt: str = typer.Argument(..., help="Prompt to send"),
    role: str = typer.Option("writer", "--role", help="planner, reader, or writer"),
    model: str | None = typer.Option(None, "--model", help="Override the configured model"),
    system: str = typer.Option(
        "You are Indagar, a careful research assistant. Answer concisely and never invent sources.",
        "--system",
        help="System prompt",
    ),
    max_tokens: int = typer.Option(0, "--max-tokens", min=0, help="0 uses the configured default"),
    temperature: float | None = typer.Option(None, "--temperature", min=0.0, max=2.0),
    json_mode: bool = typer.Option(False, "--json", help="Ask for JSON output"),
) -> None:
    """Send one prompt to the configured LLM as a smoke test."""
    settings = _settings_or_exit()
    role = role.lower()
    if role not in LLM_ROLES:
        console.print(f"[red]Unknown role: {role}. Use {', '.join(LLM_ROLES)}.[/red]")
        raise typer.Exit(2)

    try:
        provider = build_llm(settings, role=role, model=model)
        response = asyncio.run(
            provider.complete(
                prompt,
                system=system,
                max_tokens=max_tokens or None,
                temperature=temperature,
                json_mode=json_mode,
            )
        )
    except LLMError as exc:
        console.print(f"[red]LLM request failed: {exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(response.text, markup=False)
    usage: list[str] = []
    if response.input_tokens is not None:
        usage.append(f"in={response.input_tokens}")
    if response.output_tokens is not None:
        usage.append(f"out={response.output_tokens}")
    detail = f"[dim]{response.provider} · {response.model}"
    if usage:
        detail += f" · {' '.join(usage)}"
    detail += "[/dim]"
    console.print(detail)


@app.command()
def estimate(
    question: str = typer.Argument(..., help="Question or topic to estimate"),
    llm: bool = typer.Option(True, "--llm/--no-llm", help="Include LLM calls"),
    depth: int | None = typer.Option(None, "--depth", min=0, max=2),
    max_sources: int = typer.Option(0, "--max-sources", min=0, help="0 uses INDAGAR_MAX_SOURCES"),
) -> None:
    """Print a rough pre-run budget estimate without calling any provider."""
    settings = _settings_or_exit()
    try:
        result = estimate_run(
            question,
            settings,
            max_sources=max_sources or None,
            depth=depth,
            llm=llm,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    table = Table(title="Run estimate")
    table.add_column("Item")
    table.add_column("Value", justify="right")
    table.add_row("Searches", str(result.searches))
    table.add_row("Sources", str(result.sources))
    table.add_row("LLM calls", str(result.llm_calls))
    table.add_row("Input tokens", f"~{result.input_tokens:,}")
    table.add_row("Output tokens", f"~{result.output_tokens:,}")
    if result.cost_usd is not None:
        table.add_row("Estimated cost", f"~${result.cost_usd:.4f}")
    console.print(table)
    if result.llm_calls and result.cost_usd is None:
        console.print(
            "[dim]Set INDAGAR_INPUT_COST_PER_MTOK and "
            "INDAGAR_OUTPUT_COST_PER_MTOK for a dollar estimate.[/dim]"
        )
    console.print("[dim]Rough upper bound; actual usage is recorded in the run.[/dim]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
) -> None:
    """Serve the local web UI and API."""
    try:
        import uvicorn
    except ImportError as exc:
        console.print("[red]Install the web extra: pip install 'indagar[web]'[/red]")
        raise typer.Exit(1) from exc
    from .web.app import create_app

    console.print(f"Indagar web UI: http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port)


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
    llm: bool = typer.Option(
        False,
        "--llm",
        help="Use configured LLMs for planning, reading, gap checks, and synthesis",
    ),
    depth: int | None = typer.Option(
        None,
        "--depth",
        min=0,
        max=2,
        help="Follow-up rounds for --llm; 0 disables",
    ),
    max_sources: int = typer.Option(0, "--max-sources", min=0, help="0 uses INDAGAR_MAX_SOURCES"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Markdown output path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the estimate and exit"),
) -> None:
    """Plan sub-questions, search, and write a source dossier or cited report."""
    settings = _settings_or_exit()
    if max_sources:
        settings = replace(settings, max_sources=max_sources)

    try:
        estimate = estimate_run(question, settings, depth=depth, llm=llm)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    if llm or dry_run:
        console.print(estimate.line())
    if dry_run:
        return

    try:
        if llm:
            llms = build_llms(settings)
            run = asyncio.run(
                run_deep_research(
                    question,
                    settings,
                    llms=llms,
                    depth=depth,
                )
            )
        else:
            run = asyncio.run(run_research(question, settings))
    except (LLMError, RuntimeError, ValueError) as exc:
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

    if run.citations:
        console.print(f"Citations: {len(run.citations)}")
    if run.reads:
        console.print(f"Sources read: {len(run.reads)}")
    if run.usage:
        calls = sum(item.calls for item in run.usage)
        input_tokens = sum(item.input_tokens for item in run.usage)
        output_tokens = sum(item.output_tokens for item in run.usage)
        console.print(f"LLM usage: {calls} calls · {input_tokens} in / {output_tokens} out")
        cost = cost_for_tokens(input_tokens, output_tokens, settings)
        if cost is not None:
            console.print(f"Token cost: ${cost:.4f}")

    json_path, markdown_path = save_run(run, out=out)
    console.print(f"Run record: {json_path}")
    console.print(f"Markdown: {markdown_path}")


def main() -> None:
    app()


__all__ = ["app", "main"]
