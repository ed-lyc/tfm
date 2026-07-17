import os
import pandas as pd
import numpy as np

def main():
    # 1. Determinismo: Fijar semilla estocástica
    seed = 42
    np.random.seed(seed)
    
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Rutas de archivo
    standards_path_1 = os.path.join(workspace_dir, "data", "raw", "estandares finales.xlsx")
    standards_path_2 = os.path.join(workspace_dir, "data", "raw", "estandartes_finales.xlsx")
    excel_path = standards_path_1 if os.path.exists(standards_path_1) else standards_path_2
    
    operaciones_path = os.path.join(workspace_dir, "data", "raw", "operaciones.csv")
    
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"No se encontró el archivo de estándares en {standards_path_1} ni en {standards_path_2}")
    if not os.path.exists(operaciones_path):
        raise FileNotFoundError(f"No se encontró el archivo de operaciones en {operaciones_path}")
        
    print(f"[Simulación] Leyendo estándares desde: {excel_path}")
    print(f"[Simulación] Leyendo transacciones desde: {operaciones_path}")
    
    # 1. Leer excel de estándares
    df_standards_raw = pd.read_excel(excel_path)
    
    # Mapear columnas dinámicamente
    cols_mapping = {}
    for col in df_standards_raw.columns:
        col_clean = str(col).strip()
        if 'Componente' in col_clean and 'Interno' in col_clean:
            cols_mapping[col] = 'Producto'
        elif 'Operaci' in col_clean or 'Operac' in col_clean:
            cols_mapping[col] = 'Proceso'
        elif 'E_Promedio_u_h' in col_clean:
            cols_mapping[col] = 'cantidad_ejecucion_exitosa'
            
    df_standards = df_standards_raw.rename(columns=cols_mapping)
    df_standards = df_standards[['Producto', 'Proceso', 'cantidad_ejecucion_exitosa']].dropna()
    df_standards = df_standards.drop_duplicates(subset=['Producto', 'Proceso'])
    
    # Fallback rate if not found
    median_rate = df_standards['cantidad_ejecucion_exitosa'].median()
    if pd.isna(median_rate) or median_rate <= 0:
        median_rate = 120.0
        
    # 2. Leer transacciones operaciones.csv
    df_operaciones = pd.read_csv(operaciones_path)
    n_records = len(df_operaciones)
    print(f"[Simulación] Total transacciones base a procesar: {n_records}")
    
    # Buscar nombres reales de columnas en operaciones.csv (con unicode safe handling)
    col_prod = [c for c in df_operaciones.columns if 'Componente' in c and 'Interno' in c][0]
    col_proc = [c for c in df_operaciones.columns if 'Operaci' in c and 'Nombre' in c][0]
    col_inicio = [c for c in df_operaciones.columns if 'Ejecuci' in c and 'Inicio' in c][0]
    col_fin = [c for c in df_operaciones.columns if 'Ejecuci' in c and 'Fin' in c][0]
    col_existosa = [c for c in df_operaciones.columns if 'Cantidad Existosa' in c or 'Existosa' in c][0]
    col_bruta = [c for c in df_operaciones.columns if 'Cantidad Bruta' in c or 'Bruta' in c][0]
    col_rechazada = [c for c in df_operaciones.columns if 'Cantidad Rechazada' in c or 'Rechazada' in c][0]
    
    print(f"[Simulación] Mapeo de columnas en CSV completado:")
    print(f"  - Producto: '{col_prod}'")
    print(f"  - Proceso: '{col_proc}'")
    print(f"  - Inicio: '{col_inicio}'")
    print(f"  - Fin: '{col_fin}'")
    print(f"  - Exitosa: '{col_existosa}'")
    
    # 3. Calcular duración en horas
    # Convertir a datetime
    dt_inicio = pd.to_datetime(df_operaciones[col_inicio])
    dt_fin = pd.to_datetime(df_operaciones[col_fin])
    
    duration_hours = (dt_fin - dt_inicio).dt.total_seconds() / 3600.0
    
    # Mediana de duraciones válidas
    valid_durations = duration_hours[duration_hours > 0]
    median_duration = valid_durations.median()
    if pd.isna(median_duration) or median_duration <= 0:
        median_duration = 1.0 # 1 hora por defecto
        
    duration_hours = duration_hours.fillna(median_duration)
    duration_hours = np.where(duration_hours <= 0, median_duration, duration_hours)
    
    # 4. Cruce de datos (left join para traer la tasa estándar)
    # Creamos una clave Producto-Proceso temporal
    df_temp = df_operaciones[[col_prod, col_proc]].copy()
    df_temp.columns = ['Producto', 'Proceso']
    
    # Merge con estándares
    df_merged = pd.merge(
        df_temp,
        df_standards,
        on=['Producto', 'Proceso'],
        how='left'
    )
    
    # Rellenar tasas vacías con la mediana estándar
    rates = df_merged['cantidad_ejecucion_exitosa'].fillna(median_rate)
    
    # 5. Algoritmo Estocástico Vectorial
    # Cantidad esperada = tasa * duracion
    base_expected = rates * duration_hours
    
    # Ofuscación base: variabilidad de ruido entre -10% y +10%
    noise = np.random.uniform(-0.10, 0.10, size=n_records)
    lambdas = base_expected * (1 + noise)
    lambdas = np.maximum(lambdas, 0.1) # Poisson requiere lambda > 0
    
    # Operación Normal (Poisson)
    normal_qty = np.random.poisson(lam=lambdas)
    
    # Inyección de Anomalías (Tukey: Bernoulli con 3% de error)
    prob_error = 0.03
    is_anomaly = np.random.binomial(n=1, p=prob_error, size=n_records)
    
    # 50% anomalías son cero absoluto, 50% son masivas (5x a 10x la cantidad esperada)
    anomaly_type = np.random.binomial(n=1, p=0.5, size=n_records)
    massive_multipliers = np.random.uniform(5.0, 10.0, size=n_records)
    massive_values = (base_expected * massive_multipliers).round().astype(int)
    
    forced_anomaly_values = np.where(anomaly_type == 1, massive_values, 0)
    
    # Sobrescribir anomalías
    final_qty = np.where(is_anomaly == 1, forced_anomaly_values, normal_qty)
    
    # 6. Reemplazar y mantener consistencia
    df_simulado = df_operaciones.copy()
    df_simulado[col_existosa] = final_qty
    
    # Mantener consistencia: Bruta = Existosa + Rechazada
    rechazada = df_simulado[col_rechazada].fillna(0)
    df_simulado[col_bruta] = final_qty + rechazada
    
    # 7. Guardar en carpeta data/raw como operaciones_simuladas.csv
    output_path = os.path.join(workspace_dir, "data", "raw", "operaciones_simuladas.csv")
    df_simulado.to_csv(output_path, index=False)
    
    # 8. Reporte de Auditoría
    total_rows = len(df_simulado)
    anomalies_count = int(np.sum(is_anomaly))
    anomalies_pct = (anomalies_count / total_rows) * 100
    
    print("\n" + "="*50)
    print("REPORTE DE AUDITORÍA - SIMULACIÓN ESTOCÁSTICA REAL")
    print("="*50)
    print(f"Semilla utilizada:          {seed}")
    print(f"Total de registros:         {total_rows}")
    print(f"Anomalías inyectadas:       {anomalies_count}")
    print(f"Porcentaje de anomalías:    {anomalies_pct:.2f}%")
    print(f"Mediana de duraciones (h):  {median_duration:.2f} h")
    print(f"Tasa de reemplazo estándar: {median_rate:.1f} u/h")
    print(f"Archivo exportado:          {output_path}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
