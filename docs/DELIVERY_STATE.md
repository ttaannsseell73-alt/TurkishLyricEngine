# V1 uygulama ve doğrulama kaydı

Başlangıç: çalışan M1 main d53d9f4fbc270614b776d6815926bace5ab1b05f.
Geliştirme: feat/tle-complete-generation-v1. Çalışan temel korunarak yeni
production model adaptörleri, concept/hook/story kilitleri, writer tournament,
teknik/semantic critic, bounded targeted revision, dictionary/knowledge/feedback,
CLI ve local API eklendi. Bu dosya ikinci bir görev izleyicisi değildir.

## Kanıt ayrımı

2026-09-18 yerel doğrulama: full suite **135 PASS / 0 FAIL / 0 ERROR / 0 SKIP**;
130 core bunun alt kümesidir, ayrıca toplanmaz. Full suite gerçek Zeyrek0.1.3 /
NLTK3.10.3 ile çalıştırıldı. Dependency'siz core130 PASS. Kurulu V1 wheel ile
11 CLI senaryosu PASS; JSON/lyrics/journal dosyaları da denetlendi. Credential
bulunmadığı için live model validation=false. CI sonucu bu yerel sayılar değildir.

Yerel unit/integration/regression sayıları docs/validation/v1_*result.json;
kurulu paket CLI proof v1_cli_smoke.json; kaynak hash'leri v1_source_manifest.json.
CI her PR/commit'te Linux/Windows×3.11/3.12 core+installedCLI ve Linux gerçek
Zeyrek'i doğrular. Remote CI sonucu ilgili Actions/PR kaydıdır; yerel JSON
remote PASS iddiası değildir. Historical m1_* ve source_manifest.json önceki
M1 commit'inin kanıtlarıdır, güncel kaynak manifest'i değildir.

Replay fixture production implementasyonu veya insan GOLD örneği değildir.
Fixture testinde kalite puanları regression response'larıdır; canlı model
veya editöryal/hit başarısı kanıtı olarak kullanılamaz. HTTP test sunucusu
sözleşme/transport uygulamasını denetler; gerçek model üretimi kabulü değildir.

## Gerçek validation engeli

Çalışma ortamında model/API secret, çalışan yerel model veya programatik text
inference bağlantısı yoktur. Bütün implementasyon ve offline/transport testleri
bu secret olmadan yapılabilir; canlı generation/kalite doğrulaması yapılamaz.
Production komutu key eksikliğini açıkça hata olarak döndürür. Replay'e sessiz
fallback yoktur. Tam canlı V1 kabulü bu nedenle açık kalır; model erişimi olmadan
proje tamamlandı iddiası yapılmaz. Secret rapora/repo/sohbete yazılmamalıdır.

## Bilinen çalışma sınırları

- Özel şarkı/şiir/türkü/sözlük archive'ı verilmedi; örnek veriler teknik fixture.
- Metrik/grade model yargısı ve engineering heuristiği; insan review gerekir.
- Morfoloji ambiguity disambiguation yapmaz; eksik bilgi unresolved kalır.
- Yazımdan stress/phonology estimate; incelenmiş override kabul edilir.
- Aruz ve melodi/akustik vurgu/sustain bu metin V1 kapsamı değildir.
- Benzerlik verilen corpus'ta lexical exact/ngram/fuzzy/block; embedding yoktur,
  telif verdict null. Eşikler editöryal, kalibre edilmiş hukuk ölçüsü değildir.
- Büyük özel archive'da exhaustive lexical guard maliyeti/performance ölçülmedi.
- Canlı provider aynı seed için birebir replay garantisi vermez.

## Yeniden doğrulama

```bash
python -m pip install .
python -m pip install -r requirements-morphology.lock.txt
python scripts/run_checks.py --suite all --report reports/local/all.json
python scripts/smoke_cli.py --output reports/local/cli.json
tle preflight --config config/default.toml
```

Generate config validation ve transport testi live verification yerine
sayılmaz. Hata halinde run.json failed ve tamamlanan journal checkpoint'leri
kalır; düzeltme tekrarını otomatik sınırsız çalıştırmaz. Budget/rounds sınırı
kaliteyi sağlamazsa düşük final taslak açık quality_target_not_met raporudur.
