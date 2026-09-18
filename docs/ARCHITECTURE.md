# TurkishLyricEngine V1 mimarisi

Python3.11+ standart kütüphane. CLI/API aynı pipeline ve analiz modüllerini
kullanır. Gerçek model üretimi JsonProvider'dadır; ReplayProvider açık testtir.

| Modül | Uygulanan sorumluluk |
|---|---|
| text | Türkçe Unicode, I/İ, bölüm ve satır normalizasyonu |
| prosody/phonology | Hece/kelime dağılımı, hece bölümü/CV, ünlü temasları, cluster/uzun kelime ve ek yükü, stress adayı, okunabilirlik |
| meter | Serbest/7/8/11/özel hece; kıta tutarlılığı; kelime sınırında durak |
| morphology | Annotation önceliği; pinli Zeyrek; ambiguity/bilinmeyen fallback |
| redif/rhyme | Görev/yüzey eşdeğer redif; kalan fonem kuyruğunda yarım/tam/zengin/tunç/yakın adayları |
| lexicon | CSV/TSV/JSON(L)/TXT sözlük, anlam/provenance, kafiye aileleri, pronunciation/stress override |
| corpus | Transaction/dedup/provenance, satır/kıta cache, term/ngram indeks, TF-IDF retrieval, lexical motif adayları |
| cliche | İfade/2–5gram document frequency; bağlam dönüşü kanıtı; kullanıcı profili |
| feedback | Gerçek accept/reject/edit; tür bazında mekanizma ve hook tercih sayaçları |
| concept_engine/mechanisms | 20 dramatik fikir, beş soyut mekanizma, ayrı idea judge |
| hook_lab/story_engine | 50 hook ve ayrı judge; eligibility; değişim beat'leri ve hash kilidi |
| lyric_writer | 3 ayrı writer çağrısı; yalnız bildirilen satır patch'leri; hook/form/refrain kilitleri |
| critic/similarity | Teknik audit, model semantic/natural Turkish/register yargısı; exact/ngram/fuzzy line/sıra/contiguous block koruması |
| stages/pipeline | Strict validation, bütçe/journal, tournament, sınırlı rewrite/reselection |
| providers/settings | OpenAI/compatible/Ollama JSON-schema; environment secrets; TOML config |

## Kilitler ve kalite

Fikirler → idea judge → concept lock → hooks → hook judge/eligibility → hook
lock → story/section plan → story hash → rhyme plan → writer tournament →
teknik audit ve ayrı semantic critic → en güçlü taslak → hedefli patch ve
tekrar audit → kalite kapısı → final.

Fikrin açı/çatışma/turn'ü hook'tan önce belirlenir; section beat'leri hook'tan
sonra buna bağlanır. Aynı concept_id/hook_id/story_hash her taslakta zorunlu.
Form, nakarat ve max5000 karakter validation geçmeden critic çalışmaz.
Teknik hece başarısı anlamı puanlamaz. Toplam %65 semantic + %35 technical
ortalamadır; her aktif boyut hedefi karşılamalı ve hard failure olmamalıdır.
Serbest kafiye rhyme score null'dur. Skorlar kalibre edilmemiş model yargısı
ve mühendislik heuristiğidir; insan/hit kabulü değildir.

Ölçü/durak ihlali, doğrulanmış redif-only/missing kafiye, corpus copy adayı
hard failure'dır. Eksik morfoloji unresolved/rhyme50 olarak düzeltmeye girer.
Semantic critic düşük boyutu somut satır issue'suyla gerekçelendirmek zorunda.
Revision yalnız issue koordinatları; hook değişmez. Chorus patch'i tekrarlarıyla
aynıdır. En güçlü geçerli taslak tutulur; kötü rewrite final'i düşürmez.
Hook kusuru çözülemiyorsa en fazla üç hook'ta yeni story/tournament vardır.
Tüm çağrılar tek bütçedir: varsayılan40; max_rounds toplam≤6. Kalite düşükse
başarı diye gizlenmez. Judge varsayılanı aynı modelde ayrı çağrı; bağımsız ajan
kanıtı değildir. Config [judge] farklı sağlayıcı/model destekler.

## Corpus ve öğrenme

RAW → metadata/normalize → eser hash/provenance → satır/kıta → hece ve komşu
satır rhyme/redif → term/2–5gram → inverted index. M1 schema1'e additive
migration uygulanır. Transaction hata halinde indeks/provenance/metni birlikte
geri alır. Ham archive writer prompt'una girmez. Ölçü/tür statistics, cliché
kanıtı, sözlük aileleri ve gerçek kullanıcı tercih sayaçları kullanılır.
Mekanizma preference adjustment ±1'den küçüktür; küçük örneklem güçlü idea
yargısını zorla değiştirmez. Model training yoktur. GOLD/RED gerçek kullanıcı
etiketidir; fixture'lar asla GOLD değildir.

Copy guard min5 kelimelik line ratio≥.95, min8 kelimelik contiguous block veya
min20 kelimelik document ratio≥.85 adayını bildirir; rewrite sonrası tekrar
kontrol eder. Eşikler editöryaldir; hukuki özgünlük/telif hükmü değildir.
Boş corpus `not_checked` kalır. İstatistik/retrieval aynı eser dedup'ını
korur; orijinal nakarat tekrarı silinmez.

## Recovery ve sınırlar

Yeni run klasörü; atomik journal; hatada tamamlanan aşamalar korunur ve final
başarı üretmez. Mevcut klasör overwrite edilmez. Contract hatası tek düzeltme
çağrısı; transport timeout/HTTP hata otomatik retry değildir. Key yalnız
Authorization header'ında, rapor/log/error body'sinde yoktur. Redirect takibi
kapalıdır. Uzak endpoint HTTPS; loopback HTTP desteklenir.

Hece vezni aruz değildir. V1 melodi/akustik vurgu/sustain, dialect veya
embedding değerlendirmez. Lexicon override dışında stress/phonology tahmindir.
Bağlamsal morfoloji disambiguation yapılmaz; word redif aynı anlam/görev
incelemesi gerektirir. Büyük corpus'ta tam lexical guard eser/satır tarama
maliyeti taşır; özel archive performansı bu ortamda ölçülmedi.

## Bağlantı kaynakları

[OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[Chat API](https://developers.openai.com/api/reference/resources/chat),
[Ollama chat](https://docs.ollama.com/api/chat) sözleşmeleriyle adapter'lar
uygulandı. [Zeyrek](https://github.com/obulat/zeyrek)0.1.3 private single-word
surface API tek adapter'da, sürüm guard ve gerçek regression testleriyle
izole edilir; tokenizer download'u gerekmez. Diğer araştırma repo/datasetlerinin
kaynak/lisansı doğrulanmadan kod/veri taşınmadı.
