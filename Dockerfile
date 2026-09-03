FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8765 \
    INFORMTIT_ALLOWED_ORIGINS=https://jeffer91.github.io

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8765
CMD ["python", "web_entry.py"]
