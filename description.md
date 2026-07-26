# ArbsysEditor_v1 — Geliştirici Devir Notu

Bu belge, `ArbsysEditor_v1.htm` üzerinde yeni bir özellik geliştirecek başka bir Codex/ChatGPT oturumunun editörü baştan analiz etmek zorunda kalmaması için hazırlanmıştır.

## 1. Dosyalar

Ana dosyalar aynı klasörde tutulmalıdır:

- `ArbsysEditor_v1.htm` — editörün tamamı; HTML, CSS ve JavaScript tek dosyanın içindedir.
- `arbsys-logo.svg` — üst araç çubuğunun solundaki yatay Arbsys logosu. Rengi SVG içinde `#272365` olarak sabitlenmiştir.
- `Arbsys_Logo_SVG.svg` — KAYDET penceresindeki **Arbsys Şablon** düğmesinin sembol logosu.

Ana çalışma kopyası:

`D:\byamandasoyer-GPT\ArbsysEditor_v1.htm`

Kullanılan/asıl sürüm:

`C:\Users\caner\Desktop\Sablonlar Arbsys Arsiv\ArbsysEditor_Versions\ArbsysEditor_v1.htm`

Asıl dosyanın mevcut yedeği:

`C:\Users\caner\Desktop\Sablonlar Arbsys Arsiv\ArbsysEditor_Versions\ArbsysEditor_v1_before_Codex_20260725.htm`

Yeni geliştirmede önce çalışma kopyasını değiştirip test etmek, ardından asıl dosyayı yedekleyerek güncellemek tercih edilmelidir. Logo dosyalarının HTML ile aynı klasörde kalması gerekir.

## 2. Genel Mimari

Editör herhangi bir framework veya build sistemi kullanmaz. Tek bir `.htm` dosyası doğrudan tarayıcıda açılır.

- CSS, `<head>` içindeki tek büyük `<style>` bloğundadır.
- Belge verisi, `#docTable > tbody` içindeki üst seviye `<tr>` elemanlarıdır.
- Uygulama davranışı, dosyanın sonundaki tek büyük `<script>` bloğundadır.
- Modal pencereler DOM içinde önceden bulunur; `.open` sınıfı ile gösterilir.
- Araç çubuğu ve düzenleme kontrolleri baskıda/PDF’de gizlenir.
- Düzenlenebilir alanlara `contenteditable="true"` kaynak HTML’de kalıcı olarak yazılmaz. Sayfa açılınca `applyEditable()` ekler; editör HTML’i kaydedilirken `stripEditable()` geçici olarak kaldırır.

Bu dosya tarayıcıda kaydedilmiş DOM durumları içerebildiğinden büyük bazı tablo satırları tek satır HTML olarak bulunabilir. Mekanik biçimlendirme veya dosyanın tamamını yeniden formatlama yapılmamalıdır; gereksiz büyük diff ve içerik bozulması riski yaratır.

## 3. Harici Bağımlılıklar

`<head>` içinde iki internet bağımlılığı vardır:

- Google Material Icons
- JSZip 3.10.1 (`cdnjs.cloudflare.com`)

DOCX üretimi JSZip’e bağlıdır. İnternet yoksa Material Icons görünmeyebilir ve DOCX üretimi çalışmayabilir. Editörün temel HTML düzenleme, `.arbsys` şablon kaydetme/yükleme ve HTML sürüm kaydetme işlevleri kendi kodundadır.

UDF kaydı `postForFile('/api/udf', ...)` üzerinden sunucu uç noktasına gider. Dosya yalnızca `file://` olarak açıldığında bu uç nokta bulunmayabilir; UDF’nin tam çalışması uygun web sunucusu/backend gerektirir.

## 4. Belge DOM Modeli

Ana belge:

```html
<table id="docTable" class="main-container">
  <thead class="print-space-head">...</thead>
  <tbody>
    <!-- düzenlenebilir belge modülleri -->
  </tbody>
  <tfoot class="print-space-foot">...</tfoot>
</table>
```

Her üst seviye `tbody > tr` bir “modül” kabul edilir. İçe/dışa aktarım ve satır ekleme sistemi bu varsayıma dayanır.

Başlıca satır türleri:

- `.title-wrapper-row` — içindeki `.title-table` ile belge başlığı.
- `.single-row` — etiket, iki nokta ve içerik sütunlu normal satır.
- `.empty-row` — boşluk satırı.
- Tam metin/madde satırları — tek hücreli metin yapıları.
- İmza satırları — `.sig-grid` ve bir veya daha fazla `.sig-box`.

Normal etiketli satırın beklenen yapısı:

```html
<tr class="single-row">
  <td class="label-cell"><span>BAŞLIK</span></td>
  <td class="colon-cell">:</td>
  <td class="content-cell">Detay yazısı...</td>
</tr>
```

`.lbl-dd-btn` düğmeleri kaynağın kalıcı veri modeli değildir. `injectLabelDropdowns()` gerektiğinde bunları `.label-cell` içine ekler. `.arbsys` dışa aktarımında bu düğmeler temizlenir ve içe aktarımdan sonra yeniden üretilir.

Yeni bir satır/modül tipi eklenirse en az şu alanlar kontrol edilmelidir:

1. `EDITABLE_SELECTORS`
2. `addBlock(refRow, type)`
3. `ioModuleLabel(tr)`
4. `.arbsys` içe/dışa aktarımı
5. DOCX dönüşümü
6. UDF dönüşümü
7. Baskı/PDF CSS’i
8. Satır hover, sürükle-bırak ve silme davranışı

## 5. Araç Çubuğu ve Ana Arayüz

Üst araç çubuğu `.toolbar` içindedir.

- Sol üst marka: `.toolbar-brand`
- Biçimlendirme düğmeleri: `.toolbar-left`
- Üst/Alt Bilgi, Şablon Yükle ve KAYDET: `.toolbar-right`
- **Şablon Yükle** düğmesi `openIOModal()` çağırır.
- **KAYDET** düğmesi `openSaveModal()` çağırır.

Satırın üzerine gelindiğinde:

- `#floatPanel` ve `#floatPlus` yeni modül ekleme menüsünü gösterir.
- `#floatDeletePanel` sürükleme ve silme kontrollerini gösterir.
- `addBlock()` yeni satırı oluşturur.
- `removeBlock()` satırı siler.

Klavye kısayolları ve aktif satır tespiti mevcut koda bağlıdır. Yeni modül ekleme düğmesi eklenirse hem `data-action` hem `addBlock()` eşlemesi güncellenmelidir.

## 6. KAYDET Penceresi

Modal: `#saveModal`

Dosya adının tek kaynağı:

```js
getFileName()
```

Bu fonksiyon `#fileNameInput` değerini alır, geçersiz dosya adı karakterlerini temizler. Yeni bir kayıt biçimi eklenecekse aynı fonksiyonu kullanmalıdır.

`executeSave(type)` yönlendirmeleri:

- `arbsys` → `exportArbsys(getFileName())`
- `pdf` → `saveAsPdf()`
- `docx` → `exportToDocx()`
- `udfjson` → `exportToUdfJson()`
- `htm` → `saveAsHtm()`

Görünen ana seçenekler:

- **Arbsys Şablon**
- PDF
- DOCX
- UDF

HTML editör kaydı kullanıcıya açık bir “HTML” düğmesi değildir. KAYDET penceresinin sol altındaki küçük **`-versiyon-`** yazısı `executeSave('htm')` çağırır. Bu davranış özellikle gizli tutulmuştur; düğmenin metnini “HTML” gibi açıklayıcı bir metne çevirmeyin.

Sağ alttaki **Ayarlar** bağlantısı `openSettingsModal()` çağırır.

“Üst / alt bilgi olmadan kaydet” seçeneği PDF, DOCX, UDF ve editör HTML’i davranışlarıyla ilişkili olabilir. Yeni kayıt türlerinde bu tercihin geçerli olup olmadığı açıkça değerlendirilmelidir.

## 7. `.arbsys` Şablon Biçimi

`.arbsys` aslında sade bir HTML parçasıdır; tam uygulama değildir.

Başlangıç işareti:

```text
<!-- ARBSYS-CONTENT v1 -->
```

İçerik yaklaşık olarak şöyledir:

```html
<table>
  <tbody>
    <!-- docTable içindeki üst seviye satırlar -->
  </tbody>
</table>
```

`exportArbsys(fileName)`:

- Yalnızca `#docTable > tbody` içeriğini kaydeder.
- Üst/alt bilgi ve logo ayarlarını içermez.
- Geçici hover/silme sınıflarını temizler.
- Dropdown düğmelerini kaldırır.
- `contenteditable` niteliklerini kaldırır.

`ioHandleFile()` ve `ioParseText()`:

- `.arbsys`, `.htm` ve `.html` okuyabilir.
- Güvenlik için içe aktarılan `script` elemanlarını siler.
- Önce `.arbsys` tablo biçimini, bulamazsa tam editördeki `#docTable > tbody` yapısını arar.

İçe aktarma modları:

- **Değiştir** — mevcut `tbody` içeriğini tamamen değiştirir ve kullanıcıdan onay ister.
- **Ekle** — seçilen üst seviye modülleri belgenin sonuna ekler.

İçe aktarımdan sonra mutlaka:

```js
injectLabelDropdowns();
applyEditable();
```

çağrıları yapılır.

## 8. Tam Editör HTML’i Kaydetme

`saveAsHtm()` editörün çalışır durumdaki tamamını şu yöntemle indirir:

```js
document.documentElement.outerHTML
```

Kaydetmeden önce:

- Form input değerleri HTML niteliklerine senkronize edilir.
- Checkbox/radio `checked` nitelikleri senkronize edilir.
- Gerekirse üst/alt bilgi geçici olarak kapatılır.
- `stripEditable()` çağrılır.

İndirmeden sonra `applyEditable()` ile düzenlenebilirlik geri eklenir.

Bu yöntem nedeniyle DOM içine eklenen kalıcı ayar verileri kaydedilmiş `.htm` dosyasına taşınabilir. Ancak yalnızca JavaScript değişkeninde tutulan veri `outerHTML` içine girmez. Kalıcı olması gereken yeni ayarlar bir DOM düğümüne/JSON veri bloğuna senkronize edilmelidir.

## 9. Başlık Dropdown Sistemi

Dropdown:

- Ana kapsayıcı: `#lblDropdown`
- Arama alanı: `.lbl-search`
- Seçenek listesi: `.lbl-opts-list`
- Seçenek: `.lbl-opt`

Hazır seçenekler:

```js
const BASE_LABEL_PRESETS = [
  { label: 'Listede görünen metin', value: 'BELGEYE YAZILACAK METİN' }
];
```

Burada:

- `label` dropdown’da kullanıcıya görünen isimdir.
- `value` seçildiğinde `.label-cell span` içine HTML olarak yazılan değerdir.
- Bazı hazır `value` değerlerinde bilinçli olarak `<br>` bulunur.

Saat alanlarının mevcut doğru değerleri:

```js
{ label: 'Toplantı Başlama Saati', value: 'TOPLANTI BAŞL. SAATİ' }
{ label: 'Toplantı Bitiş Saati', value: 'TOPLANTI BİTİŞ. SAATİ' }
```

Özel seçenekler:

```js
let CUSTOM_LABEL_PRESETS = loadCustomLabelPresets();
let LABEL_PRESETS = BASE_LABEL_PRESETS.concat(CUSTOM_LABEL_PRESETS);
```

Kalıcı veri düğümü:

```html
<script id="customLabelPresetsData" type="application/json">[]</script>
```

Önemli akış:

1. Sayfa açılırken `loadCustomLabelPresets()` JSON’u okur.
2. Ayarlarda yeni satır eklenince `CUSTOM_LABEL_PRESETS` güncellenir.
3. `refreshLabelPresets()` çalışır.
4. `persistCustomLabelPresets()` JSON script düğümünü günceller.
5. `renderLabelDropdownOptions()` dropdown’ı yeniden çizer.
6. `renderSettingsList()` Ayarlar listesini yeniden çizer.
7. Kullanıcı `-versiyon-` ile HTML’i kaydedince JSON düğümü `outerHTML` içinde kalır.

Hazır seçenekler Ayarlar’dan silinemez. Kullanıcının eklediği özel seçenekler silinebilir.

## 10. Ayarlar Penceresi

Modal: `#settingsModal`

İki sütun bulunur:

- “Listede Görünen İsim”
- “Sayfaya Yazılacak Metin”

İlgili fonksiyonlar:

- `openSettingsModal()`
- `closeSettingsModal(e)`
- `renderSettingsList()`
- `toggleSettingsAddRow()`
- `addCustomLabelPreset()`
- `removeCustomLabelPreset(index)`
- `refreshLabelPresets()`

Ayarlar penceresi açıldığında KAYDET penceresi kapanır. Eklenen seçenek hemen dropdown’a yansır; fakat yeni editör dosyasına kalıcı olması için kullanıcı KAYDET penceresini yeniden açıp **`-versiyon-`** bağlantısına basmalıdır.

Bu sisteme yeni ayar türü eklenirse kalıcılık için yalnızca çalışma zamanı değişkenine güvenmeyin; `saveAsHtm()` tarafından kaydedilecek DOM tabanlı bir veri alanı kullanın.

## 11. Üst/Alt Bilgi

Kontrol paneli: `#hfPanel`

Başlıca fonksiyonlar:

- `toggleHFPanel()`
- `toggleHFData(type)`
- `clearHFData(type)`
- `updateStatusDot()`
- `handleLogoSelect(input)`
- `padLogoTo4x1(srcDataUrl, callback)`
- `updateFooterText()`

Yüklenen üst bilgi logosu base64 olarak çalışma DOM’una yerleştirilir. `padLogoTo4x1()` logo alanını baskı düzenine uygun 4:1 tuvale dönüştürür.

Baskı başlığı/alt bilgisi:

- `.fixed-print-header`
- `.fixed-print-footer`
- `#logoPrintBox`
- `#footerPrintBox`

Bu alanların ekran görünümü ve baskı görünümü ayrı CSS kurallarına sahiptir.

## 12. PDF, DOCX ve UDF

### PDF

`saveAsPdf()` tarayıcının `window.print()` mekanizmasını kullanır.

- Geçici hover ve açık menü durumlarını temizler.
- Dosya adı önerisi için geçici olarak `document.title` değerini değiştirir.
- Baskı CSS’i A4 düzeni, sabit üst/alt bilgi ve kenar boşluklarını yönetir.

### DOCX

`exportToDocx()`:

- JSZip ile doğrudan `.docx` paketi üretir.
- Belge satırlarını WordprocessingML’e dönüştürür.
- Etiketli satırlar, tam metinler, başlıklar ve imza tabloları için ayrı dönüşüm mantıkları içerir.
- Yeni DOM sınıfları eklendiğinde DOCX tarafında sessizce kaybolmaması için bu fonksiyon mutlaka güncellenmelidir.

### UDF

`exportToUdfJson()` belgeyi ara JSON yapısına dönüştürür ve `/api/udf` uç noktasına gönderir.

- Hizalama ve temel inline biçimlendirmeler kendi dönüştürücüsünde işlenir.
- Son çıktı istemcide üretilmez; sunucu yanıtından indirilir.
- Yeni satır/modül tipleri UDF dönüşümüne ayrıca eklenmelidir.

## 13. Stil ve Renkler

Temel marka rengi:

```css
#272365
```

Editörde tarihsel olarak kullanılan ana indigo:

```css
#3c40c6
```

Diğer kayıt düğmeleri kendi vurgu renklerine sahiptir:

- PDF: kırmızı
- DOCX: mavi
- UDF: mor
- Şablon yükleme: teal

Yeni arayüz elemanları mevcut `.tb-btn`, `.tb-btn-wide`, `.modal-overlay`, `.modal-content` ve vurgu sınıflarını mümkün olduğunca yeniden kullanmalıdır.

## 14. Güvenli Değişiklik Kuralları

Başka bir chat bu editöre bir özellik uygularken:

1. Dosyanın UTF-8 kodlamasını korumalıdır.
2. Türkçe karakterleri mojibake hâline getirmemelidir.
3. Tüm dosyayı otomatik yeniden biçimlendirmemelidir.
4. `#docTable > tbody > tr` modül modelini bozmamalıdır.
5. Geçici UI elemanlarını belge verisine veya `.arbsys` çıktısına karıştırmamalıdır.
6. Yeni düzenlenebilir alanları `EDITABLE_SELECTORS` sistemine bağlamalıdır.
7. Yeni dinamik satırlardan sonra `applyEditable()` ve gerekiyorsa `injectLabelDropdowns()` çağırmalıdır.
8. Kalıcı ayarları yalnızca JS değişkeninde bırakmamalıdır.
9. Dosya adı gereken her yerde `getFileName()` kullanmalıdır.
10. KAYDET penceresindeki gizli HTML kaydını **`-versiyon-`** olarak korumalıdır.
11. Mevcut `.arbsys`, PDF, DOCX ve UDF akışlarında gerileme olmadığını kontrol etmelidir.
12. Asıl masaüstü dosyasını değiştirmeden önce yeni bir yedek almalıdır.

## 15. Asgari Test Kontrol Listesi

Bir değişiklikten sonra en az şunlar doğrulanmalıdır:

- Sayfa JavaScript hatası olmadan açılıyor.
- Sol üst Arbsys logosu görünüyor.
- Biçimlendirme düğmeleri çalışıyor.
- Satır üzerine gelince ekle, sürükle ve sil kontrolleri çalışıyor.
- Başlık dropdown’ı açılıyor, aranıyor ve değer seçildiğinde belgeye doğru metni yazıyor.
- KAYDET penceresi açılıyor.
- Arbsys Şablon kaydı `.arbsys` uzantısıyla ve `Kayıt Dosya Adı` değeriyle başlıyor.
- Şablon Yükle penceresinde Değiştir/Ekle akışları çalışıyor.
- Ayarlar’dan özel seçenek ekleniyor ve dropdown’a anında geliyor.
- `-versiyon-` ile kaydedilen `.htm` yeniden açıldığında özel seçenek korunuyor.
- PDF baskı önizlemesinde araç çubuğu ve geçici kontroller görünmüyor.
- DOCX ve UDF’de yeni içerik türü kaybolmuyor.
- Tarayıcı konsolunda yeni hata oluşmuyor.

## 16. Yeni Chat İçin Önerilen İstek Kalıbı

Aşağıdaki metin, bu belge ile birlikte yeni chat’e verilebilir:

> `description.md` dosyasını tamamen oku ve içindeki mimari/kalıcılık/test kurallarına uy. `ArbsysEditor_v1.htm` dosyasına şu özelliği uygula: **[buraya istenen özelliği yaz]**. Önce çalışma kopyasında uygula, JavaScript ve arayüz akışını test et, mevcut kayıt/şablon/dropdown davranışlarını bozma. Asıl masaüstü dosyasını güncellemeden önce tarihli bir yedek oluştur.

