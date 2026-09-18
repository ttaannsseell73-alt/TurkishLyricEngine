# Yerel JSON API

`tle serve --out outputs/api` varsayılan127.0.0.1:8765. Port/host ayarlanabilir.
Non-loopback bind TLE_SERVER_TOKEN gerektirir; token varsa bütün uçlar
Authorization: Bearer header'ıyla çağrılır. CLI anahtarı argüman olarak almaz.

| Yol | Method/body | Sonuç |
|---|---|---|
| /health | GET | Sürüm/config booleans; credential yok |
| /analyze | POST {text,meter?,durak?} | Prosody ve vezin JSON; text≤20000chars |
| /generate | POST Brief alanları; theme zorunlu; seed opsiyonel | Pipeline final; server run klasöründe journal/lyrics |
| /search | POST {query,limit?} | Archive metadata sonuçları; raw text yok |
| /feedback | POST gerçek FeedbackStore.add alanları | ID ve genre preference statistics |

Generate alanları: theme,genre,mood,meter,durak,rhyme_scheme,max_chars,
concept_count,hook_count,writer_count,max_rounds,target_score,max_calls,avoid,
prefer_nonverb_endings,seed. Bilinmeyen alan reddedilir. Runtime provider
server --config veya TLE_PROVIDER/TLE_MODEL/TLE_BASE_URL ile ayarlanır;
credential sadece environment'tadır. İstemci model key'i veya dosya yolu
vermez; çıktı server root altında rastgele run klasörüne kaydedilir.

```json
{"theme":"Kendi yoluna dönmek","meter":7,"durak":[4,3],"rhyme_scheme":"ABCB"}
```

Server --db/--dictionary/--feedback-db ile kaynakları bağlar. Feedback için
run_id,genre,decision,original,mechanism_id,hook_words zorunlu; replacement/edit
ve note isteğe bağlıdır. Bu uç kullanıcı beyanını kaydeder; otomatik artistik
kabul vermez. CLI feedback provenance/GOLD-RED eklemesi ayrı bir tercihtir.

Request≤100000bytes; chunked encoding reddedilir; body okuma timeout15s.
Tek generation aynı anda çalışır; diğeri409. Hatalı body/config400,
auth401, bilinmeyen route404, büyük/boş body413. Her cevap JSON UTF-8,
Cache-Control:no-store. URL/request log yoktur. Model bağlantı hatası body
ve credential'ı echo etmez. Health config varlığı canlı model testi değildir.
Remote publishing/deployment bu local API'nin çalışma koşulu değildir.
