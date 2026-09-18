# Corpus ve sözlük sözleşmesi

## Eser kaydı

UTF-8 JSONL (satır başına eser), JSON array, CSV veya TXT/TXT klasörü.
CSV text alanı tırnak içinde çok satırlı olabilir; production_allowed literal
true/false/0/1 kabul eder. TXT metadata `eser.txt.meta.json`; eksik metadata'da
literary, dosya adı/title, unknown rights ve production_allowed=false vardır.

| Alan | Tip/kural |
|---|---|
| record_id | Kalıcı, boş olmayan ID; aynı ID ile farklı kayıt reddedilir |
| kind | song/poem/turku/literary/rhyme_dictionary/gold/red |
| title/text/source | Boş olmayan string; sadece etiket/noktalama söz kabul edilmez |
| rights | owned/public_domain/permission/restricted/unknown; default unknown |
| production_allowed | Boolean defaultfalse; unknown/restricted ile true reddedilir |

Hak alanı kaynak beyanıdır; otomatik izin veya hukuk kararı değildir. Ingestion
model training başlatmaz. Unicode NFC, Türkçe I/İ, apostrof/boşluk normalleşir.
Bölüm başlıkları analiz dışında; source original_text aynen kalır. Hash satır
sırası/refrain adedini korur; noktalama/case farkları dedup olur. Yeni numeric
surface kayıtları farklı sayıları birleştirmez. Değişmeden reingest edilen
legacy M1 numeric kayıtları eski kimliğini korur.

SQLite documents=eser/analiz; records=provenance/orijinal metin. corpus_lines
satır/kıta/bölüm/hece/komşu redif-rhyme cache; corpus_terms ve corpus_ngrams
ters indekslerdir. Schema1 M1 migration additive'dir; create=False eski db'yi
mutate etmeden scan fallback kullanır. create=True indeks/backfill ekler.
Her batch atomiktir; aynı kayıt idempotent; metadata güncellemesi örtük yapılmaz.
Bilinmeyen schema/foreign db reddedilir. Fonetik/morfoloji unresolved adayları
cache'de kesin kafiye diye kaydedilmez.

İstatistiklerde kelime/phrase sayımı eser dedup'ından sonra, refrain adedi
korunarak yapılır. Cliché öğrenme document frequency kullanır; aynı nakaratın
çok tekrarı çok eser sayılmaz. Motifler editorial lexical stem adaylarıdır,
gerçek semantic motif etiketi değildir. Search TF-IDF term indeksindedir;
text ancak yerel include_text=True tercihiyle döner. Writer text almaz.

## Kafiye sözlüğü

JSON array/JSONL/CSV/TSV: her satır lexeme; TXT: her satır tek kelime.

| Alan | Tip/kural |
|---|---|
| word | Tek Türkçe kelime, normalize lowercase |
| source/rights | Kaynak ve rights beyanı; default filename/unknown |
| definition | Anlam açıklaması; writer'ın anlamsız kafiye seçimini azaltır |
| base_surface/lemma | Birlikte isteğe bağlı incelenmiş morfoloji |
| suffixes | [{surface,function}] listesi; CSV'de JSON string |
| pronunciation | Fonem string listesi; CSV'de JSON string; explicit override |
| stress_syllable | 1 tabanlı, hece sayısı içinde incelenmiş stress index |

base_surface + suffix yüzeyleri kelimeyi aynen kurmalıdır. Fonem kuyruğu,
ortak ek yüzeyi ve grammatical function birlikte değerlendirilir. Aynı ekin
başka görevi redif değildir. Lexicon incelenmiş annotation'ı öncelikle sağlar;
eksik/ambiguous morfoloji gerçek kafiye diye sunulmaz. Birbirinden farklı
kökte sadece görevdeş ek ortaksa redif-only dışlanır. Kafiye ailesinde kaynak,
anlam, hece ve kanıt bulunur. Teknik fixture `examples/rhyme_dictionary.json`.

## GOLD/RED

Feedback gerçek kullanıcı accept/reject/edit, run_id, genre, original,
replacement(edit), mechanism_id, hook_words, note içerir. Ayrı feedback db
idempotent event hash'i ve türe göre tercih sayacı tutar. Ham lyrics prompt'a
aktarılmaz. CLI feedback --db verilirse user kararını gold/red corpus'a
kaynak/run bağlantısıyla ekler; rights unknown, production_allowed=false.
Replay çıktısı bu şekilde etiketlenemez. Feedback corpus ile aynı db değildir.
