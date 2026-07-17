import os
import sys
import re
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Evitar errores de codificación de caracteres en Windows (emojis)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# 1. Cargar variables de entorno
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# 2. Configurar la ruta del archivo CSV de usuarios
CSV_PATH = "data/raw/usuarios.csv"
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def normalizar_columnas(df):
    """
    Limpia los nombres de las columnas: quita tildes, caracteres especiales,
    reemplaza espacios por guiones bajos y lo pasa todo a minúsculas.
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

def cargar_datos_raw_usuarios():
    print("⏳ Leyendo archivo CSV de usuarios...")
    try:
        # Usamos sep=',' por defecto, si tu CSV usa punto y coma, cambiar a sep=';'
        df = pd.read_csv(CSV_PATH, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_PATH, encoding='latin1')
        
    print(f"📊 Filas detectadas: {len(df)}")
    
    # Eliminar columnas basura antes de normalizar
    df = df.loc[:, ~df.columns.str.contains('^Unnamed', case=False)]

    print("🧼 Normalizando nombres de columnas...")
    df = normalizar_columnas(df)
    
    # Rellenar los valores vacíos en la columna de la sección para evitar nulos en BD
    if 'comentario_1' in df.columns:
        df['comentario_1'] = df['comentario_1'].fillna('Sin Asignar')
    
    print(f"📋 Columnas resultantes: {list(df.columns)}")
    
    print("🔌 Conectando a PostgreSQL en Docker...")
    engine = create_engine(DATABASE_URL)
    
    # 3. Subir a PostgreSQL
    print("🚀 Subiendo datos a la tabla 'raw_usuarios'...")
    df.to_sql(
        name='raw_usuarios', 
        con=engine, 
        if_exists='replace', 
        index=False,
        chunksize=5000
    )
    print("✅ ¡Carga exitosa! La tabla raw de usuarios ya está en la base de datos.")

if __name__ == "__main__":
    cargar_datos_raw_usuarios()