FROM python:3.10-slim

WORKDIR /app/outlok

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["python", "app.py"]
