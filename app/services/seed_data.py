"""Generador de datos semilla y soportes documentales reales en PDF e imagen (PNG/JPG) para demostración DARA."""

from datetime import datetime, timedelta
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.models import (
    Aspirante,
    MockHistoricoUis,
    MockIcfesOficial,
    ProgramaAcademico,
    SoporteDocumental,
)
from app.services.rules_engine import liquidar_derechos_inscripcion

SEED_DOCS_DIR = Path("seed_docs")
SIMPLEDOCS_DIR = SEED_DOCS_DIR / "simpledocs"


def extraer_datos_pdf_icfes_real(ruta_pdf: Path) -> Optional[Dict[str, Any]]:
    """Extrae texto real desde un reporte PDF del Examen Saber 11° (simpledocs o generado) usando pdftotext."""
    if not ruta_pdf.exists() or not ruta_pdf.is_file():
        return None
    try:
        res = subprocess.run(
            ["pdftotext", str(ruta_pdf), "-"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        txt = res.stdout or ""
    except Exception:
        return None

    if not txt.strip():
        return None

    # Caso 1: Reporte oficial Saber 11° en formato ICFES (seed_docs/simpledocs/*.pdf)
    snp_m = re.search(r"\b(AC\d{10,14})\b", txt)
    doc_m = re.search(r"(?:T\.I\.|C\.C\.)\s*(\d+)", txt)
    glob_m = re.search(r"(\d{1,3})\s*/\s*500", txt)
    scores_100 = [float(x) for x in re.findall(r"\b(\d{1,3})\s*/\s*100\b", txt)]

    if snp_m and doc_m and glob_m and len(scores_100) >= 5:
        lines = [line.strip() for line in txt.splitlines() if line.strip()]
        nombre = ""
        for idx, line in enumerate(lines):
            if re.match(r"^(?:T\.I\.|C\.C\.)\s*\d+$", line) and idx > 0:
                nombre = lines[idx - 1]
                break
        fec_m = re.search(r"(\d{2})/(\d{2})/(20\d{2})", txt)
        anio = int(fec_m.group(3)) if fec_m else 2026
        fecha_pres = (
            f"{fec_m.group(3)}-{fec_m.group(2)}-{fec_m.group(1)}"
            if fec_m
            else f"{anio}-01-25"
        )
        return {
            "registro_snp": snp_m.group(1),
            "documento_identidad": doc_m.group(1),
            "nombres_completos": nombre or "Evaluado Saber 11",
            "anio_examen": anio,
            "fecha_presentacion": fecha_pres,
            "puntaje_global": float(glob_m.group(1)),
            "lectura_critica": scores_100[0],
            "matematicas": scores_100[1],
            "sociales_ciudadanas": scores_100[2],
            "ciencias_naturales": scores_100[3],
            "ingles": scores_100[4],
        }

    return None


def leer_datos_aspirantes_xlsx(ruta_xlsx: Path) -> List[Dict[str, Any]]:
    """Lee las filas de DatosAspirantes.xlsx sin requerir dependencias externas usando zipfile y ElementTree."""
    if not ruta_xlsx.exists() or not ruta_xlsx.is_file():
        return []

    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(ruta_xlsx, "r") as zf:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root_ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root_ss.findall("s:si", ns):
                shared.append("".join((t.text or "") for t in si.findall(".//s:t", ns)))

        root_sh = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        filas_crudas: List[Dict[str, str]] = []
        for row_el in root_sh.findall(".//s:sheetData/s:row", ns):
            row_dict: Dict[str, str] = {}
            for cell_el in row_el.findall("s:c", ns):
                col_ref = "".join(ch for ch in cell_el.attrib.get("r", "") if ch.isalpha())
                cell_type = cell_el.attrib.get("t", "")
                val_el = cell_el.find("s:v", ns)
                val_txt = val_el.text if val_el is not None and val_el.text is not None else ""
                if cell_type == "s" and val_txt.isdigit():
                    val_txt = shared[int(val_txt)]
                row_dict[col_ref] = val_txt
            filas_crudas.append(row_dict)

    # Saltar fila de encabezado (índice 0) y filtrar filas vacías
    registros: List[Dict[str, Any]] = []
    for idx_fila, r in enumerate(filas_crudas[1:], start=1):
        nombre_raw = (r.get("A") or "").strip().rstrip(".")
        if not nombre_raw or not (r.get("D") or "").strip():
            continue

        partes_nombre = nombre_raw.split()
        if len(partes_nombre) >= 4:
            nombres = " ".join(partes_nombre[:-2])
            apellidos = " ".join(partes_nombre[-2:])
        elif len(partes_nombre) == 3:
            nombres = partes_nombre[0]
            apellidos = " ".join(partes_nombre[1:])
        elif len(partes_nombre) == 2:
            nombres, apellidos = partes_nombre[0], partes_nombre[1]
        else:
            nombres, apellidos = nombre_raw, "UIS"

        tipo_doc_raw = (r.get("B") or "").lower()
        tipo_doc = "TI" if "tarjeta" in tipo_doc_raw else "CC"
        snp = (r.get("C") or "").strip()
        documento = str(int(float(r["D"].strip())))

        edad = 17
        if (r.get("E") or "").strip():
            try:
                dias_excel = int(float(r["E"].strip()))
                fecha_nac = datetime(1899, 12, 30) + timedelta(days=dias_excel)
                edad = max(15, min(30, 2026 - fecha_nac.year))
            except Exception:
                edad = 17

        registros.append(
            {
                "indice_simpledocs": idx_fila,
                "nombre_completo": nombre_raw,
                "nombres": nombres,
                "apellidos": apellidos,
                "tipo_documento": tipo_doc,
                "documento_identidad": documento,
                "registro_snp": snp,
                "edad": edad,
                "anio_examen": int(snp[2:6]) if len(snp) >= 6 and snp[2:6].isdigit() else 2026,
                "puntaje_global": float(r.get("F") or 0.0),
                "lectura_critica": float(r.get("G") or 0.0),
                "matematicas": float(r.get("H") or 0.0),
                "sociales_ciudadanas": float(r.get("I") or 0.0),
                "ciencias_naturales": float(r.get("J") or 0.0),
                "ingles": float(r.get("K") or 0.0),
                "ciudad_residencia": (r.get("L") or "").strip(),
            }
        )

    return registros


def generar_pdf_reporte_icfes(
    ruta_destino: Path,
    registro_snp: str,
    documento: str,
    nombre_completo: str,
    anio: int,
    puntaje_global: float,
    cn: float,
    sc: float,
    mat: float,
    lc: float,
    ing: float,
) -> Path:
    """Genera un archivo PDF real con el reporte individual de resultados Saber 11°."""
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(ruta_destino), pagesize=letter)
    c.setTitle(f"Reporte Saber 11 - {registro_snp}")

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 740, "INSTITUTO COLOMBIANO PARA LA EVALUACIÓN DE LA EDUCACIÓN - ICFES")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 720, "REPORTE INDIVIDUAL DE RESULTADOS EXAMEN DE ESTADO SABER 11°")
    c.line(50, 712, 560, 712)

    c.setFont("Helvetica", 11)
    c.drawString(50, 690, f"Número de Registro SNP : {registro_snp}")
    c.drawString(50, 672, f"Documento de Identidad : {documento}")
    c.drawString(50, 654, f"Evaluado(a)            : {nombre_completo}")
    c.drawString(50, 636, f"Año de Presentación    : {anio} (Fecha: {anio}-08-18)")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 612, f"PUNTAJE GLOBAL         : {puntaje_global:.1f} / 500")

    c.line(50, 600, 560, 600)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, 582, "DESGLOSE DE PUNTAJES POR PRUEBA (0 a 100 PUNTOS):")
    c.setFont("Helvetica", 11)
    c.drawString(65, 560, f"1. Ciencias Naturales      : {cn:.1f} puntos")
    c.drawString(65, 542, f"2. Sociales y Ciudadanas   : {sc:.1f} puntos")
    c.drawString(65, 524, f"3. Matemáticas             : {mat:.1f} puntos")
    c.drawString(65, 506, f"4. Lectura Crítica         : {lc:.1f} puntos")
    c.drawString(65, 488, f"5. Inglés                  : {ing:.1f} puntos")

    c.line(50, 470, 560, 470)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(
        50,
        452,
        "Soporte oficial generado para validación documental de admisión de pregrado UIS (Procedimiento PAR.01).",
    )
    c.save()
    return ruta_destino


def generar_png_diploma_bachiller(
    ruta_destino: Path,
    documento: str,
    nombre_completo: str,
    anio: int,
) -> Path:
    """Genera una imagen PNG real que representa un Acta/Diploma de Bachiller."""
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (820, 520), color=(252, 250, 242))
    draw = ImageDraw.Draw(img)

    # Marco decorativo
    draw.rectangle([15, 15, 805, 505], outline=(24, 92, 55), width=4)
    draw.rectangle([25, 25, 795, 495], outline=(180, 150, 70), width=2)

    draw.text((190, 55), "REPÚBLICA DE COLOMBIA - MINISTERIO DE EDUCACIÓN", fill=(24, 92, 55))
    draw.text((175, 90), "INSTITUTO TÉCNICO SUPERIOR DÁMASO ZAPATA - BUCARAMANGA", fill=(30, 30, 30))
    draw.text((255, 140), "DIPLOMA Y ACTA DE GRADO DE BACHILLER", fill=(24, 92, 55))
    draw.text((90, 200), f"Certifica que el(la) estudiante: {nombre_completo}", fill=(20, 20, 20))
    draw.text((90, 235), f"Identificado(a) con Documento N°: {documento}", fill=(20, 20, 20))
    draw.text(
        (90, 270),
        f"Cursó y aprobó satisfactoriamente los estudios de Educación Media (Grado 11°)",
        fill=(20, 20, 20),
    )
    draw.text(
        (90, 305),
        f"Optando al título de BACHILLER ACADÉMICO en la promoción del año {anio}.",
        fill=(20, 20, 20),
    )
    draw.text((90, 380), "Firma Rectoría: [Verificado Digitalmente]   |   Registro Folio Oficial DARA-UIS", fill=(80, 80, 80))

    img.save(str(ruta_destino), format="PNG")
    return ruta_destino


def generar_png_certificado_electoral(
    ruta_destino: Path,
    documento: str,
    nombre_completo: str,
    fecha_elecciones: str = "2023-10-29",
) -> Path:
    """Genera una imagen PNG real que representa un Certificado Electoral colombiano."""
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (760, 420), color=(240, 248, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([12, 12, 748, 408], outline=(15, 65, 130), width=4)
    draw.text((160, 40), "ORGANIZACIÓN ELECTORAL - REGISTRADURÍA NACIONAL", fill=(15, 65, 130))
    draw.text((220, 75), "CERTIFICADO ELECTORAL OFICIAL - COLOMBIA", fill=(180, 30, 30))
    draw.text((70, 135), f"Cédula de Ciudadanía : {documento}", fill=(20, 20, 20))
    draw.text((70, 170), f"Nombres y Apellidos  : {nombre_completo}", fill=(20, 20, 20))
    draw.text((70, 205), f"Jornada Electoral    : {fecha_elecciones} (Elecciones inmediatamente anteriores)", fill=(20, 20, 20))
    draw.text((70, 240), "Departamento / Mpio  : SANTANDER - BUCARAMANGA (Zona 01 Puesto 02 Mesa 14)", fill=(20, 20, 20))
    draw.text(
        (70, 300),
        "Válido para desempate de admisión en instituciones de educación superior (Ley 403 de 1997 / PAR.01 UIS).",
        fill=(24, 92, 55),
    )

    img.save(str(ruta_destino), format="PNG")
    return ruta_destino


def poblar_escenario_semilla(
    db: Session,
    directorio_soportes: Path = SEED_DOCS_DIR,
) -> Dict[str, Any]:
    """Reinicia la base de datos y carga programas de las 4 facultades UIS, registros ICFES/Histórico y 12 aspirantes con casos borde."""
    directorio_soportes.mkdir(parents=True, exist_ok=True)

    # Limpiar tablas existentes en orden de dependencias
    db.query(SoporteDocumental).delete()
    db.query(Aspirante).delete()
    db.query(MockHistoricoUis).delete()
    db.query(MockIcfesOficial).delete()
    db.query(ProgramaAcademico).delete()
    db.commit()

    # 1. Crear 4 Programas Académicos (uno por cada Facultad mencionada en PAR.01)
    prog_sistemas = ProgramaAcademico(
        codigo="ING-SIS",
        nombre="Ingeniería de Sistemas",
        facultad="Facultad de Ingenierías Físico-Mecánicas",
        modalidad="PRESENCIAL",
        cupos_ofertados=3,
        peso_ciencias_naturales=25.0,
        peso_sociales_ciudadanas=10.0,
        peso_matematicas=40.0,
        peso_lectura_critica=15.0,
        peso_ingles=10.0,
    )
    prog_medicina = ProgramaAcademico(
        codigo="MED",
        nombre="Medicina",
        facultad="Facultad de Salud",
        modalidad="PRESENCIAL",
        cupos_ofertados=2,
        peso_ciencias_naturales=35.0,
        peso_sociales_ciudadanas=10.0,
        peso_matematicas=20.0,
        peso_lectura_critica=25.0,
        peso_ingles=10.0,
    )
    prog_derecho = ProgramaAcademico(
        codigo="DER",
        nombre="Derecho",
        facultad="Facultad de Ciencias Humanas",
        modalidad="PRESENCIAL",
        cupos_ofertados=2,
        peso_ciencias_naturales=10.0,
        peso_sociales_ciudadanas=30.0,
        peso_matematicas=10.0,
        peso_lectura_critica=40.0,
        peso_ingles=10.0,
    )
    prog_matematicas = ProgramaAcademico(
        codigo="MAT",
        nombre="Matemáticas",
        facultad="Facultad de Ciencias",
        modalidad="PRESENCIAL",
        cupos_ofertados=2,
        peso_ciencias_naturales=20.0,
        peso_sociales_ciudadanas=10.0,
        peso_matematicas=50.0,
        peso_lectura_critica=10.0,
        peso_ingles=10.0,
    )
    prog_industrial = ProgramaAcademico(
        codigo="ING-IND",
        nombre="Ingeniería Industrial",
        facultad="Facultad de Ingenierías Físico-Mecánicas",
        modalidad="PRESENCIAL",
        cupos_ofertados=10,
        peso_ciencias_naturales=20.0,
        peso_sociales_ciudadanas=10.0,
        peso_matematicas=35.0,
        peso_lectura_critica=20.0,
        peso_ingles=15.0,
    )
    prog_civil = ProgramaAcademico(
        codigo="ING-CIV",
        nombre="Ingeniería Civil",
        facultad="Facultad de Ingenierías Físico-Mecánicas",
        modalidad="PRESENCIAL",
        cupos_ofertados=5,
        peso_ciencias_naturales=25.0,
        peso_sociales_ciudadanas=10.0,
        peso_matematicas=35.0,
        peso_lectura_critica=15.0,
        peso_ingles=15.0,
    )
    db.add_all(
        [
            prog_sistemas,
            prog_medicina,
            prog_derecho,
            prog_matematicas,
            prog_industrial,
            prog_civil,
        ]
    )
    db.commit()
    for p in (
        prog_sistemas,
        prog_medicina,
        prog_derecho,
        prog_matematicas,
        prog_industrial,
        prog_civil,
    ):
        db.refresh(p)

    # 2. Definir los 12 aspirantes cubriendo todos los casos borde del procedimiento PAR.01
    definiciones_aspirantes: List[Dict[str, Any]] = [
        # 1. Admitida Puesto 1 en Ingeniería de Sistemas
        {
            "orden": 1,
            "doc": "1098700001",
            "nombres": "Camila Andrea",
            "apellidos": "Gómez Ruiz",
            "correo": "camila.gomez@correo.uis.edu.co",
            "edad": 18,
            "sisben": "A2",
            "op1": prog_sistemas.id,
            "op2": prog_matematicas.id,
            "snp": "AC2024100001",
            "anio": 2024,
            "decl": (435.0, 86.0, 80.0, 92.0, 84.0, 82.0),
            "ofic": (435.0, 86.0, 80.0, 92.0, 84.0, 82.0),
            "voto": True,
        },
        # 2. Caso Borde Paso 7 (P.F.U.): Tiene el 2do mejor puntaje en Sistemas, pero registra P.F.U. vigente -> Anulado y corre el cupo
        {
            "orden": 2,
            "doc": "1098700002",
            "nombres": "Sebastián",
            "apellidos": "Morales Díaz",
            "correo": "sebastian.morales@correo.uis.edu.co",
            "edad": 21,
            "sisben": "B4",
            "op1": prog_sistemas.id,
            "op2": None,
            "snp": "AC2023100002",
            "anio": 2023,
            "decl": (422.0, 84.0, 78.0, 90.0, 82.0, 80.0),
            "ofic": (422.0, 84.0, 78.0, 90.0, 82.0, 80.0),
            "voto": False,
            "historico": (
                "PFU",
                "Pérdida de calidad de estudiante por bajo rendimiento académico (P.F.U.) en Ingeniería Mecánica",
                "2025-2",
            ),
        },
        # 3. Caso Borde Empate resuelto por Certificado Electoral (Regla 4): Empata en ponderado (78.0), Global (390), LC (78) y SC (78) con Santiago (#4), pero Valentina tiene Certificado Electoral válido
        {
            "orden": 4,
            "doc": "1098700003",
            "nombres": "Valentina",
            "apellidos": "Rojas Pinzón",
            "correo": "valentina.rojas@correo.uis.edu.co",
            "edad": 19,
            "sisben": "B2",
            "op1": prog_sistemas.id,
            "op2": prog_matematicas.id,
            "snp": "AC2024100003",
            "anio": 2024,
            "decl": (390.0, 78.0, 78.0, 78.0, 78.0, 78.0),
            "ofic": (390.0, 78.0, 78.0, 78.0, 78.0, 78.0),
            "voto": True,
        },
        # 4. Empatado con Valentina (#3) sin certificado electoral, pero alcanza el 3er cupo de Sistemas gracias al corrimiento por P.F.U. de Sebastián (#2)
        {
            "orden": 3,
            "doc": "1098700004",
            "nombres": "Santiago",
            "apellidos": "Herrera Castro",
            "correo": "santiago.herrera@correo.uis.edu.co",
            "edad": 19,
            "sisben": "C4",
            "op1": prog_sistemas.id,
            "op2": prog_matematicas.id,
            "snp": "AC2024100004",
            "anio": 2024,
            "decl": (390.0, 78.0, 78.0, 78.0, 78.0, 78.0),
            "ofic": (390.0, 78.0, 78.0, 78.0, 78.0, 78.0),
            "voto": False,
        },
        # 5. Caso Segunda Opción: No alcanza cupo en Sistemas (ponderado 74.5), pero es admitido en su 2da opción (Matemáticas)
        {
            "orden": 5,
            "doc": "1098700005",
            "nombres": "Nicolás",
            "apellidos": "Pardo Vargas",
            "correo": "nicolas.pardo@correo.uis.edu.co",
            "edad": 18,
            "sisben": "C8",
            "op1": prog_sistemas.id,
            "op2": prog_matematicas.id,
            "snp": "AC2024100005",
            "anio": 2024,
            "decl": (372.0, 72.0, 70.0, 78.0, 74.0, 72.0),
            "ofic": (372.0, 72.0, 70.0, 78.0, 74.0, 72.0),
            "voto": False,
        },
        # 6. Caso Borde Paso 5 (<31 puntos): Obtiene 28.0 en Inglés (< 31 mínimo reglamentario) -> ANULADO_PUNTAJE_MINIMO
        {
            "orden": 6,
            "doc": "1098700006",
            "nombres": "Daniela",
            "apellidos": "Quintero Silva",
            "correo": "daniela.quintero@correo.uis.edu.co",
            "edad": 18,
            "sisben": "A1",
            "op1": prog_medicina.id,
            "op2": None,
            "snp": "AC2024100006",
            "anio": 2024,
            "decl": (355.0, 82.0, 74.0, 76.0, 78.0, 28.0),
            "ofic": (355.0, 82.0, 74.0, 76.0, 78.0, 28.0),
            "voto": False,
        },
        # 7. Caso Borde Paso 5 (Vigencia vencida > 5 años): Examen presentado en 2018 (antigüedad 8 años > 5) -> ANULADO_VIGENCIA_EXAMEN
        {
            "orden": 7,
            "doc": "1098700007",
            "nombres": "Jorge Eliécer",
            "apellidos": "Mantilla Gómez",
            "correo": "jorge.mantilla@correo.uis.edu.co",
            "edad": 25,
            "sisben": "OTROS",
            "op1": prog_medicina.id,
            "op2": None,
            "snp": "AC2018100007",
            "anio": 2018,
            "decl": (410.0, 85.0, 80.0, 82.0, 81.0, 79.0),
            "ofic": (410.0, 85.0, 80.0, 82.0, 81.0, 79.0),
            "voto": True,
        },
        # 8. Caso Borde Paso 4 (Inconsistencia ICFES): Declaró Matemáticas=94.0 y Global=418.0, pero en ICFES tiene Matemáticas=64.0 y Global=340.0
        {
            "orden": 8,
            "doc": "1098700008",
            "nombres": "Andrés Felipe",
            "apellidos": "Mendoza Duarte",
            "correo": "andres.mendoza@correo.uis.edu.co",
            "edad": 19,
            "sisben": "OTROS",
            "op1": prog_derecho.id,
            "op2": None,
            "snp": "AC2024100008",
            "anio": 2024,
            "decl": (418.0, 70.0, 82.0, 94.0, 86.0, 75.0),
            "ofic": (340.0, 70.0, 68.0, 64.0, 69.0, 65.0),
            "voto": False,
        },
        # 9. Admitida Puesto 1 en Medicina
        {
            "orden": 9,
            "doc": "1098700009",
            "nombres": "Mariana",
            "apellidos": "Villamizar Ortiz",
            "correo": "mariana.villamizar@correo.uis.edu.co",
            "edad": 19,
            "sisben": "B1",
            "op1": prog_medicina.id,
            "op2": None,
            "snp": "AC2024100009",
            "anio": 2024,
            "decl": (442.0, 92.0, 84.0, 86.0, 90.0, 85.0),
            "ofic": (442.0, 92.0, 84.0, 86.0, 90.0, 85.0),
            "voto": True,
        },
        # 10. Admitida Puesto 2 en Medicina
        {
            "orden": 10,
            "doc": "1098700010",
            "nombres": "Gabriela",
            "apellidos": "Serrano Cala",
            "correo": "gabriela.serrano@correo.uis.edu.co",
            "edad": 18,
            "sisben": "C2",
            "op1": prog_medicina.id,
            "op2": None,
            "snp": "AC2024100010",
            "anio": 2024,
            "decl": (415.0, 86.0, 80.0, 82.0, 84.0, 80.0),
            "ofic": (415.0, 86.0, 80.0, 82.0, 84.0, 80.0),
            "voto": False,
        },
        # 11. Admitida Puesto 1 en Derecho
        {
            "orden": 11,
            "doc": "1098700011",
            "nombres": "Laura Sofía",
            "apellidos": "Castellanos Niño",
            "correo": "laura.castellanos@correo.uis.edu.co",
            "edad": 20,
            "sisben": "A3",
            "op1": prog_derecho.id,
            "op2": None,
            "snp": "AC2024100011",
            "anio": 2024,
            "decl": (408.0, 74.0, 88.0, 72.0, 90.0, 80.0),
            "ofic": (408.0, 74.0, 88.0, 72.0, 90.0, 80.0),
            "voto": True,
        },
        # 12. No Admitido por agotamiento de cupos en Medicina
        {
            "orden": 12,
            "doc": "1098700012",
            "nombres": "David Alejandro",
            "apellidos": "Rincón Tarazona",
            "correo": "david.rincon@correo.uis.edu.co",
            "edad": 18,
            "sisben": "OTROS",
            "op1": prog_medicina.id,
            "op2": None,
            "snp": "AC2024100012",
            "anio": 2024,
            "decl": (360.0, 72.0, 70.0, 71.0, 73.0, 70.0),
            "ofic": (360.0, 72.0, 70.0, 71.0, 73.0, 70.0),
            "voto": False,
        },
    ]

    archivos_creados: List[str] = []

    for item in definiciones_aspirantes:
        nombre_completo = f"{item['nombres']} {item['apellidos']}"
        num_opciones = 2 if item["op2"] is not None else 1
        liq = liquidar_derechos_inscripcion(item["sisben"], num_opciones=num_opciones)

        pg_d, cn_d, sc_d, mat_d, lc_d, ing_d = item["decl"]
        pg_o, cn_o, sc_o, mat_o, lc_o, ing_o = item["ofic"]

        # Crear registro en MockIcfesOficial
        db.add(
            MockIcfesOficial(
                registro_snp=item["snp"],
                documento_identidad=item["doc"],
                nombres_completos=nombre_completo,
                anio_examen=item["anio"],
                fecha_presentacion=f"{item['anio']}-08-18",
                puntaje_global=pg_o,
                ciencias_naturales=cn_o,
                sociales_ciudadanas=sc_o,
                matematicas=mat_o,
                lectura_critica=lc_o,
                ingles=ing_o,
            )
        )

        # Crear antecedente en MockHistoricoUis si aplica
        if "historico" in item:
            tipo_inh, desc_inh, per_inh = item["historico"]
            db.add(
                MockHistoricoUis(
                    documento_identidad=item["doc"],
                    nombres_completos=nombre_completo,
                    tipo_inhabilidad=tipo_inh,
                    vigente=True,
                    descripcion_causal=desc_inh,
                    periodo_registro=per_inh,
                )
            )

        # Crear Aspirante
        asp = Aspirante(
            orden_inscripcion=item["orden"],
            tipo_documento="CC",
            documento_identidad=item["doc"],
            nombres=item["nombres"],
            apellidos=item["apellidos"],
            correo=item["correo"],
            edad=item["edad"],
            grupo_sisben=item["sisben"],
            programa_opcion_1_id=item["op1"],
            programa_opcion_2_id=item["op2"],
            tarifa_inscripcion_smlmv=liq["total_smlmv"],
            registro_snp=item["snp"],
            anio_examen=item["anio"],
            puntaje_global_declarado=pg_d,
            ciencias_naturales_declarado=cn_d,
            sociales_ciudadanas_declarado=sc_d,
            matematicas_declarado=mat_d,
            lectura_critica_declarado=lc_d,
            ingles_declarado=ing_d,
            nivel_educativo_valido=True,
            certificado_electoral_valido=bool(item["voto"]),
            estado_proceso="INSCRITO",
            causal_decision="Inscrito en convocatoria pregrado UIS. Pendiente de verificación ICFES (Paso 4).",
        )
        asp.append_log(
            "PASO_2_INSCRIPCION",
            f"Inscripción registrada (Turno #{item['orden']}). Tarifa SISBÉN ({liq['categoria_sisben']}): {liq['total_smlmv']} SMLMV.",
        )
        db.add(asp)
        db.flush()

        # Generar PDF real de soporte ICFES Saber 11°
        ruta_pdf_icfes = directorio_soportes / f"icfes_{item['doc']}.pdf"
        generar_pdf_reporte_icfes(
            ruta_destino=ruta_pdf_icfes,
            registro_snp=item["snp"],
            documento=item["doc"],
            nombre_completo=nombre_completo,
            anio=item["anio"],
            puntaje_global=pg_o,
            cn=cn_o,
            sc=sc_o,
            mat=mat_o,
            lc=lc_o,
            ing=ing_o,
        )
        archivos_creados.append(str(ruta_pdf_icfes))
        db.add(
            SoporteDocumental(
                aspirante_id=asp.id,
                tipo_documento="ICFES",
                nombre_archivo=ruta_pdf_icfes.name,
                ruta_archivo=str(ruta_pdf_icfes),
                mime_type="application/pdf",
                es_valido=True,
            )
        )

        # Generar PNG real de Diploma de Bachiller
        ruta_png_diploma = directorio_soportes / f"diploma_{item['doc']}.png"
        generar_png_diploma_bachiller(
            ruta_destino=ruta_png_diploma,
            documento=item["doc"],
            nombre_completo=nombre_completo,
            anio=item["anio"],
        )
        archivos_creados.append(str(ruta_png_diploma))
        db.add(
            SoporteDocumental(
                aspirante_id=asp.id,
                tipo_documento="DIPLOMA_BACHILLER",
                nombre_archivo=ruta_png_diploma.name,
                ruta_archivo=str(ruta_png_diploma),
                mime_type="image/png",
                es_valido=True,
            )
        )

        # Generar PNG real de Certificado Electoral si el aspirante adjuntó voto
        if item["voto"]:
            ruta_png_voto = directorio_soportes / f"certificado_electoral_{item['doc']}.png"
            generar_png_certificado_electoral(
                ruta_destino=ruta_png_voto,
                documento=item["doc"],
                nombre_completo=nombre_completo,
            )
            archivos_creados.append(str(ruta_png_voto))
            db.add(
                SoporteDocumental(
                    aspirante_id=asp.id,
                    tipo_documento="CERTIFICADO_ELECTORAL",
                    nombre_archivo=ruta_png_voto.name,
                    ruta_archivo=str(ruta_png_voto),
                    mime_type="image/png",
                    es_valido=True,
                )
            )

    db.commit()

    # 3. Cargar los 20 aspirantes y 40 soportes reales de seed_docs/simpledocs/
    res_simpledocs = cargar_aspirantes_simpledocs(
        db=db,
        prog_op1_id=prog_industrial.id,
        prog_op2_id=prog_civil.id,
        directorio_simpledocs=directorio_soportes / "simpledocs"
        if (directorio_soportes / "simpledocs").exists()
        else SIMPLEDOCS_DIR,
        orden_inicial=len(definiciones_aspirantes) + 1,
    )

    return {
        "programas_creados": 6,
        "aspirantes_creados": len(definiciones_aspirantes) + res_simpledocs["aspirantes_simpledocs_creados"],
        "aspirantes_base": len(definiciones_aspirantes),
        "aspirantes_simpledocs": res_simpledocs["aspirantes_simpledocs_creados"],
        "archivos_soportes_generados": len(archivos_creados) + res_simpledocs["soportes_simpledocs_registrados"],
        "directorio_soportes": str(directorio_soportes),
    }


def cargar_aspirantes_simpledocs(
    db: Session,
    prog_op1_id: int,
    prog_op2_id: Optional[int] = None,
    directorio_simpledocs: Path = SIMPLEDOCS_DIR,
    orden_inicial: int = 13,
) -> Dict[str, Any]:
    """Carga los 20 aspirantes de DatosAspirantes.xlsx y vincula sus 20 PDFs ICFES y 20 JPGs de Diploma."""
    ruta_xlsx = directorio_simpledocs / "DatosAspirantes.xlsx"
    registros_xlsx = leer_datos_aspirantes_xlsx(ruta_xlsx)
    if not registros_xlsx:
        return {"aspirantes_simpledocs_creados": 0, "soportes_simpledocs_registrados": 0}

    grupos_sisben_ciclo = ["A2", "B1", "B4", "C3", "C7", "A3", "B2", "C1", "B5", "OTROS"]
    aspirantes_creados = 0
    soportes_registrados = 0

    for reg in registros_xlsx:
        idx = reg["indice_simpledocs"]
        orden = orden_inicial + idx - 1
        sisben = grupos_sisben_ciclo[(idx - 1) % len(grupos_sisben_ciclo)]
        num_opciones = 2 if prog_op2_id is not None else 1
        liq = liquidar_derechos_inscripcion(sisben, num_opciones=num_opciones)

        # Buscar archivos de soporte en seed_docs/simpledocs/
        archivos_pdf = sorted(directorio_simpledocs.glob(f"{idx} AC*.pdf"))
        ruta_pdf = archivos_pdf[0] if archivos_pdf else None
        ruta_jpg = directorio_simpledocs / f"{idx} Diploma.jpg"

        # Verificar si el PDF adjunto corresponde al SNP declarado por el aspirante
        snp_en_nombre_pdf = ""
        if ruta_pdf is not None:
            m_snp = re.search(r"\b(AC\d{10,14})\b", ruta_pdf.name)
            if m_snp:
                snp_en_nombre_pdf = m_snp.group(1)

        # Poblar MockIcfesOficial cuando el certificado PDF oficial coincide con el SNP del aspirante (#02..#20)
        if snp_en_nombre_pdf and snp_en_nombre_pdf == reg["registro_snp"]:
            ya_existe_snp = (
                db.query(MockIcfesOficial)
                .filter(MockIcfesOficial.registro_snp == reg["registro_snp"])
                .first()
            )
            if not ya_existe_snp:
                db.add(
                    MockIcfesOficial(
                        registro_snp=reg["registro_snp"],
                        documento_identidad=reg["documento_identidad"],
                        nombres_completos=reg["nombre_completo"],
                        anio_examen=reg["anio_examen"],
                        fecha_presentacion=f"{reg['anio_examen']}-07-26",
                        puntaje_global=reg["puntaje_global"],
                        ciencias_naturales=reg["ciencias_naturales"],
                        sociales_ciudadanas=reg["sociales_ciudadanas"],
                        matematicas=reg["matematicas"],
                        lectura_critica=reg["lectura_critica"],
                        ingles=reg["ingles"],
                    )
                )

        # Construir correo institucional de contacto
        slug_correo = re.sub(
            r"[^a-z0-9]+",
            ".",
            reg["nombre_completo"]
            .lower()
            .translate(str.maketrans("áéíóúñü", "aeiounu")),
        ).strip(".")
        correo = f"{slug_correo}.{idx}@aspirante.uis.edu.co"

        asp = Aspirante(
            orden_inscripcion=orden,
            tipo_documento=reg["tipo_documento"],
            documento_identidad=reg["documento_identidad"],
            nombres=reg["nombres"],
            apellidos=reg["apellidos"],
            correo=correo,
            edad=reg["edad"],
            grupo_sisben=sisben,
            programa_opcion_1_id=prog_op1_id,
            programa_opcion_2_id=prog_op2_id,
            tarifa_inscripcion_smlmv=liq["total_smlmv"],
            registro_snp=reg["registro_snp"],
            anio_examen=reg["anio_examen"],
            puntaje_global_declarado=reg["puntaje_global"],
            ciencias_naturales_declarado=reg["ciencias_naturales"],
            sociales_ciudadanas_declarado=reg["sociales_ciudadanas"],
            matematicas_declarado=reg["matematicas"],
            lectura_critica_declarado=reg["lectura_critica"],
            ingles_declarado=reg["ingles"],
            nivel_educativo_valido=True,
            certificado_electoral_valido=False,
            estado_proceso="INSCRITO",
            causal_decision=(
                f"Inscrito desde lote documental simpledocs ({reg['ciudad_residencia']}). "
                "Pendiente de verificación ICFES (Paso 4)."
            ),
        )
        asp.append_log(
            "PASO_2_INSCRIPCION",
            f"Inscripción registrada desde DatosAspirantes.xlsx (Turno #{orden}, Lote simpledocs #{idx}). "
            f"Ciudad: {reg['ciudad_residencia']}. Tarifa SISBÉN ({liq['categoria_sisben']}): {liq['total_smlmv']} SMLMV.",
        )
        db.add(asp)
        db.flush()
        aspirantes_creados += 1

        if ruta_pdf is not None and ruta_pdf.exists():
            db.add(
                SoporteDocumental(
                    aspirante_id=asp.id,
                    tipo_documento="ICFES",
                    nombre_archivo=ruta_pdf.name,
                    ruta_archivo=f"seed_docs/simpledocs/{ruta_pdf.name}",
                    mime_type="application/pdf",
                    es_valido=True,
                )
            )
            soportes_registrados += 1

        if ruta_jpg.exists():
            db.add(
                SoporteDocumental(
                    aspirante_id=asp.id,
                    tipo_documento="DIPLOMA_BACHILLER",
                    nombre_archivo=ruta_jpg.name,
                    ruta_archivo=f"seed_docs/simpledocs/{ruta_jpg.name}",
                    mime_type="image/jpeg",
                    es_valido=True,
                )
            )
            soportes_registrados += 1

    db.commit()
    return {
        "aspirantes_simpledocs_creados": aspirantes_creados,
        "soportes_simpledocs_registrados": soportes_registrados,
    }
