# Imagen base ligera con Python 3.12
FROM python:3.12-slim

# Buenas prácticas de ejecución en contenedor
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero para aprovechar la caché de capas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación (ver .dockerignore para exclusiones)
COPY . .

# Puerto expuesto por el servidor Flask
EXPOSE 5000

# Arranque del servidor web
CMD ["python", "app/main.py"]
