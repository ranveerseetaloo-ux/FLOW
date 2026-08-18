FROM python:3.12-slim

WORKDIR /app/control-plane
# install deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# the app imports the sibling data-plane package at ../../data-plane,
# so the compose file mounts the whole repo at /app. For a standalone image,
# COPY both trees:
COPY . /app/control-plane
COPY ../data-plane /app/data-plane

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
