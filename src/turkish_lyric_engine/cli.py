"""Analysis stays local; generation uses an explicitly configured real model."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sqlite3
import sys

from . import __version__
from .contracts import Brief, validate_song
from .corpus import CorpusStore, read_archive
from .critic import local_audit
from .feedback import FeedbackStore
from .lexicon import RhymeLexicon
from .morphology import AnnotationMorphology, AutoMorphology, ZeyrekMorphology
from .meter import MeterSpec, analyze_meter, parse_durak
from .prosody import ProsodyPolicy, analyze_text
from .rhyme import analyze_pair
from .redif import analyze_redif
from .similarity import check_corpus
from .pipeline import LyricPipeline
from .providers import ReplayProvider
from .settings import load_settings, make_provider


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tle", description="TurkishLyricEngine — Turkish lyric intelligence")
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
    redif = commands.add_parser("redif", help="Equivalent affixes and candidate word redif separately")
    redif.add_argument("left")
    redif.add_argument("right")
    redif.add_argument("--annotations", type=Path)
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
    families = commands.add_parser("rhymes", help="Rhyme dictionary families with phonetic/morphology evidence")
    families.add_argument("word")
    families.add_argument("--dictionary", required=True, type=Path)
    families.add_argument("--syllables", type=int)
    families.add_argument("--limit", type=int, default=20)
    search = commands.add_parser("search", help="Search indexed archive metadata without sending lyrics to models")
    search.add_argument("query")
    search.add_argument("--db", required=True, type=Path)
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--include-text", action="store_true", help="Local research only")
    generate = commands.add_parser("generate", help="Real multi-writer generation and bounded quality loop")
    generate.add_argument("theme")
    generate.add_argument("--out", required=True, type=Path, help="New run directory; refuses existing paths")
    generate.add_argument("--genre")
    generate.add_argument("--mood")
    generate.add_argument("--meter", type=int)
    generate.add_argument("--durak")
    generate.add_argument("--rhyme-scheme", choices=["free", "AABB", "ABAB", "ABCB"])
    generate.add_argument("--concepts", type=int)
    generate.add_argument("--hooks", type=int)
    generate.add_argument("--writers", type=int)
    generate.add_argument("--rounds", type=int)
    generate.add_argument("--target", type=int)
    generate.add_argument("--max-calls", type=int)
    generate.add_argument("--seed", type=int, default=0)
    generate.add_argument("--mechanisms", type=Path)
    preflight = commands.add_parser("preflight", help="Validate provider configuration; performs no model request")
    replay = commands.add_parser("replay", help="Explicit technical fixture playback; never production generation")
    replay.add_argument("--fixture", required=True, type=Path)
    replay.add_argument("--brief", required=True, type=Path)
    replay.add_argument("--out", required=True, type=Path)
    replay.add_argument("--seed", type=int, default=0)
    audit = commands.add_parser("audit", help="Re-run local critics on a structured generation report")
    audit.add_argument("file", type=Path)
    feedback = commands.add_parser("feedback", help="Record real accept/reject/edit feedback and GOLD/RED provenance")
    feedback.add_argument("--run", required=True, type=Path)
    feedback.add_argument("--decision", required=True, choices=["accept", "reject", "edit"])
    feedback.add_argument("--replacement", type=Path)
    feedback.add_argument("--note", default="")
    feedback.add_argument("--feedback-db", required=True, type=Path)
    server = commands.add_parser("serve", help="Local JSON API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--out", required=True, type=Path)
    for command in (generate, preflight, server):
        command.add_argument("--config", type=Path)
    for command in (generate, preflight):
        command.add_argument("--provider", choices=["openai", "compatible", "ollama"])
        command.add_argument("--model")
        command.add_argument("--base-url")
    for command in (generate, replay, audit, feedback, server):
        command.add_argument("--db", type=Path)
    for command in (generate, replay, audit, server):
        command.add_argument("--dictionary", type=Path)
    for command in (generate, replay, server):
        command.add_argument("--feedback-db", type=Path)
    for command in (analyze, rhyme, redif, meter, ingest, stats, similarity, families, search, preflight, audit, feedback):
        command.add_argument("--output", type=Path, help="Create a report file; refuses to overwrite")
    return root


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        # Refuse conflicting output paths before mutating an archive.
        report_output = getattr(args, "output", None)
        if report_output and report_output.exists():
            raise ValueError(f"output already exists: {args.output}")
        if report_output and not report_output.parent.is_dir():
            raise ValueError(f"output directory does not exist: {args.output.parent}")
        if args.command == "analyze":
            result = analyze_text(args.file.read_text(encoding="utf-8-sig"),
                                  ProsodyPolicy(target_syllables=args.meter, tolerance=args.tolerance))
        elif args.command == "rhyme":
            provider = (AnnotationMorphology.from_file(args.annotations) if args.annotations else
                        ZeyrekMorphology() if args.zeyrek else AutoMorphology())
            result = analyze_pair(args.left, args.right, provider)
        elif args.command == "meter":
            parts = parse_durak(args.durak) if args.durak else None
            spec = MeterSpec(args.syllables, parts)
            result = analyze_meter(args.file.read_text(encoding="utf-8-sig"), spec)
        elif args.command == "redif":
            provider = AutoMorphology(AnnotationMorphology.from_file(args.annotations) if args.annotations else None)
            result = analyze_redif(args.left, args.right, provider)
        elif args.command == "ingest":
            records = read_archive(args.file)
            with CorpusStore(args.db) as store:
                result = store.ingest(records)
        elif args.command == "stats":
            with CorpusStore(args.db, create=False) as store:
                result = store.stats()
        elif args.command == "similarity":
            candidate = args.file.read_text(encoding="utf-8-sig")
            with CorpusStore(args.db, create=False) as store:
                result = check_corpus(candidate, store, top_k=args.top_k)
        elif args.command == "rhymes":
            result = {"word": args.word, "family": RhymeLexicon.from_file(args.dictionary).family(args.word, syllables=args.syllables, limit=args.limit)}
        elif args.command == "search":
            with CorpusStore(args.db, create=False) as store:
                result = store.search(args.query, limit=args.limit, include_text=args.include_text)
        elif args.command == "preflight":
            settings = load_settings(args.config)
            provider = make_provider(settings["provider"], overrides={"kind": args.provider, "model": args.model, "base_url": args.base_url})
            result = {"status": "configuration_validated", "provider": provider.name, "model": provider.model,
                      "model_request_performed": False, "credentials_in_report": False}
        elif args.command in {"generate", "replay"}:
            with ExitStack() as stack:
                corpus = stack.enter_context(CorpusStore(args.db, create=False)) if args.db else None
                feedback_store = stack.enter_context(FeedbackStore(args.feedback_db)) if args.feedback_db else None
                lexicon = RhymeLexicon.from_file(args.dictionary) if args.dictionary else None
                if args.command == "replay":
                    provider, judge = ReplayProvider(args.fixture), None
                    values = json.loads(args.brief.read_text(encoding="utf-8"))
                    mechanism_path = None
                else:
                    settings = load_settings(args.config)
                    provider = make_provider(settings["provider"], overrides={"kind": args.provider, "model": args.model, "base_url": args.base_url})
                    judge = make_provider(settings["judge"]) if settings["judge"] else None
                    values = {**settings["generation"], "theme": args.theme}
                    for field, argument in (("genre", "genre"), ("mood", "mood"), ("meter", "meter"), ("rhyme_scheme", "rhyme_scheme"),
                                            ("concept_count", "concepts"), ("hook_count", "hooks"), ("writer_count", "writers"),
                                            ("max_rounds", "rounds"), ("target_score", "target"), ("max_calls", "max_calls")):
                        if getattr(args, argument) is not None:
                            values[field] = getattr(args, argument)
                    if args.durak:
                        values["durak"] = parse_durak(args.durak)
                    mechanism_path = args.mechanisms
                if values.get("durak"):
                    values["durak"] = tuple(values["durak"])
                engine = LyricPipeline(provider, judge=judge, corpus=corpus, lexicon=lexicon, feedback=feedback_store, mechanisms_path=mechanism_path)
                result = engine.generate(Brief(**values), directory=args.out, seed=args.seed)
        elif args.command == "audit":
            report = json.loads(args.file.read_text(encoding="utf-8"))
            brief = Brief(**report["brief"])
            validate_song(report["song"], report["concept"], report["hook"], report["story"], brief.max_chars)
            with ExitStack() as stack:
                corpus = stack.enter_context(CorpusStore(args.db, create=False)) if args.db else None
                lexicon = RhymeLexicon.from_file(args.dictionary) if args.dictionary else None
                result = local_audit(report["song"], brief, corpus=corpus,
                                     morphology=AutoMorphology(lexicon.annotations if lexicon else None), lexicon=lexicon)
        elif args.command == "feedback":
            from .corpus import CorpusRecord
            from .text import words
            report = json.loads(args.run.read_text(encoding="utf-8"))
            if not report.get("live"):
                raise ValueError("technical fixture output cannot be labeled GOLD/RED feedback")
            replacement = args.replacement.read_text(encoding="utf-8") if args.replacement else None
            with FeedbackStore(args.feedback_db) as store:
                identity = store.add(run_id=report["run_id"], genre=report["brief"]["genre"], decision=args.decision,
                                     original=report["lyrics"], replacement=replacement, note=args.note,
                                     mechanism_id=report["concept"]["mechanism_id"], hook_words=len(words(report["hook"]["text"])))
                result = {"feedback_id": identity, "preferences": store.preferences(report["brief"]["genre"])}
            if args.db:
                text = replacement if args.decision == "edit" else report["lyrics"]
                record = CorpusRecord("feedback:" + identity, "red" if args.decision == "reject" else "gold",
                                      report["song"]["title"], text, "user_feedback:" + report["run_id"], "unknown", False)
                with CorpusStore(args.db) as store:
                    result["corpus_ingest"] = store.ingest([record])
        else:
            from .api import serve
            serve(host=args.host, port=args.port, output_root=args.out, corpus_path=args.db, lexicon_path=args.dictionary,
                  feedback_path=args.feedback_db, config=args.config)
            return 0
        output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if report_output:
            with report_output.open("x", encoding="utf-8") as file:
                file.write(output)
        else:
            print(output, end="")
        return 0
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
