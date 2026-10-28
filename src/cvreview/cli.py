"""cvreview CLI — Typer application (plan §22)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console  # typer pulls rich on install? (fallback below)

from cvreview.ingestion.packet import ingest_packet
from cvreview.settings import RAW_DIR

app = typer.Typer(help="Candidate document review pipeline (Increment 1: ingestion).")
console = Console()
try:
    from rich.table import Table
    _HAS_RICH = True
except ImportError:  # pragma: no cover
    _HAS_RICH = False


@app.command()
def ingest(
    pdf: Path = typer.Argument(..., exists=True, dir_okay=False,
                               help="Path to the candidate packet PDF."),
    no_png: bool = typer.Option(False, help="Skip writing page PNGs."),
) -> None:
    """Ingest one candidate packet: classify pages, capture provenance."""
    packet = ingest_packet(pdf, write_pngs=not no_png)
    _print_summary(packet)


@app.command("ingest-folder")
def ingest_folder(
    folder: Path = typer.Argument(RAW_DIR, exists=True, file_okay=False),
    no_png: bool = typer.Option(False, help="Skip writing page PNGs."),
) -> None:
    """Ingest every PDF in a folder (default: data/raw)."""
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        typer.echo(f"No PDFs found in {folder}")
        raise typer.Exit(1)
    for pdf in pdfs:
        packet = ingest_packet(pdf, write_pngs=not no_png)
        _print_summary(packet)


def _print_summary(packet) -> None:
    typer.echo(f"\nPacket {packet.packet_id}  ({len(packet.pages)} pages, "
               f"{len(packet.documents)} documents)")
    if _HAS_RICH:
        table = Table(show_header=True)
        table.add_column("Page")
        table.add_column("Type")
        table.add_column("Text")
        table.add_column("Flags")
        for p in packet.pages:
            table.add_row(
                str(p.page_number), p.page_type.value, p.source_text.source,
                ",".join(p.flags) or "-",
            )
        console.print(table)
    else:  # pragma: no cover
        for p in packet.pages:
            typer.echo(f"  p{p.page_number}: {p.page_type.value} "
                       f"[{p.source_text.source}] {' '.join(p.flags)}")
    for g in packet.duplicate_groups:
        typer.echo(f"  duplicates: {g.group_id} {g.doc_ids} ({g.basis}"
                   f"{f', sim={g.similarity}' if g.similarity else ''})")
    for w in packet.warnings:
        typer.echo(f"  ⚠ {w}")


def main() -> None:  # entry point
    app()


if __name__ == "__main__":
    main()
