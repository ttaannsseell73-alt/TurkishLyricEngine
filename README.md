# TurkishLyricEngine

Türkçe şarkı sözü üretimi için temiz, denetlenebilir dil ve corpus altyapısı.
**V0.1 / M1 çalışan kapsam:** arşiv alma, hece sayımı, hece vezni/durak,
kanıtlı morfolojiyle kafiye–redif ayrımı ve yerel korpusla sözcüksel benzerlik.
Bu sürüm henüz tema girince tam şarkı üretmez.

## Çalıştırma

Python 3.11+; çekirdeğin harici runtime bağımlılığı yoktur.

```bash
python -m pip install .
tle analyze examples/lyric_11.txt
tle meter examples/lyric_7.txt --syllables 7 --durak 4+3
tle meter examples/lyric_11.txt --syllables 11 --durak 6+5
tle rhyme "Bir dalda kalan güller" "Bir elde solan küller" --annotations examples/morphology.json
tle ingest examples/archive.jsonl --db corpus.sqlite3
tle stats --db corpus.sqlite3
tle similarity examples/lyric_11.txt --db corpus.sqlite3
```

Windows'ta `tle` PATH'te yoksa aynı komutları `python -m turkish_lyric_engine` ile çalıştır.
Kurulum olmadan kaynakta çalışmak için Bash'te `PYTHONPATH=src`, PowerShell'de
`$env:PYTHONPATH = "src"` kullan.

Gerçek Zeyrek backend'i isteğe bağlıdır:

```bash
python -m pip install -r requirements-morphology.lock.txt
tle rhyme yaralıyım hatalıyım --zeyrek
```

`yaralıyım / hatalıyım` için backend kök yüzeylerini `yara / hata` olarak,
ortak ek dizisini `lıyım` olarak ayırır. Kalan ortak harf `a`dır;
`güller / küller` örneğinde ise incelenmiş isim çoğul analiziyle redif `ler`,
kafiye adayı `ül` olur. Aynı son ek otomatik olarak gerçek kafiye sayılmaz.
Birden fazla kök/ek yorumu varsa motor `unresolved` döner.

## Vezin ve durak

`meter` bir pozitif hece ölçüsü veya serbest biçim kabul eder. Yaygın profiller:
7 → 4+3; 8 → 4+4; 11 → 6+5 veya 4+4+3; 14 → 7+7.
Başka bir bölünme `--durak` ile açıkça istenebilir. Ölçü belirtilmezse serbesttir.
Durak toplamı ölçüyle eşleşmeli ve kelime içinden geçmemelidir.
Kelime sınırında teknik uyum, o durağın cümlede doğal veya melodide doğru
olduğunu kanıtlamaz. Rapor bu ayrımı korur.

**Aruz taraması henüz uygulanmadı.** Hece vezni ve aruz aynı analiz değildir.
Metinden çıkan hece tahmini, melodik prozodi/vurgu değerlendirmesi yerine geçmez.
Sayılar, yabancı harfler ve sesli içermeyen kısaltmalar belirsizlik taşır;
hece tahmini belirsizken sabit ölçüye uyum PASS olarak sunulmaz.
Türkçe alfabeyle yazılmış yabancı kelimelerin telaffuzu otomatik doğrulanmaz.

## Arşiv

V1 giriş biçimi UTF-8 JSONL'dir: satır başına tek eser/record.
Şarkı/şiir/türkü/kafiye sözlüğü/GOLD/RED için `kind` alanları desteklenir.
`examples/archive.jsonl` özgün **teknik fixture** içerir; GOLD veya başarılı söz
örneği değildir. Gerçek özel arşiv henüz yüklenmemiştir.

Kaynak ve hak bilgisi zorunlu olarak kayıtla ilişkilidir; kesin hukuki izin
olarak yorumlanmaz. Aynı eser tek içerik olarak sayılır, her kaynağın özgün
metni/provenance kaydı ayrı korunur. Nakarat tekrarları silinmez.
Batch hatası veya ID çakışması tüm batch'i geri alır; örtük kayıt güncellemesi yoktur.

Özel arşivi `data/private/` altında tut. SQLite/.env dosyaları Git'e dahil değildir.
Ingestion metni internete veya modele göndermez. PDF/DOCX/OCR ve mevcut
sözlük biçimlerinin dönüştürülmesi gerçek arşiv görüldükten sonra eklenecektir.
V1 `rhyme_dictionary` içeriğini genel arşiv olarak saklar; kelime başına
doğrulanmış morfolojik kafiye indeksi henüz yoktur.

Benzerlik kontrolü yalnız yüklenen korpusta exact/3-gram/kelime sırası/satır
eşleşmesi arar. Embedding veya kapsamlı telif kararı üretmez. Boş korpus
`not_checked_empty_corpus` olarak raporlanır; "temiz" sonucu verilmez.

## Doğrulama ve devam

```bash
python scripts/run_checks.py --suite core
python -m pip install -r requirements-morphology.lock.txt
python scripts/run_checks.py --suite morphology
python scripts/run_checks.py --suite all
```

Core ve gerçek morfoloji suite'leri ayrıdır. Zorunlu backend suite'inde eksik
paket başarı/skip diye gizlenmez. CI Linux ve Windows core; Linux gerçek
Zeyrek entegrasyonu çalıştırır. Yerel PASS, GitHub CI PASS yerine geçmez.

Kalite çekirdeği [LYRIC_CONSTITUTION.md](docs/LYRIC_CONSTITUTION.md), veri biçimi
[CORPUS_CONTRACT.md](docs/CORPUS_CONTRACT.md), sınırlar ve devam mimarisi
[ARCHITECTURE.md](docs/ARCHITECTURE.md) içindedir.
Aktif görevler sohbetler arasında mevcut tek `PROJECT_STATE.md` dosyasından
izlenir; burada ikinci bir ana görev dosyası tutulmaz.

Proje kodu sıfırdan yazılmıştır; eski SongEngine/LyricEngine_Lab taşınmamıştır.
Üçüncü taraf paketleri kendi lisanslarıyla kullanılır; özel arşiv lisansı
proje kodunun lisansından bağımsızdır. Proje için henüz açık kaynak lisansı seçilmedi.
