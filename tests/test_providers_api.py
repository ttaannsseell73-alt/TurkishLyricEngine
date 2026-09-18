from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from turkish_lyric_engine.api import make_handler, serve
from turkish_lyric_engine.contracts import object_schema
from turkish_lyric_engine.pipeline import LyricPipeline
from turkish_lyric_engine.providers import HttpJsonProvider, ProviderError, configured_provider
from turkish_lyric_engine.settings import load_settings
from test_generation import RecordingReplay, fixtures


@contextmanager
def server(handler):
    http = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=http.serve_forever, kwargs={'poll_interval':.02}, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(http.server_port)
    finally:
        http.shutdown()
        http.server_close()
        thread.join(2)


def transport_handler(response=None, *, code=200, redirect=None, responses=None, capture=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if capture is not None:
                capture.append({'path':self.path,'body':body,'authorization':self.headers.get('Authorization')})
            self.send_response(code)
            if redirect:
                self.send_header('Location', redirect)
            self.end_headers()
            value = response
            if responses is not None:
                row = responses.pop(0)
                if row['stage'] != body['response_format']['json_schema']['name']:
                    value = {'error':'unexpected test stage'}
                else:
                    value = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(row['response'],ensure_ascii=False)}}]}
            self.wfile.write(json.dumps(value,ensure_ascii=False).encode('utf-8'))
    return Handler


class ProviderTests(unittest.TestCase):
    schema = object_schema({'text':{'type':'string'}})

    def test_optional_usage_missing_or_null_does_not_break_pipeline(self):
        rows,brief=fixtures()
        class NullUsageReplay(RecordingReplay):
            last_usage=None
        result=LyricPipeline(NullUsageReplay(rows)).generate(brief)
        self.assertEqual(result['calls'],11)

    def test_openai_http_envelope_and_strict_schema(self):
        response = {'choices':[{'finish_reason':'stop','message':{'content':'{"text":"İçimde"}'}}], 'usage':{'total_tokens':20}}
        capture = []
        with server(transport_handler(response,capture=capture)) as url:
            provider = HttpJsonProvider('configured-model',kind='openai',base_url=url+'/v1',api_key='transport-test-key')
            result = provider.complete('unit','system',{'theme':'Türkçe'},self.schema)
        self.assertEqual(result,{'text':'İçimde'})
        self.assertEqual(capture[0]['path'],'/v1/chat/completions')
        self.assertTrue(capture[0]['body']['response_format']['json_schema']['strict'])
        self.assertEqual(provider.last_usage['total_tokens'],20)

    def test_ollama_chat_format_and_completion(self):
        capture=[]
        with server(transport_handler({'done':True,'message':{'content':'{"text":"yol"}'},'eval_count':12},capture=capture)) as url:
            provider=HttpJsonProvider('installed-model',kind='ollama',base_url=url)
            self.assertEqual(provider.complete('unit','system',{},self.schema),{'text':'yol'})
        self.assertEqual(capture[0]['path'],'/api/chat')
        self.assertFalse(capture[0]['body']['stream'])
        self.assertEqual(capture[0]['body']['format'],self.schema)

    def test_ollama_truncated_response_is_not_accepted(self):
        for done,reason in [(False,None),(True,'length')]:
            with self.subTest(done=done,reason=reason), server(transport_handler({'done':done,'done_reason':reason,'message':{'content':'{}'}})) as url:
                with self.assertRaises(ProviderError):
                    HttpJsonProvider('model',kind='ollama',base_url=url).complete('unit','system',{},self.schema)

    def test_non_object_transport_envelopes_are_clean_provider_errors(self):
        for value in ([],None,'invalid-envelope'):
            with self.subTest(value=value), server(transport_handler(value)) as url:
                with self.assertRaises(ProviderError):
                    HttpJsonProvider('model',kind='ollama',base_url=url).complete('unit','system',{},self.schema)

    def test_transport_failure_does_not_echo_body_or_key(self):
        capture=[]
        with server(transport_handler({'private':'transport-test-key'},code=429,capture=capture)) as url:
            with self.assertRaises(ProviderError) as context:
                HttpJsonProvider('model',kind='compatible',base_url=url,api_key='transport-test-key').complete('unit','system',{},self.schema)
        self.assertIn('429',str(context.exception))
        self.assertNotIn('transport-test-key',str(context.exception))
        self.assertEqual(len(capture),1)

    def test_redirect_is_not_followed_with_bearer_token(self):
        forwarded=[]
        with server(transport_handler({},capture=forwarded)) as destination:
            with server(transport_handler({},code=307,redirect=destination)) as origin:
                with self.assertRaises(ProviderError):
                    HttpJsonProvider('model',kind='compatible',base_url=origin,api_key='transport-test-key').complete('unit','system',{},self.schema)
        self.assertEqual(forwarded,[])

    def test_refusal_truncation_and_non_object_rejected(self):
        envelopes=[{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]},
                   {'choices':[{'finish_reason':'stop','message':{'refusal':'no','content':'{}'}}]},
                   {'choices':[{'finish_reason':'stop','message':{'content':'[]'}}]},
                   {'choices':[]}]
        for value in envelopes:
            with self.subTest(value=value), server(transport_handler(value)) as url:
                with self.assertRaises(ProviderError):
                    HttpJsonProvider('model',kind='compatible',base_url=url).complete('unit','system',{},self.schema)

    def test_remote_http_and_embedded_url_credentials_rejected(self):
        for url in ('http://example.com','https://user:password@example.com','https://example.com?key=secret','file:///tmp/model'):
            with self.subTest(url=url), self.assertRaises(ProviderError):
                HttpJsonProvider('model',kind='compatible',base_url=url)

    def test_missing_credentials_or_model_do_not_fall_back_to_mock(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(ProviderError,'model'):
                configured_provider()
            with self.assertRaisesRegex(ProviderError,'OPENAI_API_KEY'):
                configured_provider(model='explicit-model')

    def test_whole_pipeline_uses_real_http_transport_with_test_responses(self):
        # Exercises the HTTP implementation; the server intentionally is a test fixture.
        rows,brief=fixtures()
        capture=[]
        with server(transport_handler(responses=rows,capture=capture)) as url:
            result=LyricPipeline(HttpJsonProvider('transport-fixture',kind='compatible',base_url=url)).generate(brief)
        self.assertEqual(len(capture),11)
        self.assertEqual(result['revision_rounds'],1)
        self.assertTrue(result['audit']['target_met'])
        self.assertNotIn('Authorization',result)

    def test_config_rejects_credentials_in_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bad.toml'
            path.write_text('[provider]\napi_key="secret"\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'secrets'):
                load_settings(path)


class ApiTests(unittest.TestCase):
    def request(self,url,path,body=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:
            headers['Authorization']='Bearer '+token
        req=Request(url+path,data=json.dumps(body).encode('utf-8') if body is not None else None,headers=headers)
        with urlopen(req,timeout=10) as response:
            return response.status,json.loads(response.read())

    def test_health_and_turkish_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            with server(make_handler(output_root=temp)) as url:
                self.assertEqual(self.request(url,'/health')[1]['status'],'ok')
                code,value=self.request(url,'/analyze',{'text':'Beni unut sen artık','meter':7,'durak':[4,3]})
                self.assertEqual(code,200)
                self.assertTrue(value['meter']['all_lines_match'])

    def test_api_generation_persists_all_run_artifacts(self):
        rows,brief=fixtures()
        with tempfile.TemporaryDirectory() as temp:
            handler=make_handler(output_root=temp,provider_factory=lambda:RecordingReplay(rows))
            with server(handler) as url:
                code,value=self.request(url,'/generate',brief.to_dict())
                self.assertEqual(code,200)
                self.assertEqual(value['status'],'demo_only_fixture_replay')
            self.assertEqual(len(list(Path(temp).glob('*/final.json'))),1)
            self.assertEqual(len(list(Path(temp).glob('*/lyrics.txt'))),1)

    def test_token_authorization(self):
        with tempfile.TemporaryDirectory() as temp:
            with server(make_handler(output_root=temp,token='server-test-token')) as url:
                with self.assertRaises(HTTPError) as context:
                    self.request(url,'/health')
                self.assertEqual(context.exception.code,401)
                context.exception.close()
                self.assertEqual(self.request(url,'/health',token='server-test-token')[0],200)

    def test_invalid_payload_and_unknown_route(self):
        with tempfile.TemporaryDirectory() as temp:
            with server(make_handler(output_root=temp)) as url:
                for path,body,code in [('/analyze',{'text':'x','secret':1},400),('/unknown',{},404),('/generate',{'theme':'x','path':'../../file'},400)]:
                    with self.subTest(path=path), self.assertRaises(HTTPError) as context:
                        self.request(url,path,body)
                    self.assertEqual(context.exception.code,code)
                    context.exception.close()

    def test_empty_corpus_search_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            with server(make_handler(output_root=temp)) as url:
                self.assertEqual(self.request(url,'/search',{'query':'bekleme'})[1]['status'],'no_corpus')

    def test_remote_bind_requires_token(self):
        with patch.dict('os.environ',{},clear=True), self.assertRaisesRegex(ValueError,'TLE_SERVER_TOKEN'):
            serve(host='0.0.0.0',output_root='unused-test-path')


if __name__=='__main__':
    unittest.main()
