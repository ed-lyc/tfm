import os
import sys
import re
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Evitar errores de codificación de caracteres en Windows (emojis)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# NOTA (confidencialidad): la ingesta de los exportables operativos de origen se realiza
# fuera de este repositorio por razones de confidencialidad industrial. El pipeline
# versionado parte del conjunto de datos sintetico generado por simula_operaciones.py
# (ver PASO 0 en ejecutar_automatizacion()).






# 1. Cargar configuración de base de datos
load_dotenv()
DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
CSV_HECHOS_PATH = "data/raw/operaciones_simuladas.csv"


def normalizar_columnas(df):
    """
    Normaliza idénticamente a tu script original.
    Quita tildes, espacios por guiones bajos y remueve caracteres extraños.
    """
    nuevas_columnas = []
    for col in df.columns:
        c = str(col).lower().strip()
        c = re.sub(r'[áàäâ]', 'a', c)
        c = re.sub(r'[éèëê]', 'e', c)
        c = re.sub(r'[íìïî]', 'i', c)
        c = re.sub(r'[óòöô]', 'o', c)
        c = re.sub(r'[úùüû]', 'u', c)
        c = re.sub(r'[ñ]', 'n', c)
        c = re.sub(r'[^a-z0-9_]', '_', c)
        c = re.sub(r'_+', '_', c).strip('_')
        nuevas_columnas.append(c)
    df.columns = nuevas_columnas
    return df

def ejecutar_automatizacion():
    # === PASO 0: REGENERAR DATOS SIMULADOS ===
    print("[Actualizacion] Generando dataset estocastico operaciones_simuladas.csv...")
    try:
        import subprocess
        import sys
        script_simula = os.path.join(os.path.dirname(__file__), "simula_operaciones.py")
        subprocess.run([sys.executable, script_simula], check=True)
        print("[Actualizacion] Simulacion finalizada y operaciones_simuladas.csv regenerado.")
    except Exception as e:
        print(f"[Actualizacion] Advertencia al ejecutar simula_operaciones.py: {str(e)}")
        print("Se continuara usando el archivo operaciones_simuladas.csv existente.")

    engine = create_engine(DATABASE_URL)
    
    # === PASO 1: CARGAR HECHOS EN BRUTO (CAPA STAGING) ===
    print("⏳ 1/3: Leyendo y subiendo nueva tabla de hechos raw...")
    try:
        df = pd.read_csv(CSV_HECHOS_PATH, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_HECHOS_PATH, encoding='latin1')
        
    # Limpieza de columnas fantasmas del CSV
    df = df.loc[:, ~df.columns.str.contains('^Unnamed', case=False)]
    df = normalizar_columnas(df)
    
    # Inyectar a la base de datos reemplazando la versión anterior
    df.to_sql(name='raw_operaciones', con=engine, if_exists='replace', index=False, chunksize=5000)
    print("✅ Hechos cargados exitosamente en la tabla 'raw_operaciones'.")

    # === PASO 2: AUTOMATIZAR DIMENSIONES EN POSTGRESQL (UPSERT INCREMENTAL) ===
    print("🔄 2/3: Sincronizando dimensiones de forma incremental en PostgreSQL...")
    
    sql_dimensiones = """
    -- Asegurar restricciones UNIQUE en las llaves primarias/de negocio para soportar el ON CONFLICT
    -- (Las restricciones ya fueron creadas en ejecuciones anteriores)
    -- ALTER TABLE dim_componente ADD CONSTRAINT unq_componente_id UNIQUE (componente_id_bd);
    -- ALTER TABLE dim_operador ADD CONSTRAINT unq_operador_id UNIQUE (operador_id_bd);
    -- ALTER TABLE dim_operacion ADD CONSTRAINT unq_operacion_id UNIQUE (operacion_id_bd);

    -- A. Insertar componentes nuevos del CSV si no existen en la dimensión
    INSERT INTO dim_componente (
        componente_id_bd, componente_codigo_interno, componente_nombre, 
        componente_medida, componente_familia_codigo, componente_familia_nombre, 
        componente_categoria_codigo, componente_categoria_nombre
    )
    SELECT DISTINCT 
        componente_id_bd, componente_codigo_interno, componente_nombre, 
        componente_medida, componente_familia_codigo, componente_familia_nombre, 
        componente_catetoria_codigo, componente_catetoria_nombre -- Mapeado del error del CSV original
    FROM raw_operaciones
    ON CONFLICT (componente_id_bd) DO NOTHING;

    -- B. Insertar operadores nuevos del CSV si no existen en la dimensión
    -- Dejamos 'seccion_planta' sin tocar para no sobreescribir tus cargas manuales de usuarios
    INSERT INTO dim_operador (operador_id_bd, operador_codigo_interno, operador_nombre, operador_alias)
    SELECT DISTINCT 
        operador_id_bd, operador_codigo_interno, operador_nombre, operador_alias
    FROM raw_operaciones
    ON CONFLICT (operador_id_bd) DO NOTHING;

    -- C. Insertar operaciones nuevas del CSV si no existen en la dimensión
    INSERT INTO dim_operacion (
        operacion_id_bd, operacion_codigo_interno, operacion_nombre, 
        operacion_paso_final, operacion_tipo_codigo, operacion_tipo_nombre, operacion_general
    )
    SELECT DISTINCT 
        operacion_id_bd, operacion_codigo_interno, operacion_nombre, 
        operacion_paso_final, operacion_tipo_codigo, operacion_tipo_nombre, operacion_general
    FROM raw_operaciones
    ON CONFLICT (operacion_id_bd) DO NOTHING;

    -- D. Insertar ordenes nuevas del CSV si no existen en la dimensión
    INSERT INTO dim_orden (
        orden_id_bd, orden_numero, orden_anio, orden_semana, 
        orden_estado_activo, orden_cantidad_solicitada
    )
    SELECT DISTINCT 
        orden_id_bd, orden_numero, orden_anio, orden_semana, 
        orden_estado_activo, orden_cantidad_solicitada
    FROM raw_operaciones
    WHERE orden_id_bd IS NOT NULL
    ON CONFLICT (orden_id_bd) DO NOTHING;

    -- E. Insertar estaciones nuevas del CSV si no existen en la dimensión
    INSERT INTO dim_estacion (
        estacion_id_bd, estacion_codigo_interno, estacion_nombre, 
        estacion_alias, estacion_modelo_id_bd, estacion_modelo_nombre, 
        estacion_modelo_tipo
    )
    SELECT DISTINCT 
        estacion_id_bd, estacion_codigo_interno, estacion_nombre, 
        estacion_alias, estacion_modelo_id_bd, estacion_modelo_nombre, 
        estacion_modelo_tipo
    FROM raw_operaciones
    WHERE estacion_id_bd IS NOT NULL
    ON CONFLICT (estacion_id_bd) DO NOTHING;
    """
    
    # === PASO 3: REESTRUCTURAR LA TABLA DE HECHOS FINAL ===
    print("🚀 3/3: Poblando la tabla estrella 'fact_ejecuciones' con integridad referencial...")
    
    sql_fact_table = """
    -- Vaciamos la tabla de hechos relacional para reconstruirla limpiamente sin duplicados
    TRUNCATE TABLE fact_ejecuciones RESTART IDENTITY CASCADE;

    -- Insertamos cruzando directamente con las dimensiones validadas
    INSERT INTO fact_ejecuciones (
        id, operador_id_bd, componente_id_bd, estacion_id_bd, operacion_id_bd, orden_id_bd,
        ejecucion_fecha_inicio, ejecucion_fecha_fin, ejecucion_estado, ejecucion_estado_descripcion, ejecucion_usuario,
        orden_cantidad_confirmada, orden_cantidad_producida, orden_cantidad_inventariada, orden_cantidad_material, orden_cantidad_despachada,
        ejecucion_cantidad_existose, ejecucion_cantidad_bruta, ejecucion_cantidad_rechazada, ejecucion_inventariar,
        sub_eje_paralelo, paralelo_eje_origen
    )
    SELECT 
        r.id, r.operador_id_bd, r.componente_id_bd, r.estacion_id_bd, r.operacion_id_bd, r.orden_id_bd,
        r.ejecucion_fecha_inicio::TIMESTAMP, r.ejecucion_fecha_fin::TIMESTAMP, r.ejecucion_estado, r.ejecucion_estado_descripcion, r.ejecucion_usuario,
        r.orden_cantidad_confirmada, r.orden_cantidad_producida, r.orden_cantidad_inventariada, r.orden_cantidad_material, r.orden_cantidad_despachada,
        r.ejecucion_cantidad_existosa, r.ejecucion_cantidad_bruta, r.ejecucion_cantidad_rechazada, r.ejecucion_inventariar,
        r.sub_eje_paralelo, r.paralelo_eje_origen
    FROM raw_operaciones r
    JOIN dim_componente c ON r.componente_id_bd = c.componente_id_bd
    JOIN dim_operador o ON r.operador_id_bd = o.operador_id_bd
    JOIN dim_operacion op ON r.operacion_id_bd = op.operacion_id_bd;
    """

    # Ejecución transaccional segura
    try:
        with engine.begin() as conexion:
            print("   -> Sincronizando Catálogos de Dimensiones...")
            conexion.execute(text(sql_dimensiones))
            print("   -> Vinculando y construyendo 'fact_ejecuciones'...")
            conexion.execute(text(sql_fact_table))
        print("🎉 ¡Carga de base de datos terminada con éxito!")
        
        # Ejecutar automáticamente el pipeline analítico
        import subprocess
        import sys
        print("⏳ Iniciando recálculo del pipeline analítico (03_calculos.py)...")
        script_calculos = os.path.join(os.path.dirname(__file__), "03_calculos.py")
        resultado = subprocess.run([sys.executable, script_calculos], check=True)
        print("🎉 ¡Almacén de Datos y Pipeline de Cálculos actualizados al día!")
    except Exception as e:
        print(f"❌ Error crítico detectado durante la carga en Postgres: {str(e)}")

if __name__ == "__main__":
    ejecutar_automatizacion()