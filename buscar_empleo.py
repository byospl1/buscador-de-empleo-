#!/usr/bin/env python3
"""
Buscador diario de empleo — ventas médicas / visitador médico (Baja California).
Fuentes:
  1) Adzuna (API gratuita).
  2) Google Jobs vía SerpAPI (agrega LinkedIn, Indeed, OCC, Computrabajo).
     -> Opcional: solo se activa si existe la variable SERPAPI_KEY.
Filtra por puesto y experiencia (<=1 año), descarta vacantes ya vistas
y envía un digest curado al correo de Hugo.
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
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"]
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")   # opcional

PAIS = "mx"
UBICACIONES = ["Tijuana"]  # para Adzuna
UBICACION_GOOGLE = "Tijuana, Baja California, Mexico"                  # para Google Jobs
PUESTOS = [
    "representante medico",
    "visitador medico",
    "ventas medicas",
    "ventas farmaceuticas",
    "representante farmaceutico",
]
MAX_DIAS = 3
RESULTS_PER_PAGE = 50
ARCHIVO_VISTOS = "vistos.json"

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
    texto = normaliza(f"{titulo} {desc}")
    for patron in PATRONES_EXCLUIR:
        if re.search(patron, texto):
            return False
    return True


def limpia(t):
    return re.sub(r"<.*?>", "", t or "")


def cargar_vistos():
    if os.path.exists(ARCHIVO_VISTOS):
        with open(ARCHIVO_VISTOS, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def guardar_vistos(vistos):
    with open(ARCHIVO_VISTOS, "w", encoding="utf-8") as f:
        json.dump(sorted(vistos), f, ensure_ascii=False, indent=0)


# ---------- Fuente 1: Adzuna ----------

def buscar_adzuna():
    encontradas = {}
    for puesto in PUESTOS:
        for lugar in UBICACIONES:
            url = f"https://api.adzuna.com/v1/api/jobs/{PAIS}/search/1"
            params = {
                "app_id": ADZUNA_ID, "app_key": ADZUNA_KEY,
                "what": puesto, "where": lugar,
                "results_per_page": RESULTS_PER_PAGE, "max_days_old": MAX_DIAS,
                "sort_by": "date", "content-type": "application/json",
            }
            try:
                r = requests.get(url, params=params, timeout=30)
                r.raise_for_status()
            except requests.RequestException as e:
                print(f"[warn] adzuna '{puesto}'/'{lugar}': {e}")
                continue

            for job in r.json().get("results", []):
                jid = "adz-" + str(job.get("id"))
                if jid in encontradas:
                    continue
                titulo, desc = limpia(job.get("title")), limpia(job.get("description"))
                if not cumple_experiencia(desc, titulo):
                    continue
                encontradas[jid] = {
                    "id": jid, "titulo": titulo,
                    "empresa": (job.get("company") or {}).get("display_name", "N/D"),
                    "ubicacion": (job.get("location") or {}).get("display_name", "N/D"),
                    "desc": desc[:280], "fecha": job.get("created", "")[:10],
                    "fuente": "Adzuna",
                    "enlaces": [("Ver y aplicar", job.get("redirect_url", ""))],
                }
    return encontradas


# ---------- Fuente 2: Google Jobs (SerpAPI) ----------

def buscar_google():
    if not SERPAPI_KEY:
        return {}
    encontradas = {}
    for puesto in PUESTOS:
        params = {
            "engine": "google_jobs", "q": puesto,
            "location": UBICACION_GOOGLE, "gl": "mx", "hl": "es",
            "api_key": SERPAPI_KEY,
        }
        try:
            r = requests.get("https://serpapi.com/search", params=params, timeout=45)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"[warn] google '{puesto}': {e}")
            continue

        for job in r.json().get("jobs_results", []):
            jid = "goo-" + str(job.get("job_id", ""))[:40]
            if jid in encontradas:
                continue
            titulo, desc = limpia(job.get("title")), limpia(job.get("description"))
            if not cumple_experiencia(desc, titulo):
                continue
            ext = job.get("detected_extensions", {}) or {}
            enlaces = [(o.get("title", "Aplicar"), o.get("link", ""))
                       for o in job.get("apply_options", []) if o.get("link")]
            if not enlaces and job.get("share_link"):
                enlaces = [("Ver en Google", job["share_link"])]
            encontradas[jid] = {
                "id": jid, "titulo": titulo,
                "empresa": job.get("company_name", "N/D"),
                "ubicacion": job.get("location", "N/D"),
                "desc": desc[:280], "fecha": ext.get("posted_at", ""),
                "fuente": "Google Jobs",
                "enlaces": enlaces,
            }
    return encontradas


# ---------- Correo ----------

def construir_html(nuevas):
    hoy = datetime.now(ZoneInfo("America/Tijuana")).strftime("%d/%m/%Y")
    cards = ""
    for j in nuevas:
        botones = "".join(
            f'<a href="{url}" style="display:inline-block;background:#111;color:#fff;'
            f'text-decoration:none;padding:7px 13px;border-radius:6px;font-size:12px;'
            f'margin:3px 6px 0 0;">{txt} &rarr;</a>'
            for txt, url in j["enlaces"] if url
        )
        fecha = f" · {j['fecha']}" if j["fecha"] else ""
        cards += f"""
        <div style="border:1px solid #e2e2e2;border-radius:10px;padding:16px;margin-bottom:14px;">
          <div style="font-size:11px;color:#0a7;font-weight:600;text-transform:uppercase;">{j['fuente']}</div>
          <div style="font-size:16px;font-weight:600;color:#111;margin-top:2px;">{j['titulo']}</div>
          <div style="font-size:13px;color:#555;margin:4px 0;">{j['empresa']} · {j['ubicacion']}{fecha}</div>
          <div style="font-size:13px;color:#333;margin-bottom:10px;">{j['desc']}&hellip;</div>
          {botones}
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
        Solo incluye vacantes que no habías visto antes.
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
    hora = datetime.now(ZoneInfo("America/Tijuana")).hour
    if hora != 8 and os.environ.get("FORZAR") != "1":
        print(f"[skip] hora local {hora}:00, no son las 8am")
        return

    vistos = cargar_vistos()
    todas = {}
    todas.update(buscar_adzuna())
    todas.update(buscar_google())

    nuevas = [j for jid, j in todas.items() if jid not in vistos]

    unicas, claves = [], set()
    for j in sorted(nuevas, key=lambda x: x["fecha"], reverse=True):
        k = normaliza(j["titulo"]) + "|" + normaliza(j["empresa"])
        if k in claves:
            continue
        claves.add(k)
        unicas.append(j)

    if not unicas:
        print("[ok] sin vacantes nuevas hoy")
    else:
        enviar(unicas)

    vistos.update(todas.keys())
    guardar_vistos(vistos)


if __name__ == "__main__":
    main()
