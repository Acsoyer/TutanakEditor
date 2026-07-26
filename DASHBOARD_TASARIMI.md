# Arbsys Veri Yönetimi Dashboard Tasarımı

## Amaç

Editörün içinden uyuşmazlık verilerini ve `.arbsys` belge şablonlarını aramak,
incelemek, eklemek, değiştirmek ve kaldırmak. Yapılan değişiklikler editörle
birlikte taşınmalı ve yedeklenebilmelidir.

## Ana ekranlar

### 1. Kayıtlar

- Tür, alt tür, konu ve eksik/tam durumuna göre filtreleme
- Tüm metin alanlarında arama
- D, E ve F alanlarının doluluk durumunu ayrı ayrı gösterme
- Eksik kayıtları kırmızı uyarıyla öne çıkarma
- Kaydı inceleme, düzenleme, çoğaltma ve silme
- Altı Excel alanını tek düzenleme formunda gösterme
- E ve F içindeki alternatifleri ayrı kartlar halinde ekleme, silme ve sıralama
- Değişiklikleri kaydetmeden önce önizleme

### 2. Tür / Alt Tür / Konu Yönetimi

- Yeni tür, alt tür ve konu ekleme
- Ad değiştirme ve silme
- Alt tür bulunmayan kayıtları doğrudan türe bağlama
- Bir öğe silinmeden önce etkilenecek kayıt sayısını gösterme
- Dolu kayıtları sahipsiz bırakacak silme işlemlerini engelleme veya taşıma isteme
- Aynı adla yinelenen kayıtları uyarma

### 3. Belge Şablonları

- Mevcut `.arbsys` şablonlarını listeleme ve arama
- Yeni şablon yükleme
- Şablon adını değiştirme, içeriğini güncelleme ve silme
- Numaralı varyasyonları aynı belge ailesi altında gruplama
- Şablonun içerdiği hedef alanları gösterme:
  - UYUŞMAZLIK TÜRÜ
  - UYUŞMAZLIK KONUSU (Talep Konusu)
  - VARILAN ANLAŞMA
- Geçersiz veya gerekli temel alanları eksik şablonu kullanıma kapatma
- “Sehven Kayıt” gibi yeni belge türlerini herhangi bir kod değişikliği olmadan ekleme

### 4. Kontrol ve Yedek

- Toplam kayıt, eksik kayıt ve şablon sayılarını gösterme
- Eksik D, E veya F alanlarını ayrı raporlama
- Sahipsiz alt tür, yinelenen konu ve bozuk şablon kontrolleri
- Tüm veri paketini JSON olarak dışa aktarma
- JSON yedeğini içe aktarma ve geri yüklemeden önce fark özeti gösterme
- Son değişikliklerin kısa geçmişini tutma

## Saklama yaklaşımı

Canlı veri, editör HTML dosyasının içindeki JSON veri bloklarında tutulacak.
Böylece “Kaydet” ile üretilen yeni editör sürümü bütün güncel kayıtları ve
şablonları yanında taşıyacak.

- JSON dışa aktarma ana yedekleme yöntemi olacak.
- Tarayıcı içi geçici kurtarma kaydı, kaydedilmemiş değişikliklere karşı yardımcı
  olacak; ana veri kaynağı olmayacak.
- Kaynak Excel dosyası başlangıç aktarımı ve gerektiğinde dışa aktarım için
  kullanılacak; dashboard doğrudan kullanıcının Excel dosyasını sessizce
  değiştirmeyecek.

## Veri kuralları

- Her tür, alt tür, konu kaydı ve şablon değişmeyen benzersiz bir kimlik taşıyacak.
- Ad değiştirmek bağlantıları bozmayacak.
- D, E veya F sütunlarından biri eksikse kayıt `(Şimdilik Eksik)` kalacak ve belge
  oluşturamayacak.
- E ve F alternatifleri ham metindeki “Veya” sözcüğüne göre değil, ayrı dizi
  öğeleri olarak saklanacak.
- F alanı şablonda yoksa şablonun kendi sonucu korunacak.
- Anlaşılan/anlaşılamayan hususlar dashboard tarafından otomatik
  doldurulmayacak.

## Uygulama sırası

1. Veri modelini kalıcı kimlikler, yedekleme ve otomatik eski-veri dönüşümüyle
   hazırlama.
2. Kayıt arama, eksik kayıt filtresi ve altı alanlı düzenleme ekranını ekleme.
3. Tür / alt tür / konu ekleme, değiştirme ve güvenli silme işlemlerini ekleme.
4. `.arbsys` şablon yükleme, değiştirme, aileleme ve doğrulama ekranını ekleme.
5. Bütünlük raporu, JSON içe/dışa aktarma ve son kullanıcı testlerini tamamlama.
