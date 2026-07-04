#!/usr/bin/env python3
"""
Buscador diario de empleo — ventas médicas / visitador médico (Baja California).
Fuentes:
  1) Adzuna (API gratuita).
  2) Google Jobs vía SerpAPI (agrega LinkedIn, Indeed, OCC, Computrabajo).
  3) Google Custom Search con operadores site: (OCC, Computrabajo, Indeed,
     LinkedIn, EmpleoNuevo) — gratis 100 queries/día.
  4) Gemini analiza cada vacante y rankea por experiencia + fit con CV.
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
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
GEMINI_KEY = os.environ.get("GEMINI_KEY")

PAIS = "mx"
UBICACIONES = ["Tijuana"]
UBICACION_GOOGLE = "Tijuana, Baja California, Mexico"
PUESTOS = [
    "representante medico",
    "visitador medico",
    "ventas medicas",
    "ventas farmaceuticas",
    "representante farmaceutico",
    "planner",
    "quality engineer",
    "NPI engineer",
    "sterilization engineer",
]
MAX_DIAS = 3
RESULTS_PER_PAGE = 50
ARCHIVO_VISTOS = "vistos.json"

PATRONES_EXCLUIR = [
    # Más de 1 año de experiencia
    r"\b([2-9]|1[0-9])\s*(a[nñ]os?|years?)\b",
    r"m[ií]nimo\s*(de\s*)?([2-9]|1[0-9])\s*a[nñ]os",
    r"al\s*menos\s*([2-9]|1[0-9])\s*a[nñ]os",
    r"experiencia\s*(comprobable\s*)?(de\s*)?([2-9]|1[0-9])\s*a[nñ]os",
    # Niveles senior (solo pasan Nivel C, Nivel 1, o sin nivel)
    r"\b(senior|sr\.?|lead|nivel\s*a|nivel\s*b|level\s*a|level\s*b)\b",
]

# Resumen del CV para Gemini
CV_RESUMEN = """
LORENZO HUGO BRACAMONTES SAMBRANO
Representante Médico | Ventas | Bilingüe
lorenzohugo33@gmail.com | +52 664 308 9446 | Tijuana, Baja California

PERFIL PROFESIONAL
Representante médico con experiencia en promoción farmacéutica, segmentación de médicos y ejecución de
ciclos de visita en zonas de alta competencia (Tijuana, Ensenada, Rosarito). Orientado a resultados con habilidad
para construir relaciones con prescriptores, analizar market share por producto, y comunicar beneficios clínicos
de forma efectiva a profesionales de la salud. Base técnica sólida en ingeniería química aplicada al conocimiento
de mecanismos de acción y composición de productos farmacéuticos.

EXPERIENCIA PROFESIONAL
Siegfried Rhein / Nutribaby | Representante Médico | ABR 2026 – Jun 2026
- Ejecuté ciclos de visita médica con cobertura de más de 220 médicos en Tijuana, Ensenada y Rosarito.
- Implementé segmentación de cartera médica bajo el modelo Efficientia (Defender/Atacar/Recuperar/Monitorear).
- Realicé análisis de market share y tendencia de recetas por médico y por competidor.
- Presenté información clínica de línea de nutrición infantil (Nutribaby/Proteflor) a pediatras y neonatólogos.
- Coordiné Business Reviews con datos de crecimiento de recetas y análisis de competidores.

First Quality Chemicals | Representante de Ventas Técnicas | JUL 2025 – MAY 2026
- Gestioné y expandí cartera de clientes industriales en Baja California y estados adyacentes.
- Conduje presentaciones técnicas sobre productos químicos especializados ante tomadores de decisión.
- Prospecté nuevos clientes mediante llamadas en frío y visitas sin cita, cerrando contratos de suministro.
- Negocié condiciones comerciales y mantuve seguimiento post-venta.

Ventas Rachel | Ejecutivo de Ventas | ENE 2024 – FEB 2025
- Desarrollé campañas de adquisición de clientes vía Facebook Ads.
- Negocié y cerré transacciones de venta directa, ciclo completo desde prospección hasta cierre.

Instituto de Enseñanza Media Superior Siglo XXI | Docente de Ciencias | SEP 2020 – ENE 2024
- Diseñé programas académicos y conduje clases para grupos de hasta 40 estudiantes.
- Implementé métricas de seguimiento académico con dashboards en Excel.

Turbo Tecnologías de Reparaciones | Ingeniero Interno | SEP 2019 – FEB 2020
- Implementé el sistema globalmente armonizado (SGA) bajo la NOM-005-STPS-1998.
- Automaticé captura de datos termoquímicos mediante macros de Excel.

EDUCACIÓN
Licenciatura en Psicología – Universidad Humanitas, Tijuana | 2024 – Actualidad
Ingeniería Química – Instituto Tecnológico de Tijuana | 2015 – 2020
Técnico en Administración de Empresas – IEMS Siglo XXI | 2012 – 2015

COMPETENCIAS CLAVE
Detalle médico, Segmentación de cartera, Market share y análisis de recetas, KOL management,
Ciclos de visita, Gestión de territorio, CRM y reporting, Presentaciones clínicas, Negociación,
Prospección en frío, Bilingüe (Español/Inglés), Power BI, Excel avanzado (macros, dashboards),
SAP, Ingeniería química aplicada, Programación básica.

CERTIFICACIONES
NOM-005-STPS-1998, ISO 9001, Metodología 5S, Metodología Efficientia, Licencia de manejo vigente.

Busca: representante médico, visitador médico, ventas médicas/farmacéuticas, planner,
quality engineer, NPI engineer, sterilization engineer (nivel C o 1).
Zona: Baja California. Disponibilidad inmediata.
"""

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
                    "texto_completo": desc,
                }
    return encontradas


# ---------- Fuente 2: Google Jobs (SerpAPI) ----------

def buscar_google_jobs():
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
            print(f"[warn] google_jobs '{puesto}': {e}")
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
                "texto_completo": desc,
            }
    return encontradas


# ---------- Gemini: análisis y ranking ----------

def analizar_con_gemini(vacantes):
    """Envía las vacantes a Gemini para rankear y recomendar."""
    if not GEMINI_KEY or not vacantes:
        return vacantes

    # Preparar resumen de vacantes para Gemini
    resumen_vacantes = []
    for i, v in enumerate(vacantes):
        resumen_vacantes.append(
            f"VACANTE {i+1}:\n"
            f"Título: {v['titulo']}\n"
            f"Empresa: {v['empresa']}\n"
            f"Fuente: {v['fuente']}\n"
            f"Descripción: {v.get('texto_completo', v['desc'])[:800]}\n"
        )

    prompt = f"""Eres un asesor de empleo. Analiza estas vacantes para el siguiente candidato.

CANDIDATO:
{CV_RESUMEN}

VACANTES:
{"---".join(resumen_vacantes)}

Para cada vacante responde en JSON (sin markdown, sin backticks):
[
  {{
    "indice": 1,
    "experiencia_estimada": "0-1 año",
    "fit_score": 85,
    "recomendacion": "Frase corta de por qué sí o no aplicar",
    "carta": "Mensaje corto para pegar al aplicar"
  }}
]

Reglas:
- experiencia_estimada: lo que pide la vacante (ej: "sin experiencia", "0-1 año", "1-2 años", "3+ años", "no especifica")
- fit_score: 0-100 qué tan bien encaja el candidato
- recomendacion: máximo 15 palabras
- carta: máximo 40 palabras, en español, lista para copiar y pegar en la casilla de "mensaje al reclutador". Debe mencionar el puesto específico y 1 fortaleza relevante del candidato para ESA vacante. Sin saludo genérico, sin "estimado/a", sin despedida. Directo.
- Ordena el array de MAYOR fit_score a MENOR
- Solo JSON, nada más"""

    import time
    modelos = ["gemini-2.0-flash-lite", "gemini-2.0-flash"]
    r = None
    for modelo in modelos:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{modelo}:generateContent?key={GEMINI_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60,
            )
            if r.status_code == 429:
                print(f"[warn] gemini {modelo}: 429, probando siguiente...")
                time.sleep(5)
                continue
            break
        except requests.RequestException:
            continue
    try:
        r.raise_for_status()
        texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        texto = texto.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        analisis = json.loads(texto)

        # Aplicar análisis a las vacantes
        mapa = {a["indice"]: a for a in analisis}
        for i, v in enumerate(vacantes):
            a = mapa.get(i + 1, {})
            v["exp_estimada"] = a.get("experiencia_estimada", "?")
            v["fit_score"] = a.get("fit_score", 50)
            v["recomendacion"] = a.get("recomendacion", "")
            v["carta"] = a.get("carta", "")

        # Ordenar por fit_score descendente
        vacantes.sort(key=lambda x: x.get("fit_score", 0), reverse=True)
        print(f"[gemini] analisis OK, {len(analisis)} vacantes rankeadas")
    except Exception as e:
        print(f"[warn] gemini: {e}")
        for v in vacantes:
            v.setdefault("exp_estimada", "?")
            v.setdefault("fit_score", 50)
            v.setdefault("recomendacion", "")
            v.setdefault("carta", "")

    return vacantes


# ---------- Correo ----------

def construir_html(nuevas):
    hoy = datetime.now(ZoneInfo("America/Tijuana")).strftime("%d/%m/%Y")
    cards = ""
    for j in nuevas:
        botones = "".join(
            f'<a href="{url}" style="display:inline-block;background:#111;color:#fff;'
            f'text-decoration:none;padding:7px 13px;border-radius:6px;font-size:12px;'
            f'margin:3px 6px 0 0;">{txt} &rarr;</a>'
            for txt, url in j.get("enlaces", []) if url
        )
        fecha = f" · {j['fecha']}" if j.get("fecha") else ""

        # Badges de Gemini
        exp = j.get("exp_estimada", "")
        fit = j.get("fit_score", "")
        reco = j.get("recomendacion", "")
        gemini_html = ""
        if exp or fit:
            fit_color = "#0a7" if (isinstance(fit, int) and fit >= 70) else (
                "#e90" if (isinstance(fit, int) and fit >= 40) else "#c33"
            )
            gemini_html = f"""
            <div style="margin:8px 0;padding:8px 12px;background:#f7f7f7;border-radius:6px;font-size:12px;">
              <span style="color:{fit_color};font-weight:700;">FIT {fit}%</span>
              <span style="color:#666;margin:0 6px;">·</span>
              <span style="color:#555;">Exp: {exp}</span>
              {f'<div style="color:#333;margin-top:4px;font-style:italic;">💡 {reco}</div>' if reco else ''}
            </div>"""

        carta = j.get("carta", "")
        carta_html = ""
        if carta:
            carta_html = f"""
            <div style="margin:6px 0;padding:8px 10px;background:#eef6ff;border-left:3px solid #39f;border-radius:4px;font-size:12px;color:#222;">
              📋 <strong>Copiar y pegar:</strong><br>{carta}
            </div>"""

        cards += f"""
        <div style="border:1px solid #e2e2e2;border-radius:10px;padding:16px;margin-bottom:14px;">
          <div style="font-size:11px;color:#0a7;font-weight:600;text-transform:uppercase;">{j['fuente']}</div>
          <div style="font-size:16px;font-weight:600;color:#111;margin-top:2px;">{j['titulo']}</div>
          <div style="font-size:13px;color:#555;margin:4px 0;">{j['empresa']} · {j['ubicacion']}{fecha}</div>
          {gemini_html}
          <div style="font-size:13px;color:#333;margin-bottom:10px;">{j['desc']}&hellip;</div>
          {carta_html}
          {botones}
        </div>"""

    fuentes_activas = set(j["fuente"] for j in nuevas)
    fuentes_txt = ", ".join(sorted(fuentes_activas)) if fuentes_activas else "Adzuna"

    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:auto;">
      <h2 style="color:#111;">Vacantes nuevas — {hoy}</h2>
      <p style="color:#555;font-size:14px;">
        {len(nuevas)} vacante(s) nueva(s) · Fuentes: {fuentes_txt}
        · Ordenadas por compatibilidad con tu perfil
      </p>
      {cards}
      <p style="color:#999;font-size:12px;margin-top:20px;">
        FIT% = compatibilidad con tu CV (Gemini). Aplica con tu CV y adapta la carta.
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
    todas.update(buscar_google_jobs())

    nuevas = [j for jid, j in todas.items() if jid not in vistos]

    unicas, claves = [], set()
    for j in sorted(nuevas, key=lambda x: x.get("fecha", ""), reverse=True):
        k = normaliza(j["titulo"]) + "|" + normaliza(j["empresa"])
        if k in claves:
            continue
        claves.add(k)
        unicas.append(j)

    if not unicas:
        print("[ok] sin vacantes nuevas hoy")
    else:
        unicas = analizar_con_gemini(unicas)
        enviar(unicas)

    vistos.update(todas.keys())
    guardar_vistos(vistos)


if __name__ == "__main__":
    main()
