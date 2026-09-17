# Corpus sözleşmesi — schema 1

UTF-8 JSONL, eser başına bir JSON nesnesi. Kaynak metni özel arşivde tutulur.

| Alan | Tip / kural |
|---|---|
| `record_id` | Kaynakta kalıcı, boş olmayan string; aynı ID ile farklı kayıt reddedilir |
| `kind` | `song`, `poem`, `turku`, `rhyme_dictionary`, `gold`, `red` |
| `title` | Boş olmayan string |
| `text` | Boş olmayan string; yalnız etiket/noktalama kabul edilmez |
| `source` | Boş olmayan string; gerçek kaynağa/yerel arşiv tanımına işaret eder |
| `rights` | `owned`, `public_domain`, `permission`, `restricted`, `unknown`; varsayılan `unknown` |
| `production_allowed` | Boolean; varsayılan false. `unknown`/`restricted` ile true reddedilir |

Hak alanı kullanıcı/kaynak beyanıdır. Bir şiirin GitHub'da veya internette
bulunması kullanım izni oluşturmaz. Bu katman veri eğitimini otomatik başlatmaz.

Normalizasyon NFC/Türkçe I ayrımı, satır boşlukları ve apostrof standardıdır.
Bilinen bölüm etiketleri analiz dışında kalır; serbest köşeli parantez içeriği
silinmez. Başlıkların yazıldığı orijinal metin provenance kaydında kalır.
Kanonik içerik hash'i satır sırasını ve tekrar adedini korur; aynı metnin
noktalama/case/bölüm başlığı farklarını tek eser olarak sayabilir.
Her farklı kaynak kaydının metni, türü ve hak beyanı ayrı korunur.

`documents` içerik/analiz; `records` eser kaynağı/metaveri/orijinal metin.
Foreign-key zorunlu. Schema sürümü `PRAGMA user_version` ile kontrol edilir.
Bilinen olmayan schema veya başka bir SQLite veritabanı sessizce dönüştürülmez.
Yanlış batch tamamen rollback; yeniden aynı batch idempotent.
Değişen ID/metaveri için gelecekte açık migration/feedback API gerekir.

GOLD ve RED kaynak türleri depolanabilir; bu sürüm gerçek kullanıcı geri
bildiriminden öğrenme veya model eğitimi yapmaz. Demonstration fixture'ları
GOLD değildir. Kafiye sözlüğünün madde/lemma/ek/okunuş şeması gerçek dosya
incelenince ayrı adapter sözleşmesiyle tanımlanacaktır.
