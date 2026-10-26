"""Generador de datos semilla y soportes documentales reales en PDF e imagen (PNG) para demostración DARA."""

from pathlib import Path
from typing import Any, Dict, List
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
    db.add_all([prog_sistemas, prog_medicina, prog_derecho, prog_matematicas])
    db.commit()
    for p in (prog_sistemas, prog_medicina, prog_derecho, prog_matematicas):
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
    return {
        "programas_creados": 4,
        "aspirantes_creados": len(definiciones_aspirantes),
        "archivos_soportes_generados": len(archivos_creados),
        "directorio_soportes": str(directorio_soportes),
    }
