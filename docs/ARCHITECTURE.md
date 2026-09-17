# TurkishLyricEngine mimarisi

## Uygulanan M1

`text` → Türkçe Unicode/etiket/satır normalizasyonu.
`prosody` → yazımdan hece tahmini, belirsizlik, istenirse satır uzunluğu uyarısı.
`meter` → hece vezni/durak, serbest biçim, kelime sınırı kontrolü.
`morphology` → incelenmiş segmentation + pinlenmiş isteğe bağlı Zeyrek adapter.
`rhyme` → tekrar/ek redifi/kök yüzeyi adayı; belirsizlik korunur.
`corpus` → provenance/rights/dedup/istatistik SQLite ingestion.
`similarity` → exact/trigram/sıra/satır eşleşmesi, yalnız yerel korpus.
`cli` → JSON raporları, arşiv metnini internete göndermez.

## Devam tasarımı (uygulanmadı)

Tema → Concept adayları → ayrı Idea Judge → Core Idea Lock → Hook Lab →
Hook Judge/Lock → Story/Lock → Rhyme/Prosody planı → Writer Tournament →
bağımsız critic'ler → yalnız zayıf satırları rewrite → final değerlendirme →
çok ölçekli benzerlik kontrolü → final söz ve rapor.

Model provider'ı arayüzden bağlanır; key dosyada/repo içinde tutulmaz.
Gerçek provider ve kullanım maliyeti görülmeden model seçimi veya kalite
skoru başarısı ilan edilmez. Hook/Concept kaynakları mekanizma kimliğiyle
izlenir; tam corpus satırları varsayılan writer girdisi olmaz.

Kullanıcının gerçek kabul/ret/satır değişikliği GOLD/RED olarak kaydedilecek.
Judge kendine verdiği puanla başarı kabulü yapmayacak. Sabit regression ve
kullanıcı kör değerlendirmesi/çift karşılaştırması ile kalibrasyon gerekir.

## Önemli sınırlar

- Morfoloji bağlamdan anlam ayrıştırmaz; birden fazla analiz unresolved olur.
- Ortak ekte hem yüzey hem grammatical function eşleşir. Aynı işlevin farklı
  seslenişleri kalan ekleri belirsiz bırakabilir; örtük allomorph kesimi yoktur.
- Aynı kelime/phrase tekrarı word-redif adayıdır; aynı anlam/görev olduğuna
  bağlam denetimi yapılmadan kesin semantik hüküm verilmez.
- Yarım/tam/zengin sınıfı **ortografik adaydır**. Fonem transkripsiyonu,
  zengin/cinaslı/tunç gibi bütün geleneksel türlerin tam sınıflaması yapılmaz.
- Hece vezni aruz değildir; aruz uzun/kısa hece ve imale/ulama/zihaf katmanı
  ayrıca tasarlanmalıdır. Melodi üstünde prozodi kabulü bu sürümde yoktur.
- Sözcüksel benzerlik paraphrase'ı güvenilir yakalamaz; embedding/semantik,
  blok ve ezgi/hook hizalama henüz yoktur. Hukuki copyright verdict null kalır.
- Özel arşiv, kapsamlı kafiye sözlüğü, klişe classifier ve gerçek LLM üretimi
  henüz bağlanmadı. Empty/mock veri gerçek kalite kanıtı yapılmaz.
- Büyük arşivde V1 pairwise line similarity maliyetlidir; MinHash/FTS/adayı
  daraltma gibi indeksli retrieval geniş korpustan önce eklenecektir.

## Doğrulanmış dış bileşen

[Zeyrek](https://github.com/obulat/zeyrek) morfolojik analiz için isteğe bağlı
backend; dağıtım sürümü 0.1.3 pinlenmiştir. Root/segment yüzeyleri için private
API kullanımı tek adapter içinde ve sürüm koruması altındadır. Tokenizer veri
download'u gerekmez; sözcük analizi real integration suite'inde çalıştırılır.
Repo README'si alpha/API değişim riski bildirir; bu yüzden `latest` kullanılmaz.

[Zemberek](https://github.com/ahmetaa/zemberek-nlp) alternatif backend adaydır;
V1'e kurulmuş/entegre edilmiş değildir. Önceki sohbetlerde anılan başka
repo/datasetlerin kaynağı ve lisansı doğrulanmadan kod veya veri alınmadı.
