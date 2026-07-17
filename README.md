# Sistema de Visualización Interactiva de Indicadores Operativos (MES analítico)

Prototipo de un **Sistema de Ejecución de Manufactura (MES)** analítico, interactivo y
bidireccional para la **detección, gestión y visualización de anomalías** en datos
operativos de manufactura discreta. Desarrollado como Trabajo Fin de Máster del
*Máster Universitario en Análisis y Visualización de Datos Masivos* (UNIR).

## Descripción

La solución integra:

- Un **pipeline ETL** programático y vectorizado en **Python + Pandas** (ingesta,
  *staging*, sincronización de dimensiones e inserción masiva con SQLAlchemy).
- Una base de datos **PostgreSQL** con **modelo dimensional en esquema estrella**.
- Un **motor de detección de anomalías** basado en el método del **rango intercuartílico
  (IQR) de Tukey**, aplicado por segmento (producto × operación).
- Una **capa de cuarentena lógica** que aísla los registros anómalos sin destruir la
  información, preservando trazabilidad.
- Una **interfaz web reactiva** con **Apache ECharts** y **Tabulator.js**, con
  capacidades de edición bidireccional (**write-back**) vía API REST.

## Estructura del repositorio

```
TFM_EMMT/
├── app/                    # Aplicación web (Flask)
│   ├── main.py             # Servidor + API REST
│   ├── templates/          # Vistas HTML
│   └── static/             # CSS y JS (ECharts, Tabulator)
├── scripts/                # Pipeline ETL y analítica
│   ├── actualiza_todo.py   # Orquestador ETL (staging → dimensiones → hechos → cálculos)
│   ├── 01_carga_raw.py     # Ingesta a capa staging
│   ├── 03_calculos.py      # Motor analítico IQR + tablas derivadas
│   ├── simula_operaciones.py
│   ├── cargar_usuarios.py
│   └── validacion/         # Validación del detector (matriz de confusión, métricas)
├── queries/                # Consultas SQL (opcional)
├── requirements.txt
├── Dockerfile              # Imagen del servicio web (Flask)
├── docker-compose.yml      # Orquestación web + PostgreSQL
├── .dockerignore
├── .env.example            # Plantilla de variables de entorno
└── README.md
```

## Requisitos e instalación

```bash
python -m venv venv
# Windows: venv\Scripts\activate   |   Linux/Mac: source venv/bin/activate
pip install -r requirements.txt

# Configurar credenciales
cp .env.example .env        # y editar con los valores locales
```

Requiere una instancia de **PostgreSQL** accesible con las credenciales del `.env`.

## Ejecución

```bash
# 1) Poblar la base de datos y recalcular el pipeline analítico
python scripts/actualiza_todo.py

# 2) Levantar el servidor web
python app/main.py          # http://localhost:5000
```

## Despliegue con Docker Compose

El proyecto incluye un `Dockerfile` para el servicio web y un `docker-compose.yml` que
orquesta la aplicación **Flask** junto con una instancia de **PostgreSQL**, reproduciendo
el entorno de ejecución sin instalación manual de dependencias.

```bash
# 1) Definir las credenciales (el archivo .env NO se versiona)
cp .env.example .env        # y editar DB_PASSWORD (obligatorio)

# 2) Construir y levantar los servicios
docker compose up --build   # aplicación en http://localhost:5000

# 3) Poblar la base de datos y recalcular el pipeline analítico
docker compose exec web python scripts/actualiza_todo.py

# Detener y eliminar los contenedores
docker compose down         # añadir -v para borrar también el volumen de datos
```

Dentro de la red de Compose, la aplicación accede a la base de datos mediante el nombre
de servicio `db` (puerto interno `5432`); en el host, PostgreSQL se publica en el puerto
`5433` y el servidor web en el `5000`. El volumen `pgdata` conserva los datos entre
reinicios. La contraseña de la base de datos se toma de la variable `DB_PASSWORD` del
archivo `.env` y nunca se incluye en la imagen ni en el repositorio.

## Nota sobre los datos (confidencialidad)

Los conjuntos de datos operativos **no se incluyen en este repositorio** por razones de
**confidencialidad industrial**. El sistema se validó con datos **sintéticos**, generados
por simulación estocástica a partir de distribuciones y catálogos anonimizados; ni los
identificadores ni los registros reales forman parte del material publicado. Las carpetas
`data/` y `datos simulados/` están excluidas mediante `.gitignore`.

## Autor

Edgar Manuel Matute Tapia — Máster Universitario en Análisis y Visualización de Datos
Masivos (UNIR).
