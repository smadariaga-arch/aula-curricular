from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
import os
import urllib.request

app = FastAPI(title="AulaCurricular API")

# Permitir peticiones desde el Frontend (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "curriculo_escolar.db"

# --- 1. INICIALIZACIÓN DE BASE DE DATOS Y DATOS DE PRUEBA (3° BÁSICO HISTORIA) ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Creación de Tablas
    cursor.execute('''CREATE TABLE IF NOT EXISTS cursos (id INTEGER PRIMARY KEY, nombre TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS asignaturas (id INTEGER PRIMARY KEY, curso_id INT, nombre TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS unidades (id INTEGER PRIMARY KEY, asignatura_id INT, numero INT, titulo TEXT, descripcion TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS vocabulario (id INTEGER PRIMARY KEY, unidad_id INT, palabra TEXT, definicion TEXT)''')

    # Poblar si está vacía
    cursor.execute("SELECT COUNT(*) FROM cursos")
    if cursor.fetchone()[0] == 0:
        # Cursos
        cursor.execute("INSERT INTO cursos (id, nombre) VALUES (1, '3° Básico')")
        cursor.execute("INSERT INTO cursos (id, nombre) VALUES (2, '4° Básico')")

        # Asignaturas
        cursor.execute("INSERT INTO asignaturas (id, curso_id, nombre) VALUES (1, 1, 'Historia, Geografía y C. Sociales')")
        cursor.execute("INSERT INTO asignaturas (id, curso_id, nombre) VALUES (2, 1, 'Ciencias Naturales')")

        # Unidades para 3° Básico Historia
        cursor.execute("INSERT INTO unidades (id, asignatura_id, numero, titulo, descripcion) VALUES (1, 1, 1, 'Grecia y Roma en la Antigüedad', 'Legado de las civilizaciones clásica en la vida cotidiana moderna.')")
        cursor.execute("INSERT INTO unidades (id, asignatura_id, numero, titulo, descripcion) VALUES (2, 1, 2, 'Pueblos Originarios de Chile', 'Modos de vida nómada y sedentario de los ancestros locales.')")

        # Vocabulario de la Unidad 1 (Grecia y Roma)
        vocabs_u1 = [
            ("Acrópolis", "Recinto fortificado en la cima de las ciudades griegas."),
            ("Democracia", "Sistema de gobierno donde los ciudadanos participan."),
            ("Politeísta", "Creencia en múltiples dioses o divinidades."),
            ("Patricio", "Miembro de la clase social alta e influyente en la antigua Roma."),
            ("Foro", "Plaza pública donde se realizaba el comercio y los debates.")
        ]
        for p, d in vocabs_u1:
            cursor.execute("INSERT INTO vocabulario (unidad_id, palabra, definicion) VALUES (1, ?, ?)", (p, d))

        # Vocabulario de la Unidad 2 (Pueblos Originarios)
        vocabs_u2 = [
            ("Nómada", "Grupo humano que se desplaza continuamente sin asentamiento fijo."),
            ("Sedentario", "Comunidad establecida de forma permanente en un lugar."),
            ("Trueque", "Intercambio de bienes o servicios sin uso de dinero."),
            ("Pucará", "Fortificación de piedra construida por pueblos andinos.")
        ]
        for p, d in vocabs_u2:
            cursor.execute("INSERT INTO vocabulario (unidad_id, palabra, definicion) VALUES (2, ?, ?)", (p, d))

    conn.commit()
    conn.close()

init_db()

# --- 2. ENDPOINTS DE CONSULTA CURRICULAR ---

@app.get("/api/cursos")
def get_cursos():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM cursos")
    res = [{"id": r[0], "nombre": r[1]} for r in cursor.fetchall()]
    conn.close()
    return res

@app.get("/api/cursos/{curso_id}/asignaturas")
def get_asignaturas(curso_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM asignaturas WHERE curso_id = ?", (curso_id,))
    res = [{"id": r[0], "nombre": r[1]} for r in cursor.fetchall()]
    conn.close()
    return res

@app.get("/api/asignaturas/{asig_id}/unidades")
def get_unidades(asig_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, numero, titulo, descripcion FROM unidades WHERE asignatura_id = ?", (asig_id,))
    res = [{"id": r[0], "numero": r[1], "titulo": r[2], "descripcion": r[3]} for r in cursor.fetchall()]
    conn.close()
    return res

@app.get("/api/unidades/{unidad_id}/vocabulario")
def get_vocabulario(unidad_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT palabra, definicion FROM vocabulario WHERE unidad_id = ?", (unidad_id,))
    res = [{"palabra": r[0], "definicion": r[1]} for r in cursor.fetchall()]
    conn.close()
    return res

# --- 3. ENDPOINT PARA GENERAR LECTURA CON IA Y CURRÍCULO ---

class GenerarLecturaRequest(BaseModel):
    unidad_id: int
    api_key: str

@app.post("/api/generar-lectura")
def generar_lectura(req: GenerarLecturaRequest):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Obtener detalles de la unidad, asignatura y curso
    cursor.execute("""
        SELECT c.nombre, a.nombre, u.titulo, u.descripcion 
        FROM unidades u
        JOIN asignaturas a ON u.asignatura_id = a.id
        JOIN cursos c ON a.curso_id = c.id
        WHERE u.id = ?
    """, (req.unidad_id,))
    unidad_info = cursor.fetchone()
    
    if not unidad_info:
        conn.close()
        raise HTTPException(status_code=404, detail="Unidad no encontrada")
        
    curso, asignatura, titulo_unidad, desc_unidad = unidad_info

    # Obtener palabras de vocabulario
    cursor.execute("SELECT palabra, definicion FROM vocabulario WHERE unidad_id = ?", (req.unidad_id,))
    vocab_list = cursor.fetchall()
    conn.close()

    palabras_txt = ", ".join([f"'{v[0]}' ({v[1]})" for v in vocab_list])

    # Construir Prompt con los datos de la Base de Datos
    prompt_system = f"""Eres un pedagogo experto en literatura infantil y currículo escolar.
Crea un texto narrativo de lectura para el curso {curso} en la asignatura {asignatura}.

DATOS CURRICULARES OBLIGATORIOS:
- Unidad: {titulo_unidad}
- Aprendizaje Clave: {desc_unidad}
- PALABRAS DE VOCABULARIO QUE DEBES INCLUIR EN EL TEXTO (destácalas en **negrita**):
  {palabras_txt}

REGLAS ESTRUCTURALES:
1. Longitud exacta: Entre 450 y 500 palabras (duración: 3.5 min de lectura en voz alta).
2. Tono: Entretenido, claro, narrativo y adaptado para estudiantes de {curso}.
3. Formato de respuesta JSON estricto:
{{
  "titulo": "Título de la lectura",
  "parrafos": ["Párrafo 1...", "Párrafo 2...", "Párrafo 3...", "Párrafo 4..."],
  "preguntas": ["Pregunta de debate 1?", "Pregunta de debate 2?"]
}}"""

    # Llamada directa a OpenAI via REST API
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {req.api_key}"
    }
    
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": "Genera la lectura basada exactamente en la unidad y el vocabulario entregado."}
        ],
        "temperature": 0.6,
        "response_format": {"type": "json_object"}
    }

    try:
        req_obj = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req_obj) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            lectura_json = json.loads(res_data["choices"][0]["message"]["content"])
            
            return {
                "curso": curso,
                "asignatura": asignatura,
                "unidad": titulo_unidad,
                "vocabulario_utilizado": [v[0] for v in vocab_list],
                "contenido": lectura_json
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando texto con IA: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
