# services/llm-router — تنها درگاه همه‌ی فراخوانی‌های مدل

Python 3.12 + FastAPI. فقط داخلی است (پورت 8000، روی شبکه‌های `hq-internal` و `hq-llm`، بدون پورت منتشرشده).

- **مستندات کامل:** `docs/ops/LLM_LAYER.md`
- **کد:** `src/llm_router/`
  - `service.py`: مسیر یک فراخوانی: پذیرش، تخصیص، بودجه، صف، breaker، ledger، رویداد
  - `assignment.py`، `budget.py`، `scheduler.py`، `breaker.py`: منطق خالص با پوشش تست ≥ ۸۵٪
  - `backends/`: ‏`claude_runtime.py` (اشتراک) و `litellm_backend.py` (API؛ فعلاً همه خاموش)
  - `ledger.py`، `registry.py`، `events.py`، `metrics.py`، `auth.py`، `main.py`
- **دیتابیس:** migrationهای Alembic در `migrations/`، که job ‏`llm-migrate` آن‌ها را با نقش `hq` اجرا میکند. seedها در `seed/*.yaml` هستند: فقط ردیف‌های ناموجود اضافه میشوند و هیچ ردیفی بازنویسی نمیشود.
- **اجرا:** `python -m llm_router`. مهاجرت: `python -m llm_router.migrate`. تست واقعی: `make llm-smoke`.
- **وابستگی‌ها:** نسخه‌ها در `requirements.in` و lock با hash در `requirements.lock` (`make lock`).
- **تست:** `make test-services` (Postgres و NATS موقت).
