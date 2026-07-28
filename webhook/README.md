# webhook/ — opcional / legado

El endpoint canónico de Stripe es:

```
POST /stripe/webhook
```

en la app FastAPI (`web/routers/stripe_hook.py`).

Este directorio (`webhook/`) era un microservicio aparte para Railway.
Puedes dejar de desplegarlo tras el cutover; conserva el código solo como referencia.
