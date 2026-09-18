"""Exercise the installed package, CLI, and persisted outputs without a key.

Replay is explicitly a technical fixture, not proof of live lyric quality.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path)
args = parser.parse_args()
checks = []


def call(name, *arguments):
    result = subprocess.run([sys.executable, '-m', 'turkish_lyric_engine', *map(str,arguments)],
                            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=False)
    if result.returncode:
        raise RuntimeError(f'{name}: exit {result.returncode}: {result.stderr[:500]}')
    value = json.loads(result.stdout)
    checks.append({'command':name, 'exit_code':result.returncode})
    return value


with tempfile.TemporaryDirectory() as temp:
    directory = Path(temp)
    db = directory / 'corpus.sqlite3'
    value = call('meter7', 'meter', ROOT/'examples/lyric_7.txt', '--syllables',7,'--durak','4+3')
    assert value['all_lines_match']
    value = call('meter11', 'meter',ROOT/'examples/lyric_11.txt','--syllables',11,'--durak','6+5')
    assert value['all_lines_match']
    value = call('annotated_rhyme','rhyme','güller','küller','--annotations',ROOT/'examples/morphology.json')
    assert value['base_tail']=='ül' and value['suffix_redif']=='ler'
    value = call('redif','redif','güller','küller','--annotations',ROOT/'examples/morphology.json')
    assert value['suffix_redif']=='ler'
    value = call('dictionary','rhymes','yollarım','--dictionary',ROOT/'examples/rhyme_dictionary.json')
    assert any(r['word']=='kollarım' and r['analysis']['suffix_redif']=='larım' for r in value['family'])
    value = call('ingest','ingest',ROOT/'examples/archive.jsonl','--db',db)
    assert value['inserted_documents']==2
    value = call('stats','stats','--db',db)
    assert value['unique_documents']==2
    value = call('search','search','unut','--db',db)
    assert value['matches']
    value = call('similarity','similarity',ROOT/'examples/lyric_11.txt','--db',db)
    assert value['matches'][0]['metrics']['exact_document_match']
    out = directory/'replay'
    value = call('explicit_fixture_replay','replay','--fixture',ROOT/'examples/replay_run.json','--brief',ROOT/'examples/replay_brief.json','--out',out)
    assert value['status']=='demo_only_fixture_replay' and value['revision_rounds']==1 and value['calls']==11
    assert (out/'lyrics.txt').is_file() and (out/'final.json').is_file()
    call('audit','audit',out/'final.json')
report = {'successful':True, 'checks':checks, 'live_model_validation':False,'fixture_is_gold':False}
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
