FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py callback_server.py ./

# Run both bot and callback server
CMD bash -c "python callback_server.py & python bot.py"
