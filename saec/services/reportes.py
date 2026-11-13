"""Exportación del diagnóstico y de los datos a PDF (ReportLab) y Excel (openpyxl)."""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from . import graficos
from .diagnostico import Diagnostico, fmt

AZUL = colors.HexColor("#1F3B57")
AZUL2 = colors.HexColor("#2E5E8C")
NIVEL_COLOR = {"ALTA": colors.HexColor("#C0392B"), "MEDIA": colors.HexColor("#E08A2E"), "BAJA": colors.HexColor("#4E9A4E")}


def _estilos():
    ss = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("t", parent=ss["Title"], textColor=AZUL, fontSize=18, leading=22, spaceAfter=4),
        "sub": ParagraphStyle("s", parent=ss["Normal"], textColor=colors.HexColor("#5B6B7A"), fontSize=9, leading=12),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=AZUL2, fontSize=13, spaceBefore=10, spaceAfter=4),
        "p": ParagraphStyle("p", parent=ss["Normal"], fontSize=9.5, leading=13.5, alignment=TA_JUSTIFY),
        "li": ParagraphStyle("li", parent=ss["Normal"], fontSize=9.5, leading=13, leftIndent=12, bulletIndent=2),
        "adv": ParagraphStyle("adv", parent=ss["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#8A5A00"),
                              backColor=colors.HexColor("#FEF5E7"), borderPadding=4, spaceAfter=4),
        "celda": ParagraphStyle("c", parent=ss["Normal"], fontSize=8.5, leading=11),
    }


def _img(fig, ancho_cm: float = 15.5) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    w, h = fig.get_size_inches()
    return Image(buf, width=ancho_cm * cm, height=ancho_cm * cm * h / w)


def _valor(v, columna: str = "") -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    if str(columna).lower() in ("año", "anio", "id"):
        return str(int(v)) if isinstance(v, (int, float, np.integer, np.floating)) else str(v)
    if isinstance(v, (bool, np.bool_)):
        return "Sí" if v else "No"
    if isinstance(v, (int, np.integer)):
        return fmt(int(v))
    if isinstance(v, (float, np.floating)):
        return fmt(float(v), 1)
    return str(v)


def _pdf_txt(t: str) -> str:
    """Las fuentes estándar del PDF no tienen algunos símbolos."""
    return t.replace("χ²", "chi²").replace("⚠", "").replace("→", "-").replace("–", "-")


def _tabla(df: pd.DataFrame, est) -> Table:
    datos = [[Paragraph(f"<b>{c}</b>", est["celda"]) for c in df.columns]]
    for _, fila in df.iterrows():
        datos.append([Paragraph(_valor(v, c), est["celda"]) for c, v in zip(df.columns, fila.values)])
    t = Table(datos, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE6EF")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C4D0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FA")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawString(2 * cm, 1.2 * cm, "SAEC · Diagnóstico situacional de enfermedades crónicas · Subred Norte")
    canvas.drawRightString(letter[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


def diagnostico_pdf(dx: Diagnostico, ruta: Path) -> Path:
    est = _estilos()
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(ruta), pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title="Diagnóstico situacional SAEC", author="SAEC")
    h = [Paragraph("Diagnóstico situacional de enfermedades crónicas", est["titulo"]),
         Paragraph(f"EPOC · Asma · Diabetes - Subred Integrada de Servicios de Salud Norte, Bogotá D.C.<br/>"
                   f"Generado: {dx.generado:%Y-%m-%d %H:%M} · {dx.filtro}<br/>Fuente de datos: {dx.fuente}", est["sub"]),
         Spacer(1, 8)]
    for a in dx.advertencias:
        h.append(Paragraph("<b>Atención:</b> " + _pdf_txt(a), est["adv"]))
    # KPIs
    k = dx.kpis
    if k:
        celdas = [["Atenciones", "EPOC", "Asma", "Diabetes", "Periodo"],
                  [fmt(k["total"]), fmt(k["por_enfermedad"]["EPOC"]), fmt(k["por_enfermedad"]["ASMA"]),
                   fmt(k["por_enfermedad"]["DIABETES"]), k["periodo"]]]
        t = Table(celdas, colWidths=[3.4 * cm] * 5)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), AZUL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("FONTSIZE", (0, 1), (-1, 1), 13),
                               ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BOX", (0, 0), (-1, -1), 0.5, AZUL),
                               ("TOPPADDING", (0, 1), (-1, 1), 7), ("BOTTOMPADDING", (0, 1), (-1, 1), 7)]))
        h += [t, Spacer(1, 10)]
    h += [Paragraph("Conclusión general", est["h2"]), Paragraph(_pdf_txt(dx.conclusion), est["p"])]
    # prioridades
    if dx.prioridades:
        h.append(Paragraph("Priorización", est["h2"]))
        filas = [[Paragraph("<b>#</b>", est["celda"]), Paragraph("<b>Enfermedad</b>", est["celda"]),
                  Paragraph("<b>Prioridad</b>", est["celda"]), Paragraph("<b>Razones</b>", est["celda"]),
                  Paragraph("<b>Acciones sugeridas</b>", est["celda"])]]
        for p in dx.prioridades:
            filas.append([str(p["orden"]), p["enfermedad"],
                          Paragraph(f"<font color='{NIVEL_COLOR[p['nivel']].hexval()}'><b>{p['nivel']}</b></font><br/>"
                                    f"puntaje {fmt(p['puntaje'], 2)}", est["celda"]),
                          Paragraph("<br/>".join("• " + _pdf_txt(r) for r in p["razones"]), est["celda"]),
                          Paragraph("<br/>".join("• " + a for a in p["acciones"]), est["celda"])])
        t = Table(filas, colWidths=[0.7 * cm, 2.2 * cm, 2.3 * cm, 5.0 * cm, 7.3 * cm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE6EF")),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C4D0")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 8.5)]))
        h.append(t)
    h.append(PageBreak())
    for s in dx.secciones:
        bloque = [Paragraph(s.titulo, est["h2"])]
        bloque += [Paragraph(_pdf_txt(x), est["li"], bulletText="•") for x in s.hallazgos]
        h.append(KeepTogether(bloque))
        if s.grafico:
            h += [Spacer(1, 4), _img(graficos.figura(s.grafico, dx), 14.5)]
        if s.tabla is not None and not s.tabla.empty:
            h += [Spacer(1, 4), _tabla(s.tabla, est)]
        h.append(Spacer(1, 6))
    h += [Spacer(1, 10), Paragraph(
        "<i>Nota: diagnóstico poblacional generado automáticamente a partir de registros administrativos. "
        "Las cifras corresponden a atenciones, no a tasas de prevalencia. No constituye diagnóstico clínico "
        "ni reemplaza el criterio de los profesionales de la salud.</i>", est["sub"])]
    doc.build(h, onFirstPage=_pie, onLaterPages=_pie)
    return ruta


def diagnostico_excel(dx: Diagnostico, ruta: Path) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(ruta, engine="openpyxl") as xw:
        resumen = pd.DataFrame({"Campo": ["Generado", "Filtro", "Fuente", "Total atenciones", "Conclusión"],
                                "Valor": [f"{dx.generado:%Y-%m-%d %H:%M}", dx.filtro, dx.fuente, dx.total, dx.conclusion]})
        resumen.to_excel(xw, sheet_name="Resumen", index=False)
        pd.DataFrame([{"Orden": p["orden"], "Enfermedad": p["enfermedad"], "Prioridad": p["nivel"],
                       "Puntaje": p["puntaje"], "Razones": " | ".join(p["razones"]),
                       "Acciones": " | ".join(p["acciones"])} for p in dx.prioridades]
                     ).to_excel(xw, sheet_name="Priorización", index=False)
        filas = [{"Sección": s.titulo, "Hallazgo": hz} for s in dx.secciones for hz in s.hallazgos]
        pd.DataFrame(filas).to_excel(xw, sheet_name="Hallazgos", index=False)
        for s in dx.secciones:
            if s.tabla is not None and not s.tabla.empty:
                s.tabla.to_excel(xw, sheet_name=s.titulo[:31].replace("/", "-"), index=False)
        dx.datos.to_excel(xw, sheet_name="Datos", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                largo = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, largo + 2), 90)
    return ruta


def nombre_archivo(prefijo: str, ext: str, carpeta: Path) -> Path:
    return Path(carpeta) / f"{prefijo}_{datetime.now():%Y%m%d_%H%M%S}.{ext}"
