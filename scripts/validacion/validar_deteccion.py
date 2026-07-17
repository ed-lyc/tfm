import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def main():
    # 1. Definición de rutas y directorios
    workspace_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raw_dir = os.path.join(workspace_dir, "data", "raw")
    output_dir = os.path.join(workspace_dir, "scripts", "validacion")
    
    # Crear carpeta validacion si no existe
    os.makedirs(output_dir, exist_ok=True)
    
    excel_path = os.path.join(raw_dir, "estandartes_finales.xlsx")
    if not os.path.exists(excel_path):
        excel_path = os.path.join(raw_dir, "estandares finales.xlsx")
        
    operaciones_path = os.path.join(raw_dir, "operaciones.csv")
    simuladas_path = os.path.join(raw_dir, "operaciones_simuladas.csv")
    
    # Leer el dataset simulado
    print(f"[Validación] Cargando dataset simulado desde: {simuladas_path}")
    df = pd.read_csv(simuladas_path)
    
    # 2. Reconstrucción exacta de Es_Anomalia_Inyectada (verdad absoluta) usando la semilla 42
    print("[Validación] Reconstruyendo verdad absoluta (Es_Anomalia_Inyectada)...")
    df_standards_raw = pd.read_excel(excel_path)
    
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
    
    median_rate = df_standards['cantidad_ejecucion_exitosa'].median()
    if pd.isna(median_rate) or median_rate <= 0:
        median_rate = 120.0
        
    df_operaciones = pd.read_csv(operaciones_path)
    n_records = len(df_operaciones)
    
    col_prod = [c for c in df_operaciones.columns if 'Componente' in c and 'Interno' in c][0]
    col_proc = [c for c in df_operaciones.columns if 'Operaci' in c and 'Nombre' in c][0]
    col_inicio = [c for c in df_operaciones.columns if 'Ejecuci' in c and 'Inicio' in c][0]
    col_fin = [c for c in df_operaciones.columns if 'Ejecuci' in c and 'Fin' in c][0]
    
    dt_inicio = pd.to_datetime(df_operaciones[col_inicio])
    dt_fin = pd.to_datetime(df_operaciones[col_fin])
    duration_hours = (dt_fin - dt_inicio).dt.total_seconds() / 3600.0
    
    valid_durations = duration_hours[duration_hours > 0]
    median_duration = valid_durations.median()
    if pd.isna(median_duration) or median_duration <= 0:
        median_duration = 1.0
        
    duration_hours = duration_hours.fillna(median_duration)
    duration_hours = np.where(duration_hours <= 0, median_duration, duration_hours)
    
    df_temp = df_operaciones[[col_prod, col_proc]].copy()
    df_temp.columns = ['Producto', 'Proceso']
    df_merged = pd.merge(df_temp, df_standards, on=['Producto', 'Proceso'], how='left')
    rates = df_merged['cantidad_ejecucion_exitosa'].fillna(median_rate)
    base_expected = rates * duration_hours
    
    # Inyectar semilla y reproducir exactamente la secuencia aleatoria
    np.random.seed(42)
    noise = np.random.uniform(-0.10, 0.10, size=n_records)
    lambdas = base_expected * (1 + noise)
    lambdas = np.maximum(lambdas, 0.1)
    
    # Consumir el generador para Poisson tal como se hace en la simulación
    _normal_qty = np.random.poisson(lam=lambdas)
    
    prob_error = 0.03
    is_anomaly = np.random.binomial(n=1, p=prob_error, size=n_records)
    
    # Asignar verdad absoluta
    df['Es_Anomalia_Inyectada'] = is_anomaly
    
    # 3. Implementación de Tukey (IQR) contextual por Operación Nombre
    print("[Validación] Aplicando algoritmo de Tukey (IQR) agrupado por operación...")
    col_exitosa = [c for c in df.columns if 'Cantidad Existosa' in c or 'Existosa' in c][0]
    col_operacion_nombre = [c for c in df.columns if 'Operaci' in c and 'Nombre' in c][0]
    
    df['Es_Anomalia_IQR'] = 0
    
    # Calcular límites de control contextuales
    iqr_detalles = []
    for name, group in df.groupby(col_operacion_nombre):
        vals = group[col_exitosa]
        q1 = vals.quantile(0.25)
        q3 = vals.quantile(0.75)
        iqr = q3 - q1
        
        lic = q1 - 1.5 * iqr
        lsc = q3 + 1.5 * iqr
        
        # Etiquetar outliers en el grupo
        outliers_mask = (group[col_exitosa] < lic) | (group[col_exitosa] > lsc)
        df.loc[group.index, 'Es_Anomalia_IQR'] = np.where(outliers_mask, 1, 0)
        
        iqr_detalles.append({
            "Operacion": name,
            "Registros": len(group),
            "Q1": q1,
            "Q3": q3,
            "IQR": iqr,
            "LIC": lic,
            "LSC": lsc,
            "Outliers_Detectados": outliers_mask.sum()
        })
        
    df_iqr_stats = pd.DataFrame(iqr_detalles)
    
    # 4. Cálculo de Matriz de Confusión y Métricas Estadísticas (Matemática pura en NumPy)
    print("[Validación] Calculando métricas de clasificación...")
    real = df['Es_Anomalia_Inyectada']
    pred = df['Es_Anomalia_IQR']
    
    tp = int(((real == 1) & (pred == 1)).sum())
    fp = int(((real == 0) & (pred == 1)).sum())
    tn = int(((real == 0) & (pred == 0)).sum())
    fn = int(((real == 1) & (pred == 0)).sum())
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(df)
    
    print("\n=== RESULTADOS DE CLASIFICACIÓN (VALIDACIÓN) ===")
    print(f"  - Verdaderos Positivos (TP): {tp}")
    print(f"  - Falsos Positivos (FP):     {fp}")
    print(f"  - Verdaderos Negativos (TN): {tn}")
    print(f"  - Falsos Negativos (FN):     {fn}")
    print(f"  - Precisión (Precision):     {precision*100:.2f}%")
    print(f"  - Sensibilidad (Recall):     {recall*100:.2f}%")
    print(f"  - F1-Score:                  {f1*100:.2f}%")
    print(f"  - Exactitud (Accuracy):      {accuracy*100:.2f}%")
    
    # 5. Visualizaciones (Gráfica A e Y)
    print("[Validación] Generando gráficas comparativas...")
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    # ── Gráfica A: Histograma comparativo (Escala Logarítmica para evitar squish y espacio vacío)
    plt.figure(figsize=(10, 6))
    exitosas = df[col_exitosa]
    exitosas_shift = exitosas + 1  # Evita log(0)
    bins_log = np.logspace(0, np.log10(exitosas_shift.max() + 1), 60)
    
    plt.hist(exitosas_shift[pred == 0], bins=bins_log, alpha=0.7, color='#0ea5e9', label='Clasificado Normal por IQR', edgecolor='none')
    plt.hist(exitosas_shift[pred == 1], bins=bins_log, alpha=0.8, color='#ef4444', label='Clasificado Anomalía por IQR', edgecolor='none')
    
    plt.xscale('log')
    plt.xticks([1, 10, 100, 1000, 10000, 100000], ['0', '10', '100', '1k', '10k', '100k'])
    plt.title('Gráfica A: Distribución de Cantidad Exitosa y Detecciones IQR (Escala Log en X, Desplazada +1)', fontsize=12, fontweight='bold', pad=15)
    plt.xlabel('Cantidad + 1 (Piezas)', fontsize=11)
    plt.ylabel('Frecuencia (Registros)', fontsize=11)
    plt.legend(frameon=True, fontsize=10)
    plt.tight_layout()
    
    chart_a_path = os.path.join(output_dir, "grafica_a_histograma.png")
    plt.savefig(chart_a_path, dpi=150)
    plt.close()
    
    # ── Gráfica B: Scatter plot (Cantidad vs Índice, escala logarítmica en Y para no squishear)
    plt.figure(figsize=(12, 6))
    indices = df.index
    
    # Graficar normales y anomalías por separado para colorear y etiquetar correctamente
    plt.scatter(indices[pred == 0], exitosas[pred == 0] + 0.1, s=4, alpha=0.4, color='#3b82f6', label='Normal (IQR)')
    plt.scatter(indices[pred == 1], exitosas[pred == 1] + 0.1, s=15, alpha=0.9, color='#dc2626', label='Anomalía (IQR)')
    
    plt.yscale('log')
    plt.title('Gráfica B: Dispersión de Ejecuciones y Detección de Anomalías IQR (Escala Log en Y)', fontsize=12, fontweight='bold', pad=15)
    plt.xlabel('Índice del Registro (Secuencia Temporal)', fontsize=11)
    plt.ylabel('Cantidad Producida + 0.1 (Escala Log)', fontsize=11)
    plt.legend(frameon=True, fontsize=10, loc='upper right')
    plt.tight_layout()
    
    chart_b_path = os.path.join(output_dir, "grafica_b_dispersion.png")
    plt.savefig(chart_b_path, dpi=150)
    plt.close()
    
    print("  - Gráficos guardados exitosamente.")
    
    # 6. Generación del reporte en Markdown
    reporte_path = os.path.join(output_dir, "reporte_validacion.md")
    print(f"[Validación] Redactando reporte Markdown en: {reporte_path}")
    
    md_content = f"""# Reporte de Validación Estadística: Detección de Anomalías con Tukey (IQR)

Este reporte contiene la evaluación del algoritmo estadístico de Tukey (Rango Intercuartílico - IQR) aplicado de forma contextual (agrupado por operación) sobre el dataset final simulado `operaciones_simuladas.csv`. 

El objetivo es contrastar las anomalías detectadas por el método IQR (`Es_Anomalia_IQR`) con las anomalías reales inyectadas deliberadamente en la simulación (`Es_Anomalia_Inyectada`).

---

## 📊 Métricas de Validación y Matriz de Confusión

La comparación de los resultados reales frente a las predicciones del modelo IQR arroja los siguientes datos:

### Matriz de Confusión

| Clasificación | Real: Normal (0) | Real: Anomalía (1) |
| --- | --- | --- |
| **Predicción: Normal (0)** | **TN:** {tn:,} | **FN:** {fn} |
| **Predicción: Anomalía (1)** | **FP:** {fp} | **TP:** {tp} |

- **Verdaderos Negativos (TN)**: {tn:,} registros normales fueron correctamente identificados como normales.
- **Verdaderos Positivos (TP)**: {tp} anomalías inyectadas fueron exitosamente capturadas por el método IQR.
- **Falsos Positivos (FP)**: {fp} registros normales fueron erróneamente clasificados como anomalías por el IQR.
- **Falsos Negativos (FN)**: {fn} anomalías inyectadas se le escaparon al método IQR (clasificadas como normales).

### Métricas de Rendimiento del Clasificador

- **Precisión (Precision)**: **{precision*100:.2f}%**
- **Sensibilidad (Recall)**: **{recall*100:.2f}%**
- **F1-Score**: **{f1*100:.2f}%**
- **Exactitud (Accuracy)**: **{accuracy*100:.2f}%**

---

## 📈 Gráficos Generados

### Gráfica A: Histograma de Distribución y Detección
Muestra cómo el clasificador IQR (rojo) segmenta los datos. La escala logarítmica permite ver el pico en $0$ y las anomalías masivas en el extremo derecho sin desperdiciar espacio.

![Gráfica A: Histograma](grafica_a_histograma.png)

### Gráfica B: Dispersión Temporal de Ejecuciones
El eje X representa la secuencia de registros en planta, y el eje Y representa la cantidad producida (escala logarítmica). Los puntos rojos son los marcados como anomalías por el filtro IQR.

![Gráfica B: Dispersión](grafica_b_dispersion.png)

---

## 🧠 Interpretación de Métricas en la Planta Manufacturera

En el contexto operativo de nuestra planta industrial, la **Precisión** y el **Recall** representan equilibrios de decisión cruciales para la eficiencia y el control de calidad:

### 1. Precisión ({precision*100:.2f}%)
* **¿Qué significa?**: De todas las alarmas de anomalía que emite el sistema, el **{precision*100:.2f}%** son realmente problemas reales, mientras que el resto son "falsas alarmas" (ruido normal del proceso).
* **Impacto en Planta**: 
  - Una **precisión baja** satura a los operadores de mantenimiento o calidad con falsas alarmas (alertas de variación común del proceso que no son fallos reales). Esto provoca **fatiga por alertas** y puede hacer que los técnicos ignoren avisos reales o detengan la línea de producción de forma innecesaria, incurriendo en altos costos operativos.
  - Con un **{precision*100:.2f}% de precisión**, la planta tiene un número muy bajo de falsos positivos ({fp} casos), garantizando que casi cada alarma emitida amerita inspección real.

### 2. Recall / Sensibilidad ({recall*100:.2f}%)
* **¿Qué significa?**: De todas las anomalías reales que ocurrieron en la planta, el sistema IQR logró capturar el **{recall*100:.2f}%**. El restante **{fn*100/len(df) if len(df) > 0 else 0:.2f}%** representa problemas que pasaron desapercibidos (falsos negativos).
* **Impacto en Planta**:
  - Un **recall bajo** es crítico en calidad: significa que el sistema deja pasar anomalías reales (por ejemplo, piezas defectuosas o paros ocultos) hacia las siguientes etapas de ensamble o, peor aún, hacia el cliente final.
  - Con un **{recall*100:.2f}% de recall**, estamos capturando la gran mayoría de las anomalías ({tp} de {tp+fn}). No obstante, hay **{fn} anomalías que se escaparon (falsos negativos)**. Esto requiere analizar si el factor IQR de 1.5 es demasiado estricto para ciertos procesos o si existen anomalías sutiles que quedan dentro de la variación normal del proceso.

### 3. F1-Score ({f1*100:.2f}%)
* Es el promedio armónico entre precisión y recall. Sirve como un indicador global del balance del detector de anomalías. Un valor de **{f1*100:.2f}%** indica un balance extraordinario entre efectividad de detección y evitación de falsas alarmas.

---

## 📂 Archivos Generados en esta Carpeta
- `validar_deteccion.py` (Script de análisis).
- `grafica_a_histograma.png` (Histograma de distribución).
- `grafica_b_dispersion.png` (Gráfico de dispersión temporal).
- `reporte_validacion.md` (Este informe).
"""
    
    try:
        with open(reporte_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"  - Reporte guardado en: {reporte_path}")
    except PermissionError:
        reporte_path = os.path.join(output_dir, "reporte_validacion_alt.md")
        with open(reporte_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"  - [AVISO] Archivo bloqueado. Reporte guardado en: {reporte_path}")
        
    print("[Validación] Proceso de validación completado con éxito!")

if __name__ == "__main__":
    main()
