# services/claude-runtime — اجرای مدل با اشتراک Claude

Python 3.12 + **Claude Agent SDK رسمی** (`claude-agent-sdk==0.2.163`، همراه با Claude Code CLI 2.1.286). **فقط llm-router میتواند آن را صدا بزند:** فقط روی شبکه‌ی `hq-llm`، با توکن router از OpenBao.

- **مستندات کامل:** `docs/ops/LLM_LAYER.md` §۲
- **ایمنی هر اجرا:**
  - هیچ ابزار، MCP، skill یا فایل تنظیمات
  - system prompt جایگزین کامل، از فایل
  - پوشه‌ی کار و HOME خالی، که بعد از اجرا پاک میشوند
  - بدون ریپو، سوکت Docker یا دسترسی به شبکه‌ی داخلی
- **مصرف** از نتیجه‌ی SDK خوانده میشود (`usage` و `total_cost_usd`). نشانه‌های سقف اشتراک به `quota_exhausted` تبدیل میشوند، همراه زمان ریست.
- **توکن اشتراک:** فقط مالک: `claude setup-token` و بعد `make claude-token`. توکن در OpenBao ‏(`kv/claude-runtime/oauth`) ذخیره میشود و موقع start خوانده میشود.
- **تست‌ها** SDK واقعی را با یک **CLI جعلی** (`testing/fake_claude.py`) اجرا میکنند، پس هیچ سهمیه‌ای مصرف نمیشود.
