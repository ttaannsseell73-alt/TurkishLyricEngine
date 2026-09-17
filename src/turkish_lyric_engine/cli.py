"""CLI outputs machine-readable reports and uses no network/model access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from . import __version__
from .corpus import CorpusStore, read_jsonl
from .morphology import AnnotationMorphology, ZeyrekMorphology
from .meter import MeterSpec, analyze_meter, parse_durak
from .prosody import ProsodyPolicy, analyze_text
from .rhyme import analyze_pair
from .similarity import check_corpus


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tle", description="TurkishLyricEngine M1 — corpus and text analysis")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Orthographic syllables; melody/stress not evaluated")
    analyze.add_argument("file", type=Path)
    analyze.add_argument("--meter", type=int, default=None)
    analyze.add_argument("--tolerance", type=int, default=1)
    rhyme = commands.add_parser("rhyme", help="Ending comparison with explicit morphology evidence")
    rhyme.add_argument("left")
    rhyme.add_argument("right")
    morphology = rhyme.add_mutually_exclusive_group()
    morphology.add_argument("--annotations", type=Path)
    morphology.add_argument("--zeyrek", action="store_true", help="Use the pinned optional morphology backend")
    meter = commands.add_parser("meter", help="Hece vezni and word-boundary durak analysis")
    meter.add_argument("file", type=Path)
    meter.add_argument("--syllables", type=int, default=None, help="7, 8, 11, 14 or any positive integer; absent = free")
    meter.add_argument("--durak", help="Pause grouping such as 6+5 or 4+4+3")
    ingest = commands.add_parser("ingest", help="Atomically ingest a validated JSONL archive")
    ingest.add_argument("file", type=Path)
    ingest.add_argument("--db", required=True, type=Path)
    stats = commands.add_parser("stats", help="Corpus counts, refrain/ending and phrase statistics")
    stats.add_argument("--db", required=True, type=Path)
    similarity = commands.add_parser("similarity", help="Lexical overlap with only your local corpus")
    similarity.add_argument("file", type=Path)
    similarity.add_argument("--db", required=True, type=Path)
    similarity.add_argument("--top-k", type=int, default=5)
    for command in (analyze, rhyme, meter, ingest, stats, similarity):
        command.add_argument("--output", type=Path, help="Create a report file; refuses to overwrite")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        # Refuse conflicting output paths before mutating an archive.
        if args.output and args.output.exists():
            raise ValueError(f"output already exists: {args.output}")
        if args.output and not args.output.parent.is_dir():
            raise ValueError(f"output directory does not exist: {args.output.parent}")
        if args.command == "analyze":
            result = analyze_text(args.file.read_text(encoding="utf-8-sig"),
                                  ProsodyPolicy(target_syllables=args.meter, tolerance=args.tolerance))
        elif args.command == "rhyme":
            provider = (AnnotationMorphology.from_file(args.annotations) if args.annotations else
                        ZeyrekMorphology() if args.zeyrek else AnnotationMorphology())
            result = analyze_pair(args.left, args.right, provider)
        elif args.command == "meter":
            parts = parse_durak(args.durak) if args.durak else None
            spec = MeterSpec(args.syllables, parts)
            result = analyze_meter(args.file.read_text(encoding="utf-8-sig"), spec)
        elif args.command == "ingest":
            records = read_jsonl(args.file)
            with CorpusStore(args.db) as store:
                result = store.ingest(records)
        elif args.command == "stats":
            with CorpusStore(args.db, create=False) as store:
                result = store.stats()
        else:
            candidate = args.file.read_text(encoding="utf-8-sig")
            with CorpusStore(args.db, create=False) as store:
                result = check_corpus(candidate, store, top_k=args.top_k)
        output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as file:
                file.write(output)
        else:
            print(output, end="")
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
