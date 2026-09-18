from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from turkish_lyric_engine.contracts import Brief, fingerprint, validate_candidates, validate_song
from turkish_lyric_engine.critic import combine_audit, local_audit, validate_semantic
from turkish_lyric_engine.hook_lab import hook_metrics
from turkish_lyric_engine.lyric_writer import apply_patches
from turkish_lyric_engine.morphology import AutoMorphology
from turkish_lyric_engine.pipeline import LyricPipeline
from turkish_lyric_engine.providers import ProviderError, ReplayProvider

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def fixtures():
    rows = json.loads((EXAMPLES / 'replay_run.json').read_text(encoding='utf-8'))
    brief = Brief(**json.loads((EXAMPLES / 'replay_brief.json').read_text(encoding='utf-8')))
    return rows, brief


def objects():
    rows, brief = fixtures()
    return rows[0]['response']['concepts'][0], rows[2]['response']['hooks'][0], rows[4]['response'], rows[5]['response'], brief


class RecordingReplay:
    name, model, live = 'test-replay', 'explicit-fixture', False

    def __init__(self, rows):
        self.rows, self.requests = deepcopy(rows), []

    def complete(self, stage, system, payload, schema):
        self.requests.append((stage, deepcopy(payload)))
        if not self.rows:
            raise ProviderError('fixture exhausted')
        row = self.rows.pop(0)
        if row['stage'] != stage:
            raise ProviderError('fixture stage mismatch')
        return deepcopy(row['response'])


class GenerationTests(unittest.TestCase):
    def test_low_technical_dimension_cannot_be_hidden_by_average(self):
        rows,brief=fixtures()
        local=local_audit(rows[5]['response'],brief,morphology=AutoMorphology(use_zeyrek=False))
        local['dimensions']['rhyme']=50
        combined=combine_audit(local,rows[10]['response'],80)
        self.assertGreater(combined['score'],80)
        self.assertFalse(combined['target_met'])

    def test_max_rounds_is_a_hard_limit_for_unimproved_output(self):
        rows, brief = fixtures()
        brief = Brief(**{**brief.to_dict(),'writer_count':1,'max_rounds':6})
        sequence = deepcopy(rows[:7])
        for index in range(6):
            sequence.append({'stage':'revision','response':{'patches':[{'section_id':'verse1','line':1,
                'text':'Bugün yine kendimi unuttum' if index % 2 == 0 else 'Bugün kendimi biraz erteledim'}]}})
            sequence.append(deepcopy(rows[6]))
        result = self.pipeline(RecordingReplay(sequence)).generate(brief)
        self.assertEqual(result['revision_rounds'],6)
        self.assertEqual(result['calls'],19)
        self.assertFalse(result['audit']['target_met'])

    def test_weak_locked_hook_is_reselected_with_a_new_story(self):
        rows, brief = fixtures()
        brief = Brief(**{**brief.to_dict(),'writer_count':1})
        sequence = deepcopy(rows[:7])
        sequence[-1]['response']['dimensions']['natural_turkish']=94
        sequence[-1]['response']['dimensions']['hook_strength']=50
        sequence[-1]['response']['issues']=[{'section_id':'chorus','line':1,'reason':'weak hook fixture','suggestion':'Reselect hook.'}]
        story = deepcopy(rows[4]['response'])
        story['hook_id']='h02'
        song = deepcopy(rows[5]['response'])
        song['hook_id']='h02'
        song['story_hash']=fingerprint(story)
        for index in (2,5,7):
            song['sections'][index]['lines'][0]=rows[2]['response']['hooks'][1]['text']
        sequence.extend([{'stage':'story','response':story},{'stage':'draft','response':song},deepcopy(rows[10])])
        result=self.pipeline(RecordingReplay(sequence)).generate(brief)
        self.assertEqual(result['hook']['id'],'h02')
        self.assertEqual(result['story']['hook_id'],'h02')
        self.assertEqual(result['hook_reselections'],1)
        self.assertTrue(result['audit']['target_met'])

    def pipeline(self, provider):
        return LyricPipeline(provider, morphology=AutoMorphology(use_zeyrek=False))

    def test_bounded_revision_changes_reported_line_and_improves_score(self):
        rows, brief = fixtures()
        provider = RecordingReplay(rows)
        result = self.pipeline(provider).generate(brief)
        self.assertEqual(result['status'], 'demo_only_fixture_replay')
        self.assertFalse(result['live'])
        self.assertEqual(result['calls'], 11)
        self.assertEqual(result['revision_rounds'], 1)
        self.assertEqual(result['song']['sections'][0]['lines'][0], 'Bugün yine kendimi unuttum')
        revision_payload = [payload for stage, payload in provider.requests if stage == 'revision'][0]
        self.assertIn(['verse1', 1], [list(c) for c in revision_payload['allowed_coordinates']])
        self.assertEqual(result['song']['story_hash'], fingerprint(result['story']))
        self.assertTrue(result['audit']['target_met'])
        self.assertEqual(result['hook']['text'], result['song']['sections'][2]['lines'][0])

    def test_fixture_replay_is_deterministic(self):
        _, brief = fixtures()
        first = self.pipeline(ReplayProvider(EXAMPLES / 'replay_run.json')).generate(brief, seed=42)
        second = self.pipeline(ReplayProvider(EXAMPLES / 'replay_run.json')).generate(brief, seed=42)
        self.assertEqual(first, second)

    def test_model_failure_retains_completed_artifacts(self):
        rows, brief = fixtures()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            with self.assertRaises(ProviderError):
                self.pipeline(RecordingReplay(rows[:5])).generate(brief, directory=out)
            run = json.loads((out / 'run.json').read_text(encoding='utf-8'))
            self.assertEqual(run['status'], 'failed')
            self.assertTrue((out / 'concept_lock.json').is_file())
            self.assertTrue((out / 'story_lock.json').is_file())
            self.assertFalse((out / 'final.json').exists())

    def test_existing_directory_is_not_overwritten(self):
        rows, brief = fixtures()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileExistsError):
                self.pipeline(RecordingReplay(rows)).generate(brief, directory=temp)

    def test_max_rounds_zero_leaves_rejected_draft(self):
        rows, brief = fixtures()
        brief = Brief(**{**brief.to_dict(), 'max_rounds': 0})
        result = self.pipeline(RecordingReplay(rows[:9])).generate(brief)
        self.assertEqual(result['revision_rounds'], 0)
        self.assertFalse(result['audit']['target_met'])

    def test_insufficient_budget_rejected_before_calls(self):
        rows, brief = fixtures()
        provider = RecordingReplay(rows)
        brief = Brief(**{**brief.to_dict(), 'max_calls': 8})
        with self.assertRaisesRegex(ValueError, 'at least'):
            self.pipeline(provider).generate(brief)
        self.assertFalse(provider.requests)

    def test_budget_bounds_revision_without_fake_success(self):
        rows, brief = fixtures()
        brief = Brief(**{**brief.to_dict(), 'max_calls': 9})
        result = self.pipeline(RecordingReplay(rows[:9])).generate(brief)
        self.assertEqual(result['calls'], 9)
        self.assertFalse(result['audit']['target_met'])

    def test_critic_retries_low_score_without_actionable_issue_once(self):
        rows, brief = fixtures()
        broken = deepcopy(rows[6])
        broken['response']['issues'] = []
        rows.insert(6, broken)
        provider = RecordingReplay(rows)
        result = self.pipeline(provider).generate(brief)
        self.assertEqual(result['calls'], 12)
        self.assertTrue(any('contract_correction' in body for stage, body in provider.requests if stage == 'critic'))

    def test_concept_and_hook_locks_reject_unrelated_draft(self):
        concept, hook, story, song, brief = objects()
        for key in ('concept_id', 'hook_id', 'story_hash'):
            broken = deepcopy(song)
            broken[key] = 'unrelated'
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'lock'):
                validate_song(broken, concept, hook, story)

    def test_chorus_repetition_and_hook_lock(self):
        concept, hook, story, song, brief = objects()
        for index in (2, 5, 7):
            broken = deepcopy(song)
            broken['sections'][index]['lines'][0] = 'Yabancı bir nakarat geldi'
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'lock'):
                validate_song(broken, concept, hook, story)

    def test_form_and_character_limit_are_real_guards(self):
        concept, hook, story, song, brief = objects()
        bad = deepcopy(song)
        bad['sections'][0]['lines'].pop()
        with self.assertRaises(ValueError):
            validate_song(bad, concept, hook, story)
        with self.assertRaisesRegex(ValueError, 'max_chars'):
            validate_song(song, concept, hook, story, 200)

    def test_rewrite_cannot_touch_unreported_or_hook_line(self):
        concept, hook, story, song, _ = objects()
        for sid, number in [('verse2', 1), ('chorus', 1), ('chorus2', 1)]:
            response = {'patches':[{'section_id':sid,'line':number,'text':'Yeni bir cümle geldi'}]}
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                apply_patches(response, song, {('verse1', 1), ('chorus', 1)}, concept, hook, story, 5000)

    def test_chorus_rewrite_updates_all_repeats(self):
        concept, hook, story, song, _ = objects()
        new = apply_patches({'patches':[{'section_id':'chorus','line':2,'text':'İçimde bir karar kaldı'}]}, song,
                            {('chorus',2)}, concept, hook, story, 5000)
        self.assertEqual(new['sections'][2]['lines'], new['sections'][5]['lines'])
        self.assertEqual(new['sections'][2]['lines'], new['sections'][7]['lines'])
        self.assertEqual(song['sections'][2]['lines'][1], 'Sevmek geri dönmek değil')

    def test_unchanged_rewrite_is_rejected(self):
        concept, hook, story, song, _ = objects()
        text = song['sections'][0]['lines'][0]
        with self.assertRaisesRegex(ValueError, 'did not change'):
            apply_patches({'patches':[{'section_id':'verse1','line':1,'text':text}]}, song, {('verse1',1)}, concept, hook, story, 5000)

    def test_duplicate_hooks_and_invalid_lengths_rejected(self):
        rows, _ = fixtures()
        hooks = deepcopy(rows[2]['response'])
        hooks['hooks'][1]['text'] = hooks['hooks'][0]['text']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validate_candidates(hooks,'hooks',2,concept_id='c01')
        hooks['hooks'][1]['text'] = 'Sen gel'
        with self.assertRaisesRegex(ValueError, '4–7'):
            validate_candidates(hooks,'hooks',2,concept_id='c01')

    def test_equal_syllables_do_not_replace_semantic_quality(self):
        _, hook, _, song, brief = objects()
        brief = Brief(**{**brief.to_dict(), 'meter':7})
        song['sections'][0]['lines'][0] = hook['text']
        local = local_audit(song, brief, morphology=AutoMorphology(use_zeyrek=False))
        self.assertTrue(local['lines'][0]['meter']['meter_status'] == 'matches')
        self.assertEqual(local['melodic_stress_status'], 'not_evaluated_without_melody')
        self.assertGreater(local['hard_failures'], 0)

    def test_hook_meter_and_durak_are_checked_before_lock(self):
        _, hook, _, _, brief = objects()
        good = Brief(**{**brief.to_dict(),'meter':7,'durak':(4,3)})
        self.assertTrue(hook_metrics(hook, good)['eligible'])
        bad = Brief(**{**brief.to_dict(),'meter':8})
        self.assertFalse(hook_metrics(hook, bad)['eligible'])

    def test_empty_corpus_does_not_claim_originality_check(self):
        _, _, _, song, brief = objects()
        audit = local_audit(song, brief, morphology=AutoMorphology(use_zeyrek=False))
        self.assertEqual(audit['copying']['status'], 'not_checked_no_corpus')

    def test_missing_morphology_falls_back(self):
        with patch('turkish_lyric_engine.morphology.ZeyrekMorphology', side_effect=ValueError('missing')):
            provider = AutoMorphology()
            self.assertEqual(provider.analyze('yollarım'), ())
            self.assertEqual(provider.status, 'annotation_or_unresolved_fallback')

    def test_nonfinite_or_bool_critic_scores_rejected(self):
        rows, _ = fixtures()
        song = rows[5]['response']
        for score in (float('nan'),True,101,-1):
            critic = deepcopy(rows[10]['response'])
            critic['dimensions']['natural_turkish'] = score
            with self.subTest(score=score), self.assertRaises(ValueError):
                validate_semantic(critic,song,80)


if __name__ == '__main__':
    unittest.main()
