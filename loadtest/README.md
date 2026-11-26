# Навантажувальні тести (k6)

```bash
VUS=45 ./loadtest/run.sh no-cache        # основний сценарій: 1 запис + 9 читань
SCRIPT=queue.js RATE=15 ./loadtest/run.sh queue   # лише записи через чергу
```

Адреса береться з `terraform output app_url` або зі змінної `BASE_URL`. Потрібен k6 або Docker.
Результати зберігаються в `loadtest/results/<мітка>.json`. Опис — у `docs/LOADTEST.md` і `docs/QUEUE.md`.
