#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POST /api/udf
    Govde: HTM editorunun urettigi udfdata JSON'u (exportToUdfJson ciktisi)
    Yanit: application/octet-stream olarak .udf (zip icinde content.xml)

Converter mantigi DEGISMEDI: api/_udf_lib.py, json_to_udf_v37.py'nin
birebir kopyasidir (sadece interaktif __main__ blogu cikarildi).
Burada yaptigimiz tek sey, diske yazmak yerine bellekte zip uretmek.
"""

from http.server import BaseHTTPRequestHandler
from urllib.parse import quote
import json
import io
import os
import sys
import zipfile

# _udf_lib'i, bu dosya nasil yuklenirse yuklensin bulabilmek icin kendi
# klasorumuzu sys.path'e ekliyoruz. Dosya-tabanli /api yonlendirmesinde
# gerekmez, ama pyproject.toml + tool.vercel.entrypoint yontemine gecilirse
# modul "api.udf" olarak import edilir ve duz "from _udf_lib import" patlar.
# Bu iki satir her iki modu da calisir tutar.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _udf_lib import build_udf_content_xml, _has_header_footer

MAX_BODY = 20 * 1024 * 1024  # 20 MB (base64 logo payload'i icin bol bol yeter)


def build_udf_bytes(data: dict) -> bytes:
    """convert() ile ayni is, ama dosya yerine bellege yazar."""
    content_xml = build_udf_content_xml(data)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.xml", content_xml.encode("utf-8"))
    return buf.getvalue()


def safe_filename(data: dict) -> str:
    base = (data.get("fileName") or "Arabuluculuk_Tutanak").strip()
    for ch in '\\/:*?"<>|\r\n':
        base = base.replace(ch, "")
    base = base.strip() or "Arabuluculuk_Tutanak"
    # Yerel scriptteki adlandirma kuralini koru
    suffix = "_ile_header_footer" if _has_header_footer(data) else "_header_footer_yok"
    return base + suffix + ".udf"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._error(413, "Gecersiz veya cok buyuk govde.")

            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                return self._error(400, "JSON bir nesne olmali.")

            udf = build_udf_bytes(data)
            name = safe_filename(data)

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            # RFC 5987: Turkce karakterli dosya adlari icin filename* sart
            self.send_header(
                "Content-Disposition",
                "attachment; filename=\"document.udf\"; "
                "filename*=UTF-8''" + quote(name, safe=""),
            )
            self.send_header("Content-Length", str(len(udf)))
            self.end_headers()
            self.wfile.write(udf)

        except json.JSONDecodeError as e:
            self._error(400, f"JSON cozumlenemedi: {e}")
        except Exception as e:
            self._error(500, f"Donusturme hatasi: {type(e).__name__}: {e}")

    def _error(self, code: int, msg: str):
        body = json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
