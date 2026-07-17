import os
import sys
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Evitar errores de codificación de caracteres en Windows (emojis)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ============================================================================
# ⚙️ CONFIGURACIÓN ANALÍTICA MODIFICABLE
# ============================================================================
UMBRAL_MINIMO_MUESTRAS = 30  

# ============================================================================
# 🔌 CONFIGURACIÓN DE CONEXIÓN
# ============================================================================
load_dotenv()
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin123")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "tfm_db")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def procesar_pipeline_analitico():
    print("🔌 Conectando a PostgreSQL...")
    engine = create_engine(DATABASE_URL)
    
    query = """
        SELECT 
            f.id,
            f.ejecucion_fecha_inicio,
            f.ejecucion_fecha_fin,
            f.ejecucion_cantidad_bruta,
            f.ejecucion_cantidad_rechazada,
            c.componente_codigo_interno,
            c.componente_nombre,
            o.operacion_nombre
        FROM fact_ejecuciones f
        JOIN dim_componente c ON f.componente_id_bd = c.componente_id_bd
        JOIN dim_operacion o ON f.operacion_id_bd = o.operacion_id_bd;
    """
    df = pd.read_sql(query, con=engine)
    print(f"📥 {len(df)} registros de planta cargados para el análisis.")
    
    # 1. Transformación Base y Cálculos en HORAS
    df['ejecucion_fecha_inicio'] = pd.to_datetime(df['ejecucion_fecha_inicio'])
    df['ejecucion_fecha_fin'] = pd.to_datetime(df['ejecucion_fecha_fin'])
    
    # Duración estrictamente en HORAS
    df['duracion_horas'] = (df['ejecucion_fecha_fin'] - df['ejecucion_fecha_inicio']).dt.total_seconds() / 3600.0
    df['piezas_buenas'] = df['ejecucion_cantidad_bruta'].fillna(0) - df['ejecucion_cantidad_rechazada'].fillna(0)
    
    # Ciclo de producción: PIEZAS POR HORA
    df['ciclo_piezas_hora'] = np.where(
        df['duracion_horas'] > 0, 
        df['piezas_buenas'] / df['duracion_horas'], 
        0
    )
    
    # Inicialización de columnas de control estadístico
    df['es_anomalidad'] = 0
    df['nota_calidad'] = None
    
    # Columnas para almacenar el conteo del segmento
    df['muestras_totales_segmento'] = 0
    df['muestras_validas_segmento'] = 0
    df['muestras_invalidas_segmento'] = 0
    
    print("🧠 Analizando segmentos y aplicando reglas de calidad...")
    grouped = df.groupby(['componente_codigo_interno', 'operacion_nombre'])
    df_procesado_list = []
    
    for name, group in grouped:
        group = group.copy()
        
        # Filtro de registros iniciales con errores de registro severos (tiempos negativos)
        idx_tiempo_negativo = group['duracion_horas'] < 0
        group.loc[idx_tiempo_negativo, 'es_anomalidad'] = 1
        group.loc[idx_tiempo_negativo, 'nota_calidad'] = 'Error: Tiempo negativo'
        
        # Trabajamos sobre registros con tiempos lógicos para el análisis IQR
        idx_tiempos_validos = group['duracion_horas'] >= 0
        ciclos_analizables = group[idx_tiempos_validos & (group['ciclo_piezas_hora'] > 0)]['ciclo_piezas_hora']
        
        # --- Cálculo del IQR del segmento ---
        if not ciclos_analizables.empty:
            q1 = ciclos_analizables.quantile(0.25)
            q3 = ciclos_analizables.quantile(0.75)
            iqr = q3 - q1
            
            # En piezas por hora, una anomalía por lentitud extrema se evalúa con el límite inferior
            limite_inferior = q1 - (1.5 * iqr)
            limite_superior = q3 + (1.5 * iqr)
            
            # Es outlier si produce absurdamente rápido o lento respecto a la velocidad normal
            es_outlier_velocidad = (group['ciclo_piezas_hora'] < limite_inferior) | (group['ciclo_piezas_hora'] > limite_superior)
        else:
            es_outlier_velocidad = pd.Series(False, index=group.index)

        # --- Aplicación de Reglas Combinadas de Muestreo y Calidad ---
        total_muestras = len(group)
        
        if total_muestras < UMBRAL_MINIMO_MUESTRAS:
            # Caso Muestreo Bajo: Aceptamos los normales, alertamos las anomalías en muestras bajas
            group.loc[idx_tiempos_validos & ~es_outlier_velocidad, 'nota_calidad'] = 'Muestreo Bajo'
            
            # Si se detecta un outlier de velocidad aun en muestreo bajo, se marca
            idx_anomalia_baja = idx_tiempos_validos & es_outlier_velocidad
            group.loc[idx_anomalia_baja, 'es_anomalidad'] = 1
            group.loc[idx_anomalia_baja, 'nota_calidad'] = 'Anomalía en Muestreo Bajo'
        else:
            # Caso Muestreo Suficiente (Clásico)
            idx_anomalia_alta = idx_tiempos_validos & es_outlier_velocidad
            group.loc[idx_anomalia_alta, 'es_anomalidad'] = 1
            group.loc[idx_anomalia_alta, 'nota_calidad'] = 'Anomalía: Ritmo fuera de rango'
            
        # --- Conteo estadístico del segmento ---
        # Un registro es inválido si fue catalogado como anomalía
        invalidas = int(group['es_anomalidad'].sum())
        validas = int(total_muestras - invalidas)
        
        group['muestras_totales_segmento'] = total_muestras
        group['muestras_validas_segmento'] = validas
        group['muestras_invalidas_segmento'] = invalidas
        
        df_procesado_list.append(group)
        
    df_final = pd.concat(df_procesado_list)
    
    # Limpieza matemática final
    df_final['ciclo_piezas_hora'] = df_final['ciclo_piezas_hora'].replace([np.inf, -np.inf], 0).fillna(0)
    df_final['duracion_horas'] = df_final['duracion_horas'].fillna(0)
    
    # 2. Persistir Tabla: historicos_iqr
    columnas_historico = [
        'id', 'duracion_horas', 'piezas_buenas', 'ciclo_piezas_hora', 
        'es_anomalidad', 'nota_calidad', 'muestras_totales_segmento', 
        'muestras_validas_segmento', 'muestras_invalidas_segmento'
    ]
    df_historicos_iqr = df_final[columnas_historico]
    
    print("🚀 Guardando tabla 'historicos_iqr'...")
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE historicos_iqr CASCADE;"))
        try: conn.commit()
        except: pass
    df_historicos_iqr.to_sql('historicos_iqr', con=engine, if_exists='append', index=False, chunksize=5000)
    
    # 3. Cálculo de la segunda tabla: tabla_estandares
    print("📈 Calculando 'tabla_estandares' basados en registros limpios...")
    # Para el cálculo del estándar industrial, usamos solo los registros válidos (es_anomalidad == 0)
    df_limpio = df_final[df_final['es_anomalidad'] == 0]
    
    # Agrupamos para consolidar las métricas por producto y proceso
    estandares = df_limpio.groupby(['componente_codigo_interno', 'operacion_nombre']).agg(
        descripcion_pieza=('componente_nombre', 'first'),
        promedio_ciclo_piezas_hora=('ciclo_piezas_hora', 'mean'),
        cuantos_validos=('muestras_validas_segmento', 'first'),
        cuantos_invalidos=('muestras_invalidas_segmento', 'first')
    ).reset_index()
    
    # Renombrar columnas para calzar con tus requerimientos exactos
    estandares.rename(columns={
        'componente_codigo_interno': 'codigo_interno_pieza',
        'operacion_nombre': 'proceso'
    }, inplace=True)
    
    print("🚀 Guardando tabla 'tabla_estandares'...")
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE tabla_estandares CASCADE;"))
        try: conn.commit()
        except: pass
    estandares.to_sql('tabla_estandares', con=engine, if_exists='append', index=False)
    
    # 4. Infraestructura SQL e Índices en Docker
    print("🏗️ Estructurando llaves primarias y foráneas...")
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Verificar si ya existen las llaves primarias, foráneas e índices
            pk_historicos_exists = conn.execute(text("""
                SELECT 1 FROM pg_class c
                JOIN pg_index i ON c.oid = i.indrelid
                WHERE c.relname = 'historicos_iqr' AND i.indisprimary;
            """)).fetchone()
            
            fk_exists = conn.execute(text("""
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_fact_ejecuciones';
            """)).fetchone()
            
            idx_exists = conn.execute(text("""
                SELECT 1 FROM pg_class WHERE relname = 'idx_historicos_anomalidad';
            """)).fetchone()
            
            pk_estandares_exists = conn.execute(text("""
                SELECT 1 FROM pg_class c
                JOIN pg_index i ON c.oid = i.indrelid
                WHERE c.relname = 'tabla_estandares' AND i.indisprimary;
            """)).fetchone()

            # Restricciones para historicos_iqr
            if not pk_historicos_exists:
                conn.execute(text("ALTER TABLE historicos_iqr ADD PRIMARY KEY (id);"))
            if not fk_exists:
                conn.execute(text("ALTER TABLE historicos_iqr ADD CONSTRAINT fk_fact_ejecuciones FOREIGN KEY (id) REFERENCES fact_ejecuciones(id);"))
            if not idx_exists:
                conn.execute(text("CREATE INDEX idx_historicos_anomalidad ON historicos_iqr (es_anomalidad);"))
            
            # Restricciones para tabla_estandares
            if not pk_estandares_exists:
                conn.execute(text("ALTER TABLE tabla_estandares ADD PRIMARY KEY (codigo_interno_pieza, proceso);"))
            
            trans.commit()
            print("✅ Base de datos indexada y amarrada de forma óptima.")
        except Exception as e:
            try:
                trans.rollback()
            except Exception:
                pass
            print(f"⚠️ Nota de infraestructura: {e}")
            
    print("🎉 Pipeline analítico completado con éxito.")

if __name__ == "__main__":
    procesar_pipeline_analitico()