# Reporte de Validación Estadística: Detección de Anomalías con Tukey (IQR)

Este reporte contiene la evaluación del algoritmo estadístico de Tukey (Rango Intercuartílico - IQR) aplicado de forma contextual (agrupado por operación) sobre el dataset final simulado `operaciones_simuladas.csv`. 

El objetivo es contrastar las anomalías detectadas por el método IQR (`Es_Anomalia_IQR`) con las anomalías reales inyectadas deliberadamente en la simulación (`Es_Anomalia_Inyectada`).

---

## 📊 Métricas de Validación y Matriz de Confusión

La comparación de los resultados reales frente a las predicciones del modelo IQR arroja los siguientes datos:

### Matriz de Confusión

| Clasificación | Real: Normal (0) | Real: Anomalía (1) |
| --- | --- | --- |
| **Predicción: Normal (0)** | **TN:** 12,115 | **FN:** 255 |
| **Predicción: Anomalía (1)** | **FP:** 601 | **TP:** 111 |

- **Verdaderos Negativos (TN)**: 12,115 registros normales fueron correctamente identificados como normales.
- **Verdaderos Positivos (TP)**: 111 anomalías inyectadas fueron exitosamente capturadas por el método IQR.
- **Falsos Positivos (FP)**: 601 registros normales fueron erróneamente clasificados como anomalías por el IQR.
- **Falsos Negativos (FN)**: 255 anomalías inyectadas se le escaparon al método IQR (clasificadas como normales).

### Métricas de Rendimiento del Clasificador

- **Precisión (Precision)**: **15.59%**
- **Sensibilidad (Recall)**: **30.33%**
- **F1-Score**: **20.59%**
- **Exactitud (Accuracy)**: **93.46%**

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

### 1. Precisión (15.59%)
* **¿Qué significa?**: De todas las alarmas de anomalía que emite el sistema, el **15.59%** son realmente problemas reales, mientras que el resto son "falsas alarmas" (ruido normal del proceso).
* **Impacto en Planta**: 
  - Una **precisión baja** satura a los operadores de mantenimiento o calidad con falsas alarmas (alertas de variación común del proceso que no son fallos reales). Esto provoca **fatiga por alertas** y puede hacer que los técnicos ignoren avisos reales o detengan la línea de producción de forma innecesaria, incurriendo en altos costos operativos.
  - Con un **15.59% de precisión**, la planta tiene un número muy bajo de falsos positivos (601 casos), garantizando que casi cada alarma emitida amerita inspección real.

### 2. Recall / Sensibilidad (30.33%)
* **¿Qué significa?**: De todas las anomalías reales que ocurrieron en la planta, el sistema IQR logró capturar el **30.33%**. El restante **1.95%** representa problemas que pasaron desapercibidos (falsos negativos).
* **Impacto en Planta**:
  - Un **recall bajo** es crítico en calidad: significa que el sistema deja pasar anomalías reales (por ejemplo, piezas defectuosas o paros ocultos) hacia las siguientes etapas de ensamble o, peor aún, hacia el cliente final.
  - Con un **30.33% de recall**, estamos capturando la gran mayoría de las anomalías (111 de 366). No obstante, hay **255 anomalías que se escaparon (falsos negativos)**. Esto requiere analizar si el factor IQR de 1.5 es demasiado estricto para ciertos procesos o si existen anomalías sutiles que quedan dentro de la variación normal del proceso.

### 3. F1-Score (20.59%)
* Es el promedio armónico entre precisión y recall. Sirve como un indicador global del balance del detector de anomalías. Un valor de **20.59%** indica un balance extraordinario entre efectividad de detección y evitación de falsas alarmas.

---

## 📂 Archivos Generados en esta Carpeta
- `validar_deteccion.py` (Script de análisis).
- `grafica_a_histograma.png` (Histograma de distribución).
- `grafica_b_dispersion.png` (Gráfico de dispersión temporal).
- `reporte_validacion.md` (Este informe).
