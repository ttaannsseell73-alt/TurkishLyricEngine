# TurkishLyricEngine

Türkçe şarkı sözü için hece, vezin/durak, fonetik kafiye, redif ve morfoloji
analizi; corpus zekâsı; fikir/hook/hikâye kilitleri; çoklu yazar ve hedefli
quality loop. Python 3.11+. Çekirdek runtime yalnız standart kütüphanedir.

Üretim gerçek, açıkça seçilen bir model bağlantısı gerektirir. OpenAI,
OpenAI-compatible JSON-schema endpoint ve yerel Ollama adaptörleri vardır.
Credential eksikliğinde sahte söz veya puan üreten bir fallback bulunmaz.
`replay` yalnız teknik regression fixture'ıdır; sanatsal başarı kanıtı değildir.

## Kurulum ve yerel analiz

```bash
python -m pip install .
tle meter examples/lyric_7.txt --syllables 7 --durak 4+3
tle meter examples/lyric_11.txt --syllables 11 --durak 6+5
tle rhyme güller küller --annotations examples/morphology.json
tle redif güller küller --annotations examples/morphology.json
tle rhymes yollarım --dictionary examples/rhyme_dictionary.json
tle analyze examples/lyric_11.txt
tle ingest examples/archive.jsonl --db corpus.sqlite3
tle stats --db corpus.sqlite3
tle search "unut" --db corpus.sqlite3
tle similarity examples/lyric_11.txt --db corpus.sqlite3
```

PATH'te `tle` yoksa `python -m turkish_lyric_engine` kullanılabilir. Kaynakta
kurulumsuz Bash: `PYTHONPATH=src`; PowerShell: `$env:PYTHONPATH="src"`.
Gerçek morfoloji backend'i isteğe bağlıdır:

```bash
python -m pip install -r requirements-morphology.lock.txt
tle rhyme yaralıyım hatalıyım --zeyrek
```

Annotation önceliklidir. Zeyrek yoksa dependency eksikliği analizi çökertmez;
bilinmeyen/çok anlamlı morfoloji `unresolved` kalır. İlk parse seçilmez veya
eksiz olduğu varsayılmaz. `yollarım/kollarım`: incelenmiş analizde `lar+ım`
redif, `ol` kafiye adayıdır. Ortak ek tek başına kafiye değildir.

## Gerçek üretim

Güvenli ortamda `TLE_MODEL` ve sağlayıcının credential'ı yapılandırılır:
OpenAI için `OPENAI_API_KEY`; compatible endpoint için gerekiyorsa `TLE_API_KEY`.
Anahtar repo, CLI argümanı, rapor veya sohbet içine yazılmaz.

```bash
tle preflight --config config/default.toml
tle generate "Birini hâlâ seviyorsun ama artık beklemiyorsun." --config config/default.toml --out outputs/first
```

Yerel, önceden çalışan Ollama için anahtar gerekmeyebilir:

```bash
tle generate "Sevmek sürüyor, beklemek bitiyor." --provider ollama --model <kurulu-model> --out outputs/local
```

Modelin Türkçe/JSON-schema yeterliliği değerlendirme gerektirir; model adı
veya download varsayımı yapılmaz. Endpoint için `--base-url`/`TLE_BASE_URL`
vardır. HTTP yalnız loopback'te; uzak endpoint HTTPS olmalıdır. Eksik/refused
JSON kabul edilmez. `preflight` config denetimidir; model çağrısı yapmaz.

Varsayılan: 20 fikir → ayrı idea judge/top5 → fikir kilidi → 50 hook → hook
judge/top5 → uygun hook kilidi → hikâye/bölüm planı → 3 yazar → teknik/anlamsal
critics → en güçlü taslak → en fazla 6 hedefli rewrite → final söz/rapor.
En fazla 40 model çağrısı vardır. Contract düzeltmesi en fazla bir ek çağrı
alır; transport hatasında otomatik ücretli retry yapılmaz.

```bash
tle generate "Tema" --meter 11 --durak 6+5 --rhyme-scheme ABAB --db corpus.sqlite3 --dictionary data/private/words.json --feedback-db feedback.sqlite3 --out outputs/with_archive
```

Serbest ölçü varsayılandır. 7/8/11/özel pozitif ölçü ve durak seçilebilir.
Kafiye için anlam bozma kabul edilmez. Hece eşitliği söyleyiş/duygu puanı değildir.
Form: V4/P2/C4/V4/P2/C4/B2/C4. Chorus ilk satırı hook'tur; üç nakarat aynıdır.
Söz etiketleri dahil en fazla5000 karakter doğrulanır. İkinci prechorus ayrı
beat'tir. Rewrite yalnız bildirilen zayıf koordinatları değiştirir; chorus
patch'i tekrarlarına eşlenir. Zayıf kilitli hook yeniden seçilecekse yeni
hikâye ve yeni taslaklar başlatılır. Judge varsayılanı aynı sağlayıcıda ayrı
çağrıdır; `[judge]` config ile farklı model seçilebilir.

Çıktı klasörü mevcutsa overwrite edilmez. `lyrics.txt`, `final.json`, çağrı/usage
özeti, adaylar/gerekçeler, kilitler, taslak denetimleri ve revision kayıtları
saklanır. Hata tamamlanan artifact'ları silmez. Kalite eşiği altında
`quality_target_not_met` döner. `review_ready` insan değerlendirmesine hazır
taslaktır. Puanlar hit/viral/telif güvencesi değildir. Her aktif boyut eşik
altında geçişi engeller; yüksek ortalama zayıf boyutu örtemez.

## Corpus ve geri bildirim

JSONL/JSON/CSV eser kayıtları; TXT veya TXT klasörü desteklenir. TXT metadata'sı
`eser.txt.meta.json` yanındadır. Satır/kıta/bölüm, hece, kafiye/redif adayları,
kelime/2–5 gram istatistiği ve ters indeks tutulur. M1 veritabanına additive
indeks migration uygulanır; kaynak/orijinal metin korunur. Bozuk batch
provenance ve indeksleriyle birlikte tamamen rollback yapar.

Writer ham archive sözlerini almaz. Corpus ölçü/tür istatistiği, klişe frekansı
ve denetim; sözlük anlamı olan kafiye aileleri sağlar. `search --include-text`
yalnız yerel araştırma için açık bir tercihtir.

```bash
tle feedback --run outputs/first/final.json --decision accept --feedback-db feedback.sqlite3 --db corpus.sqlite3
tle feedback --run outputs/first/final.json --decision edit --replacement corrected.txt --note "Dili sadeleştirdim" --feedback-db feedback.sqlite3
tle audit outputs/first/final.json --db corpus.sqlite3
```

GOLD/RED yalnız gerçek kullanıcı kararından oluşur; replay bu şekilde
etiketlenemez. Tür bazında mekanizma kabul/ret ve hook uzunluğu sayaçları
sonraki üretimde kullanılır. Küçük örneklem mutlak kural veya model eğitimi
sayılmaz. `.env`, SQLite, `data/private/` ve `outputs/` Git dışındadır.

## API ve doğrulama

```bash
tle serve --out outputs/api --db corpus.sqlite3 --feedback-db feedback.sqlite3
python scripts/run_checks.py --suite core
python -m pip install -r requirements-morphology.lock.txt
python scripts/run_checks.py --suite all
python scripts/smoke_cli.py --output reports/local/cli.json
```

API varsayılanı `127.0.0.1:8765`: `/health`, `/analyze`, `/generate`, `/search`,
`/feedback`. Dış arayüz bind için `TLE_SERVER_TOKEN` gerekir.
[API](docs/API.md), [mimari](docs/ARCHITECTURE.md),
[corpus/sözlük biçimi](docs/CORPUS_CONTRACT.md),
[kalite prensipleri](docs/LYRIC_CONSTITUTION.md),
[doğrulama ve sınırlar](docs/DELIVERY_STATE.md).

CI Linux/Windows × Python3.11/3.12 çekirdek ve kurulu CLI; Linux gerçek Zeyrek
regression suite. Test HTTP sunucusu yalnız transport testidir; canlı model
kabulü değildir. `--seed` teknik replay'de aynı sonucu sağlar; canlı servis
birebir aynı çıktı garantisi vermez.

Özel archive ve canlı model erişimi bu çalışma ortamında bulunmadığından
archive kapsamı/canlı üretim kalitesi doğrulanmadı. Aruz, melodi üzerinde
vurgu/sustain ve embedding benzerliği metin V1 kapsamı dışındadır. Yazımdan
fonetik/stress tahmini ile incelenmiş telaffuz farklı etiketlenir. Yalnız
verilen corpus'ta lexical copy adayları aranır; hukuki telif hükmü verilmez.

Çalışan M1 korundu; legacy SongEngine taşınmadı. Third-party dependency'ler
kendi lisanslarıyla kullanılır. Repo için açık kaynak lisansı seçilmedi;
archive hakları kod lisansından ayrıdır.
