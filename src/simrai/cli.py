"""
CLI entrypoint for SIMRAI.

Commands:
- queue: run the mood-to-queue pipeline and print a styled table.
- serve: run the FastAPI microservice for remote access.
"""

import typer
from rich.console import Console
from rich.table import Table
import uvicorn

from .pipeline import generate_queue
from .spotify import SpotifyError


app = typer.Typer(help="SIMRAI – Spotify-Induced Music Recommendation AI (mood-to-queue CLI).")


def _bar(value: float, width: int = 8) -> str:
    """Return a simple unstyled bar visualization for a 0–1 value."""
    value = max(0.0, min(1.0, value))
    filled = int(round(value * width))
    empty = width - filled
    return "█" * filled + "·" * empty


@app.command("queue")
def queue(
    mood: str = typer.Argument(..., help="Mood description, e.g. 'rainy midnight drive'"),
    length: int = typer.Option(
        12,
        "--length",
        "-n",
        min=8,
        max=30,
        help="Desired queue length (8–30).",
    ),
    intense: bool = typer.Option(False, "--intense", help="Bias toward higher energy."),
    soft: bool = typer.Option(False, "--soft", help="Bias toward lower energy, gentler vibes."),
) -> None:
    """
    Run the SIMRAI mood-to-queue pipeline and render a styled table.
    """
    console = Console()

    # ASCII-style header inspired by pixel platformers (original art, not Nintendo).
    console.print(
        "[bold red]"
        "╔══════════════════════════════╗\n"
        "║  SIMRAI  ::  PIXEL DJ MODE   ║\n"
        "╚══════════════════════════════╝"
        "[/bold red]"
    )

    with console.status("[bold cyan]Warping pipe... Brewing your queue from the mood...[/bold cyan]"):
        try:
            result = generate_queue(
                mood,
                length=length,
                intense=intense,
                soft=soft,
            )
        except SpotifyError as exc:
            console.print(f"[bold red]Spotify error:[/bold red] {exc}")
            raise typer.Exit(1)
        except Exception as exc:  # pragma: no cover - safety net
            console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
            raise typer.Exit(1)

    if not result.tracks:
        console.print("[bold yellow]No suitable tracks found for that mood.[/bold yellow]")
        console.print(f"[dim]{result.summary}[/dim]")
        raise typer.Exit(0)

    # Header with interpreted mood vector.
    console.print(
        f"[bold cyan]Mood:[/bold cyan] {result.mood_text!r}  "
        f"[magenta]Valence[/magenta]: {result.mood_vector.valence:.2f}  "
        f"[magenta]Energy[/magenta]: {result.mood_vector.energy:.2f}"
    )

    table = Table(title=f"SIMRAI Queue – {mood!r}", show_lines=False)
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("Track", style="bold")
    table.add_column("Artist", style="magenta")
    table.add_column("Valence", justify="right")
    table.add_column("Energy", justify="right")
    table.add_column("URI", style="dim")

    for idx, track in enumerate(result.tracks, start=1):
        uri_snippet = track.uri
        if len(uri_snippet) > 32:
            uri_snippet = uri_snippet[:29] + "..."
        v_cell = f"{track.valence:.2f} [gold1]{_bar(track.valence)}[/gold1]"
        e_cell = f"{track.energy:.2f} [red1]{_bar(track.energy)}[/red1]"
        table.add_row(
            str(idx),
            track.name,
            track.artists,
            v_cell,
            e_cell,
            uri_snippet,
        )

    console.print(table)

    # Highlight fallback vs fully featured pipeline.
    if "Audio features endpoint is unavailable" in result.summary:
        console.print("[black on yellow] MODE: METADATA-ONLY (audio features blocked) [/]")
        console.print(f"[yellow]{result.summary}[/yellow]")
    else:
        console.print("[black on green] MODE: FULL FEATURES [/]")
        console.print(f"[green]{result.summary}[/green]")


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind the SIMRAI API server to."),
    port: int = typer.Option(8000, help="Port to bind the SIMRAI API server to."),
    reload: bool = typer.Option(False, help="Enable auto-reload (development only)."),
) -> None:
    """
    Run the SIMRAI FastAPI microservice.

    Example:
        simrai serve --host 0.0.0.0 --port 8000
    """
    uvicorn.run(
        "simrai.api:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()


