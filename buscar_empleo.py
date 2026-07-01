#!/usr/bin/env python3
"""
Buscador diario de empleo — ventas médicas / visitador médico (Baja California).
Consulta la API de Adzuna, filtra por puesto y experiencia (<=1 año),
descarta vacantes ya vistas y envía un digest curado al correo de Hugo.
"""

import os
import re
import json
import smtplib
import unicodedata
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from zoneinfo import ZoneInfo

import requests

# ---------- Configuración ----------

ADZUNA_ID = os.environ["ADZUNA_APP_ID"]
ADZUNA_KEY = os.environ["ADZUNA_APP_KEY"]
GMAIL_USER = os.environ["GMAIL_USER"]        # tu correo (remitente = destinatario)
GMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"]  # App Password de Google (16 dígitos)

PAIS = "mx"
UBICACIONES = ["Tijuana", "Ensenada", "Rosarito", "Baja California"]
PUESTOS = [
    "representante medico",
    "visitador medico",
    "ventas medicas",
    "ventas farmaceuticas",
    "representante farmaceutico",
]
MAX_DIAS = 3            # solo vacantes publicadas en los ultimos 3 dias
RESULTS_PER_PAGE = 50
ARCHIVO_VISTOS = "vistos.json"

# Frases que indican MAS de 1 año de experiencia -> se descartan
PATRONES_EXCLUIR = [
    r"\b([2-9]|1[0-9])\s*(a[nñ]os?|years?)\b",
    r"m[ií]nimo\s*(de\s*)?([2-9]|1[0-9])\s*a[nñ]os",
    r"al\s*menos\s*([2-9]|1[0-9])\s*a[nñ]os",
    r"experiencia\s*(comprobable\s*)?(de\s*)?([2-9]|1[0-9])\s*a[nñ]os",
]

# ---------- Utilidades ----------

def normaliza(texto):
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower()


def cumple_experiencia(desc, titulo):
    """True si NO exige mas de 1 año (o no menciona experiencia)."""
    texto = normaliza(f"{titulo} {desc}")
    for patron in PATRONES_EXCLUIR:
        if re.search(patron, texto):
            return False
    return True


def cargar_vistos():
    if os.path.exists(ARCHIVO_VISTOS):
        with open(ARCHIVO_VISTOS, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def guardar_vistos(vistos):
    with open(ARCHIVO_VISTOS, "w", encoding="utf-8") as f:
        json.dump(sorted(vistos), f, ensure_ascii=False, indent=0)


# ---------- Búsqueda ----------

def buscar():
    encontradas = {}
    for puesto in PUESTOS:
        for lugar in UBICACIONES:
            url = f"https://api.adzuna.com/v1/api/jobs/{PAIS}/search/1"
            params = {
                "app_id": ADZUNA_ID,
                "app_key": ADZUNA_KEY,
                "what": puesto,
                "where": lugar,
                "results_per_page": RESULTS_PER_PAGE,
                "max_days_old": MAX_DIAS,
                "sort_by": "date",
                "content-type": "application/json",
            }
            try:
                r = requests.get(url, params=params, timeout=30)
                r.raise_for_status()
            except requests.RequestException as e:
                print(f"[warn] fallo '{puesto}' en '{lugar}': {e}")
                continue

            for job in r.json().get("results", []):
                jid = str(job.get("id"))
                if jid in encontradas:
                    continue
                titulo = job.get("title", "")
                desc = job.get("description", "")
                if not cumple_experiencia(desc, titulo):
                    continue
                encontradas[jid] = {
                    "id": jid,
                    "titulo": re.sub(r"<.*?>", "", titulo),
                    "empresa": (job.get("company") or {}).get("display_name", "N/D"),
                    "ubicacion": (job.get("location") or {}).get("display_name", "N/D"),
                    "desc": re.sub(r"<.*?>", "", desc)[:280],
                    "url": job.get("redirect_url", ""),
                    "fecha": job.get("created", "")[:10],
                    "salario_min": job.get("salary_min"),
                    "salario_max": job.get("salary_max"),
                }
    return encontradas


# ---------- Correo ----------

def salario_txt(j):
    lo, hi = j.get("salario_min"), j.get("salario_max")
    if lo and hi:
        return f"${lo:,.0f} – ${hi:,.0f} MXN/año"
    if lo:
        return f"desde ${lo:,.0f} MXN/año"
    return "no publicado"


def construir_html(nuevas):
    hoy = datetime.now(ZoneInfo("America/Tijuana")).strftime("%d/%m/%Y")
    cards = ""
    for j in nuevas:
        cards += f"""
        <div style="border:1px solid #e2e2e2;border-radius:10px;padding:16px;margin-bottom:14px;">
          <div style="font-size:16px;font-weight:600;color:#111;">{j['titulo']}</div>
          <div style="font-size:13px;color:#555;margin:4px 0;">
            {j['empresa']} · {j['ubicacion']} · publicada {j['fecha']}
          </div>
          <div style="font-size:12px;color:#777;margin-bottom:8px;">💰 {salario_txt(j)}</div>
          <div style="font-size:13px;color:#333;margin-bottom:12px;">{j['desc']}…</div>
          <a href="{j['url']}" style="display:inline-block;background:#111;color:#fff;
             text-decoration:none;padding:8px 16px;border-radius:6px;font-size:13px;">
             Ver y aplicar →</a>
        </div>"""

    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:auto;">
      <h2 style="color:#111;">Vacantes nuevas — {hoy}</h2>
      <p style="color:#555;font-size:14px;">
        {len(nuevas)} vacante(s) nueva(s) de ventas médicas / visitador médico
        en Baja California (máx 1 año de experiencia).
      </p>
      {cards}
      <p style="color:#999;font-size:12px;margin-top:20px;">
        Revisa cada una, aplica con tu CV y adapta la carta de presentación.
        Este correo solo incluye vacantes que no habías visto antes.
      </p>
    </div>"""


def enviar(nuevas):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🩺 {len(nuevas)} vacante(s) nueva(s) — ventas médicas"
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER
    msg.attach(MIMEText(construir_html(nuevas), "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)
    print(f"[ok] enviado digest con {len(nuevas)} vacantes")


# ---------- Main ----------

def main():
    # Ejecutar solo si en Tijuana son ~8am (el cron dispara a 15:00 y 16:00 UTC por DST)
    hora = datetime.now(ZoneInfo("America/Tijuana")).hour
    if hora != 8 and os.environ.get("FORZAR") != "1":
        print(f"[skip] hora local {hora}:00, no son las 8am")
        return

    vistos = cargar_vistos()
    todas = buscar()
    nuevas = [j for jid, j in todas.items() if jid not in vistos]

    if not nuevas:
        print("[ok] sin vacantes nuevas hoy")
    else:
        nuevas.sort(key=lambda x: x["fecha"], reverse=True)
        enviar(nuevas)

    vistos.update(todas.keys())
    guardar_vistos(vistos)


if __name__ == "__main__":
    main()
