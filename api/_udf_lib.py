#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
json_to_udf.py

HTM editorunden uretilen ara JSON verisini ("udfdata.json") alip
UYAP Kelime Islemci'nin actigi .udf (aslinda zip icinde content.xml) formatina
cevirir.

Kullanim:
    python3 json_to_udf.py girdi.udfdata.json cikti.udf

UDF content.xml yapisi (kisa ozet):
    <template format_id="1.8">
      <content><![CDATA[ ...TUM DUZ METIN TEK AKIS HALINDE... ]]></content>
      <properties><pageFormat .../></properties>
      <elements resolver="hvl-default">
        <header> ...paragraph/table/image... </header>
        ...body: paragraph/table elemanlari...
        <footer> ...paragraph/table/image... </footer>
        ...(sayfa sonu ince cizgi imaji)
      </elements>
      <styles>...</styles>
    </template>

Kritik nokta: <content> icindeki metin TEK bir karakter akisidir. <elements>
icindeki <content startOffset=".." length=".." .../> etiketleri bu akistan
bir dilim alip bicim (bold/italic/underline/font) uygular. Yani bicim,
metinden AYRI, offset tabanli bir "overlay" olarak tutulur (DOCX'teki gibi
inline run degil).

Bu yuzden bu script iki asamali calisir:
  1) JSON'daki paragraflari gezip TUM duz metni tek bir string'de biriktirir
     (offset defterini tutarak)
  2) Ayni gezinti sirasinda, biriken offset/length bilgisiyle
     <paragraph>/<table>/<content> XML'ini uretir.

Not: '\xa0' (nbsp) karakterleri UDF'de <content> yerine <space> etiketiyle
temsil ediliyor (orijinal ornek belgede boyle gozlemlendi). Bu script de
ayni kurala uyar.
"""

import json
import sys
import zipfile
import io
import os
import base64

# ----
# Sabitler (orijinal ornek UDF'den cikarilan cizgi imajlari, sayfa formati)
# ----

SEP_LINE_2PX_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAEUlEQVR42mMICQn5D8IMMAAAM4oD"
    "94WRpYUAAAASUVORK5CYII="
)  # 514x2 ince ayirici cizgi (header ve footer'da kullanilir)

SEP_LINE_1PX_FINAL_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAgIAAAABCAYAAACsTsZLAAAAGklEQVR42mMICQn5P4pH8SgexaN4"
    "FI/ikYkBsWP6JF+/+nsAAAASUVORK5CYII="
)  # 514x1 belge sonu ince cizgi

# ----
# Olcu sabitleri (kullanicinin verdigi spesifikasyona gore, cm -> point)
# 1 cm = 28.3464567 pt
# ----
CM_TO_PT = 28.3464567

LEFT_MARGIN_CM = 1.75
RIGHT_MARGIN_CM = 1.25
TOP_HEADER_AREA_CM = 3.0      # sayfa ustunden ayrilan toplam header alani
                    # (0.5cm ust bosluk + 2cm logo + cizgi icin pay)
BOTTOM_FOOTER_AREA_CM = 2.0   # sayfa altindan ayrilan toplam footer alani

# ----
# v34 DEGISIKLIGI - HEADER/FOOTER UST-ALT BOSLUGU ARTIK "SAYFA YAPISINDAN"
# (headerFOffset / footerFOffset) VERILIYOR, header/footer ICERIGINDEN DEGIL.
#
# ONCEKI MODEL (v33): headerFOffset=0, footerFOffset=0 idi; ust bosluk
#   header'in ilk paragrafina SpaceAbove ile, alt bosluk footer'in son
#   paragrafina SpaceBelow ile "icerden" veriliyordu (sahte bosluk).
#
# YENI MODEL (v34): UYAP'in kendi bos belgesindeki gibi (default UDF'te
#   headerFOffset=0.706cm, SpaceAbove YOK) - bosluk SAYFA SEVIYESINDE
#   verilir, header/footer ICINDEKI SpaceAbove/SpaceBelow SIFIRLANIR.
#
# KRITIK: Bosluk TEK KAYNAKTAN gelmeli. Hem headerFOffset hem SpaceAbove
#   a(yni anda) verilirse bosluk IKI KEZ sayilir -> header topMargin'i
#   asar -> govdeyle CAKISIR -> layout bozulur (v33 oncesi yasanan sorun).
#   Bu yuzden asagida SpaceAbove/SpaceBelow TAMAMEN kaldirildi.
#
# GEOMETRI KORUNUMU: topMargin (3.0cm) ve bottomMargin (2.1cm) DEGISMEDI;
#   govde metni ayni yerde baslar/biter. Sadece "ust/alt bosluk" mekanizmasi
#   sahte (paragraf) yerine gercek (sayfa offset) hale getirildi. Logo, ust
#   bosluk 0.4->0.5 yapildigi icin 0.1cm asagi kayar; footer 0.5->0.5 oldugu
#   icin BIREBIR ayni kalir. Logoyu da birebir ayni tutmak istersen
#   HEADER_FOFFSET_CM'yi 0.4 yap.
HEADER_FOFFSET_CM = 0.5      # <-- Kenardan > Ust Yazi (headerFOffset). Ayarlanabilir.
FOOTER_FOFFSET_CM = 0.3      # <-- Kenardan > Alt Yazi (footerFOffset). (v34.1: 0.5 -> 0.3)

HEADER_TOP_GAP_CM = 0.4      # (v34: ARTIK KULLANILMIYOR - bosluk headerFOffset'a tasindi)
LOGO_HEIGHT_CM = 2.0
LOGO_WIDTH_CM = 8.0

FOOTER_BOTTOM_GAP_CM = 0.5    # (v34: ARTIK KULLANILMIYOR - bosluk footerFOffset'a tasindi)

LEFT_MARGIN_PT = LEFT_MARGIN_CM * CM_TO_PT
RIGHT_MARGIN_PT = RIGHT_MARGIN_CM * CM_TO_PT
TOP_HEADER_AREA_PT = TOP_HEADER_AREA_CM * CM_TO_PT
BOTTOM_FOOTER_AREA_PT = BOTTOM_FOOTER_AREA_CM * CM_TO_PT
HEADER_TOP_GAP_PT = HEADER_TOP_GAP_CM * CM_TO_PT
LOGO_HEIGHT_PT = LOGO_HEIGHT_CM * CM_TO_PT
LOGO_WIDTH_PT = LOGO_WIDTH_CM * CM_TO_PT
FOOTER_BOTTOM_GAP_PT = FOOTER_BOTTOM_GAP_CM * CM_TO_PT
# v34: sayfa seviyesindeki header/footer offset'leri (point)
HEADER_FOFFSET_PT = HEADER_FOFFSET_CM * CM_TO_PT
FOOTER_FOFFSET_PT = FOOTER_FOFFSET_CM * CM_TO_PT

# A4 sayfa genisligi (point) - UDF pageFormat'ta mediaSizeName=1 (A4) kullaniliyor
A4_WIDTH_PT = 595.28

# Sayfa ici (kenar bosluklari haric) kullanilabilir genislik - cizgilerin
# ve imza tablosunun genisligi bununla sinirli olmali.
CONTENT_WIDTH_PT = A4_WIDTH_PT - LEFT_MARGIN_PT - RIGHT_MARGIN_PT

# DUZELTME GECMISI - tableWidth denemesi (KALDIRILDI):
# Once ana tabloya "tableWidth" attribute'u eklemistik (18cm karsiligi,
# sonra +1cm telafi ile 19cm karsiligi point). Kullanicinin dogrudan UYAP
# testi (Tablo Ozellikleri > Tercih Edilen Genislik: 17 -> 18 yapip
# kaydetmesi) SONUCUNDA ortaya cikan content.xml incelendiginde:
#   - tableWidth attribute'u TAMAMEN SILINMIS (UYAP tarafindan)
#   - columnSpans HIC DEGISMEMIS (hala 26,2,72)
#   - pageFormat HIC DEGISMEMIS
# Bu, UYAP'in tabloyu HER ZAMAN sayfa icerik genisligine (marjinler arasi)
# OTOMATIK yaydigini ve bizim yazdigimiz tableWidth degerinin GEREKSIZ
# (hatta yanlis yorumlanarak sorun yaratan) bir attribute oldugunu
# gosteriyor. Bu yuzden tableWidth TAMAMEN KALDIRILDI - orijinal referans
# belgede de zaten hic yoktu, en bastan dogru olan buydu.

# UYAP "Sayfa Duzenleme" ekranindaki alanlarin content.xml karsiliklari
# (kullanicinin ekran goruntusu + elle degistirdigi dosyalar karsilastirilarak
# tespit edildi):
#   - Kenarlar > Ust/Alt   <-> pageFormat topMargin / bottomMargin (point)
#   - Kenardan > Ust Yazi / Alt Yazi <-> pageFormat headerFOffset / footerFOffset (point)
# Kullanicinin son talebi: Kenarlar > Ust=3cm, Alt=2.1cm; Kenardan > Ust
# Yazi=0, Alt Yazi=0 (bu ikincisi zaten dogruydu).
TOP_MARGIN_CM = 3.0
BOTTOM_MARGIN_CM = 1.4   # (v34.1: 2.1 -> 1.4, kullanici talebi; footer daha yukari)
TOP_MARGIN_PT = TOP_MARGIN_CM * CM_TO_PT
BOTTOM_MARGIN_PT = BOTTOM_MARGIN_CM * CM_TO_PT

# ----
# VARSAYILAN SEKME (TAB) UZAKLIGI = 1.25 cm
# UYAP'ta "Paragraf Ozellikleri > Sekmeler > Varsayilan Sekme (cm)" degeri
# 1.25 yapildiginda, program HER govde paragrafina asagidaki gibi bir
# TabSet listesi (1.25cm = 35.43307 pt araliklarla 511 durak) ekler VE
# belge sonuna <tabLength length="1.25"> elemanini koyar. Boylece "Satir
# Basi" (word-tab) ile eklenen her tab, 2.5cm (UYAP varsayilani) yerine
# 1.25cm girinti verir. Asagidaki dize, UYAP'in kendi urettigi content.xml'
# den BIREBIR alinmistir (Java float bicimi dahil) - bu yuzden numpy vb.
# bir bagimlilik olmadan, dogrudan literal olarak gomulmustur.
TAB_LENGTH_CM = 1.25
TABSET_1_25CM = (
    "35.43307:0:0,70.86614:0:0,106.29921:0:0,141.73228:0:0,177.16536:0:0,212.59842:0:0,248.0315:0:0,283.46457:0:0,318.89764:0:0,354.33072:0:0,389.7638:0:0,425.19684:0:0,460.6299:0:0,496.063:0:0,531.4961:0:0,566.92914:0:0,602.3622:0:0,637.7953:0:0,673.22833:0:0,708.66144:0:0,744.0945:0:0,779.5276:0:0,814.96063:0:0,850.3937:0:0,885.8268:0:0,921.2598:0:0,956.69293:0:0,992.126:0:0,1027.5591:0:0,1062.9922:0:0,1098.4252:0:0,1133.8583:0:0,1169.2914:0:0,1204.7244:0:0,1240.1575:0:0,1275.5906:0:0,1311.0237:0:0,1346.4567:0:0,1381.8898:0:0,1417.3229:0:0,1452.7559:0:0,1488.189:0:0,1523.6221:0:0,1559.0552:0:0,1594.4882:0:0,1629.9213:0:0,1665.3544:0:0,1700.7874:0:0,1736.2205:0:0,1771.6536:0:0,1807.0867:0:0,1842.5197:0:0,1877.9528:0:0,1913.3859:0:0,1948.819:0:0,1984.252:0:0,2019.685:0:0,2055.1182:0:0,2090.5513:0:0,2125.9844:0:0,2161.4172:0:0,2196.8503:0:0,2232.2834:0:0,2267.7166:0:0,2303.1497:0:0,2338.5828:0:0,2374.0159:0:0,2409.4487:0:0,2444.8818:0:0,2480.315:0:0,2515.748:0:0,2551.1812:0:0,2586.6143:0:0,2622.0474:0:0,2657.4802:0:0,2692.9133:0:0,2728.3464:0:0,2763.7795:0:0,2799.2126:0:0,2834.6458:0:0,2870.0789:0:0,2905.5117:0:0,2940.9448:0:0,2976.378:0:0,3011.811:0:0,3047.2441:0:0,3082.6772:0:0,3118.1104:0:0,3153.5432:0:0,3188.9763:0:0,3224.4094:0:0,3259.8425:0:0,3295.2756:0:0,3330.7087:0:0,3366.1418:0:0,3401.5747:0:0,3437.0078:0:0,3472.441:0:0,3507.874:0:0,3543.3071:0:0,3578.7402:0:0,3614.1733:0:0,3649.6064:0:0,3685.0393:0:0,3720.4724:0:0,3755.9055:0:0,3791.3386:0:0,3826.7717:0:0,3862.2048:0:0,3897.638:0:0,3933.0708:0:0,3968.504:0:0,4003.937:0:0,4039.37:0:0,4074.8032:0:0,4110.2363:0:0,4145.6694:0:0,4181.1025:0:0,4216.5356:0:0,4251.9688:0:0,4287.4014:0:0,4322.8345:0:0,4358.2676:0:0,4393.7007:0:0,4429.134:0:0,4464.567:0:0,4500.0:0:0,4535.433:0:0,4570.866:0:0,4606.2993:0:0,4641.7324:0:0,4677.1655:0:0,4712.5986:0:0,4748.0317:0:0,4783.465:0:0,4818.8975:0:0,4854.3306:0:0,4889.7637:0:0,4925.197:0:0,4960.63:0:0,4996.063:0:0,5031.496:0:0,5066.929:0:0,5102.3623:0:0,5137.7954:0:0,5173.2285:0:0,5208.6616:0:0,5244.0947:0:0,5279.528:0:0,5314.9604:0:0,5350.3936:0:0,5385.8267:0:0,5421.26:0:0,5456.693:0:0,5492.126:0:0,5527.559:0:0,5562.992:0:0,5598.4253:0:0,5633.8584:0:0,5669.2915:0:0,5704.7246:0:0,5740.1577:0:0,5775.591:0:0,5811.0234:0:0,5846.4565:0:0,5881.8896:0:0,5917.3228:0:0,5952.756:0:0,5988.189:0:0,6023.622:0:0,6059.055:0:0,6094.4883:0:0,6129.9214:0:0,6165.3545:0:0,6200.7876:0:0,6236.2207:0:0,6271.654:0:0,6307.0864:0:0,6342.5195:0:0,6377.9526:0:0,6413.3857:0:0,6448.819:0:0,6484.252:0:0,6519.685:0:0,6555.118:0:0,6590.5513:0:0,6625.9844:0:0,6661.4175:0:0,6696.8506:0:0,6732.2837:0:0,6767.717:0:0,6803.1494:0:0,6838.5825:0:0,6874.0156:0:0,6909.4487:0:0,6944.882:0:0,6980.315:0:0,7015.748:0:0,7051.181:0:0,7086.6143:0:0,7122.0474:0:0,7157.4805:0:0,7192.9136:0:0,7228.3467:0:0,7263.78:0:0,7299.213:0:0,7334.6455:0:0,7370.0786:0:0,7405.5117:0:0,7440.945:0:0,7476.378:0:0,7511.811:0:0,7547.244:0:0,7582.6772:0:0,7618.1104:0:0,7653.5435:0:0,7688.9766:0:0,7724.4097:0:0,7759.843:0:0,7795.276:0:0,7830.7085:0:0,7866.1416:0:0,7901.5747:0:0,7937.008:0:0,7972.441:0:0,8007.874:0:0,8043.307:0:0,8078.74:0:0,8114.1733:0:0,8149.6064:0:0,8185.0396:0:0,8220.473:0:0,8255.905:0:0,8291.339:0:0,8326.771:0:0,8362.205:0:0,8397.638:0:0,8433.071:0:0,8468.504:0:0,8503.9375:0:0,8539.37:0:0,8574.803:0:0,8610.236:0:0,8645.669:0:0,8681.103:0:0,8716.535:0:0,8751.969:0:0,8787.401:0:0,8822.835:0:0,8858.268:0:0,8893.701:0:0,8929.134:0:0,8964.567:0:0,9000.0:0:0,9035.434:0:0,9070.866:0:0,9106.299:0:0,9141.732:0:0,9177.165:0:0,9212.599:0:0,9248.031:0:0,9283.465:0:0,9318.897:0:0,9354.331:0:0,9389.764:0:0,9425.197:0:0,9460.63:0:0,9496.063:0:0,9531.496:0:0,9566.93:0:0,9602.362:0:0,9637.795:0:0,9673.229:0:0,9708.661:0:0,9744.095:0:0,9779.527:0:0,9814.961:0:0,9850.394:0:0,9885.827:0:0,9921.26:0:0,9956.693:0:0,9992.126:0:0,10027.56:0:0,10062.992:0:0,10098.425:0:0,10133.858:0:0,10169.291:0:0,10204.725:0:0,10240.157:0:0,10275.591:0:0,10311.023:0:0,10346.457:0:0,10381.89:0:0,10417.323:0:0,10452.756:0:0,10488.189:0:0,10523.622:0:0,10559.056:0:0,10594.488:0:0,10629.921:0:0,10665.3545:0:0,10700.787:0:0,10736.221:0:0,10771.653:0:0,10807.087:0:0,10842.52:0:0,10877.953:0:0,10913.386:0:0,10948.819:0:0,10984.252:0:0,11019.686:0:0,11055.118:0:0,11090.551:0:0,11125.984:0:0,11161.417:0:0,11196.851:0:0,11232.283:0:0,11267.717:0:0,11303.149:0:0,11338.583:0:0,11374.016:0:0,11409.449:0:0,11444.882:0:0,11480.315:0:0,11515.748:0:0,11551.182:0:0,11586.614:0:0,11622.047:0:0,11657.48:0:0,11692.913:0:0,11728.347:0:0,11763.779:0:0,11799.213:0:0,11834.6455:0:0,11870.079:0:0,11905.512:0:0,11940.945:0:0,11976.378:0:0,12011.812:0:0,12047.244:0:0,12082.678:0:0,12118.11:0:0,12153.543:0:0,12188.977:0:0,12224.409:0:0,12259.843:0:0,12295.275:0:0,12330.709:0:0,12366.142:0:0,12401.575:0:0,12437.008:0:0,12472.441:0:0,12507.874:0:0,12543.308:0:0,12578.74:0:0,12614.173:0:0,12649.606:0:0,12685.039:0:0,12720.473:0:0,12755.905:0:0,12791.339:0:0,12826.771:0:0,12862.205:0:0,12897.638:0:0,12933.071:0:0,12968.504:0:0,13003.9375:0:0,13039.37:0:0,13074.804:0:0,13110.236:0:0,13145.669:0:0,13181.103:0:0,13216.535:0:0,13251.969:0:0,13287.401:0:0,13322.835:0:0,13358.268:0:0,13393.701:0:0,13429.134:0:0,13464.567:0:0,13500.0:0:0,13535.434:0:0,13570.866:0:0,13606.299:0:0,13641.732:0:0,13677.165:0:0,13712.599:0:0,13748.031:0:0,13783.465:0:0,13818.897:0:0,13854.331:0:0,13889.764:0:0,13925.197:0:0,13960.63:0:0,13996.063:0:0,14031.496:0:0,14066.93:0:0,14102.362:0:0,14137.795:0:0,14173.229:0:0,14208.661:0:0,14244.095:0:0,14279.527:0:0,14314.961:0:0,14350.394:0:0,14385.827:0:0,14421.26:0:0,14456.693:0:0,14492.126:0:0,14527.56:0:0,14562.992:0:0,14598.426:0:0,14633.858:0:0,14669.291:0:0,14704.725:0:0,14740.157:0:0,14775.591:0:0,14811.023:0:0,14846.457:0:0,14881.89:0:0,14917.323:0:0,14952.756:0:0,14988.189:0:0,15023.622:0:0,15059.056:0:0,15094.488:0:0,15129.921:0:0,15165.3545:0:0,15200.787:0:0,15236.221:0:0,15271.653:0:0,15307.087:0:0,15342.52:0:0,15377.953:0:0,15413.386:0:0,15448.819:0:0,15484.252:0:0,15519.686:0:0,15555.118:0:0,15590.552:0:0,15625.984:0:0,15661.417:0:0,15696.851:0:0,15732.283:0:0,15767.717:0:0,15803.149:0:0,15838.583:0:0,15874.016:0:0,15909.449:0:0,15944.882:0:0,15980.315:0:0,16015.748:0:0,16051.182:0:0,16086.614:0:0,16122.048:0:0,16157.48:0:0,16192.913:0:0,16228.347:0:0,16263.779:0:0,16299.213:0:0,16334.6455:0:0,16370.079:0:0,16405.512:0:0,16440.945:0:0,16476.379:0:0,16511.81:0:0,16547.244:0:0,16582.678:0:0,16618.111:0:0,16653.543:0:0,16688.977:0:0,16724.41:0:0,16759.842:0:0,16795.275:0:0,16830.709:0:0,16866.143:0:0,16901.574:0:0,16937.008:0:0,16972.441:0:0,17007.875:0:0,17043.307:0:0,17078.74:0:0,17114.174:0:0,17149.605:0:0,17185.04:0:0,17220.473:0:0,17255.906:0:0,17291.338:0:0,17326.771:0:0,17362.205:0:0,17397.639:0:0,17433.07:0:0,17468.504:0:0,17503.938:0:0,17539.371:0:0,17574.803:0:0,17610.236:0:0,17645.67:0:0,17681.102:0:0,17716.535:0:0,17751.969:0:0,17787.402:0:0,17822.834:0:0,17858.268:0:0,17893.701:0:0,17929.135:0:0,17964.566:0:0,18000.0:0:0,18035.434:0:0,18070.867:0:0,18106.299:0:0"
)
# Her govde paragrafinin acilis etiketine eklenecek hazir attribute parcasi.
TABSET_ATTR = 'TabSet="' + TABSET_1_25CM + '" '
# Belge sonuna (</styles> ile </template> arasina) eklenecek eleman.
TAB_LENGTH_XML = (
    '<tabLength length="' + ("%s" % TAB_LENGTH_CM) + '" resolver="hvl-default" >\n\n</tabLength>\n'
)


def _page_format_xml():
    # KRITIK DUZELTME (kullanici geri bildirimi, 3 asama):
    # 1) topMargin/bottomMargin eskiden header/footer paragraflarimizin
    #    SpaceAbove/SpaceBelow ile CAKISIYORDU - 0 yapilinca duzeldi.
    # 2) headerFOffset/footerFOffset ("Kenardan: Ust Yazi/Alt Yazi") de
    #    ayni sekilde 0 yapildi ve dogru oldugu onaylandi.
    # 3) topMargin/bottomMargin ("Kenarlar: Ust/Alt") = Ust=3cm, Alt=2.1cm.
    #
    # v34 DEGISIKLIGI:
    #    headerFOffset/footerFOffset ARTIK 0 DEGIL. Ust/alt bosluklar
    #    (eskiden SpaceAbove/SpaceBelow ile sahte veriliyordu) buraya,
    #    UYAP'in dogru kabul ettigi "Kenardan > Ust Yazi / Alt Yazi"
    #    alanlarina tasindi. build_header_xml / build_footer_xml icinde
    #    SpaceAbove/SpaceBelow SIFIRLANDI (cift sayimi/cakismayi onlemek icin).
    #    topMargin/bottomMargin DEGISMEDI -> govde ayni yerde kalir.
    return (
        f'<pageFormat mediaSizeName="1" leftMargin="{LEFT_MARGIN_PT:.4f}" '
        f'rightMargin="{RIGHT_MARGIN_PT:.4f}" topMargin="{TOP_MARGIN_PT:.4f}" '
        f'bottomMargin="{BOTTOM_MARGIN_PT:.4f}" paperOrientation="1" '
        f'headerFOffset="{HEADER_FOFFSET_PT:.4f}" footerFOffset="{FOOTER_FOFFSET_PT:.4f}" />'
    )


PAGE_FORMAT = _page_format_xml()

STYLES_XML = (
    '<styles><style name="default" description="Ge\u00e7erli" family="Dialog" size="12" '
    'bold="false" italic="false" foreground="-13421773" '
    'FONT_ATTRIBUTE_KEY="javax.swing.plaf.FontUIResource[family=Dialog,name=Dialog,style=plain,size=12]" />'
    '<style name="hvl-default" family="Tahoma" size="12" description="G\u00f6vde" /></styles>'
)

FONT_FAMILY = "Arial"
FONT_SIZE = "10"

# ----
# BOS SATIR SATIR ARALIGI (kullanici testiyle dogrulandi - BOS-1 dosyasi)
# ----
# UYAP "Paragraf Ozellikleri > Aralik > Satir araligi (satir)" degeri
# content.xml'de LineSpacing attribute'u ile tutulur ve saklanan deger
# (carpan - 1)'dir:  1.25 satir  ->  LineSpacing="0.25"
#                    1.00 satir  ->  LineSpacing attribute'u HIC YAZILMAZ
#                                    (UYAP dialogda 1 secilince niteligi siler)
#
# Kullanici, SADECE BOS SATIRLARDA (icinde gercek metin olmayan, yalnizca
# paragraf sonu "\n" tasiyan paragraflar) bu degeri 1.25'ten 1'e indirince
# sayfa yerlesimi DOCX ile birebir ayni hale geldi. Metin iceren paragraflar
# ise 1.25 (LineSpacing="0.25") olarak KALIR.
#
# BODY_LINESPACING  : gercek metin tasiyan paragraflar (= 1.25 satir)
# EMPTY_LINESPACING : bos paragraflar (= 1.00 satir; nitelik yazilmaz)
# Bu iki sabiti degistirerek davranisi kolayca ayarlayabilirsiniz. Ornegin
# bos satirlari da tekrar 1.25 yapmak isterseniz EMPTY_LINESPACING = "0.25".
BODY_LINESPACING = "0.25"   # 1.25 satir araligi (metin paragraflari)
EMPTY_LINESPACING = None    # None => nitelik hic yazilmaz => 1.00 satir araligi


def _linespacing_attr(is_empty_paragraph: bool) -> str:
    """Paragraf acilis etiketine eklenecek LineSpacing nitelik parcasini
    dondurur. Bos paragraflarda EMPTY_LINESPACING, dolu paragraflarda
    BODY_LINESPACING kullanilir. Deger None ise nitelik hic yazilmaz
    (UYAP'in 1.0 satir araligi icin yaptigi gibi)."""
    val = EMPTY_LINESPACING if is_empty_paragraph else BODY_LINESPACING
    if val is None:
        return ""
    return f'LineSpacing="{val}" '
# Ayirici cizgi (header alt / footer ust) sadece 2px yukseklikte bir gorsel
# tasiyor, ama bu gorseli barindiran <paragraph>'in kendi satir yuksekligi
# paragrafin "size" degerine gore hesaplaniyor - gorselin gercek boyutuna
# gore DEGIL. size="10" (normal metin boyutu) kullanmak, gorunmez sekilde
# neredeyse tam bir metin satiri kadar fazladan yer kaplatiyordu (kullanici
# bunu "cizginin uzerinde/altinda gizli bir bosluk" olarak tarif etti).
# DOCX tarafinda ayni cizgi bir paragraf KENARLIGI (w:pBdr) olarak, bos
# (w:before=0 w:after=0) bir paragrafin uzerine ciziliyor - o yuzden DOCX'te
# bu sorun yok. UDF'de gercek bir "kenarlik" ozelligi yok (resim olarak
# cizmek zorundayiz), ama paragrafin "size"ini kucultup gereksiz rezerve
# edilen satir yuksekligini asgariye indirebiliyoruz.
SEP_LINE_FONT_SIZE = "4"

# ----
# v34.1 - FOOTER AYIRICI CIZGISININ "1 SATIR FAZLA BOSLUK" SORUNU
# ----
# BELIRTI: Footer'in en ustundeki ayirici cizgi, 2px'lik bir gorsel olmasina
#   ragmen TAM BIR METIN SATIRI kadar dikey yer kaplar; cizgi ile altindaki
#   footer yazisi arasinda ~1 satirlik istenmeyen bosluk olusur.
#
# KOK NEDEN: Footer'in YAZI paragraflarinda LineSpacing="0.200005" (sik
#   satir araligi) var; ama AYIRICI CIZGI paragrafinda LineSpacing YOK, o
#   yuzden UYAP'in varsayilan (daha genis) satir kutusunu kullaniyor. Cizgi
#   paragrafinin punto/font boyutunu degistirmek ISE YARAMADI (kullanici
#   denedi: cursor 4pt gosteriyordu ama yukseklik degismedi) - cunku fazla
#   yukseklik FONT'tan degil, EKSIK LineSpacing'ten geliyordu.
#
# COZUM: Footer ayirici cizgi paragrafina da (yazi paragraflari gibi)
#   LineSpacing ver VE placeholder content'in puntosunu kucult. Boylece
#   satir kutusu neredeyse 2px'lik gorsele kadar daralir, yazi cizgiye
#   yapisir. (HEADER ayirici cizgisine DOKUNULMAZ - orada bu bosluk zaten
#   "logo ile cizgi arasi bosluk" olarak isteniyor.)
FOOTER_SEP_LINESPACING = "0.0"   # 0.0 = mumkun oldugunca dar. Ayarlanabilir.
FOOTER_SEP_CONTENT_SIZE = "1"    # placeholder metnin puntosu (satir kutusunu belirler)

# Ana tablo kolon genislikleri (yuzde, toplam 100) - HTM tarafindaki
# colW1=2654, colW2=204, colW3=7348 (toplam 10206 dxa) ile TAM oranli:
# 2654/10206=26.00%, 204/10206=2.00%, 7348/10206=71.997% (yuvarlaninca 72).
# ONCEKI SURUMDE yanlislikla "27,1,72" kullanilmisti (1. sutun fazla,
# 2. sutun eksikti) - duzeltildi.
MAIN_COL_SPANS = "26,2,72"

# ====
# TABLO GENISLIGI HIPOTEZI (test edilecek): UYAP tablo genisligini
# content.xml'de saklamaz; ama columnSpans degerleri "pt" cinsinden
# sutun genislikleri olabilir (format dokumantasyonu). Bizim TUM
# tablolarimizin columnSpans'i 100'e toplaniyordu (26+2+72, 34+32+34,
# 50+50, 100) -> 100pt ~ 3.5cm, muhtemelen bir MINIMUM'a (~16cm)
# kirpilyor, bu yuzden HEPSI 16cm cikiyor. Cozum denemesi: oranlari
# koruyarak columnSpans'i GERCEK genislige (18cm = ~510pt) olceklemek.
TABLE_WIDTH_PT = 510  # 18cm = 18*72/2.54 = 510.24 pt (gerekirse kalibre edilir)

def scale_spans(spans_csv: str, total_pt: int = TABLE_WIDTH_PT) -> str:
    """'26,2,72' gibi (toplami ~100) oranlari, toplami total_pt olacak
    sekilde olcekler; yuvarlama artigini son sutuna verir."""
    vals = [float(x) for x in str(spans_csv).split(",") if x.strip() != ""]
    ssum = sum(vals) or 1.0
    scaled = [int(round(v * total_pt / ssum)) for v in vals]
    diff = total_pt - sum(scaled)
    if scaled:
        scaled[-1] += diff  # toplam tam total_pt olsun
    return ",".join(str(x) for x in scaled)


# Sabit satir yuksekligi (UDF biriminde, ornek belgeden gozlemlenen tipik deger)
# DEFAULT_ROW_HEIGHT: kullanici tarafindan kademeli test edildi.
# 510 (orijinal) -> 500 -> 490 -> 485 (bu surumde). Font boyutunu (FONT_SIZE)
# kucultmek denendi ama UYAP ondalikli punto degerini (9.8/9.6) TANIMADI,
# hepsini varsayilan 12 puntoya buyuttu - o yuzden FONT_SIZE'a DOKUNULMUYOR,
# sadece satir yuksekligi kucultuluyor. 485, su ana kadar en iyi sonucu
# veren deger.
DEFAULT_ROW_HEIGHT = "485"
# ONEMLI: EMPTY_ROW_HEIGHT, DEFAULT_ROW_HEIGHT ile HER ZAMAN AYNI (510)
# KALMALI. Kullanici bunu farkli bir deger yaptiginda tablo genislikleri
# bozuluyor (kanitlanmis, tekrar denenmemeli). Bos satirlarin kompaktlik
# sorunu bu degeri degistirerek DEGIL, bos satirlari tablo satiri olmaktan
# tamamen cikarip (bkz. build_spacer_paragraph / body assembly) kucuk bir
# paragraf araligiyla temsil ederek cozuluyor.
EMPTY_ROW_HEIGHT = "485"

# ----
# v34.2 - IMZA BLOGUNUN SAYFA ARASINDA BOLUNMEMESI ("keep together")
# ----
# SORUN: Imza alani (3'lu/2'li/tekli) simdiye kadar HER SATIRI ayri bir
#   <row> olan cok-satirli bir tablo olarak uretiliyordu. UYAP, bir tablonun
#   satirlarini sayfa sonunda BIRBIRINDEN AYIRIP bir kismini sonraki sayfaya
#   tasiyabildigi icin, imza blogu ikiye bolunuyordu. PDF/DOCX'te bu,
#   "page-break-inside: avoid" / <w:cantSplit/> ile cozuluyor; UDF'te bizim
#   denedigimiz keepTogether="true" niteligini UYAP TANIMIYOR (sessizce yok
#   sayiyor) - bu yuzden ise yaramiyordu.
#
# COZUM: Imza blogunu TEK BIR <row> yap. Her imzalayan = o satirin TEK bir
#   <cell>'i; o imzalayanin tum paragraflari (baslik, isim, unvan, bosluklar)
#   hucrenin ICINDE dikey yigin olarak durur. UYAP tek bir tablo SATIRINI
#   sayfa arasinda BOLMEZ - satir sigmazsa butun halinde sonraki sayfaya
#   gecer. Boylece imza blogu her zaman butun kalir.
#
#   Dikey hizalama: kisa hucreler, en uzun hucre (max_lines) kadar bos
#   paragrafla doldurulur -> tum sutunlar ayni satir sayisinda, ust hizalari
#   ayni. Gorsel sonuc cok-satirli surumle AYNI; sadece 10 <row> yerine 10
#   paragraf tasiyan 1 <row> var. (Satir yuksekligi zaten XML'e yazilmiyordu,
#   UYAP icerige gore otomatik buyutuyor - bkz. flush_main_table'da row_spans
#   uretilip KULLANILMAMASI.)
#
# Sorun cikarsa False yapip eski cok-satirli davranisa donebilirsin.
SIGGRID_SINGLE_ROW = True


def esc_xml(s: str) -> str:
    """XML attribute/metin icin kacis (escape)."""
    if s is None:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class ContentBuilder:
    """
    Duz metin akisini (CDATA icin) biriktirir ve her eklenen parca icin
    offset/length dondurur.

    NOT: add() hala bir 'is_space' degeri donduruyor (nbsp-only parca
    tespiti) ama bu deger artik run_tag() tarafindan KULLANILMIYOR - UYAP'ta
    <space> etiketinin justify paragraflarda tablo genisligini bozdugu
    kanitlandigi icin <space> etiketi tamamen kaldirildi, her metin
    <content> olarak yaziliyor (bkz. run_tag() aciklamasi). is_space,
    ileride tekrar ihtiyac duyulursa diye (veya baska bir amacla) burada
    zararsizca duruyor.
    """

    def __init__(self):
        self.buffer = []
        self.offset = 0
        # DENEME (kullanici gozlemi): Art arda gelen farkli genislikte
        # tablolarin (3'lu ana -> 2'li imza -> 3'lu imza gibi) UYAP'ta
        # genislik hesaplarini birbirine "sizdirdigi" gozlemlendi. Butun
        # tablolar ayni tableName="Sabit" kullaniyordu - bunun UYAP'in
        # tablolari ayni grup sanip cache/layout karistirmasina sebep
        # olma ihtimaline karsi, her tabloya BENZERSIZ bir isim vermek
        # icin bir sayac ekleniyor.
        self.table_counter = 0

    def next_table_name(self) -> str:
        self.table_counter += 1
        return f"Sabit{self.table_counter}"

    def add(self, text: str):
        """Metni akisa ekler, (start_offset, length, is_space) dondurur."""
        if text == "":
            return None
        start = self.offset
        length = len(text)
        self.buffer.append(text)
        self.offset += length
        # nbsp iceren parcalar UDF'de <space> olarak temsil ediliyor.
        # Basitlik icin: parca TAMAMEN nbsp ise space, degilse content.
        is_space = all(ch == "\xa0" for ch in text)
        return (start, length, is_space)

    def get_full_text(self) -> str:
        return "".join(self.buffer)


def run_tag(cb: ContentBuilder, text: str, bold=False, italic=False,
            underline=False, extra_attrs="", family=None, size=None,
            force_content=False):
    """
    Bir metin parcasini content akisina ekler ve buna karsilik gelen
    <content> XML etiketini uretir. Bos string icin None doner.

    force_content: artik HER ZAMAN True gibi davranilir - bkz. asagidaki
    "KESIN COZUM" notu. Parametre geriye-donuk uyumluluk icin (diger
    fonksiyonlarin cagri imzasini degistirmemek adina) tutuluyor ama
    hicbir kod yolu artik <space> uretmiyor.

    ONEMLI KOK NEDEN (kullanicinin iki ayri kaniti ile netlesti): UYAP'in
    <space> etiketi, "esnek/gerilebilir bir justify boslugu" gibi
    yorumlaniyor olmali - iki yana yaslanmis (justify) bir paragrafta
    <space> etiketi bulunmasi, UYAP'in o satirin "dogal genisligini"
    yanlis hesaplayip TUM TABLOYU sayfa disina tasirmasina (35cm+) sebep
    oluyor. Bu, "Satir Basi" ile eklenen nbsp karakterlerinin bazen
    (DOM'un olusum sekline bagli olarak) TAMAMEN-nbsp, kendi basina bir
    run olarak kalip <space> etiketini almasi yuzunden ortaya cikiyordu.

    Once "run'i bol, nbsp kismini <space> yap" yaklasimi denendi -
    calismadi. Sonra "hicbir zaman bolme, tek parca <content> yap"
    yaklasimi denendi - ama tarayici DOM'u zaten kendiliginden bazen ayri,
    TAMAMEN-nbsp bir run OLUSTURUYORDU (bizim kontrolumuz disinda), o da
    yetersiz kaldi.

    KESIN COZUM: <space> etiketi TAMAMEN KALDIRILDI. Nbsp (\xa0) icersin
    icermesin HER metin parcasi <content> olarak yaziliyor. UDF format
    acisindan bunun bir sakincasi yok - <content> zaten herhangi bir
    metni (nbsp dahil) tasiyabiliyor, sadece orijinal referans belgede
    UYAP'in KENDISI ayrim yapmis olmasi bizim de ayni ayrimi yapmamizi
    ZORUNLU kilmiyor. Bu, hem "Satir Basi" hem "Madde Ekle" hem de
    ileride ortaya cikabilecek benzer nbsp-agirlikli senaryolar icin
    KOKTEN VE KALICI bir cozum.
    """
    res = cb.add(text)
    if res is None:
        return ""
    start, length, is_space = res
    fam = family or FONT_FAMILY
    sz = size or FONT_SIZE
    attrs = f'family="{fam}" size="{sz}"'
    if bold:
        attrs += ' bold="true"'
    if italic:
        attrs += ' italic="true"'
    if underline:
        attrs += ' underline="true"'
    if extra_attrs:
        attrs += " " + extra_attrs
    tag = "content"
    return f'<{tag} {attrs} startOffset="{start}" length="{length}" />'


def paragraph_xml(cb: ContentBuilder, para, align_map=None, extra_para_attrs="", size=None, force_content=False):
    """
    JSON'daki bir paragraf objesini ({align, runs:[...]}) UDF <paragraph>
    XML'ine cevirir.

    size: verilirse paragrafin punto degerini (dolayisiyla satirin rezerve
    ettigi yuksekligi) FONT_SIZE yerine bu deger ile ayarlar. Ozellikle
    "gercek metin tasimayan, sadece bosluk amacli" paragraflarda (orn.
    baslik oncesi bosluk) satir yuksekligini kucultmek icin kullanilir.

    force_content: True verilirse, bu paragraf icindeki HICBIR run <space>
    etiketi ALMAZ (nbsp icerse bile) - hepsi <content> olarak yazilir.
    Bu, justify (iki yana yasla) hizalanmis serbest metin bloklarinda
    (full-row / "Tam Metin", "Madde Ekle") <space> etiketinin UYAP'ta
    tablo genisligini bozdugu kanitlandigi icin KULLANILMASI GEREKEN bir
    guvenlik onlemi (bkz. run_tag() aciklamasi).

    KOK NEDEN BULUNDU (kullanicinin once/sonra content.xml kanitiyla,
    lorem ipsum testi): Her paragrafin sonuna, paragrafin GERCEK metin
    run'larindan AYRI, kendi basina bir "\n" run_tag() cagrisi ekliyorduk.
    Bu, her paragrafta İKİ ayri <content> etiketi olusturuyordu (biri
    gercek metin icin, biri sadece "\n" icin, uzunlugu 1). UYAP'in kendi
    ac/kapa-diyalog duzeltmesi bu ikisini HER ZAMAN TEK bir <content>
    etiketine birlestiriyordu (uzunluk toplami +1 farkla ayni kaliyordu).
    Yani UYAP, bir paragrafta BIRDEN FAZLA <content> parcasi oldugunda
    (herhangi bir sebeple, formatlama degil de sadece "\n" eklemek icin
    bile olsa) BIR SEKILDE genislik hesabini SASIRIYOR OLMALI - tipki
    <space> etiketinin veya karisik row-height'in yaptigi gibi, "paragraf
    icinde beklenenden fazla content-tag parcasi" UYAP'in ilk render'da
    yanlis genislik hesaplamasina yol acan GENEL bir kalip gibi duruyor.

    COZUM: "\n" artik AYRI bir run_tag() cagrisi DEGIL - PARAGRAFIN SON
    GERCEK RUN'ININ METNININ SONUNA EKLENIYOR, boylece TEK bir run_tag()
    cagrisiyla TEK bir <content> etiketi uretiliyor (UYAP'in kendi
    urettigi yapiyla BIREBIR ayni). Eger paragrafta hic run yoksa (bos
    paragraf), o zaman "\n" tek basina tek bir <content> olarak kalir -
    bu zaten tek parca oldugu icin sorun degil.
    """
    align_map = align_map or {"left": "0", "center": "1", "right": "2", "justify": "3"}
    align_val = align_map.get(para.get("align", "left"), "0")
    para_size = size or FONT_SIZE

    inner = ""
    raw_runs = list(para.get("runs", []))

    # KOK NEDEN (lorem ipsum + satir-basi testleriyle DOGRULANDI): UYAP,
    # bir paragrafta BIRDEN FAZLA <content>/<space> XML parcasi oldugunda
    # (formatlama farki OLMASA BILE - orn. sadece DOM'un ayri text node'lara
    # bolmus olmasi yuzunden) tablo genislik hesabini SASIRIYOR. Bunun en
    # net kaniti: bizim paragraf sonuna eklediğimiz ayri "\n" tag'i (biri
    # yukarida duzeltildi) VE JSON'dan gelen, AYNI bicimlendirmeye (bold/
    # italic/underline) sahip ama DOM'un rastgele ayirdigi ardisik metin
    # run'lari (orn. "Satir Basi" ile eklenen 6 nbsp + hemen ardindan gelen
    # metin - tarayici bunlari bazen ayri text node olarak birakiyor).
    #
    # COZUM: Runs listesini islemeye baslamadan once, ARDISIK ve AYNI
    # bicimlendirmeye (bold/italic/underline) sahip, HER IKISI DE duz metin
    # olan (isTab/isLineBreak OLMAYAN) run'lari TEK bir run'da birlestiriyoruz.
    # Bu, UYAP'in kendi urettigi "tek content parcasi" yapisiyla birebir
    # ayni sonucu verir - gorsel/bicimsel hicbir kayip olmadan.
    runs = []
    for r in raw_runs:
        if (
            runs
            and not r.get("isTab") and not r.get("isLineBreak")
            and not runs[-1].get("isTab") and not runs[-1].get("isLineBreak")
            and bool(r.get("bold")) == bool(runs[-1].get("bold"))
            and bool(r.get("italic")) == bool(runs[-1].get("italic"))
            and bool(r.get("underline")) == bool(runs[-1].get("underline"))
        ):
            # ayni bicimlendirmeye sahip, ardisik duz metin run'i - birlestir
            merged = dict(runs[-1])
            merged["text"] = (runs[-1].get("text", "") or "") + (r.get("text", "") or "")
            runs[-1] = merged
        else:
            runs.append(dict(r))

    # "\n"i AYRI bir run olarak DEGIL, SON GERCEK metin run'una
    # (isTab/isLineBreak olmayan, gercek text tasiyan son run'a) EKLEMEK
    # icin, runs listesini gezip son uygun run'i buluyoruz.
    last_text_run_idx = None
    for i in range(len(runs) - 1, -1, -1):
        if not runs[i].get("isTab") and not runs[i].get("isLineBreak"):
            last_text_run_idx = i
            break

    for idx, run in enumerate(runs):
        text = run.get("text", "")
        if run.get("isLineBreak"):
            # HTM tarafinda mergeSigTitleParagraphs() tarafindan eklenen
            # "satir ici satir sonu" isareti: YENI BIR <paragraph> ACMADAN,
            # ayni paragraf icinde bir \n karakteri olarak render edilir.
            inner += run_tag(cb, "\n", size=para_size, force_content=force_content)
            continue
        if run.get("isTab"):
            # Word'deki tab UYAP editorunde de bosluk/tab karakteri olarak
            # temsil edilebilir; burada dogrudan tab karakteri ekliyoruz.
            inner += run_tag(cb, "\t", run.get("bold"), run.get("italic"), run.get("underline"), size=para_size, force_content=force_content)
            continue
        # Paragrafin SON gercek metin run'i isek, sonuna "\n" ekle (ayri
        # bir content parcasi acmadan, ayni run_tag() cagrisinin icinde).
        if idx == last_text_run_idx:
            text = text + "\n"
        inner += run_tag(cb, text, run.get("bold"), run.get("italic"), run.get("underline"), size=para_size, force_content=force_content)

    if last_text_run_idx is None:
        # Paragrafta hic gercek metin run'i yoktu (tamamen bos paragraf,
        # veya sadece tab/lineBreak run'lari vardi) - "\n" tek basina,
        # kendi content parcasi olarak kalir (zaten TEK parca, sorun yok).
        inner += run_tag(cb, "\n", size=para_size, force_content=force_content)

    # BOS SATIR AYARI: paragrafta hic gercek metin run'i yoksa (last_text_run_idx
    # is None) bu bir "bos satir"dir -> satir araligi 1.0 (EMPTY_LINESPACING).
    # Aksi halde metin paragrafidir -> 1.25 (BODY_LINESPACING). Kullanicinin
    # BOS-1 testiyle dogrulanan davranis (bkz. _linespacing_attr / sabitler).
    ls_attr = _linespacing_attr(last_text_run_idx is None)

    return (
        f'<paragraph {TABSET_ATTR}Alignment="{align_val}" {ls_attr}'
        f'family="{FONT_FAMILY}" size="{para_size}"{extra_para_attrs}>'
        f"{inner}</paragraph>"
    )


def build_labeled_row(cb: ContentBuilder, label: str, colon: str, content_paragraphs):
    """label : content seklindeki 3 kolonlu satiri uretir."""
    label_tag = run_tag(cb, label, bold=True) if label else ""
    colon_tag = run_tag(cb, colon or ":", bold=True) if colon else ""

    label_para = (
        f'<paragraph {TABSET_ATTR}Alignment="0" LineSpacing="0.25" family="{FONT_FAMILY}" size="{FONT_SIZE}">'
        f"{label_tag}</paragraph>"
    )
    colon_para = (
        f'<paragraph {TABSET_ATTR}Alignment="0" LineSpacing="0.25" family="{FONT_FAMILY}" size="{FONT_SIZE}">'
        f"{colon_tag}</paragraph>"
    )

    content_inner = ""
    # force_content=True: labeled-row content hucresi de justify hizalanmis
    # olabiliyor (varsayilan hizalama 'justify') ve kullanici buraya da
    # "Satir Basi" ile nbsp ekleyebilir - ayni <space>-tablo-genisligi
    # sorununa karsi ayni onlem burada da uygulanir (bkz. build_full_row).
    for para in content_paragraphs:
        content_inner += paragraph_xml(cb, para, force_content=True)
    if not content_paragraphs:
        content_inner = paragraph_xml(cb, {"align": "left", "runs": []}, force_content=True)

    row = (
        '<row rowName="rowX" rowType="dataRow" border="borderNone" borderWidth="0.5">'
        f'<cell border="borderNone" borderWidth="0.5">{label_para}</cell>'
        f'<cell border="borderNone" borderWidth="0.5">{colon_para}</cell>'
        f'<cell border="borderNone" borderWidth="0.5">{content_inner}</cell>'
        "</row>"
    )
    return row, DEFAULT_ROW_HEIGHT


# NOT: Eskiden burada build_empty_row() adinda, "empty" tipi satirlari ana
# tablonun icinde 3 sutunlu bir <row> olarak ureten bir fonksiyon vardi.
# Artik kullanilmiyor - "empty" satirlar artik build_udf_content_xml
# icindeki build_spacer_paragraph() ile, tablonun DISINDA kucuk bir
# paragraf olarak temsil ediliyor (bkz. o fonksiyonun yanindaki not).


def build_full_row(cb: ContentBuilder, paragraphs):
    """3 kolonu birlestiren (gridSpan benzeri) tek hucreli satir - madde metni vb.

    force_content=True KULLANILIYOR: bu satirlar HER ZAMAN justify (iki yana
    yasla) hizalanmis oluyor.

    KOK NEDEN #1 (rowSpans, bir onceki turda cozuldu): "1020" sabit
    yukseklik degeri yanlisti, artik DEFAULT_ROW_HEIGHT kullaniliyor
    (asagida degismedi).

    KOK NEDEN #2 (bu turda bulundu): Bu fonksiyonun urettigi satir, TEK
    bir <cell> iceriyor (colSpan=3 ile 3 kolonu gorsel olarak birlestiren).
    AMA bu satirin sarildigi <table>, hala 3-KOLONLU bir tanim
    (columnSpans="26,2,72", labeled-row'lar icin tasarlanmis 26%/2%/72%
    oranlari) kullaniyordu. Yani gercekte TEK hücreli bir satir, "3 kolonlu
    ama ortasi birlesik" gibi YANLIS bir sekilde tanimlaniyordu. Kullanicinin
    kanitladigi "Tablo Ozellikleri'nde genislik 16cm gorunuyor (18 yerine)"
    sorunu, UYAP'in colSpan'li tek hucreyi 3-kolonlu tanimla eslestirmeye
    calisirken YANLIS bir alt-kumeyi (orn. sadece "72" veya "26+72" gibi bir
    kombinasyonu) esas alip genisligi yanlis hesaplamasindan kaynaklaniyor
    olmali.

    COZUM: "full" satirlar artik KENDI TABLOSUNDA GERCEKTEN TEK KOLONLU
    (columnCount=1, columnSpans="100") taniminiyor - colSpan da gereksiz
    hale geldigi icin kaldirildi (tek kolonlu bir tabloda tek hucreyi
    "birlestirecek" baska kolon zaten yok). Bu, hucre yapisi ile tablo
    tanimi arasindaki UYUMSUZLUGU tamamen ortadan kaldiriyor.
    """
    inner = ""
    for para in paragraphs:
        inner += paragraph_xml(cb, para, align_map={"left": "0", "center": "1", "right": "2", "justify": "3"}, force_content=True)
    if not paragraphs:
        inner = paragraph_xml(cb, {"align": "justify", "runs": []}, force_content=True)

    row = (
        '<row rowName="rowX" rowType="dataRow" border="borderNone" borderWidth="0.5">'
        f'<cell border="borderNone" borderWidth="0.5">{inner}</cell>'
        "</row>"
    )
    return row, DEFAULT_ROW_HEIGHT



def build_siggrid_row(cb: ContentBuilder, boxes):
    """
    Imza tablosu.

    DUZELTME (orijinal ornek belge yeniden incelendikten sonra):
    Orijinal UDF'de imza alani, kutular halinde DIKEY paragraf yigini
    olarak DEGIL, SATIR BAZLI bir tablo olarak kurulmus: her <row> tum
    kutularin AYNI SATIRDAKI metnini icerir (orn. row1 = ["TARAF",
    "ARABULUCU", "TARAF"], row2 = isimler, row3 = unvanlar, ...). Boylece
    kutular arasi dikey hizalanma tablo satirlariyla otomatik saglanir ve
    tasma riski ortadan kalkar.

    Bu fonksiyon, JSON'daki her "box"un paragraf listesini en uzun box'a
    gore hizalayip (kisa olanlara bos satir ekleyerek) satir bazli bir
    tabloya donusturur.
    """
    n = len(boxes) if boxes else 1
    if n == 3:
        spans = [34, 32, 34]
    else:
        base_span = 100 // n
        spans = [base_span] * n
        spans[-1] += 100 - sum(spans)
    col_spans = scale_spans(",".join(str(s) for s in spans))  # 18cm=510pt olcekle

    max_lines = max((len(b) for b in boxes), default=1)
    max_lines = max(max_lines, 1)

    # === v34.2: TEK-SATIR modu (imza blogu sayfa arasinda bolunmesin) ===
    if SIGGRID_SINGLE_ROW:
        align_map = {"left": "0", "center": "1", "right": "2", "justify": "3"}
        cells_xml = ""
        for box_paragraphs in boxes:
            paras = list(box_paragraphs) if box_paragraphs else []
            # tum sutunlar ayni satir sayisinda olsun (ust hizalari otursun)
            while len(paras) < max_lines:
                paras.append({"align": "center", "runs": []})
            inner = "".join(paragraph_xml(cb, para, align_map=align_map) for para in paras)
            cells_xml += f'<cell border="borderNone" borderWidth="0.5">{inner}</cell>'
        # TUM imza blogu = TEK <row>. UYAP tek satiri sayfa arasinda bolmez.
        row_xml = (
            f'<row rowName="row1" rowType="dataRow" border="borderNone" borderWidth="0.5">'
            f"{cells_xml}</row>"
        )
        table_name = cb.next_table_name()
        return (
            f'<table tableName="{table_name}" columnCount="{n}" border="borderNone" borderSpec="31" '
            f'borderColor="-16777216" borderStyle="borderStyle-plain" borderWidth="1.0" '
            f'keepTogether="true" '
            f'columnSpans="{col_spans}">{row_xml}</table>'
        )
    # === /v34.2 ; asagisi eski cok-satirli davranis (SIGGRID_SINGLE_ROW=False) ===

    # DUZELTME (bu turda): Eskiden burada HER paragraf ciftinin arasina
    # OTOMATIK bos bir satir ekleniyordu ("kullanicinin enter ile
    # olusturdugu bosluklari korumak" amaciyla). Ama HTM tarafindaki
    # nodeToParagraphs() zaten KULLANICININ GERCEKTEN birakip birakmadigi
    # bos satirlari (orn. <div><br></div>) kendi bos-run'li bir paragraf
    # olarak JSON'a yaziyor - yani bu bilgi JSON'da ZATEN var. Otomatik
    # interleave, bu mevcut bilginin USTUNE bir kez daha bosluk ekleyip
    # CIFTE bosluk yaratiyordu - ozellikle "ARABULUCU"/"YETKILISI" gibi
    # kullanicinin ARASINA bosluk BIRAKMADIGI baslik->isim gecislerinde,
    # burada olmamasi gereken bir bosluk satiri ortaya cikiyordu (kullanici
    # geri bildirimi: "bu basliklardan hemen sonra bir bosluk oluyor").
    # Simdi JSON'daki paragraf listesi OLDUGU GIBI kullaniliyor - herhangi
    # bir bosluk sadece kullanicinin GERCEKTEN birakmis oldugu (bos run'li
    # bir paragraf olarak JSON'da yer alan) yerlerde olusuyor.

    rows_xml = ""
    row_heights = []
    for line_idx in range(max_lines):
        cells_xml = ""
        for box_paragraphs in boxes:
            if line_idx < len(box_paragraphs):
                para = box_paragraphs[line_idx]
            else:
                para = {"align": "center", "runs": []}
            inner = paragraph_xml(cb, para, align_map={"left": "0", "center": "1", "right": "2", "justify": "3"})
            cells_xml += f'<cell border="borderNone" borderWidth="0.5">{inner}</cell>'
        rows_xml += (
            f'<row rowName="row{line_idx + 1}" rowType="dataRow" border="borderNone" borderWidth="0.5">'
            f"{cells_xml}</row>"
        )
        # ONEMLI: Bu satirlarin hepsi (bos olsun olmasin) DEFAULT_ROW_HEIGHT
        # (510) ile AYNI kalmali - karisik yukseklik tablo genisligini
        # bozuyor (kanitlanmis). Kompaktlik sorunu satir yuksekligiyle degil,
        # bu satirlarin sayisini azaltarak / farkli bir yontemle cozulmeli.
        #
        # NOT (bu turda denendi, GERI ALINDI): "ARABULUCU"/"YETKILISI" gibi
        # baslik-tek-basina satirlarinin altinda kalan bosluk sorunu icin
        # once bu satirlari BASKA paragraflarla BIRLESTIRIP (embedded \n ile
        # tek paragraf yapip) satir sayisini azaltmayi denedik. Bu, HTM
        # tarafinda calisiyordu AMA satir-basina-hizalama modelini bozuyordu:
        # imza kutulari arasindaki gorsel hizalama (description.md madde 7)
        # HER kutunun HER satirinin ayni line_idx'te durmasina dayaniyor;
        # bir kutunun satirlarini birlestirip azaltmak, o kutuyu digerlerine
        # gore kaydiriyordu. Bu yuzden GERI ALINDI - satir sayisi/hizalamasi
        # DEGISTIRILMEDI. Eger baslik altindaki bosluk gorsel olarak hala
        # rahatsiz ediyorsa, sonraki adim: sadece o SATIRIN punto boyutunu
        # (rowSpans'i DEGIL, sadece paragraf/run "size" degerini) kucultmek
        # olabilir - bu, satir sayisini/hizalamasini bozmadan gorsel agirligi
        # azaltir. Simdilik DOKUNULMADI, cunku bunun da UYAP'ta test edilmesi
        # gerekiyor.
        row_heights.append(DEFAULT_ROW_HEIGHT)

    row_spans = ",".join(row_heights) + ","

    # DENEYSEL - TEST GEREKTIRIR: Imza tablosunun sayfa arasinda ortadan
    # bolunmemesi (madde 4, kullanici talebi) icin UDF/UYAP tarafinda
    # dogrulanmis bir "keepTogether" niteligi henuz bilinmiyor (format
    # kapali kaynak, reverse-engineering ile cozuluyor - description.md).
    # DOCX'te bunun karsiligi <w:cantSplit/>; asagida ayni isimlendirme
    # sezgisiyle "keepTogether" denemesi ekleniyor. UYAP bu niteligi
    # tanimiyorsa muhtemelen sessizce yok sayacaktir (zararsiz), ama
    # calisip calismadigi kesin degildir. Kullanicinin daha once yaptigi
    # "ac/kapa dialog + content.xml diff" yontemiyle dogrulanmasi lazim:
    # bu tabloyu sayfa sonuna yakin bir yere koyup PDF/UDF ciktisini
    # karsilastirin. Calismiyorsa bu satiri kaldirin, tek care satirlarin
    # toplam yuksekligini sayfa sinirini asmayacak sekilde kucultmek
    # (yukaridaki EMPTY_ROW_HEIGHT duzeltmesi) olabilir.
    table_name = cb.next_table_name()
    table = (
        f'<table tableName="{table_name}" columnCount="{n}" border="borderNone" borderSpec="31" '
        f'borderColor="-16777216" borderStyle="borderStyle-plain" borderWidth="1.0" '
        f'keepTogether="true" '
        f'columnSpans="{col_spans}">{rows_xml}</table>'
    )
    return table


def _png_size(raw: bytes):
    """
    PNG'nin genislik/yuksekligini saf Python ile okur (Pillow'a gerek yok).

    PNG yapisi sabittir:
      bayt  0-7   : imza  \x89PNG\r\n\x1a\n
      bayt  8-11  : IHDR chunk uzunlugu
      bayt 12-15  : "IHDR"
      bayt 16-19  : genislik  (big-endian uint32)
      bayt 20-23  : yukseklik (big-endian uint32)

    Editor logoyu her zaman canvas.toDataURL('image/png') ile urettigi icin
    (bkz. padLogoTo4x1) girdi DAIMA PNG'dir; JPEG destegi gerekmiyor.
    """
    if len(raw) < 24:
        raise ValueError("PNG icin cok kisa veri")
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG imzasi bulunamadi")
    if raw[12:16] != b"IHDR":
        raise ValueError("IHDR chunk bulunamadi")
    w = int.from_bytes(raw[16:20], "big")
    h = int.from_bytes(raw[20:24], "big")
    return w, h


def _logo_dimensions_preserving_aspect(logo_b64: str, max_width_pt: float, max_height_pt: float):
    """
    PNG base64 verisinden gercek piksel en/boy oranini okuyup, verilen
    max_width_pt x max_height_pt kutusuna sigacak (oranini bozmadan) en
    buyuk boyutu hesaplar.

    NOT: Eskiden Pillow kullaniyordu. Vercel'de kokteki requirements.txt
    Python framework algilamasini tetikleyip deploy'u bozdugu icin bagimlilik
    kaldirildi; davranis birebir ayni (bkz. _png_size).
    """
    try:
        raw = base64.b64decode(logo_b64)
        w_px, h_px = _png_size(raw)
        if w_px <= 0 or h_px <= 0:
            return max_width_pt, max_height_pt
        aspect = w_px / h_px
        # once genislige gore dene
        w = max_width_pt
        h = w / aspect
        if h > max_height_pt:
            h = max_height_pt
            w = h * aspect
        return w, h
    except Exception:
        # okunamazsa (bozuk veri vb.) kutu boyutunu oldugu gibi kullan
        return max_width_pt, max_height_pt


def build_header_xml(cb: ContentBuilder, header_data):
    """
    UDF <header> blogunu uretir.

    KRITIK DUZELTME (kullanicinin kanitlanmis calisan kodu udf_updater_v70.py
    incelenerek): Kirmizi blok / bozuk imaj sorununun KOK NEDENI, base64
    verisinin \\n ile satirlara bolunmesiydi (bkz. wrap_base64 fonksiyonundaki
    aciklama - XML attribute-value normalization \\n'i boslugaga cevirip
    base64'u bozuyor). Artik base64 TEK SATIRDA, kirilmadan yaziliyor.

    Ayrica kullanicinin kendi kodundaki ESPRESSIF pattern birebir taklit
    edildi:
      - paragraph: Alignment=1, family=Arial, size=10, foreground=-1
      - image: startOffset=N, length=1
      - hemen ardindan: content family=Arial size=9 foreground=-1
        startOffset=N+1 length=1  (bu, image'dan hemen sonraki "gorunmez"
        1 karakterlik yer tutucu - kullanicinin kodunda boyleydi)
    "foreground=-1" ozelligi GERI EKLENDI (onceki turda yanlislikla bunun
    sorun oldugunu dusunup kaldirmistik; kullanicinin calisan kodunda hala
    duruyor, demek ki asil sorun buymus).
    """
    enabled = header_data.get("enabled")
    logo_b64_raw = header_data.get("logoBase64") or ""

    if not enabled:
        nl_tag = run_tag(cb, "\n")
        return f'<header><paragraph name="hvl-default">{nl_tag}</paragraph></header>'

    parts = []

    if logo_b64_raw:
        if "," in logo_b64_raw:
            logo_b64 = logo_b64_raw.split(",", 1)[1]
        else:
            logo_b64 = logo_b64_raw
        # base64 kirilmadan (tek satir) kullanilir - bkz. wrap_base64 aciklamasi
        logo_b64_flat = wrap_base64(logo_b64)
        w_pt, h_pt = _logo_dimensions_preserving_aspect(logo_b64, LOGO_WIDTH_PT, LOGO_HEIGHT_PT)
        image_offset = cb.offset
        # image'in hemen ardina, kullanicinin kodundaki gibi 1 karakterlik
        # "yer tutucu" content ekleniyor (offset+1). Content akisina da
        # gercekten 1 karakter (bosluk/newline) ekliyoruz ki offset defteri
        # tutarli kalsin.
        placeholder_tag = run_tag(cb, "\n")
        # v34: SpaceAbove KALDIRILDI. Ust bosluk artik headerFOffset'tan
        # (sayfa yapisi) geliyor. Burada tekrar verirsek bosluk cift sayilir.
        parts.append(
            f'<paragraph name="hvl-default" Alignment="1" family="{FONT_FAMILY}" size="{FONT_SIZE}" foreground="-1" SpaceAbove="0.0" SpaceBelow="0.0">'
            f'<image imageData="{logo_b64_flat}" width="{w_pt:.2f}" height="{h_pt:.2f}" '
            f'startOffset="{image_offset}" length="1" />{placeholder_tag}</paragraph>'
        )
    else:
        # v34: SpaceAbove KALDIRILDI (bkz. yukaridaki not).
        nl_tag = run_tag(cb, "\n")
        parts.append(
            f'<paragraph name="hvl-default" Alignment="1" SpaceAbove="0.0">'
            f"{nl_tag}</paragraph>"
        )

    # header alaninin en altina, govde genisliginde ayirici cizgi
    # (SEP_LINE_FONT_SIZE kullaniliyor - bkz. tanimindaki not: bu paragrafin
    # gorsel icerigi 2px ama size=10 kullanirsak neredeyse tam bir metin
    # satiri kadar gizli bosluk rezerve edilir)
    sep_flat = wrap_base64(SEP_LINE_2PX_B64)
    sep_offset = cb.offset
    nl_tag2 = run_tag(cb, "\n")
    parts.append(
        f'<paragraph name="hvl-default" Alignment="1" family="{FONT_FAMILY}" size="{SEP_LINE_FONT_SIZE}" foreground="-1" SpaceAbove="0.0" SpaceBelow="0.0">'
        f'<image imageData="{sep_flat}" width="{CONTENT_WIDTH_PT:.2f}" height="2.0" '
        f'startOffset="{sep_offset}" length="1" />{nl_tag2}</paragraph>'
    )

    return f"<header>{''.join(parts)}</header>"


def build_footer_xml(cb: ContentBuilder, footer_data):
    """
    UDF <footer> blogunu uretir.

    KRITIK DUZELTME (referans belge header-footer-udf.udf incelenerek):
    UYAP'in "Ekle" menusundeki footer'i GERCEK/duzenlenebilir footer olarak
    tanimasi icin, footer paragraflarinin referans belgedeki gibi
    'name="hvl-default"' ozelligini tasimasi gerekiyor. Onceki surumumuzde
    bu ozellik yoktu VE footer bir <table> icine sarilmisti - referans
    belgede footer duz <paragraph> idi, <table> degildi. Bu yuzden UYAP
    footer'i "yapisina islenmis" bir footer olarak tanimiyor, "Footer Ekle"
    butonu hala aktif gorunuyordu.

    Simdi:
      - footer TAMAMEN duz <paragraph name="hvl-default"> elemanlarindan
        olusuyor (tablo YOK).
      - Sirasiyla: govde genisliginde ayirici cizgi paragrafi, sonra footer
        metin satir(lar)i, en sonda 0.6cm SpaceBelow'lu (bos) bir paragraf.
    """
    enabled = footer_data.get("enabled")
    text1 = (footer_data.get("text1") or "").strip()
    text2 = (footer_data.get("text2") or "").strip()

    if not enabled:
        nl_tag = run_tag(cb, "\n")
        return f'<footer><paragraph name="hvl-default">{nl_tag}</paragraph></footer>'

    parts = []

    # --- footer alaninin en ustune, govde genisliginde ayirici cizgi ---
    # v34.1: HEADER'dakinden FARKLI olarak, buraya LineSpacing ekleniyor VE
    # placeholder content puntosu kucultuluyor -> cizgi paragrafinin satir
    # kutusu daraliyor, cizgi ile yazi arasindaki "1 satir fazla bosluk"
    # kayboluyor (bkz. FOOTER_SEP_* sabitleri). Header ayirici cizgisi ise
    # DEGISMEDI (orada bu bosluk isteniyor).
    sep_flat = wrap_base64(SEP_LINE_2PX_B64)
    sep_offset = cb.offset
    nl_tag = run_tag(cb, "\n", size=FOOTER_SEP_CONTENT_SIZE)
    parts.append(
        f'<paragraph name="hvl-default" Alignment="1" LineSpacing="{FOOTER_SEP_LINESPACING}" family="{FONT_FAMILY}" size="{SEP_LINE_FONT_SIZE}" foreground="-1" SpaceAbove="0.0" SpaceBelow="0.0">'
        f'<image imageData="{sep_flat}" width="{CONTENT_WIDTH_PT:.2f}" height="2.0" '
        f'startOffset="{sep_offset}" length="1" />{nl_tag}</paragraph>'
    )

    lines = [t for t in (text1, text2) if t]

    if lines:
        for i, txt in enumerate(lines):
            is_last = (i == len(lines) - 1)
            t_tag = run_tag(cb, txt, family="Palatino Linotype", size="9")
            # v34: son satirdaki SpaceBelow KALDIRILDI. Alt bosluk artik
            # footerFOffset'tan (sayfa yapisi) geliyor. Burada tekrar
            # verirsek bosluk cift sayilir ve footer govdeye dogru buyur.
            extra_attr = ""
            parts.append(
                f'<paragraph name="hvl-default" Alignment="1" LineSpacing="0.200005"{extra_attr}>'
                f"{t_tag}</paragraph>"
            )
    else:
        # metin yoksa: cizgiden sonra bos paragraf (v34: SpaceBelow YOK;
        # alt bosluk footerFOffset'tan geliyor)
        nl_tag2 = run_tag(cb, "\n")
        parts.append(
            f'<paragraph name="hvl-default" Alignment="1">'
            f"{nl_tag2}</paragraph>"
        )

    return f"<footer>{''.join(parts)}</footer>"


def wrap_base64(b64: str, width: int = 76) -> str:
    """
    KRITIK DUZELTME: Bu fonksiyon ONCEDEN base64'u \\n ile 76 karakterde
    satirlara boluyordu (orijinal ornek dosyada boyle GORUNUYORDU). Ancak
    XML SPESIFIKASYONUNA GORE, bir ATTRIBUTE DEGERI icindeki \\n, \\t, \\r
    karakterleri parser tarafindan (attribute-value normalization) TEK
    BOSLUGA donusturulur. imageData bir ATTRIBUTE oldugu icin, icine
    koydugumuz \\n karakterleri boslugaga cevriliyor ve base64 verisi
    BOZULUYOR - bu da resmin "kirmizi blok / bozuk imaj" olarak render
    olmasinin kok nedeniydi.

    Kullanicinin kendi calisan referans kodunda (udf_updater_v70.py,
    ET.tostring ile serialize ediliyor) base64 HICBIR SATIR KIRILIMI
    OLMADAN, TEK SATIRDA yaziliyordu. Bu artik dogru davranis olarak
    kabul edilip, base64 OLDUGU GIBI (kirilmadan) donduruluyor.
    """
    return b64


def build_udf_content_xml(data: dict) -> str:
    cb = ContentBuilder()

    header_xml = build_header_xml(cb, data.get("header", {}))

    # baslik (title) paragraflari - ana tablodan ONCE, header'dan SONRA gelir
    #
    # DUZELTME (kullanici geri bildirimi): Editorde normal yapi soyle:
    #   bosluk
    #   BASLIK
    #   bosluk
    #   bosluk
    # (2. baslik satiri silinmis ornekte). Onceki surumumuzde basliktan
    # ONCEKI bos satir hic yoktu ve basliktan SONRA sadece 1 bos satir
    # ekleniyordu (2 yerine). Ikisi de duzeltildi.
    # DUZELTME (kullanici geri bildirimi - bu turda): Header'dan hemen sonra,
    # BASLIK'tan hemen once gereginden fazla bosluk vardi - bu bosluk
    # paragrafi normal metin boyutuyla (FONT_SIZE=10) tam bir satir
    # rezerve ediyordu. Kullanicinin talebiyle bu ozel spacer paragrafi
    # kucuk bir punto (yaklasik normal satirin 1/3'u kadar yer kaplayacak
    # sekilde) ile daraltildi. NOT: UYAP ondalikli punto degerlerini
    # (9.8, 9.6 vb.) reddedip 12'ye yuvarladigi test edildiginden
    # (kullanici kaniti), burada TAM SAYI bir deger (3) kullaniliyor.
    title_xml = paragraph_xml(cb, {"align": "center", "runs": []}, size="3")  # baslik ONCESI kucuk bosluk
    for para in data.get("title", []):
        title_xml += paragraph_xml(cb, para, align_map={"left": "0", "center": "1", "right": "2", "justify": "3"})
    # basliktan SONRA 2 bos paragraf
    title_xml += paragraph_xml(cb, {"align": "center", "runs": []})
    title_xml += paragraph_xml(cb, {"align": "center", "runs": []})

    # --- ana tablo satirlari ---
    # sig-grid varsa ana tablo kapatilip ayri bir imza tablosu eklenir,
    # sonra gerekirse ana tablo yeniden acilir. Tek gecis (tek dongu) ile
    # hem content akisina yazma hem XML uretimi yapilir; boylece her
    # paragraf/run icin offset yalnizca BIR KEZ hesaplanir.
    #
    # NOT: Onceki turda burada "JSON'daki ilk satir empty ise atla" seklinde
    # bir hack vardi. Kullanici bunun YANLIS bir varsayima dayandigini
    # belirtti: o bos satir, editorde kullanicinin KENDI ISTEYEREK biraktigi
    # gercek bir satirdi (kendi hatasiymis, bizim converter'imizin degil).
    # Hack GERI ALINDI - artik JSON'daki TUM satirlar oldugu gibi islenir.
    #
    # Asil cozulmesi gereken sorun baskaydi: "empty" tipi satirlarin UDF'deki
    # yuksekligi normal metin satiriyla ayni buyuklukteydi, oysa editorde/
    # PDF'te/DOCX'te empty-row'lar sadece MINIMAL bir bosluk. Bu fark cok
    # sayida bos satirin sayfayi gereksiz sekilde uzatmasina yol aciyordu
    # (DOCX'te 1 sayfaya sigan bir belgenin UDF'de sigmamasi gibi). AMA
    # bunu row-height degerini kucultup cozmeye calismak (EMPTY_ROW_HEIGHT)
    # tablo genisliklerini bozdugu icin TERK EDILDI. Cozum artik asagida:
    # "empty" satirlari tablonun DISINA tasiyip kucuk bir paragraf yapmak
    # (bkz. build_spacer_paragraph). EMPTY_ROW_HEIGHT sabiti artik
    # KULLANILMIYOR, sadece DEFAULT_ROW_HEIGHT ile ayni deger olarak
    # (510) yukarida durur - referans/gecmis uyumluluk icin.
    rows_data = list(data.get("rows", []))

    # KUCUK BOSLUK PARAGRAFI (empty-row yerine):
    # ONCEKI YONTEM: "empty" tipi satirlar ana tablonun icinde 3 sutunlu bir
    # <row> olarak temsil ediliyordu ve EMPTY_ROW_HEIGHT ile yukseklik
    # ayarlanmaya calisiliyordu. Kullanicinin kesin kanitiyla dogrulandi:
    # EMPTY_ROW_HEIGHT'i DEFAULT_ROW_HEIGHT'ten (510) FARKLI herhangi bir
    # deger yapmak, UYAP'ta tablo genisliklerinin bozulmasina yol aciyor
    # (karisik row-height sorunu, description.md madde 4). Bu yuzden
    # EMPTY_ROW_HEIGHT bir daha DEGISTIRILMEMELI, hep 510 kalmali.
    #
    # YENI YONTEM: "empty" satirlari artik ana tablonun icine hic
    # KOYMUYORUZ. Bunun yerine o noktada tabloyu kapatip (flush), tablonun
    # DISINDA kucuk bir paragraf (Arial, kucuk punto, sifir satir araligi)
    # ekliyoruz, sonra bir sonraki satirdan itibaren YENI bir tablo
    # aciyoruz. Boylece hicbir tabloda "karisik yukseklik" olmuyor (her
    # tablonun butun satirlari DEFAULT_ROW_HEIGHT=510 ile tek tip) ve
    # bosluklar da gercekten kucuk oluyor - cunku artik tablo satiri
    # degil, serbest bir paragraf.
    #
    # NOT: Bu yaklasim henuz UYAP'ta TEST EDILMEDI. Kontrol edilecekler:
    # 1) Ardisik "empty" satirlarinin (orn. bir bosluk yerine iki bosluk)
    #    her biri ayri birer paragraf mi olmali yoksa tek paragrafta
    #    SpaceBelow ile mi birlestirilmeli - once basit yontemi (her
    #    biri ayri kucuk paragraf) deniyoruz.
    # 2) Cok sayida ardisik kucuk tabloya bolunmenin (her empty-row'da
    #    tablo kapanip yeniden aciliyor) UYAP'ta gorsel/performans yan
    #    etkisi olup olmadigi.
    EMPTY_SPACER_FONT_SIZE = "8"

    def build_spacer_paragraph(cb: ContentBuilder) -> str:
        """Empty-row yerine gecen, tablonun DISINDA duran kucuk bosluk paragrafi."""
        nl_tag = run_tag(cb, "\n")
        # Bu paragraf "empty-row" yerine gecen bir BOS satirdir -> satir
        # araligi 1.0 (EMPTY_LINESPACING). Kullanicinin BOS-1 testiyle
        # dogrulanan davranis: bos satirlarda LineSpacing niteligi yazilmaz.
        return (
            f'<paragraph {TABSET_ATTR}Alignment="0" {_linespacing_attr(True)}'
            f'family="{FONT_FAMILY}" size="{EMPTY_SPACER_FONT_SIZE}" '
            f'SpaceAbove="0.0" SpaceBelow="0.0">{nl_tag}</paragraph>'
        )

    body_xml = ""
    pending_rows = []

    def flush_main_table():
        nonlocal body_xml, pending_rows
        if not pending_rows:
            return
        row_spans = ",".join(h for _, h in pending_rows) + ","
        rows_concat = "".join(r for r, _ in pending_rows)
        table_name = cb.next_table_name()
        body_xml += (
            f'<table tableName="{table_name}" columnCount="3" border="borderNone" borderSpec="31" '
            f'borderColor="-16777216" borderStyle="borderStyle-plain" borderWidth="1.0" '
            f'columnSpans="{scale_spans(MAIN_COL_SPANS)}">{rows_concat}</table>'
        )
        pending_rows = []

    for row in rows_data:
        rtype = row.get("type")
        if rtype == "empty":
            # Ana tabloyu kapat, kucuk bosluk paragrafini tablonun DISINA
            # ekle. Bir sonraki dolu satir gelince yeni bir tablo acilacak
            # (flush_main_table + pending_rows mekanizmasi zaten bunu
            # otomatik yapiyor - pending_rows bossa yeni satirlar yeni bir
            # tabloya birikir).
            flush_main_table()
            body_xml += build_spacer_paragraph(cb)
        elif rtype == "labeled":
            pending_rows.append(
                build_labeled_row(cb, row.get("label", ""), row.get("colon", ":"), row.get("paragraphs", []))
            )
        elif rtype == "full":
            # KOK NEDEN #1 (rowSpans - onceki turda cozuldu, bkz.
            # build_full_row aciklamasi): sabit "1020" yerine artik
            # DEFAULT_ROW_HEIGHT kullaniliyor.
            #
            # KOK NEDEN #2 (bu turda bulundu): Bu satirin tek hucresi ile
            # sarildigi tablonun kolon tanimi UYUMSUZDU - satir TEK bir
            # <cell> iceriyordu (eskiden colSpan="3" ile), ama tablo hala
            # "labeled" satirlar icin tasarlanmis 3-kolonlu (26,2,72)
            # tanimla aciliyordu. Kullanicinin kanitladigi "Tablo
            # Ozellikleri'nde 18 yerine 16cm gorunuyor" sorunu buradan
            # kaynaklaniyordu. Artik "full" satirlar GERCEKTEN tek kolonlu
            # (columnCount=1, columnSpans="100") bir tabloya sariliyor -
            # hucre yapisi ile tablo tanimi birebir uyumlu.
            # "full" (tam-genislik serbest metin): TABLO DEGIL, dogrudan
            # paragraf -> sayfanin gercek kenar bosluklarini kullanip tam
            # 18cm'e yayilir (TEST5 ile %100 dogrulandi). Sutun/hizalama
            # ihtiyaci olmadigi icin tabloya gerek yok.
            flush_main_table()
            _paras = row.get("paragraphs", [])
            if _paras:
                for _para in _paras:
                    body_xml += paragraph_xml(
                    cb, _para,
                    align_map={"left": "0", "center": "1", "right": "2", "justify": "3"},
                    force_content=True,
                    )
            else:
                body_xml += paragraph_xml(cb, {"align": "justify", "runs": []}, force_content=True)
        elif rtype == "siggrid":
            flush_main_table()
            # araya kucuk bosluk paragrafi
            body_xml += paragraph_xml(cb, {"align": "left", "runs": []})
            body_xml += build_siggrid_row(cb, row.get("boxes", []))
            body_xml += paragraph_xml(cb, {"align": "left", "runs": []})

    flush_main_table()

    footer_xml = build_footer_xml(cb, data.get("footer", {}))

    # NOT: onceki surumde burada, footer.enabled durumuna bakmaksizin HER ZAMAN
    # eklenen bir "sayfa sonu ince cizgi" imaji vardi. Bu, "footer kapali"
    # durumda bile bir cizginin gorunmesine yol aciyordu. Referans belgede
    # (header-footer-udf.udf) boyle bir eleman hic yoktu, bu yuzden tamamen
    # kaldirildi.

    elements_xml = (
        f'<elements resolver="hvl-default" >'
        f"{header_xml}"
        f"{title_xml}"
        f"{body_xml}"
        f"{footer_xml}"
        f"</elements>"
    )

    full_text = cb.get_full_text()
    # UDF ornek belgede CDATA icindeki metin escape edilmemis (dogrudan raw)
    # ancak "]]>" gecmesi ihtimaline karsi guvenlik onlemi:
    safe_text = full_text.replace("]]>", "]]]]><![CDATA[>")

    content_xml = (
        '<?xml version="1.0" encoding="UTF-8" ?> \n\n'
        '<template format_id="1.8" >\n'
        f"<content><![CDATA[{safe_text}]]></content>"
        f"<properties>{PAGE_FORMAT}</properties>\n"
        f"{elements_xml}\n"
        f"{STYLES_XML}\n"
        f"{TAB_LENGTH_XML}"
        "</template>\n"
    )
    return content_xml


def convert(json_path: str, udf_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    content_xml = build_udf_content_xml(data)

    with zipfile.ZipFile(udf_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.xml", content_xml.encode("utf-8"))

    print(f"UDF yazildi: {udf_path} ({os.path.getsize(udf_path)} bytes)")


def _has_header_footer(data: dict) -> bool:
    """
    JSON verisinde header VEYA footer acik mi (enabled=true) kontrol eder.
    HTM editor artik JSON'a bu bilgiyi acikca yaziyor (bkz. udf_editor.htm
    exportToUdfJson fonksiyonu), ama eski/elle olusturulmus JSON dosyalari
    icin de header.enabled / footer.enabled alanlarina bakarak calisir.
    """
    header = data.get("header", {}) or {}
    footer = data.get("footer", {}) or {}
    header_on = bool(header.get("enabled")) and bool(header.get("logoBase64"))
    footer_on = bool(footer.get("enabled")) and bool(
        (footer.get("text1") or "").strip() or (footer.get("text2") or "").strip()
    )
    return header_on or footer_on


def _prompt_for_json_path() -> str:
    """
    Kullanicidan JSON dosya yolunu ister. Windows'tan kopyalanan yollar
    genelde cift tirnak icinde gelir (or. "C:\\Users\\...\\dosya.json") -
    bu tirnaklari ve olasi bosluklari temizler.
    """
    raw = input(
        "Lutfen .json uzantili UDF-veri dosyanizin tam yolunu girin\n"
        "(orn. C:\\Users\\Kullanici\\Desktop\\dosya.udfdata.json): "
    ).strip()
    # basindaki/sonundaki cift veya tek tirnaklari temizle
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        raw = raw[1:-1]
    return raw.strip()


# NOT: CLI blogu Vercel icin kaldirildi. Yerel kullanim: python3 cli.py
