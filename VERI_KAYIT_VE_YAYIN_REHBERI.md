# Veri Kayıt ve Yayın Rehberi

## Hangi bilgi nerede tutuluyor?

### Uyuşmazlık verileri

Dosya adı: `arbsys-dispute-data.js`

Bu paket tür, alt tür, konu, Uyuşmazlık Türü — Belge, müzakere metinleri,
anlaşma metinleri ve seçenek başlıklarını içerir.

### Belge şablonları

Dosya adı: `arbsys-template-data.js`

Bu paket `Anlaşma Belgesi`, `Son Tutanak`, `Sehven Kayıt` gibi bütün `.arbsys`
belge şablonlarının içeriklerini tutar.

## Dashboard'da yapılan değişiklik ne olur?

1. `Kaydı Güncelle`, şablon ekleme, ad değiştirme veya silme işlemi yapıldığında
   değişiklik aynı tarayıcıda otomatik saklanır.
2. Editörü yeniden kaydetmek zorunlu değildir.
3. Bu otomatik kayıt yalnızca aynı tarayıcı ve aynı site adresi için geçerlidir.
   Başka bilgisayara veya yayımlanmış sitenin bütün kullanıcılarına kendiliğinden
   aktarılmaz.

## Site dosyalarını güncellemenin en kolay yolu

Şablon Yükle → Şablon Verileri bölümünde:

1. `Site veri klasörünü bağla` düğmesine basın.
2. Sitenizin editör ve veri dosyalarının bulunduğu klasörü seçin.
3. Editör bu klasörde `arbsys-dispute-data.js` ve
   `arbsys-template-data.js` dosyalarını oluşturur veya günceller.
4. Aynı oturumdaki sonraki değişiklikler de bu iki dosyaya otomatik yazılır.
5. Bu dosyaları GitHub'a gönderdiğinizde Vercel yeni sürümü yayımlar.

Tarayıcı doğrudan klasöre yazmayı desteklemiyorsa:

1. `Site veri paketini indir (.zip)` düğmesine basın.
2. ZIP içindeki iki `.js` dosyasını çıkarın.
3. Bu dosyaları sitenin editör dosyasıyla aynı klasöre koyun.
4. Eski dosyaların yerine geçmesine izin verin.
5. Değişiklikleri GitHub'a gönderin.

## Yedek alma

`Tüm verileri yedekle` düğmesi uyuşmazlık verileriyle belge şablonlarını tek
bir JSON dosyasında toplar. Bu dosya doğrudan site tarafından okunmaz; yalnızca
Dashboard içindeki `Yedeği geri yükle` işlemi içindir.

## Vercel neden tarayıcıdan doğrudan değiştirilemiyor?

Vercel'e yayımlanan statik dosyalar çalışırken kalıcı olarak değiştirilemez.
Kalıcı ve bütün kullanıcılar tarafından görülen bir güncelleme için:

- yeni iki `.js` veri dosyasının GitHub projesine gönderilmesi ve yeniden
  yayımlanması veya
- ayrıca yetkilendirilmiş bir veritabanı ve sunucu API'si kurulması gerekir.

Bu sürüm veritabanı gerektirmeden kullanılabilen ilk yöntemi uygular.
