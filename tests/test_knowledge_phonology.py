from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from turkish_lyric_engine.cliche import ClicheDetector
from turkish_lyric_engine.corpus import CorpusRecord, CorpusStore, read_archive, split_stanzas
from turkish_lyric_engine.critic import copying_guard, rhyme_plan
from turkish_lyric_engine.feedback import FeedbackStore
from turkish_lyric_engine.lexicon import Lexeme, RhymeLexicon
from turkish_lyric_engine.morphology import AnnotationMorphology, MorphAnalysis, Segment
from turkish_lyric_engine.phonology import articulation, phonemes, syllabify
from turkish_lyric_engine.prosody import analyze_line
from turkish_lyric_engine.rhyme import analyze_pair
from turkish_lyric_engine.redif import analyze_redif
from turkish_lyric_engine.similarity import compare_texts
from test_generation import EXAMPLES, objects


def record(identity,text,kind='song'):
    return CorpusRecord(identity,kind,'Fixture '+identity,text,'own-regression-fixture','owned',False)


class KnowledgeTests(unittest.TestCase):
    def test_numeric_surfaces_do_not_collapse_different_documents(self):
        with tempfile.TemporaryDirectory() as temp, CorpusStore(Path(temp)/'db.sqlite3') as store:
            store.ingest([record('1','Saat 5 oldu'),record('2','Saat 6 oldu')])
            self.assertEqual(store.document_count(),2)
            self.assertFalse(compare_texts('Saat 5 oldu','Saat 6 oldu')['exact_document_match'])

    def test_inverted_index_and_stanza_metadata_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'corpus.sqlite3'
            with CorpusStore(path) as store:
                store.ingest([record('1','[Verse 1]\nBeni unut sen artık\nKalan güller\n\n[Chorus]\nSolan küller')])
                rows=list(store.connection.execute('SELECT stanza, section, syllables, rhyme_json FROM corpus_lines ORDER BY ordinal'))
                self.assertEqual([r[0] for r in rows],[1,1,2])
                self.assertEqual(rows[0][2],7)
                self.assertEqual(json.loads(rows[1][3])['status'],'unresolved')
                self.assertNotIn('text',store.search('güller')['matches'][0])
            with CorpusStore(path,create=False) as store:
                self.assertEqual(store.search('güller')['matches'][0]['provenance'][0]['record_id'],'1')
                self.assertFalse(store.knowledge()['raw_archive_text_in_prompt'])

    def test_dedup_does_not_double_index_terms(self):
        with tempfile.TemporaryDirectory() as temp, CorpusStore(Path(temp)/'db.sqlite3') as store:
            store.ingest([record('1','Sen artık git'),record('2','SEN ARTIK GİT!')])
            self.assertEqual(store.document_count(),1)
            self.assertEqual(store.connection.execute('SELECT occurrences FROM corpus_terms WHERE token=?',('sen',)).fetchone()[0],1)
            self.assertEqual(len(store.search('sen')['matches'][0]['provenance']),2)

    def test_m1_database_additive_migration_preserves_text_and_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'db.sqlite3'
            with CorpusStore(path) as store:
                store.ingest([record('1','Beni unut sen artık')])
                before=store.documents()
                provenance=store.provenance(before[0]['content_hash'])
            with closing(sqlite3.connect(path)) as db:
                db.executescript('DROP TABLE corpus_lines; DROP TABLE corpus_terms; DROP TABLE corpus_ngrams;')
            with CorpusStore(path,create=False) as store:
                self.assertFalse(store.indexed)
                self.assertEqual(len(store.search('unut')['matches']),1)
            with CorpusStore(path) as store:
                self.assertTrue(store.indexed)
                self.assertEqual(store.documents(),before)
                self.assertEqual(store.provenance(before[0]['content_hash']),provenance)
                self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM corpus_lines').fetchone()[0],1)

    def test_bad_late_record_rolls_back_index_too(self):
        with tempfile.TemporaryDirectory() as temp, CorpusStore(Path(temp)/'db.sqlite3') as store:
            store.ingest([record('1','Eski bir satır')])
            with self.assertRaises(ValueError):
                store.ingest([record('2','Yeni bir satır'),record('1','Çakışan başka satır')])
            self.assertEqual(store.search('yeni')['matches'],[])
            self.assertEqual(store.document_count(),1)

    def test_txt_directory_sidecars_and_unknown_rights(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'a.txt'
            file.write_text('Beni unut sen artık',encoding='utf-8')
            sidecar=file.with_suffix('.txt.meta.json')
            sidecar.write_text(json.dumps({'record_id':'txt-a','kind':'poem','source':'user-archive'}),encoding='utf-8')
            rows=read_archive(temp)
            self.assertEqual(rows[0].record_id,'txt-a')
            self.assertEqual(rows[0].rights,'unknown')
            self.assertFalse(rows[0].production_allowed)

    def test_csv_multiline_and_strict_boolean(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'archive.csv'
            with file.open('w',encoding='utf-8',newline='') as out:
                writer=csv.DictWriter(out,fieldnames=['record_id','kind','title','text','source','production_allowed'])
                writer.writeheader()
                writer.writerow({'record_id':'csv-1','kind':'literary','title':'Test','text':'İlk satır\nİkinci satır','source':'own-test','production_allowed':'false'})
            self.assertEqual(read_archive(file)[0].text,'İlk satır\nİkinci satır')
            file.write_text(file.read_text(encoding='utf-8').replace('false','maybe'),encoding='utf-8')
            with self.assertRaises(ValueError):
                read_archive(file)

    def test_invalid_sidecar_and_empty_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                read_archive(temp)
            file=Path(temp)/'a.txt'
            file.write_text('Bir satır',encoding='utf-8')
            file.with_suffix('.txt.meta.json').write_text('[]',encoding='utf-8')
            with self.assertRaises(ValueError):
                read_archive(temp)

    def test_phrase_frequency_learns_unique_documents_not_refrain_counts(self):
        with tempfile.TemporaryDirectory() as temp, CorpusStore(Path(temp)/'db.sqlite3') as store:
            store.ingest([record(str(i),'Sana bir sözüm var\n'+str(i)+' farklı satır') for i in range(3)])
            report=ClicheDetector(store).analyze('Sana bir sözüm var',avoid=())
            self.assertTrue(any(m['phrase']=='sana bir sözüm' and m['frequency']==3 for m in report['matches']))

    def test_common_word_is_not_a_blacklist(self):
        detector=ClicheDetector()
        self.assertEqual(detector.analyze('Kalp cerrahı sıra bekler',avoid=())['matches'],[])
        self.assertEqual(detector.analyze('Kaderin oyunu artık değil',avoid=())['matches'][0]['context'],'possible_subversion_requires_critic')
        self.assertLess(detector.analyze('Kaderin oyunu artık değil',avoid=())['density_candidate'],detector.analyze('Kaderin oyunu',avoid=())['density_candidate'])

    def test_copy_guard_blocks_copied_line_inside_another_song(self):
        _,_,_,song,_=objects()
        with tempfile.TemporaryDirectory() as temp, CorpusStore(Path(temp)/'db.sqlite3') as store:
            copied='Erteledim bütün işlerimi yine bugün'
            store.ingest([record('1',copied+'\nBambaşka bir son satır')])
            song['sections'][0]['lines'][1]=copied
            guard=copying_guard(song,store)
            self.assertTrue(guard['blocked'])
            self.assertTrue(any(i['section_id']=='verse1' and i['line']==2 for i in guard['issues']))
            self.assertIsNone(guard['copyright_verdict'])


class LexiconPhonologyTests(unittest.TestCase):
    def test_redif_engine_exposes_grammatical_segments(self):
        lexicon=RhymeLexicon.from_file(EXAMPLES/'rhyme_dictionary.json')
        report=analyze_redif('yollarım','kollarım',lexicon.annotations)
        self.assertEqual(report['suffix_redif'],'larım')
        self.assertEqual([s['function'] for s in report['redif_segments']],['plural','possessive_1sg'])

    def test_invalid_affix_function_is_rejected_before_analysis(self):
        with self.assertRaises(ValueError):
            Segment('lar',7)

    def test_explicit_phonemes_change_sound_match_without_letter_match(self):
        provider=AnnotationMorphology([MorphAnalysis(w,w,w,(),'technical_phoneme_override') for w in ('kas','kaz')])
        report=analyze_pair('kas','kaz',provider,pronunciations={'kas':['k','a','s'],'kaz':['k','a','s']})
        self.assertEqual(report['base_tail'],'')
        self.assertEqual(report['status'],'base_ending_match')
        self.assertEqual(report['rhyme_class_candidate'],'zengin')
        self.assertEqual(report['phonetic_status'],'supplied_base_pronunciations')

    def test_syllable_boundaries_difficult_turkish_examples(self):
        cases={'İSTANBUL':['is','tan','bul'],'aile':['a','i','le'],'saat':['sa','at'],'Ankara':['an','ka','ra'],'Türkçe':['türk','çe'],'şiir':['şi','ir']}
        for word,expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(syllabify(word),expected)

    def test_soft_g_and_circumflex_do_not_claim_exact_pronunciation(self):
        self.assertIn('soft_g_pronunciation_needs_review',phonemes('dağ')['warnings'])
        self.assertIn('lexical_vowel_length_needs_review',phonemes('hâl')['warnings'])
        self.assertEqual(phonemes('hâl',['h','aː','l'])['status'],'supplied_pronunciation')

    def test_equal_syllables_can_have_different_articulation_load(self):
        first=analyze_line('saat')
        second=analyze_line('stratej')
        self.assertEqual(first['orthographic_syllables'],second['orthographic_syllables'])
        self.assertGreater(second['articulation_load']['cluster_count'],first['articulation_load']['cluster_count'])

    def test_stress_and_duration_are_explicitly_labelled(self):
        report=articulation('Ankara',stress_syllable=1)
        self.assertEqual(report['stress']['status'],'supplied_lexical_stress')
        self.assertEqual(report['duration_structure'],['closed','open','open'])
        with self.assertRaises(ValueError):
            articulation('Ankara',stress_syllable=4)

    def test_dictionary_returns_evidence_and_separates_redif(self):
        lexicon=RhymeLexicon.from_file(EXAMPLES/'rhyme_dictionary.json')
        family=lexicon.family('yollarım')
        match=next(m for m in family if m['word']=='kollarım')
        self.assertEqual(match['analysis']['suffix_redif'],'larım')
        self.assertEqual(match['analysis']['base_tail'],'ol')
        self.assertEqual(match['analysis']['rhyme_class_candidate'],'tam')

    def test_dictionary_filters_syllables_and_unknown_remains_unknown(self):
        lexicon=RhymeLexicon([Lexeme('bekliyorum','own-test'),Lexeme('özlüyorum','own-test')])
        family=lexicon.family('bekliyorum',syllables=4)
        self.assertEqual(family[0]['analysis']['status'],'unresolved')
        self.assertEqual(lexicon.family('bekliyorum',syllables=2),[])

    def test_csv_suffix_json_is_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'words.csv'
            with file.open('w',encoding='utf-8',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=['word','source','base_surface','lemma','suffixes'])
                writer.writeheader()
                writer.writerow({'word':'güller','source':'test','base_surface':'gül','lemma':'gül','suffixes':json.dumps([{'surface':'ler','function':'plural'}])})
            self.assertEqual(RhymeLexicon.from_file(file).entries[0].suffixes[0].surface,'ler')

    def test_invalid_dictionary_reconstruction_is_rejected(self):
        with self.assertRaises(ValueError):
            Lexeme('yollarım','test',base_surface='yol',lemma='yol')
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'bad.json'
            file.write_text('[{"word":"x","secret":"bad"}]',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'entry 1'):
                RhymeLexicon.from_file(file)

    def test_half_full_rich_tunc_and_near_rhyme_candidates(self):
        pairs=[('su','bu','yarım'),('bel','sel','tam'),('gülüş','bölüş','zengin'),('yar','diyar','tunç'),('kas','kaz','yakın')]
        entries=[MorphAnalysis(w,w,w,(),'reviewed-regression-fixture') for a,b,_ in pairs for w in (a,b)]
        provider=AnnotationMorphology(entries)
        for a,b,kind in pairs:
            with self.subTest(a=a,b=b):
                self.assertEqual(analyze_pair(a,b,provider)['rhyme_class_candidate'],kind)

    def test_dictionary_families_reach_writer_plan(self):
        concept,hook,_,_,brief=objects()
        hook['text']='Bir avuç kül kaldı gül'
        plan=rhyme_plan(brief,RhymeLexicon.from_file(EXAMPLES/'rhyme_dictionary.json'),hook,concept)
        self.assertTrue(plan['families'])


class FeedbackTests(unittest.TestCase):
    def test_real_feedback_counts_are_durable_idempotent_and_genre_specific(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'feedback.sqlite3'
            arguments={'run_id':'run1','genre':'pop','decision':'accept','original':'Kendi sözü','mechanism_id':'role_reversal','hook_words':5}
            with FeedbackStore(path) as store:
                self.assertEqual(store.preferences('pop')['status'],'no_user_feedback')
                first=store.add(**arguments)
                self.assertEqual(first,store.add(**arguments))
                store.add(**{**arguments,'run_id':'run2','decision':'reject'})
                self.assertEqual(store.preferences('pop')['sample_count'],2)
                self.assertEqual(store.preferences('rap')['sample_count'],0)
            with FeedbackStore(path) as store:
                self.assertEqual(store.preferences('pop')['mechanism_accepts']['role_reversal'],1)

    def test_edit_requires_replacement(self):
        with tempfile.TemporaryDirectory() as temp, FeedbackStore(Path(temp)/'db.sqlite3') as store:
            with self.assertRaises(ValueError):
                store.add(run_id='r',genre='pop',decision='edit',original='söz',mechanism_id='m',hook_words=5)

    def test_foreign_database_not_repurposed(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'foreign.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE unrelated (id INTEGER)')
                db.commit()
            with self.assertRaises(ValueError):
                FeedbackStore(path)


if __name__=='__main__':
    unittest.main()
