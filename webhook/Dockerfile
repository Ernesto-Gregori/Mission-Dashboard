# Webhook Stripe → Turso (deploy separado de Streamlit)

FROM python:3.12-slim
WORKDIR /app

COPY webhook/requirements.txt /app/webhook/requirements.txt
RUN pip install --no-cache-dir -r /app/webhook/requirements.txt

# Código compartido (billing + db)
COPY app /app/app
COPY webhook /app/webhook

ENV PYTHONPATH=/app
ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "webhook.main:app", "--host", "0.0.0.0", "--port", "8080"]
