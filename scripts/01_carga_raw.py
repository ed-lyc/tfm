import os
import re
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# 1. Cargar variables de entorno desde el archivo .env
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# 2. Configurar la ruta del archivo CSV y la conexión a PostgreSQL
CSV_PATH = "data/raw/operaciones_simuladas.csv"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def normalizar_columnas(df):
    """
    Limpia los nombres de las columnas: quita tildes, caracteres especiales,
    reemplaza espacios por guiones bajos y lo pasa todo a minúsculas.
    """
    nuevas_columnas = []
    for col in df.columns:
        # Pasarlo a string y a minúsculas
        c = str(col).lower().strip()
        # Reemplazar tildes comunes
        c = re.sub(r'[áàäâ]', 'a', c)
        c = re.sub(r'[éèëê]', 'e', c)
        c = re.sub(r'[íìïî]', 'i', c)
        c = re.sub(r'[óòöô]', 'o', c)
        c = re.sub(r'[úùüû]', 'u', c)
        c = re.sub(r'[ñ]', 'n', c)
        # Reemplazar espacios y caracteres no alfanuméricos por guion bajo
        c = re.sub(r'[^a-z0-9_]', '_', c)
        # Limpiar guiones bajos duplicados resultantes
        c = re.sub(r'_+', '_', c).strip('_')
        nuevas_columnas.append(c)
    
    df.columns = nuevas_columnas
    return df

def cargar_datos_raw():
    # === PASO 0: REGENERAR DATOS SIMULADOS ===
    print("[Ingestion] Generando dataset estocastico operaciones_simuladas.csv...")
    try:
        import subprocess
        import sys
        script_simula = os.path.join(os.path.dirname(__file__), "simula_operaciones.py")
        subprocess.run([sys.executable, script_simula], check=True)
        print("[Ingestion] Simulacion finalizada y operaciones_simuladas.csv regenerado.")
    except Exception as e:
        print(f"[Ingestion] Advertencia al ejecutar simula_operaciones.py: {str(e)}")
        print("Se continuara usando el archivo operaciones_simuladas.csv existente.")

    print("⏳ Leyendo archivo CSV...")
    # Leemos el CSV (si hay problemas de encoding por eñes o tildes, usamos latin1 o utf-8)
    try:
        df = pd.read_csv(CSV_PATH, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding='latin1')
        
    print(f"📊 Filas detectadas: {len(df)}")
    
    # Eliminar columnas basura si existen (como 'unnamed_49')
    if 'Unnamed: 49' in df.columns:
        df = df.drop(columns=['Unnamed: 49'])
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

    print("🧼 Normalizando nombres de columnas...")
    df = normalizar_columnas(df)
    
    print("🔌 Conectando a PostgreSQL en Docker...")
    engine = create_engine(DATABASE_URL)
    
    # 3. Subir a PostgreSQL reemplazando si ya existe (Capa RAW / Staging)
    print("🚀 Subiendo datos a la tabla 'raw_operaciones'...")
    df.to_sql(
        name='raw_operaciones', 
        con=engine, 
        if_exists='replace', 
        index=False,
        chunksize=5000 # Lo sube en bloques optimizados de 5000 filas
    )
    print("✅ ¡Carga exitosa! Los datos crudos ya están listos en PostgreSQL.")

if __name__ == "__main__":
    cargar_datos_raw()