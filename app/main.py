import os
import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# Inicializar la aplicación Flask
# Flask buscará automáticamente las carpetas 'templates' y 'static' en el mismo directorio
app = Flask(__name__)

# Habilitar CORS (Cross-Origin Resource Sharing)
CORS(app)

# ==========================================
# ⚙️ CONFIGURACIÓN DE BASE DE DATOS
# ==========================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "tfm_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")  # se define en el archivo .env (no versionado)

def get_db_connection():
    """Establece y retorna la conexión a PostgreSQL usando psycopg2."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"❌ Error conectando a PostgreSQL: {e}")
        return None

def serialize_data(data):
    """
    Recorre recursivamente los datos devueltos por la BD y convierte
    los objetos de tipo fecha/hora a cadenas ISO 8601.
    """
    if isinstance(data, list):
        return [serialize_data(item) for item in data]
    elif isinstance(data, dict):
        return {key: serialize_data(value) for key, value in data.items()}
    elif isinstance(data, (datetime.datetime, datetime.date, datetime.time)):
        return data.isoformat()
    return data

# ==========================================
# 🌐 RUTAS DE LA APLICACIÓN (VIEWS HTML)
# ==========================================

@app.route('/')
def home():
    """Renderiza el Home / Dashboard principal con información viva."""
    conn = get_db_connection()
    kpis = {
        "fecha": datetime.date.today().strftime("%Y-%m-%d"),
        "semana": datetime.date.today().isocalendar()[1],
        "rampa": 0,
        "combustion": 0,
        "soporte": 0,
        "horno": 0,
        "espartallama": 0,
        "total_en_proceso": 0,
        "personal_laborando": 0,
        "maquinas_funcionando": 0,
        "maquinas_paradas": 0,
        "anomalias_detectadas": 0
    }
    active_items = []
    
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Obtener la última fecha de ejecuciones en el sistema como referencia de "hoy" en la base de datos
                cur.execute("SELECT MAX(ejecucion_fecha_inicio::date) FROM fact_ejecuciones")
                max_date_row = cur.fetchone()
                ref_date = max_date_row['max'] if max_date_row and max_date_row['max'] else datetime.date.today()
                
                # Formatear la fecha y semana del dashboard basado en los datos
                kpis["fecha"] = ref_date.strftime("%d/%m/%Y")
                kpis["semana"] = ref_date.isocalendar()[1]
                
                # 2. Contar elementos en proceso (Estado 2=En Progreso, 3=Pausado) para la fecha de referencia
                cur.execute("""
                    SELECT 
                        SUM(CASE WHEN c.componente_nombre ILIKE '%%rampa%%' THEN 1 ELSE 0 END) as rampa,
                        SUM(CASE WHEN c.componente_nombre ILIKE '%%combustion%%' THEN 1 ELSE 0 END) as combustion,
                        SUM(CASE WHEN c.componente_nombre ILIKE '%%soporte%%' THEN 1 ELSE 0 END) as soporte,
                        SUM(CASE WHEN c.componente_nombre ILIKE '%%horno%%' THEN 1 ELSE 0 END) as horno,
                        SUM(CASE WHEN c.componente_nombre ILIKE '%%espartallama%%' THEN 1 ELSE 0 END) as espartallama,
                        COUNT(*) as total
                    FROM fact_ejecuciones f
                    JOIN dim_componente c ON f.componente_id_bd = c.componente_id_bd
                    WHERE f.ejecucion_fecha_inicio::date = %s
                      AND f.ejecucion_estado IN (2, 3)
                """, (ref_date,))
                counts = cur.fetchone()
                if counts:
                    kpis["rampa"] = counts["rampa"] or 0
                    kpis["combustion"] = counts["combustion"] or 0
                    kpis["soporte"] = counts["soporte"] or 0
                    kpis["horno"] = counts["horno"] or 0
                    kpis["espartallama"] = counts["espartallama"] or 0
                    kpis["total_en_proceso"] = counts["total"] or 0
                
                # 3. Personal laborando (Operadores activos hoy)
                cur.execute("""
                    SELECT COUNT(DISTINCT operador_id_bd) as count 
                    FROM fact_ejecuciones 
                    WHERE ejecucion_fecha_inicio::date = %s 
                      AND ejecucion_estado IN (2, 3)
                """, (ref_date,))
                op_row = cur.fetchone()
                kpis["personal_laborando"] = op_row["count"] if op_row else 0
                
                # 4. Máquinas funcionando vs paradas
                cur.execute("""
                    SELECT COUNT(DISTINCT estacion_id_bd) as count 
                    FROM fact_ejecuciones 
                    WHERE ejecucion_fecha_inicio::date = %s 
                      AND ejecucion_estado IN (2, 3)
                """, (ref_date,))
                st_active_row = cur.fetchone()
                active_st = st_active_row["count"] if st_active_row else 0
                
                cur.execute("SELECT COUNT(*) as count FROM dim_estacion")
                st_total_row = cur.fetchone()
                total_st = st_total_row["count"] if st_total_row else 0
                
                kpis["maquinas_funcionando"] = active_st
                kpis["maquinas_paradas"] = max(0, total_st - active_st)
                
                # 5. Anomalías detectadas hoy
                cur.execute("""
                    SELECT COUNT(*) as count 
                    FROM fact_ejecuciones f 
                    JOIN historicos_iqr h ON f.id = h.id 
                    WHERE f.ejecucion_fecha_inicio::date = %s 
                      AND h.es_anomalidad = 1
                """, (ref_date,))
                anom_row = cur.fetchone()
                kpis["anomalias_detectadas"] = anom_row["count"] if anom_row else 0
                
                # 6. Listado detallado de piezas en proceso para interactividad (clic en categorías)
                cur.execute("""
                    SELECT 
                        c.componente_codigo_interno as codigo,
                        c.componente_nombre as nombre,
                        op.operacion_nombre as proceso,
                        o.operador_alias as operador,
                        f.ejecucion_estado as estado_id,
                        f.ejecucion_estado_descripcion as estado,
                        COALESCE(est.estacion_alias, est.estacion_nombre, 'N/A') as estacion,
                        COALESCE(h.es_anomalidad, 0) as es_anomalidad,
                        COALESCE(h.nota_calidad, '') as nota_calidad
                    FROM fact_ejecuciones f
                    JOIN dim_componente c ON f.componente_id_bd = c.componente_id_bd
                    JOIN dim_operacion op ON f.operacion_id_bd = op.operacion_id_bd
                    JOIN dim_operador o ON f.operador_id_bd = o.operador_id_bd
                    LEFT JOIN dim_estacion est ON f.estacion_id_bd = est.estacion_id_bd
                    LEFT JOIN historicos_iqr h ON f.id = h.id
                    WHERE f.ejecucion_fecha_inicio::date = %s
                      AND (f.ejecucion_estado IN (2, 3) OR h.es_anomalidad = 1)
                    ORDER BY c.componente_nombre
                """, (ref_date,))
                active_items = cur.fetchall()
                
        except Exception as e:
            print(f"❌ Error al consultar KPIs del Home: {e}")
        finally:
            conn.close()

    return render_template('index.html', kpis=kpis, active_items=serialize_data(active_items))

@app.route('/produccion')
def produccion():
    """Página de Monitoreo en planta (Gantt Operarios)"""
    return render_template('produccion.html')

@app.route('/planificacion')
def planificacion():
    """Página de Explosión de tiempos y Pedidos"""
    return render_template('planificacion.html')

@app.route('/registros')
def registros():
    """Vista general de registros históricos"""
    return render_template('registros.html')

@app.route('/estandares')
def estandares():
    """Visualización de la tabla de estándares calculados"""
    return render_template('estandares.html')

@app.route('/vistas')
def vistas():
    """Página de administración de vistas y consultas SQL"""
    return render_template('vistas.html')

@app.route('/trazabilidad')
def trazabilidad():
    """Página de Trazabilidad de Productos"""
    return render_template('trazabilidad.html')

@app.route('/explorador')
def explorador():
    """Explorador de Datos y Diccionarios"""
    return render_template('explorador.html')

# ==========================================
# 🔌 ENDPOINTS API REST (DATOS JSON)
# ==========================================

@app.route('/api/productos', methods=['GET'])
def api_productos():
    """Retorna la lista de productos únicos (código interno y descripción)."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT codigo_interno_pieza, descripcion_pieza 
                FROM tabla_estandares 
                WHERE codigo_interno_pieza IS NOT NULL AND codigo_interno_pieza != ''
                ORDER BY codigo_interno_pieza
            """)
            resultados = cur.fetchall()
        return jsonify(serialize_data(resultados)), 200
    except Exception as e:
        print(f"❌ Error en /api/productos: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/estandares/producto/<codigo>', methods=['GET'])
def api_estandares_producto(codigo):
    """Retorna los procesos y estándares de producción de un producto específico."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT proceso, promedio_ciclo_piezas_hora 
                FROM tabla_estandares 
                WHERE codigo_interno_pieza = %s
                ORDER BY proceso
            """, (codigo,))
            resultados = cur.fetchall()
        return jsonify(serialize_data(resultados)), 200
    except Exception as e:
        print(f"❌ Error en /api/estandares/producto: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/produccion/gantt', methods=['GET'])
def api_produccion_gantt():
    """
    Endpoint 1: Retorna los datos operativos para el Diagrama de Gantt.
    Ejecuta un SELECT a la vista en tiempo real.
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
        
    try:
        # RealDictCursor permite que fetchall devuelva una lista de diccionarios
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM v_gantt_produccion_tiempo_real ORDER BY operador_alias, fecha_inicio"
            cur.execute(query)
            resultados = cur.fetchall()
            
        # Serializamos las fechas a formato ISO antes de enviar el JSON
        datos_formateados = serialize_data(resultados)
        return jsonify(datos_formateados), 200
        
    except Exception as e:
        print(f"❌ Error en /api/produccion/gantt: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/registros', methods=['GET'])
def api_registros():
    """
    Endpoint 2: Retorna el historial completo de ejecuciones.
    Cruza fact_ejecuciones con historicos_iqr.
    """
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
        
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Query que cruza la tabla de hechos con los límites IQR
            query = """
                SELECT 
                    f.*, 
                    i.limite_inferior, 
                    i.mediana AS tiempo_estandar_iqr, 
                    i.limite_superior 
                FROM fact_ejecuciones f
                LEFT JOIN historicos_iqr i 
                    ON f.id_producto = i.id_producto AND f.id_proceso = i.id_proceso
                ORDER BY f.fecha_inicio DESC
                LIMIT 500 -- Límite de seguridad
            """
            cur.execute(query)
            resultados = cur.fetchall()
            
        # Serializamos las fechas a formato ISO
        datos_formateados = serialize_data(resultados)
        return jsonify(datos_formateados), 200
        
    except Exception as e:
        print(f"❌ Error en /api/registros: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/registros/auditoria', methods=['GET'])
def api_registros_auditoria():
    """Endpoint para la auditoría de registros históricos con filtros."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
        
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    solo_anomalias = request.args.get('solo_anomalias')
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM v_registros_historicos WHERE 1=1"
            params = []
            
            if fecha_inicio:
                query += " AND fecha >= %s"
                params.append(fecha_inicio)
                
            if fecha_fin:
                query += " AND fecha <= %s"
                params.append(fecha_fin)
                
            if solo_anomalias == 'true':
                query += " AND es_anomalidad = 1"
                
            query += " ORDER BY fecha DESC, hora_inicio DESC LIMIT 2000"
            
            cur.execute(query, tuple(params))
            resultados = cur.fetchall()
            
        return jsonify(serialize_data(resultados)), 200
        
    except Exception as e:
        print(f"❌ Error en /api/registros/auditoria: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/registros/update/<int:record_id>', methods=['POST'])
def api_registros_update(record_id):
    """Actualiza los parámetros de un registro histórico en la BD."""
    data = request.get_json() or {}
    
    operador_id_bd = data.get('operador_id_bd')
    componente_id_bd = data.get('componente_id_bd')
    operacion_id_bd = data.get('operacion_id_bd')
    hora_inicio = data.get('hora_inicio')
    piezas_buenas = data.get('piezas_buenas')
    duracion_horas = data.get('duracion_horas')
    es_anomalidad = data.get('es_anomalidad', 0)
    nota_calidad = data.get('nota_calidad', '')

    # Validaciones básicas
    if not all([operador_id_bd, componente_id_bd, operacion_id_bd, hora_inicio]):
        return jsonify({"error": "Faltan parámetros requeridos (operador, pieza, proceso, hora de inicio)"}), 400

    try:
        piezas_buenas = float(piezas_buenas) if piezas_buenas is not None else 0.0
        duracion_horas = float(duracion_horas) if duracion_horas is not None else 0.0
        es_anomalidad = int(es_anomalidad)
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Valores numéricos inválidos: {e}"}), 400

    # Calcular ritmo real: piezas_buenas / duracion_horas
    ciclo_piezas_hora = piezas_buenas / duracion_horas if duracion_horas > 0 else 0.0

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500

    try:
        with conn.cursor() as cur:
            # 1. Actualizar fact_ejecuciones
            cur.execute("""
                UPDATE fact_ejecuciones
                SET operador_id_bd = %s,
                    componente_id_bd = %s,
                    operacion_id_bd = %s,
                    ejecucion_fecha_inicio = %s,
                    ejecucion_fecha_fin = %s::timestamp + %s * INTERVAL '1 hour'
                WHERE id = %s
            """, (operador_id_bd, componente_id_bd, operacion_id_bd, hora_inicio, hora_inicio, duracion_horas, record_id))

            if cur.rowcount == 0:
                return jsonify({"error": f"El registro con ID {record_id} no existe en fact_ejecuciones"}), 404

            # 2. Actualizar o insertar en historicos_iqr
            cur.execute("""
                INSERT INTO historicos_iqr (id, piezas_buenas, duracion_horas, ciclo_piezas_hora, es_anomalidad, nota_calidad)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET piezas_buenas = EXCLUDED.piezas_buenas,
                    duracion_horas = EXCLUDED.duracion_horas,
                    ciclo_piezas_hora = EXCLUDED.ciclo_piezas_hora,
                    es_anomalidad = EXCLUDED.es_anomalidad,
                    nota_calidad = EXCLUDED.nota_calidad
            """, (record_id, piezas_buenas, duracion_horas, ciclo_piezas_hora, es_anomalidad, nota_calidad))

            conn.commit()
        return jsonify({"success": True, "message": "Registro actualizado correctamente"}), 200
    except Exception as e:
        conn.rollback()
        print(f"❌ Error actualizando registro {record_id}: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/trazabilidad/gantt', methods=['GET'])
def api_trazabilidad_gantt():
    """Endpoint para el Gantt de trazabilidad de producto con filtro de fechas."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500

    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM v_gantt_trazabilidad_producto WHERE 1=1"
            params = []
            if fecha_inicio:
                query += " AND fecha_inicio >= %s"
                params.append(fecha_inicio)
            if fecha_fin:
                query += " AND fecha_fin <= %s"
                params.append(fecha_fin + ' 23:59:59')
            query += " ORDER BY codigo_pieza, fase_proceso, fecha_inicio LIMIT 5000"
            cur.execute(query, tuple(params))
            resultados = cur.fetchall()

        return jsonify(serialize_data(resultados)), 200

    except Exception as e:
        print(f"❌ Error en /api/trazabilidad/gantt: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/explorar/<nombre_tabla>', methods=['GET'])
def api_explorar(nombre_tabla):
    """Endpoint Dinámico para explorar tablas permitidas."""
    tablas_permitidas = [
        'dim_operador', 'dim_componente', 'dim_estacion', 
        'dim_operacion', 'dim_orden', 'historicos_iqr', 
        'tabla_estandares', 'fact_ejecuciones'
    ]
    
    if nombre_tabla not in tablas_permitidas:
        return jsonify({"error": "Tabla no permitida por seguridad"}), 403
        
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
        
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Query segura ya que el input ha sido validado contra la whitelist
            query = f"SELECT * FROM {nombre_tabla}"
            cur.execute(query)
            resultados = cur.fetchall()
            
        return jsonify(serialize_data(resultados)), 200
        
    except Exception as e:
        print(f"❌ Error en /api/explorar/{nombre_tabla}: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/estandares/datos', methods=['GET'])
def api_estandares_datos():
    """Endpoint para obtener todos los datos de la tabla de estándares."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
        
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM tabla_estandares ORDER BY codigo_interno_pieza, proceso")
            resultados = cur.fetchall()
            
        return jsonify(serialize_data(resultados)), 200
        
    except Exception as e:
        print(f"❌ Error en /api/estandares/datos: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/estandares/kpis', methods=['GET'])
def api_estandares_kpis():
    """Endpoint para obtener KPIs agregados de la tabla de estándares."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No se pudo conectar a la base de datos"}), 500
        
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
            SELECT 
                COUNT(DISTINCT proceso) AS total_procesos_unicos,
                AVG(promedio_ciclo_piezas_hora) AS promedio_global_ciclo,
                SUM(cuantos_invalidos) AS total_muestras_invalidas
            FROM tabla_estandares
            """
            cur.execute(query)
            resultado = cur.fetchone()
            
        return jsonify(serialize_data(resultado)), 200
        
    except Exception as e:
        print(f"❌ Error en /api/estandares/kpis: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# ==========================================
# 🚀 EJECUCIÓN DEL SERVIDOR
# ==========================================
if __name__ == '__main__':
    print("\n" + "=" * 60)
    print(">>> INICIANDO SERVIDOR MES INDUSTRIAL <<<")
    print("=" * 60)
    print("--> URL de acceso local: http://localhost:5000")
    print(f"--> Base de datos PostgreSQL: {DB_HOST}:{DB_PORT} ({DB_NAME})")
    print("=" * 60 + "\n")
    
    # Inicia el servidor en modo debug para auto-recarga en desarrollo
    app.run(host='0.0.0.0', port=5000, debug=True)
