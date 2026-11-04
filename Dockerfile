# The app as Cloud Run runs it (deploy.sh builds this on Google's side; you don't need Docker yourself).
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 MPLBACKEND=Agg
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# One process (the sheet is written by one writer at a time), several threads for parallel requests
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
