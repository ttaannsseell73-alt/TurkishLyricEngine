"""Real provider-backed generation with immutable locks and bounded revision."""
from __future__ import annotations

from copy import deepcopy
from . import __version__
from .cliche import ClicheDetector

from .concept_engine import ConceptEngine
from .contracts import Brief, fingerprint, render_song
from .critic import SemanticCoherenceEngine, combine_audit, local_audit, rhyme_plan
from .hook_lab import HookLab
from .lyric_writer import LyricWriter, canonical_coordinate
from .mechanisms import load_mechanisms
from .morphology import AutoMorphology
from .providers import ProviderError
from .stages import Journal, StageRunner
from .story_engine import StoryEngine


def _preference_adjustment(mechanism, preferences):
    accepts = preferences.get("mechanism_accepts", {}).get(mechanism, 0)
    rejects = preferences.get("mechanism_rejects", {}).get(mechanism, 0)
    return (accepts - rejects) / (accepts + rejects + 3)


def _rank_audit(entry):
    audit = entry["audit"]
    return (audit["target_met"], -audit["local"]["hard_failures"], audit["score"], -entry.get("writer", 0))


class LyricPipeline:
    def __init__(self, provider, *, judge=None, corpus=None, lexicon=None, feedback=None, morphology=None,
                 mechanisms_path=None):
        self.provider, self.judge, self.corpus = provider, judge, corpus
        self.lexicon, self.feedback = lexicon, feedback
        self.morphology = morphology or AutoMorphology(lexicon.annotations if lexicon else None)
        self.mechanisms = load_mechanisms(mechanisms_path)
        self.cliche = ClicheDetector(corpus)

    def generate(self, brief: Brief, *, directory=None, seed: int = 0) -> dict:
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        minimum = 5 + 2*brief.writer_count
        if brief.max_calls < minimum:
            raise ValueError(f"max_calls must be at least {minimum} for the requested tournament")
        journal = Journal(directory)
        runner = StageRunner(self.provider, self.judge, brief.max_calls, journal)
        manifest = {"engine_version": __version__, "brief": brief.to_dict(), "seed": seed, "provider": self.provider.name,
                    "model": self.provider.model, "judge_model": (self.judge or self.provider).model,
                    "judge_relationship": "separately_configured_provider" if self.judge else "same_provider_separate_call",
                    "live": self.provider.live and (self.judge or self.provider).live,
                    "mechanisms_hash": fingerprint(self.mechanisms),
                    "determinism": "fixture_replay" if not self.provider.live else "model_service_not_guaranteed",
                    "raw_archive_in_prompt": False}
        manifest["run_id"] = fingerprint(manifest)
        manifest["status"] = "running"
        journal.save("run", manifest)
        try:
            result = self._run(brief, runner, seed)
            result["brief"] = brief.to_dict()
            result.update({"run_id": manifest["run_id"], "live": manifest["live"], "calls": len(runner.calls),
                           "call_limit": brief.max_calls, "determinism": manifest["determinism"],
                           "judge_relationship": manifest["judge_relationship"]})
            if not manifest["live"]:
                result["status"] = "demo_only_fixture_replay"
                result["generated_via_configured_provider"] = False
            else:
                result["generated_via_configured_provider"] = True
            journal.save("final", result)
            journal.lyrics(result["lyrics"])
            manifest["status"] = result["status"]
            journal.save("run", manifest)
            return result
        except (ValueError, OSError) as exc:
            manifest["status"] = "failed"
            manifest["failure_type"] = type(exc).__name__
            manifest["error"] = str(exc)[:800]
            journal.save("run", manifest)
            raise

    def _run(self, brief, runner, seed):
        knowledge = self.corpus.knowledge() if self.corpus else {"status": "no_corpus", "documents": 0}
        preferences = self.feedback.preferences(brief.genre) if self.feedback else {"status": "no_user_feedback"}
        runner.journal.save("knowledge", knowledge)
        runner.journal.save("preferences", preferences)
        concept_engine, hook_lab, story_engine = ConceptEngine(), HookLab(), StoryEngine()
        writer, semantic = LyricWriter(), SemanticCoherenceEngine()
        concepts = concept_engine.generate(runner, brief, self.mechanisms, knowledge, preferences)
        ranked = concept_engine.evaluate(runner, brief, concepts, preferences)
        for row in ranked:
            row["preference_adjustment"] = round(_preference_adjustment(row["concept"]["mechanism_id"], preferences), 4)
        ranked.sort(key=lambda row: (-(row["score"]+row["preference_adjustment"]), row["id"]))
        concept = ranked[0]["concept"]
        runner.journal.save("concept_candidates", concepts)
        runner.journal.save("concept_rankings", ranked)
        runner.journal.save("concept_lock", {"concept": concept, "hash": fingerprint(concept)})
        hooks = hook_lab.generate(runner, brief, concept)
        hook_rankings = hook_lab.evaluate(runner, brief, concept, hooks)
        runner.journal.save("hook_candidates", hooks)
        runner.journal.save("hook_rankings", hook_rankings)
        eligible = [row for row in hook_rankings if row["metrics"]["eligible"]]
        if not eligible:
            raise ProviderError("no hook passed length/pronunciation/requested-meter checks")
        history, all_drafts, best, rounds, reselected = [], [], None, 0, 0

        def audit(song, hook, story):
            local = local_audit(song, brief, morphology=self.morphology, corpus=self.corpus, lexicon=self.lexicon, cliche=self.cliche)
            judge = semantic.evaluate(runner, brief, concept, hook, story, song, local)
            return combine_audit(local, judge, brief.target_score)

        for candidate in eligible[:3]:
            hook = candidate["hook"]
            plan = rhyme_plan(brief, self.lexicon, hook, concept)
            runner.journal.save("rhyme_plan", plan)
            runner.journal.save("hook_lock", {"hook": hook, "hash": fingerprint(hook)})
            # Every reselection starts a fresh story; it never mutates a locked draft.
            story = story_engine.plan(runner, brief, concept, hook)
            runner.journal.save("story_lock", {"story": story, "hash": fingerprint(story)})
            drafts = []
            for index in range(brief.writer_count):
                song = writer.draft(runner, brief, concept, hook, story, index + seed % 5, plan)
                entry = {"writer": index, "hook_id": hook["id"], "song": song, "audit": audit(song, hook, story), "story": story, "hook": hook}
                drafts.append(entry)
                all_drafts.append(entry)
                runner.journal.save("drafts", all_drafts)
            current = max(drafts, key=_rank_audit)
            if best is None or _rank_audit(current) > _rank_audit(best):
                best = deepcopy(current)
            while not current["audit"]["target_met"] and rounds < brief.max_rounds:
                issues = current["audit"]["issues"]
                frozen_issues = [i for i in issues if canonical_coordinate(i["section_id"], i["line"]) == ("chorus", 1)]
                if any(i.get("hard") for i in frozen_issues) or current["audit"]["semantic"]["dimensions"]["hook_strength"] < brief.target_score:
                    break
                mutable = [i for i in issues if canonical_coordinate(i["section_id"], i["line"]) != ("chorus", 1)]
                if not mutable:
                    break
                if len(runner.calls) + 2 > brief.max_calls:
                    break
                rounds += 1
                revised = writer.revise(runner, brief, current["song"], concept, hook, story, mutable, plan)
                revised_audit = audit(revised, hook, story)
                changed = {"writer": current["writer"], "hook_id": hook["id"], "song": revised,
                           "audit": revised_audit, "story": story, "hook": hook}
                history.append({"round": rounds, "before_score": current["audit"]["score"],
                                "after_score": revised_audit["score"], "reported_issues": mutable,
                                "changed_song_hash": fingerprint(revised), "audit": revised_audit})
                runner.journal.save("revisions", history)
                runner.journal.save("latest_revision", changed)
                # Keep the strongest valid draft, while allowing another corrective round from this one.
                current = changed
                if _rank_audit(current) > _rank_audit(best):
                    best = deepcopy(current)
            if best["audit"]["target_met"]:
                break
            frozen_problem = any(i.get("hard") and canonical_coordinate(i["section_id"], i["line"]) == ("chorus", 1)
                                 for i in current["audit"]["issues"])
            frozen_problem |= current["audit"]["semantic"]["dimensions"]["hook_strength"] < brief.target_score
            if not frozen_problem or len(runner.calls) + 1 + 2*brief.writer_count > brief.max_calls:
                break
            reselected += 1
        if best is None:
            raise ProviderError("no validated draft was produced")
        return {"status": best["audit"]["decision"], "song": best["song"], "lyrics": render_song(best["song"]),
                "concept": concept, "hook": best["hook"], "story": best["story"], "audit": best["audit"],
                "top_concepts": ranked[:5], "top_hooks": hook_rankings[:5], "revision_rounds": rounds,
                "hook_reselections": reselected, "writer_candidates": len(all_drafts),
                "corpus_status": knowledge["status"], "user_feedback_status": preferences["status"],
                "acceptance": "requires_human_lyric_review", "melodic_prosody": "not_evaluated_without_melody",
                "copyright_verdict": None}
