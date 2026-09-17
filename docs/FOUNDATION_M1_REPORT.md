# M1 — Corpus + hece vezni/durak + kafiye/redif

Tarih: 2026-09-17. Başlangıç: `ttaannsseell73-alt/TurkishLyricEngine`,
`main=fe77f3a236f89bc0ef7931ebdcb9119b545b5452` (yalnız README).
Dal: `feat/tle-foundation-meter-redif-v1`. Temiz başlangıç; legacy kod alınmadı.

## Çalışan sonuç

- Türkçe Unicode/I ayrımı; kanonik satırlar, tekrarları koruma.
- JSONL → transactional SQLite; kaynak/orijinal metin/hak beyanı korunur.
- Yazımdan hece sayımı; sayı/alfabe/kısaltma belirsizliği ayrıca raporlanır.
- Hece vezni: 7/8/11/14 ve özel pozitif ölçüler; serbest biçim varsayılan.
- Durak: 4+3, 4+4, 6+5, 4+4+3, 7+7 veya özel pattern; kelime içi kesme yok.
- İncelenmiş morfoloji veya gerçek Zeyrek 0.1.3 backend'i.
- Kelime tekrarı redif adayı / ek redifi / kalan kök sonu ayrımı.
- Exact/3-gram/kelime sırası/satır eşleşmesiyle yerel lexical guard.
- CLI, JSON raporları; Linux/Windows core ve Linux real-backend CI tanımı.

## Doğrudan çalıştırılan doğrulama

Ortam: Linux x86_64, Python 3.12.14. Morfoloji: Zeyrek 0.1.3 / NLTK 3.10.3.

| Koşu | PASS | FAIL | ERROR | SKIP |
|---|---:|---:|---:|---:|
| Core, harici morfoloji paketi olmadan | 60 | 0 | 0 | 0 |
| Tam suite, gerçek Zeyrek dahil | 65 | 0 | 0 | 0 |

Core 60 test, tam suite'in alt kümesidir; toplam 125 değildir.
Tam suite'te 5 gerçek morfoloji entegrasyon regresyonu vardır.
Sonuç JSON'ları `docs/validation/` içindedir; gerçek çalıştırma zamanları/ortam
orada kayıtlıdır. Bu teknik PASS, üretilmiş bir şarkının kalite kanıtı değildir.

```bash
python scripts/run_checks.py --suite core --report docs/validation/m1_core_result.json
PYTHONPATH=<installed_optional_backend> python scripts/run_checks.py --suite all --report docs/validation/m1_linux_result.json
```

Paket wheel olarak build edildi ve ayrı hedefe `--no-deps --no-build-isolation`
ile kuruldu. Kurulu pakette `python -m turkish_lyric_engine` ile 7 CLI koşusu
çalıştırıldı: iki vezin/durak, annotated redif, gerçek Zeyrek redif, ingest,
stats ve benzerlik. Özgün fixture ile iki corpus belgesi ve exact match
doğrulandı; özel kullanıcı arşivi kullanılmadı.

## Vezin/redif örnekleri

| Girdi | Raporlanan ayrım |
|---|---|
| Beni unut / sen artık | 7 hece; 4+3 kelime sınırlarına uygun |
| Beni unut artık / bana geri dön | 11 hece; 6+5 kelime sınırlarına uygun |
| güller / küller, annotated isim çoğul | redif `ler`, kök sonu adayı `ül` |
| kızlar / atlar, annotated isim çoğul | yalnız redif `lar`; kafiye ödülü yok |
| yaralıyım / hatalıyım, gerçek backend | ek dizisi `lıyım`; kök yüzeyleri `yara/hata`, ortak son `a` |
| gülüm / külüm, gerçek backend | birden çok grammatical yorum; unresolved |
| bekliyorum / özlüyorum, gerçek backend | farklı yüzeyli kalan ekler; unresolved, tahminle kesme yok |

Örnek satırlar teknik fixture'dır; sanatsal kalite/GOLD etiketi yoktur.
Word-redif adayında aynı anlam ve işlev ayrıca incelenmelidir. Yarım/tam/zengin
etiketi ortografik adaydır; fonetik veya bütün geleneksel uyak türlerinin
tam analizi değildir.

## Henüz kanıtlanmayan / sonraki kapsam

Aruz, doğal durak ve melodide vurgu; büyük gerçek arşiv; sözlüğün madde
adapter'ı; bağlamsal morfoloji; Concept/Hook/Story üretimi; Writer Tournament;
semantic critic; kullanıcı GOLD/RED öğrenmesi; embedding/block retrieval ve
ölçekli similarity index henüz uygulanmadı. Copyright verdict null kalır.

Bu belge yerel koşuları raporlar. GitHub CI sonucu bu belgenin yazıldığı anda
henüz alınmadı; PR/checkpoint ve CI sonucu mevcut tek `PROJECT_STATE.md`
dosyasında kaydedilecektir. `main` entegrasyonu bu raporla gerçekleşmiş sayılmaz.
