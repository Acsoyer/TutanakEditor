# GitHub ve Vercel Bağlantı Durumu

## Mevcut durum

`ArbsysEditor_v5` klasörü şu anda:

- bir Git deposu değildir;
- tanımlı bir GitHub uzak deposuna sahip değildir;
- `.vercel/project.json` proje bağlantısına sahip değildir;
- çalışma alanında Arbsys'e ait doğrulanabilir bir Vercel proje bağlantısı
  bulunmamaktadır.

Çalışma alanında bulunan `byamandasoyer.pt` Vercel ayarları farklı bir siteye
aittir. Arbsys dosyaları yanlış siteye gönderilmemiştir.

## Push ve yayın için gereken bilgi

Aşağıdakilerden biri sağlanmalıdır:

1. Arbsys sitesinin mevcut GitHub depo adresi ve editörün depo içindeki klasörü,
   veya
2. Yeni bir depo oluşturulacaksa depo adı ile deponun herkese açık mı özel mi
   olacağı.

Vercel GitHub deposuna zaten bağlıysa push sonrasında yayın otomatik başlar.
Bağlı değilse Vercel'deki proje adı veya proje bağlantısı da gereklidir.

## Siteye konacak temel dosyalar

- `ArbsysEditor_v5.htm` — sitenin kullandığı ada göre çoğunlukla `index.html`
- `arbsys-dispute-data.js`
- `arbsys-template-data.js`
- `Arbsys_Logo_SVG.svg`
- `arbsys-logo.svg`

Dashboard'ın ürettiği iki veri dosyası, editör HTML dosyasıyla aynı klasörde
bulunmalıdır.

