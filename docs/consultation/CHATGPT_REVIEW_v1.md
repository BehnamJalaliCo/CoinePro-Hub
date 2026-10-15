# CHATGPT_REVIEW_v1

> **تاریخ بررسی:** ۲۰۲۶-۱۰-۱۶  
> **مرجع:** `COINE_HQ_CONSULTATION_v1.md` مورخ ۲۰۲۶-۱۰-۱۵  
> **وضعیت:** نظر مستقل برای ادغام با طرح Claude؛ **نه مجوز اجرا و نه گزارش ممیزی سرورها**  
> **دامنه:** مشورت فاز صفر. هیچ ریپو، سرور، تنظیمات شبکه، داده یا سرویس عملیاتی تغییر نکرده است.  
> **تعریف اولویت:** `P0` ضروری پیش از اولین اتصال/اجرا؛ `P1` ضروری برای نسخهٔ عملیاتی؛ `P2` قابلیت رشد؛ `P3` قابلیت آینده/آزمایشی.  
> **حد قطعیت:** ترکیب فعلی سرویس‌ها، شبکه و ریپوها فقط *ادعاهای سند Claude* است، نه چیزی که من مستقل بررسی کرده باشم. ارقام قیمت دارای منبع از وب‌سایت ارائه‌دهنده‌اند؛ بودجه‌های ترکیبی، ظرفیت و KPIهای آتی **برآورد طراحی** هستند، نه وضعیت واقعی Coine.

## 0. خلاصه‌ی مدیریتی (حداکثر ۱۵ خط)

1. **رأی کلی: اجرای ایده را توصیه می‌کنم، اما نه با تصور «ده‌ها LLM همیشه فعال»؛ معماری درست یک شرکت Agentic مبتنی بر Workflow و کنترل دسترسی است.**
2. ساختار باید **CEO-centric و direct-to-agent** بماند، ولی تصمیم و اقدام از هم جدا شوند؛ هیچ «منشی AI» اجباری اضافه نشود.
3. اول **Coine HQ Control Plane** و خواندن امن داده‌ها ساخته شود؛ سپس اقدامات محدود و دارای مجوز فعال شوند.
4. اصل «هیچ دسترسی بدون Gateway» درست است؛ با این اصلاح که Gateway باید یک **Policy Enforcement Point غیرقابل دورزدن** باشد، نه فقط API Proxy.
5. «صفر اختلال» قابل تضمین نیست؛ باید آن را با **SLO، سقف بار، حالت read-only و آزمایش شکست** مدیریت کرد.
6. **هیچ مجوز دائمی برای عملیات حساس** نظیر معامله، برداشت، تغییر قیمت، ارسال انبوه، Restart یا Deploy صادر نشود.
7. همهٔ ایجنت‌ها صاحب **هویت، نسخه، دامنهٔ دسترسی، بودجه، KPI، دلیل تصمیم و تاریخ انقضای اختیار** باشند.
8. **Temporal** برای Workflowهای طولانی انتخاب خوبی است، مشروط به بودجهٔ عملیات و استقرار درست؛ در MVP کوچک می‌توان ابتدا از Job Engine ساده‌تر استفاده کرد.
9. فاز اول: وب + کارتابل + Audit + ۳ نمای مشاهدهٔ سرور، **پس از اجازهٔ صریح برای اتصال**؛ اندروید و ویس بعد از تثبیت هسته.
10. بهترین موتور رشد: **Execution → Evidence → Evaluation → Playbook**؛ تولید Playbook خودکار، به‌تنهایی یادگیری معتبر نیست.
11. **۵۰ تا ۶۰ نقش قابل تعریف** مفیدند، ولی ابتدا فقط **۸ تا ۱۲ نقش فعال** و **۲ تا ۵ Worker هم‌زمان** کافی است.
12. بودجهٔ تخمینی پایلوت **۲۰۰ تا ۷۰۰ دلار در ماه** و عملیات متوسط **۵۰۰ تا ۲٬۰۰۰ دلار در ماه** است؛ بدون نیروی توسعه و بر اساس فرض‌های بخش ۱۰.
13. برای تصمیم نهایی، **پنج ورودی حیاتی مالک** عبارت‌اند از بودجه، مجوز اتصال، نوع واقعی شبکه/سرورها، حدود استقلال و سیاست داده/ریسک معاملاتی.

## 1. بررسی بخش‌به‌بخش (برای هر § از بخش ب: ✅ موافق / ⚠️ اصلاح / ❌ مخالف + دلیل + پیشنهاد)

### §1 — قوانین پروژه: ✅ موافق، با ضمانت اجرایی دقیق‌تر [P0]

- **دلیل:** جداسازی «مشورت» از «اجرا» و read-only بودن سه ریپوی محصول، از خطای ناخواسته جلوگیری می‌کند.
- **پیشنهاد:** یک `REPOSITORY_POLICY.md` در `CoinePro-Hub` با allowlist بنویسید: تنها هدف write برابر `BehnamJalaliCo/CoinePro-Hub`؛ سه ریپوی دیگر فقط fetch/read. در همهٔ CI jobها و toolها، deny-by-default اعمال شود.
- **استثنا فقط با Change Request:** نام ریپو/سرور، فایل یا سرویس، ضرورت تغییر، Diff، ریسک، زمان، روش rollback، تأیید مشخص مالک؛ «Claude قبلاً اجازه داده» جایگزین این تأیید نیست.
- **تفاوت مهم:** read-only بودن ریپو، به معنی مجاز بودن تغییر فایروال، ساخت DB user، بازکردن پورت یا خواندن اطلاعات کاربران نیست. **هر تغییر سروری/شبکه‌ای هم مجوز مستقل می‌خواهد.**

### §2 — چشم‌انداز: ✅ موافق با مرزبندی استقلال [P0]

- **دلیل:** تجربهٔ مدیریتی مطلوب زمانی ایجاد می‌شود که مالک نتیجه ببیند، نه جریان بی‌پایان فکرکردن ایجنت‌ها.
- **اصلاح:** «کار دائمی بدون اجازهٔ مجدد» فقط برای **Work Order محدودشده** معتبر است: عملیات مجاز، سقف هزینه، سقف فراخوانی، محدودهٔ داده، بازهٔ زمانی، تاریخ انقضا و Kill Switch.
- **پیشنهاد:** برای هر کار، سه چیز مستقل ثبت شود: `Goal` (نتیجه)، `Runbook` (روش) و `Capability Grant` (اجازه). حتی مدیرعامل ایجنت حق ندارد از اختیار بالادستی خود به زیردست دسترسی وسیع‌تر بدهد.
- **تعریف موفقیت:** صرفه‌جویی زمان مالک، کیفیت تصمیم، کاهش ریسک سرویس‌های فعلی و رشد سود افزایشی؛ **رشد تصاعدی تضمین‌پذیر نیست** و باید اندازه‌گیری شود.

### §3 — دارایی‌های فعلی: ⚠️ اصلاح؛ «گزارش سند» را از «واقعیت تأییدشده» جدا کنید [P0]

- **دلیل:** فهرست TradeYar، CoinePro-FX، Pro-Chart، شبکهٔ Hetzner و مانیتورینگ را سند Claude گزارش می‌کند؛ من هیچ‌کدام را مستقلاً از Repo/Server بررسی نکرده‌ام.
- **پیشنهاد:** `ASSET_REGISTER.md` با ستون‌های `claimed / verified / access-approved / last-tested`، نوع هاست (Cloud/Dedicated)، Zone، Private IP، owner، وابستگی‌ها، metrics endpoint، مسیر Alertmanager، retention و RTO/RPO.
- **نکته:** وجود Prometheus و Loki به‌تنهایی به معنای «پوشش کامل» یا «بار خواندن تقریباً صفر» نیست. API query سنگین و log scan هم ممکن است بار ایجاد کنند؛ تست و budget لازم است.
- **محدودیت:** مانیتورینگ Pro-Chart در این سند با جزئیات دو بک‌اند دیگر توصیف نشده؛ فرض نکنید همهٔ سرورها Telemetry یکسان دارند.

### §4 — چک‌لیست مالک: ✅ موافق، با معیار پذیرش [P0]

- **پیشنهاد:** هر checkbox به Acceptance Test بدل شود: استخدام یک‌کلیک در کمتر از ۳۰ ثانیه با Scope مشخص؛ توقف کارمند در کمتر از ۱۰ ثانیه از دید Scheduler؛ اعلان مهم با تأیید دریافت؛ گزارش با دادهٔ قابل ردیابی؛ هیچ تغییر روی محصولات بدون مجوز.
- **اولویت‌بندی:** وب، کارتابل، گزارش سرورها، نقش‌ها، مجوز و Audit در `P0/P1`؛ voice و Android در `P1`؛ جلسهٔ صوتی زنده و دفتر مجازی در `P2/P3`.

### §5.1 — نام: ✅ موافق مشروط [P1]

- **پیشنهاد:** نام حقوقی/برند مادر را از محصول نرم‌افزاری جدا کنید: **Coine Holding** (نام کاری مجموعه) و **Coine HQ** (نام کاری محصول). چون محصولات فعلی مالی‌اند، برای توسعه به حوزهٔ غیرفایننس می‌توان نام تجاری مادر گسترده‌تر هم بررسی کرد.
- **شرط:** پیش از خرید دامنه/ثبت حقوقی، بررسی علامت تجاری، تعارض نام، تلفظ فارسی، حساب‌های اجتماعی و اعتبار دامنه. **هیچ آزادبودنی در این گزارش تأیید نشده است.**

### §5.2 — موتور رشد: ⚠️ اصلاح [P0]

- **دلیل:** سه چرخهٔ دانش، اعتماد و دارایی درست‌اند؛ اما خروجی موفق لزوماً روش صحیح یا قابل تکرار ندارد.
- **پیشنهاد چرخهٔ چهارم:** `Measurement & Causality`. هر Playbook باید با Evidence، Unit Test/Eval، مالک نسخه و شرایط کاربرد منتشر شود؛ اعتماد با **نتیجهٔ قابل سنجش و خطای وزنی** رشد کند، نه صرفاً تعداد تسک.
- **احتیاط:** SEO، «ذکرشدن در AI» و حجم محتوا معیار ارزش نهایی نیستند؛ خروجی باید به Conversion، Retention و Contribution Margin وصل شود.

### §5.3 — هاب و Gateway: ⚠️ اصلاح فنی مهم [P0]

- **موافق:** سرور/دامنهٔ مجزا، شبکهٔ خصوصی، Tool Gateway، Circuit Breaker، عدم SSH برای Agent Runtime، PR-only برای تغییر کد.
- **اصلاح ۱:** Private Network به‌خودی‌خود encrypted نیست؛ TLS/mTLS، احراز هویت متقابل و فایروال دوطرفه لازم‌اند. نوع Cloud Network/vSwitch و Zone باید پیش از طراحی تأیید شوند.
- **اصلاح ۲:** LLM نباید raw SQL یا arbitrary URL/command اجرا کند. حتی برای read-only، از **Query Templates + Parameter Validation + Row/Time Budget** استفاده کنید. اگر اتصال به مانیتورینگ موجود نیازمند تغییر کانفیگ است، همان تغییر هم نیاز به مجوز §1 دارد.
- **اصلاح ۳:** اگر مقصد راهکار Gateway ندارد، «Adapter» خارجیِ فقط‌خواندنی استفاده شود؛ نصب sidecar/agent روی سه سرور بدون اجازه ممنوع است.
- **اصلاح ۴:** read replica/snapshot شبانه لزوماً کم‌خطر نیست (I/O، replication lag، دادهٔ حساس)؛ با آزمون و مجوز فعال شود.
- **پیشنهاد:** Gateway دارای `Policy Decision Point` مستقل، tokenهای کوتاه‌عمر، action catalog تایپ‌شده، درخواست‌های idempotent و event log غیرقابل تغییر باشد.

### §5.4 — Stack: ⚠️ موافق با اصلاح Vendor Lock-in و هزینهٔ عملیات [P0/P1]

- **FastAPI + Postgres/pgvector + Next.js + Kotlin/Compose:** مناسب، چون با گزارش معماری فعلی هم‌خوان است.
- **Temporal:** برای تأییدهای چندروزه، retry و workflow قابل بازیابی مناسب؛ ولی self-hosting production هزینهٔ DBA/observability/upgrade دارد. **تصمیم مشروط:** MVP کوچک با Postgres-backed durable jobs؛ در صورت نیاز اثبات‌شده به orchestration طولانی یا از ابتدا با تیم DevOps توانا، Temporal. API دامنه را از موتور جدا نگه دارید.
- **Claude Agent SDK:** ابزار مناسبی است، نه تنها گزینهٔ معماری. تعریف نقش/ابزار/حافظه در هستهٔ خودمان باشد و `ModelAdapter` بتواند Anthropic/OpenAI یا provider دیگر را جایگزین کند.
- **MCP:** استاندارد قرارداد ابزار است، نه Boundary امنیتی. همهٔ MCP Serverها باید پشت Gateway/Policy و allowlist باشند.
- **Observability:** OpenTelemetry + ساختار traceهای agent/tool، نه فقط log عمومی.

### §5.5 — چارت سازمانی: ✅ موافق، با تفکیک «نقش» از «پردازش» [P1]

- **دلیل:** وجود چند SEO/GEO اختصاصی منطقی است، اما ۵۰ عنوان شغلی به معنی ۵۰ process دائمی نیست.
- **پیشنهاد:** `Agent Template → Agent Instance (per company/product) → Ephemeral Run`. سه SEO اختصاصی برای trade-future.ir، coineprofx.com و pro-chart.com بر پایهٔ یک Skill مشترک، با tenant scope و KPI جدا.
- **افزوده:** `Head of Data`, `Privacy & Compliance`, `Revenue Operations`, `Knowledge Librarian`, `Experimentation` و `Platform FinOps`.
- **تضاد منافع:** Inspector/Evaluator زیرمجموعهٔ مدیری که خروجی او را ارزیابی می‌کند نباشد؛ به CEO/Policy Board گزارش دهد.

### §5.6 — پرونده و نردبان استقلال: ⚠️ اصلاح حیاتی [P0]

- **نردبان L0-L4 مفید است، اما autonomy یک عدد جهانی نیست.** ایجنت SEO ممکن است برای گزارش L4 باشد و برای انتشار بدون تأیید L1؛ Agent مالی برای پرداخت همیشه deny.
- **پیشنهاد:** `Autonomy = f(agent, action, product, risk, data class, amount, expiry)`؛ grants با تاریخ انقضا و امکان revoke.
- **ارتقا:** به‌جای صرفاً قبولی در eval، حداقل ۳۰ اجرای shadow موفق، بررسی خطاها، تأیید مالک و rollback plan. اعداد ۳۰ اجرای shadow یک **هدف اولیهٔ پیشنهادی** است.
- **استخدام/اخراج:** حذف فقط capability و schedule، نه حذف Audit. Memory شخصی/حساس تابع retention و حق حذف است؛ «بایگانی همیشگی» درست نیست.

### §5.7 — موتور کار: ✅ موافق + طراحی دقیق رخداد [P0]

- **پیشنهاد:** شش وضعیت ثابت `DRAFT → APPROVED → SCHEDULED → RUNNING → VERIFYING → DONE` و وضعیت‌های فرعی `WAITING_APPROVAL`, `BLOCKED`, `FAILED`, `CANCELLED`, `COMPENSATED`.
- **چرا:** کارهای تکراری با retry ممکن است دوبار ایمیل بفرستند یا دوبار یک اکشن را اجرا کنند. `Idempotency Key`, de-duplication, timeout, max attempts و Compensating Action الزامی‌اند.
- **Playbook:** فقط پس از Verify + Eval به کتابخانه اضافه شود؛ تغییر Playbook در Runهای زنده نیاز به version pinning دارد.

### §5.8 — ارتباط بدون منشی: ✅ موافق، با جلوگیری از Notification Flood [P1]

- **دلیل:** مکالمهٔ مستقیم با Agentها باید ویژگی اصلی بماند.
- **اصلاح:** Cartable باید فقط **تصمیمات واقعی CEO** را بیاورد؛ پیام‌های معمولی در Inbox و گزارش تجمیع شوند. Rule Engine اولویت می‌دهد، نه واسطهٔ مکالمهٔ AI.
- **افزوده:** dedup، alert grouping، snooze، escalation، owner، acknowledge/resolve و quiet hours با استثنای Incident سطح بحرانی.
- **Telegram:** فقط کانال ثانویه با لینک امن به اپ؛ **هرگز** متن محرمانه، credential یا دکمهٔ تأیید عملیات حساس داخل پیام غیرقابل‌اعتماد قرار نگیرد.

### §5.9 — تجربهٔ CEO: ✅ موافق، با حذف سنجه‌های نمایشی [P1]

- **موافق:** Dark/Gold، RTL، Persian، فهرست کارمند، health، هزینه و Kill Switch.
- **اصلاح:** Health Score واحد می‌تواند مسئله را پنهان کند؛ باید به سه کارت جدا تقسیم شود: `Product Reliability`, `Growth & Revenue`, `Agent Safety & Cost` و زیر هر کارت evidence/time freshness.
- **«کارمند ماه»** فقط اگر تأثیر کسب‌وکار و خطا را هم وزن کند. ساعت فعال‌بودن و تعداد مکالمات KPI نیست.
- **قابلیت افزوده:** **Time Machine**: «از زمان آخرین ورودم چه تغییر کرده؟» همراه با Diff مستند و دکمهٔ drill-down.

### §5.10 — جلسات: ✅ موافق با شرط هزینه و حق تصمیم [P1]

- **پیشنهاد:** جلسه تنها وقتی تشکیل شود که چند نقش واقعاً دیدگاه مکمل داشته باشند؛ جلسهٔ روزانه به‌صورت snapshot غیرهمزمان ارزان است.
- **قانون:** LLMها می‌توانند توصیه کنند، اما مصوبهٔ اجرایی باید از `Decision Registry → Policy → Approval/Execution` عبور کند. رأی‌گیری ایجنت‌ها حق امضای مالک تولید نمی‌کند.
- **افزوده:** اختلاف‌نظر مستدل، confidence calibration، source freshness، action owner و پیگیری اثر تصمیم در ۷/۳۰ روز.

### §5.11 — شرکت زنده: ⚠️ موافق با ترتیب متفاوت [P2/P3]

- **موافق:** اساسنامه، ژورنال پیش‌بینی، کیفیت تصمیم و multi-company structure.
- **اصلاح:** Digital Twin بدون دادهٔ تجربی تنها ماشین تولید سناریو است؛ از `Scenario Calculator + Assumption Register` شروع کنید، نه ادعای پیش‌بینی معتبر.
- **دفتر 2D/3D:** فقط بعد از اثبات استفادهٔ مستمر از UI اصلی؛ P3.
- **یادگیری سلیقه:** ترجیح شخصی CEO نمی‌تواند Safety Policy یا محدودیت قانونی را دور بزند.

### §5.12 — کیفیت و هزینه: ✅ موافق، اما ناقص [P0]

- **افزوده:** هزینهٔ end-to-end بر حسب `task_id`, `agent_id`, `product_id`, `provider`, `model`, `tool`, `retry`؛ token limit کافی نیست.
- **کیفیت:** سه Eval مستقل لازم است: `answer quality`, `tool-use safety`, `business outcome`. دادهٔ خارجی untrusted و خروجی LLM نیز untrusted است تا زمانی که Validator بپذیرد.
- **Control:** بودجهٔ روزانه/ماهانه، هشدار ۷۰/۹۰٪، hard stop در ۱۰۰٪؛ استثنای اضطراری فقط طبق سیاست از پیش‌تعریف‌شده.

### §5.13 — نقشهٔ راه: ⚠️ مخالف با «شرکت کامل در ۳ ماه»؛ اصلاح پیشنهادی [P0]

- **دلیل:** با فرض یک تیم توسعهٔ کوچک، هم‌زمان ساخت orchestration، backend، وب، Android، Voice، Security، همهٔ دپارتمان‌ها و Board معتبر در ۱۲ هفته پرریسک است.
- **جایگزین:** ماه ۱ «پایلوتِ مشاهده‌پذیر»؛ ماه‌های ۲-۳ «کار واقعیِ امن»؛ ماه‌های ۴-۶ «افزایش استقلال»؛ ماه‌های ۷-۱۲ «قیاس اقتصادی و توسعهٔ هلدینگ»؛ معیارهای ماهانه در بخش ۹.
- **اگر تیم ۴ تا ۶ نفرهٔ باتجربه فول‌تایم و زیرساخت از قبل آماده باشد، بازهٔ فشرده‌تر ممکن است**؛ این ظرفیت از سند معلوم نیست.

### §5.14 — بیزینس‌پلن: ⚠️ اصلاح با Unit Economics [P0]

- **موافق:** تمرکز بر درآمد و حذف کار تکراری.
- **افزوده:** `Incremental Gross Profit - AI/Tool/Infra Costs - Review Labor - Incident Cost`، نرخ برگشت خطا و تست holdout لازم است. «ساعت صرفه‌جویی‌شده» تا وقتی به ظرفیت یا درآمد تبدیل نشود، سود نقدی نیست.
- **تصمیم:** HQ در ۱۲ ماه اول **Internal Operating System** باشد. SaaS تنها بعد از تثبیت امنیت، tenant isolation، پشتیبانی و هزینهٔ واقعی بررسی شود.

### §6 — تصمیم‌های باز: ✅ موافق؛ ترتیب مصوبه‌ها را اصلاح کنید [P0]

1. ابتدا `Risk Charter`، کلاس داده و عملیات ممنوع؛ ۲. بعد سقف بودجه و ترکیب تیم؛ ۳. سپس هویت شبکه و مجوزهای حداقلی؛ ۴. بعد اتصال read-only و MVP؛ ۵. نام نهایی و مسیر SaaS می‌توانند جلو بروند ولی مانع بررسی معماری نشوند.
2. اجازهٔ «ایجاد read-only DB account و firewall rule» یک بستهٔ کلی نیست؛ برای **هر سرور** باید درخواست تغییر مجزا و rollback داشته باشد.
3. پیشنهاد تصمیم محصول: **وب اول**؛ Android در حالی شروع شود که API و Design Tokens پایدار شده باشند.

### §7 — قدم بعدی: ✅ موافق با یک Gate قبل از Code [P0]

- ادغام دیدگاه‌ها در `VISION.md`, `ARCHITECTURE.md`, `ORG_CHART.md`, `MEETINGS.md`, `ROADMAP.md`, `BUSINESS_PLAN.md` خوب است.
- قبل از اجرای حتی یک Tool نوشتنی، سه سند دیگر هم پیشنهاد می‌کنم: `SECURITY_POLICY.md`, `AGENT_ACTION_CATALOG.md`, `ADR/` (Architecture Decision Records).
- **خروجی فاز صفر:** مصوبهٔ مالک روی حدود اختیارات، بودجه، چرخهٔ تأیید تغییر و Acceptance Criteria. تا آن لحظه فقط طراحی و تحقیق.

## 2. موارد جاافتاده (فیچرها، نقش‌ها، ریسک‌ها)

### 2.1 فیچرها و قابلیت‌های گمشده

| مورد | اولویت | دلیل و خروجی ملموس |
|---|---|---|
| **Permission Simulator** | P0 | قبل از فعال‌شدن Agent نشان دهد دقیقاً چه داده/اکشنی را می‌تواند اجرا کند و چه چیزی ممنوع است. |
| **Evidence Ledger + Freshness** | P0 | برای هر عدد لینک منبع، زمان مشاهده، واحد، روش محاسبه و کیفیت داده ثبت شود. |
| **Action Catalog + Dry Run** | P0 | هر اکشن دارای Schema، Risk، Idempotency، Preview و راه بازگشت باشد. |
| **Company/Product/Environment Scope** | P0 | تفکیک شرکت، محصول، staging/production و دادهٔ مشتری در تمام لایه‌ها. |
| **Cost Ledger & Budget Governor** | P0 | بودجهٔ توکن/ابزار/ایجنت/شرکت همراه با قطع سخت و Forecast هزینه. |
| **Eval Harness & Golden Dataset** | P0 | نمونه‌های واقعی، خطاهای تاریخی و سناریوهای تزریق prompt قبل از ارتقای استقلال. |
| **Secret Hygiene / DLP** | P0 | پاک‌سازی کلید/API، PII، اطلاعات مالی و محدودسازی خروج داده به LLM بیرونی. |
| **Immutable Audit + Time Sync** | P0 | تمام تصمیم‌ها، approvals، side effects و versionها با timestamp قابل اتکا. |
| **Idempotent Job Engine** | P0 | retry بدون دوباره‌اجرایی اثر جانبی؛ resume پس از قطع برق/کرش. |
| **Evidence-based Incident Center** | P1 | Incident ID، severity، acknowledgement، SLO، post-mortem. |
| **Knowledge Provenance & TTL** | P1 | حافظهٔ دانش سازمانی با منبع، کیفیت، expiry و روش حذف. |
| **Shadow Mode / Approval Replay** | P1 | اجرای تمرینی نقش جدید روی دادهٔ واقعی بدون اقدام، سپس مقایسه با انسان. |
| **Experiment Hub** | P1 | A/B، holdout، guardrail metrics، اثر واقعی بر Conversion/Revenue. |
| **Unified Identity + Passkey/MFA** | P1 | احراز هویت قوی، دستگاه‌های معتبر و session revoke. |
| **Offline Reading & Deferred Decisions** | P1 | گزارش قابل‌مشاهده بدون شبکه؛ اقدامات حساس فقط با اتصال و تأیید دوباره. |
| **Data Contract Monitor** | P1 | اگر معنی metric/API عوض شد، گزارش/اکشن متوقف شود. |
| **Policy-as-Code Tests** | P1 | هر تغییر مجوز در CI با تست قابل تکرار بررسی شود. |
| **Company Onboarding Wizard** | P2 | افزودن شرکت آینده همراه با template، budget، tools و policy جدا. |
| **Forecast/Scenario Lab** | P2 | سناریوسازی با دامنهٔ خطا و فرض صریح، نه پیش‌بینی قطعی. |
| **Office 2D/3D** | P3 | تجربهٔ نمایشی قابل خاموش‌کردن، فقط پس از موفقیت UI اصلی. |

### 2.2 نقش‌های سازمانی گمشده

- **Data Governance Lead [P0/P1]:** مالک تعریف هر KPI، lineage، کیفیت و retention.
- **AI Safety / Policy Officer [P0]:** مالک policy مستقل از CTO/CMO؛ حق veto.
- **Revenue Operations [P1]:** اتصال قیف ثبت‌نام/فعال‌سازی/پرداخت/تمدید به تحلیل قابل‌اتکا.
- **Experiment Lead [P1]:** طراحی آزمایش و جلوگیری از استنباط علّی اشتباه.
- **FinOps Analyst [P1]:** رصد budget burn و unit cost به‌ازای هر outcome.
- **Knowledge Librarian [P1]:** مالک Playbook و conflict resolution در حافظه.
- **Customer Trust & Compliance [P1]:** ادعاهای بازاریابی مالی، شکایات، دادهٔ خصوصی و محدودیت منطقه‌ای.
- **Incident Commander [P1]:** هماهنگی بین نقش‌ها؛ مسئولیت اجرا فقط طبق Action Policy.

### 2.3 ریسک‌های مهم مغفول

1. **Privilege Drift:** ایجنت طی چند ماه مجوزهای تجمعی می‌گیرد؛ راهکار: grants کوتاه‌عمر و بازبینی دوره‌ای.
2. **Token/Loop Storm:** retryها یا گفتگوهای دایره‌ای هزینهٔ زیاد می‌سازند؛ راهکار: max-step/depth/TTL و hard budget.
3. **False Causality:** رشد/افت SEO هم‌زمان با تغییر محصول الزاماً معلول آن نیست؛ راهکار: holdout و confidence interval.
4. **Correlated Failure:** ۱۰ ایجنت با یک مدل و یک منبع، یک اشتباه را تکرار می‌کنند؛ راهکار: evaluator مستقل و evidence check.
5. **Data Leakage:** محتوای کاربران، لاگ‌ها و کلیدها ممکن است به مدل بیرونی فرستاده شوند؛ راهکار: طبقه‌بندی داده، redaction و egress policy.
6. **Trading/Financial Harm:** توصیهٔ نادرست یا اجرای اشتباه می‌تواند زیان واقعی ایجاد کند؛ راهکار: مرز صریح advisory-only و عدم trading permission پیش‌فرض.
7. **Single Point of Failure:** سرور چهارم همزمان Gateway، DB و Workflow باشد؛ راهکار: backup/restore آزمایش‌شده و تفکیک بحرانی در زمان مناسب.
8. **Cross-company Contamination:** دانش، دسترسی و مخاطب شرکت‌ها مخلوط شود؛ راهکار: isolation سراسری حتی برای استفادهٔ داخلی.
9. **Approval Fatigue:** زیادبودن درخواست‌های تأیید باعث تأیید کورکورانه می‌شود؛ راهکار: تجمیع، risk budgets و اندازه‌گیری Decision Load.
10. **Vendor/Model Drift:** مدل‌ها قیمت، رفتار یا دسترسی‌شان تغییر می‌کند؛ راهکار: adapter، eval پیش از تغییر و version pinning.

## 3. معماری پیشنهادی تو (دیاگرام متنی + stack + دلیل هر انتخاب)

### 3.1 اصول معماری

1. **Control Plane واحد، Execution Plane محدود:** داشبورد و تصمیم در HQ؛ اجرای ابزار فقط از مسیر امن و سیاست‌دار.
2. **Stateless LLM / Stateful Platform:** «ایجنت» سرویس همیشه‌بیدار نیست؛ Run کوتاه‌عمر با وضعیت پایدار در DB/Workflow است.
3. **No Direct Network from LLM Workers:** فقط Tool Gateway حق برقراری ارتباط با مقصد مجاز را دارد؛ محدودیت شبکه و credential از هم مستقل باشند.
4. **Read-first, write-later:** فاز اول فقط خواندن از endpointهایی که مالک مجوز داده و صحت آن‌ها آزموده شده.
5. **Source of Truth مشخص:** UI، پیام و حافظهٔ Agent، منبع رسمی KPI/Policy نیستند.
6. **Defensive Degradation:** در قطع model/provider/target، سیستم fail-closed شود و فقط گزارش آخرین وضعیت **با برچسب stale** نمایش دهد.

### 3.2 دیاگرام مرزهای اعتماد

```text
                         CEO: Web / Android
                       Passkey/MFA + device check
                                  |
                             HTTPS / TLS
                                  |
                  +---------------v----------------+
                  | Coine HQ: CONTROL PLANE          |
                  |  API/BFF · Identity · Inbox      |
                  |  Cartable · Meetings · Reports   |
                  |  Policy Engine · Decision Log    |
                  +----------+-------------+---------+
                             |             |
                   +---------v----+  +-----v---------------+
                   | Postgres      |  | Durable Workflow     |
                   | Jobs, policy, |  | Scheduler/Temporal   |
                   | audit, ledger |  | queue, retry, timers |
                   | + pgvector    |  +----------+----------+
                   +--------------+             |
                                    +-----------v----------+
                                    | Ephemeral Agent Runs |
                                    | H/M/S model adapter  |
                                    | no direct secrets    |
                                    +-----------+----------+
                                                |
                                    typed tool requests only
                                                |
                                 +--------------v--------------+
                                 | TOOL GATEWAY / POLICY PEP    |
                                 | scope · DLP · quota · audit  |
                                 | schema · dry-run · timeout  |
                                 | deny-by-default + kill      |
                                 +------+------------+----------+
                                        |            |
                           approved TLS/mTLS         | approved APIs
                                        |            +-- GitHub RO/PR policy
                          Hetzner Private Network    +-- Search/Analytics/SEO
                          (NOT inherently encrypted) +-- Notifications/Channels
                                +-------+-------+
                                |       |       |
                              TradeYar  FX    Pro-Chart
                            read-only approved adapters
                            NO SSH, NO arbitrary SQL/exec
```

### 3.3 Stack اجرایی

| جزء | انتخاب | دلیل / شرط |
|---|---|---|
| API و BFF | `Python 3.12+ / FastAPI`, Pydantic | Typed contracts، سرعت توسعه، هم‌خانوادگی با دارایی‌های گزارش‌شده. |
| DB | `PostgreSQL` با RLS یا scope enforceشده + `pgvector` | Ledger تراکنشی + حافظهٔ برداری؛ vector تنها معیار بازیابی نیست. |
| Workflow | **انتخاب A:** Temporal Python SDK؛ **انتخاب B:** Postgres durable jobs + scheduler | A برای انتظار طولانی/branching؛ B برای MVP کوچک. انتزاع Workflow API ضروری است. |
| Queue/Cache | Redis در صورت نیاز واقعی؛ هرگز منبع نهایی Audit | کنترل burst و cache؛ از افزودن سرویس بدون ضرورت بپرهیزید. |
| Agent runtime | Role/Tool/Skill Registry + Model Router، provider adapters | جلوگیری از وابستگی انحصاری به یک SDK. |
| Tool execution | Gateway اختصاصی + ثبت Tool Manifest / allowlist MCP | اجرای سیاست خارج از prompt و مدل. |
| Policy | OPA/Cedar **یا** rule engine سادهٔ تست‌پذیر | در v1 قانون روشن typed کافی است؛ در رشد multi-company Policy-as-Code ترجیح دارد. |
| Web | Next.js App Router / PWA | اولویت دسترسی CEO با زمان ساخت کوتاه. |
| Android | Kotlin + Jetpack Compose، modular | تم و بستر هم‌خانوادهٔ محصول ذکرشده؛ **بدون تغییر ریپوی Pro-Chart**. |
| Live updates | SSE برای گزارش stream؛ WebSocket فقط برای voice/live bidirectional؛ FCM push | جلوگیری از پیچیدگی اتصال دائمی بی‌مورد. |
| Observability | OpenTelemetry traces + Prometheus-compatible metrics + Loki | اتصال lineage تصمیم/کار/API به هر `run_id`. |
| Identity | OIDC provider یا auth امن داخلی با Passkey/MFA؛ server-side sessions | اجرای حساس مستلزم step-up authentication. |
| Secret store | Vault/managed secret manager پس از ارزیابی Ops؛ حداقل secrets encrypted + rotation | Vault بدون نگهداری/Unseal/Backup درست خودش ریسک می‌سازد. |
| Object storage | S3-compatible، لینک کوتاه‌عمر، lifecycle | فایل گزارش، صوت و Evidence با حداقل دسترسی. |
| Deploy | Docker Compose برای پایلوت، CI تست امنیت، بعد split services | Kubernetes در این مرحله الزام ندارد. |
| Test | pytest، contract/integration tests، k6/Locust، fault injection | مخصوصاً تست no-write و no-duplicate. |

### 3.4 طرح اتصال سه محصول

**حالت A — بدون دسترسی سروری:** ابتدا از APIهای موجود (Prometheus query / Grafana read API / Alertmanager API / approved public metrics) **در صورت وجود و اجازهٔ مالک** استفاده شود؛ سرور مقصد تغییر نکند. دسترسی به GitHub صرفاً read برای تحلیل ساختار؛ نه نشانهٔ سلامت production.

**حالت B — نیاز به تغییر حداقلی:** برای هر محصول جداگانه `Change Request` ایجاد شود: service account محدود، read-only endpoint، firewall allowlist، TTL credential، timeout و روش بازگردانی. ساخت database role یا exporter بدون مجوز ممنوع.

**حالت C — اجرای عملیات:** فقط در فاز بعد و با approved action adapter؛ `restart_service`, `deploy`, `publish`, `change_price`, `send_campaign` هرکدام سیاست مستقل دارند. `deploy` بدون review و gate صرفاً بر اساس نظر Agent فعال نشود.

**نکتهٔ مهم دربارهٔ Hetzner:** Cloud Private Network، dedicated server با vSwitch و region/zone یکسان فرض‌شدنی نیستند. نحوهٔ اتصال سرور چهارم باید پس از پاسخ سؤال‌های مالک و بررسی مستندات رسمی تعیین شود. ارتباط خصوصی به معنای TLS نیست [S1].

### 3.5 معماری داده و قراردادهای حیاتی

```text
Entity: Company > Product > Environment > DataSource
Entity: AgentTemplate > AgentInstance > Grant > AgentRun
Entity: Goal > WorkOrder > WorkflowRun > ToolAction > Verification
Entity: Evidence > MetricDefinition > Observation > Decision > Outcome
Entity: Budget > CostEvent > Alert > Approval > Revocation
```

- **IDهای غیرقابل‌تغییر:** `company_id`, `product_id`, `agent_id`, `run_id`, `action_id`, `approval_id`, `source_id`.
- **هر Evidence:** `source_url/connector`, `fetched_at`, `source_updated_at`, `unit`, `time_window`, `query_hash`, `redaction_class`, `confidence_kind`.
- **هر اقدام:** `requested_by`, `effective_principal`, `policy_version`, `scope`, `dry_run_hash`, `approval_expires_at`, `idempotency_key`, `postcondition`.
- **حافظه:** چهار قسمت جدا: short-lived working context؛ conversation؛ verified playbooks؛ sourced company knowledge. دادهٔ یک شرکت در جست‌وجوی شرکت دیگر قابل بازیابی نباشد.
- **Retention پیشنهادی ابتدایی:** دادهٔ خام صوت ۷ روز یا تا حذف توسط مالک؛ transcript عملیاتی ۳۰ تا ۹۰ روز؛ audit امنیتی ۳۶۵ روز؛ هرکدام مشروط به قانون/قرارداد/رضایت مالک و سیاست نهایی. این اعداد **گزینهٔ پیشنهادی** هستند، نه تکلیف حقوقی.

### 3.6 منابع، ظرفیت و SLO شروع

- **پایلوت یک‌نودی:** `8 vCPU / 16 GB RAM` در سطح CPX42، فضای SSD مطابق پلن/region، به‌علاوهٔ off-site backup و monitoring بیرونی؛ برای **۲ تا ۵ اجرای هم‌زمان** تحت بار آزموده‌شده. این سقف **benchmark تأییدشده نیست**.
- **عملیات سبک دومرحله‌ای:** یک node API/Worker با `8 vCPU / 16 GB` و یک node داده/پشتیبان با `4 vCPU / 8 GB`؛ برای production جدی DB replica یا managed DB با تست failover اضافه شود. **دو VM به‌تنهایی HA واقعی نیست.**
- **SLO پیشنهادی پس از پایدارشدن:** ۹۹٫۵٪ دسترسی HQ در ماه؛ ۹۹٪ انجام موفق کارهای low-risk در زمان هدف؛ `0` اجرای side effect بدون Grant معتبر؛ ۱۰۰٪ اقدامات نوشتنی دارای Audit و Idempotency Key.
- **قید عملکرد:** آستانهٔ Gate برای مقصدها، با `p95 latency`, CPU, memory, error rate و budget تعیین شود؛ اگر Telemetry معتبر نیست، **write بسته** و read throttled باشد.
- **بازیابی:** هدف اولیه `RPO <= 24h`, `RTO <= 8h` برای پایلوت؛ برای production تصمیم CEO دربارهٔ RPO ۱ ساعت / RTO ۲ ساعت نیازمند معماری و هزینهٔ بیشتر است.

### 3.7 تصمیم فنی پیشنهادی برای آغاز

`P0`: Data/Policy/Action Contracts و یک Vertical Slice از «هشدار واقعی → Evidence → پیشنهاد → Cartable → تصمیم CEO → ثبت». سپس الگوی قابل تکرار برای تمام دپارتمان‌ها. **به‌جای ساخت یک‌بارهٔ ۵۰ Agent، یک خط کامل end-to-end بسازید.**

## 4. کاتالوگ کامل کارمندان ایجنت (جدول: دپارتمان | سمت | شرح وظایف | KPI | ابزارها | سطح استقلال اولیه | مدل پیشنهادی)

**تعاریف:** `D` = Rule-based/SQL بدون LLM؛ `S` = مدل سبک برای خلاصه‌سازی/طبقه‌بندی؛ `M` = مدل میانی برای تحلیل؛ `H` = مدل قوی برای تصمیم پیچیده. نمونه‌های نرخ قابل سنجش در بخش ۱۰: Claude Haiku 4.5 (`S`)، Sonnet 4.6 (`M`)، Opus 4.8 (`H`)؛ این **نام‌گذاری معماری** است، نه الزام به Vendor. همهٔ نقش‌ها ابتدا بدون مجوز نوشتن به production هستند، حتی اگر L2 ذکر شود. `L2` به معنای «انجام **پس از تأیید** در Action Catalog» است. ۳ SEO/GEO باید **۳ instance** با دامنهٔ محصول جدا داشته باشند.

| دپارتمان | سمت | شرح وظایف | KPI | ابزارها | سطح استقلال اولیه | مدل پیشنهادی |
|---|---|---|---|---|---|---|
| راهبری | Chief of Staff **غیراجباری/پشت‌صحنه** | تنها تجمیع KPI/برنامه، بدون واسطه‌گری در مکالمه | دقت گزارش، زمان CEO | Data API, Decision Registry | L1 | M |
| راهبری | Strategy Analyst | تحلیل برنامه/سناریو و فرض‌ها | تحقق OKR، دقت فرض | Metrics, Scenario Lab | L1 | H |
| فنی | CTO Agent | تخصیص کار و مرور معماری | SLO، change failure rate | Registry, Metrics, GitHub RO | L1 | H |
| فنی | SRE — TradeYar | هشدارها و ظرفیت سرویس TradeYar | MTTD، false alerts | Prometheus/Loki scoped | L1 | S/M |
| فنی | SRE — CoinePro-FX | پایش feed, engine, MT5-related telemetry | MTTD، missed incidents | Metrics scoped | L1 | S/M |
| فنی | SRE — Pro-Chart | پایش web/app backend طبق منابع تأییدشده | uptime، latency | Approved metrics | L1 | S/M |
| فنی | Incident Commander | اولویت، هماهنگی و گزارش Incident | MTTA، MTTR | Alertmanager, Incident | L1 | M |
| فنی | Code Review Agent | تحلیل PR و ریسک تغییر | review precision | GitHub read/PR | L1 | H |
| فنی | Test/QA Engineer | ساخت تست، regression و reproduction | escaped defect rate | CI read, test sandbox | L1 | M |
| فنی | Release Manager | طراحی change window و rollback | change success | CI status, runbooks | L1 | M |
| فنی | Security Analyst | شناسایی ناهنجاری و policy violation | valid security findings | Audit, alerts | L1 | H |
| داده | Head of Data | تعریف و تأیید KPI و lineage | metric consistency | Source registry, SQL templates | L1 | H |
| داده | Data Quality Monitor | drift، gap و stale metric | freshness، error rate | Data contracts | L1 | D/S |
| داده | Knowledge Librarian | مرور Playbook و منابع | verified reuse rate | Knowledge registry | L1 | M |
| کوانت | Head of Quant | سیاست کیفیت سیگنال و ریسک | calibration، risk-adjusted metrics | Read-only quant data | L1 | H |
| کوانت | TradeYar Signal QA | پایش سیگنال کریپتو با هزینه و افق زمانی | false signals، drift | Signals RO, reports | L1 | M |
| کوانت | FX Signal QA | پایش سیگنال طلا/فارکس | risk-adjusted outcomes | FX RO, reports | L1 | M |
| کوانت | Backtest Auditor | رصد look-ahead، survivorship و overfit | invalid backtest rate | Backtest artifacts RO | L1 | H |
| کوانت | Risk Watcher | هشدار drawdown، latency، exposure | time-to-alert | Risk metrics RO | L1 | D/S |
| کوانت | Paper/Live Divergence | تشخیص اختلاف paper و live | divergence detection | Read-only ledgers | L1 | M |
| رشد | CMO Agent | هدف‌گذاری کانال‌ها و بودجه | incremental CAC/LTV | Analytics, CRM aggregate | L1 | H |
| رشد | SEO/GEO — TradeYar | سئوی trade-future.ir | nonbrand qualified traffic | Search Console, analytics | L1 | M |
| رشد | SEO/GEO — CoinePro-FX | سئوی coineprofx.com | lead-to-paid organic | Search Console, analytics | L1 | M |
| رشد | SEO/GEO — Pro-Chart | سئوی pro-chart.com | qualified app installs | Search Console, Play data | L1 | M |
| رشد | Content Strategist | تقویم محتوا و زاویهٔ محتوایی | attributed conversions | Content inventory, search | L1 | M |
| رشد | Content Writer | پیش‌نویس محتوا با citations | approved factual posts | Docs draft, retrieval | L1 | M |
| رشد | GEO Citation Auditor | بررسی ذکر/استناد برند در پاسخ مدل‌ها | valid mention share | Search samples, evidence | L1 | S/M |
| رشد | Social Media Manager | پیش‌نویس پست/CTA و پاسخ امن | qualified leads | Social APIs draft | L1 | M |
| رشد | Ads Planner | پیشنهاد آزمایش تبلیغ و بودجه | incremental ROAS | Ads read, analytics | L1 | H |
| رشد | Creative Analyst | تحلیل عملکرد هوک و کاور | retention، CTR | Media metrics | L1 | M |
| رشد | Conversion Analyst | کشف نشت قیف و آزمایش | paid conversion uplift | Analytics, Experiments | L1 | M |
| رشد | Competitive Intel | تغییرات قابل‌اثبات رقبا | useful alerts/month | Public web, registry | L1 | M |
| فروش | CSO Agent | برنامهٔ فروش/نگهداشت | net revenue retention | CRM aggregates | L1 | H |
| فروش | Lead Qualification | امتیاز lead بدون تبعیض | qualified lead precision | CRM RO, form data | L1 | S/M |
| فروش | VIP Sales Advisor | آماده‌سازی پیام و پاسخ امن | verified close-rate uplift | CRM, product FAQ | L1 | M |
| فروش | Support Triage | دسته‌بندی درخواست و ارجاع | first response time | Ticketing, knowledge | L1 | S |
| فروش | Retention Specialist | تحلیل علت لغو اشتراک | churn reduction vs holdout | Billing RO, cohorts | L1 | M |
| فروش | Affiliate Operations | سنجش سلامت ارجاع و کمیسیون | verified payout accuracy | Affiliate ledger RO | L1 | M |
| محصول | CPO Agent | اولویت‌بندی roadmap و trade-off | outcome per release | Product metrics, feedback | L1 | H |
| محصول | PM — TradeYar | تحلیل کاربرد و بازخورد | activation/retention | Events, support | L1 | M |
| محصول | PM — CoinePro-FX | تحلیل قیف و feature adoption | paid adoption | Events, support | L1 | M |
| محصول | PM — Pro-Chart | کیفیت تجربهٔ موبایل | crash-free users | Play reviews, telemetry | L1 | M |
| محصول | UX Researcher | دسته‌بندی pain pointها | validated issue count | Interviews/tickets | L1 | M |
| محصول | Experiment Lead | طرح و تحلیل A/B + guardrail | valid experiments | Experiment registry | L1 | H |
| مالی | CFO Agent | برآورد هزینه و سود با منابع | forecast error | Billing reports, cost | L1 | H |
| مالی | Subscription Analyst | ردیابی درآمد/تمدید | reconciliation accuracy | Billing RO | L1 | D/M |
| مالی | AI FinOps | هزینهٔ مدل‌ها و ابزارها | $/verified outcome | Token ledger | L2 صرفاً تنظیم سقف مجاز | D/S |
| مالی | Infrastructure FinOps | ظرفیت/هزینهٔ سرور | infra cost per workload | Provider invoices RO | L1 | S/M |
| نظارت | Inspector General | داوری مستقل نتیجهٔ ایجنت‌ها | incident escape rate | Audit, decisions | L1 | H |
| نظارت | Evidence Fact-checker | تطبیق ادعا با منبع | unsupported claim rate | Evidence registry | L1 | M |
| نظارت | AI Safety Officer | veto روی کار پرخطر و نقص مجوز | unauthorized action count | Policy/audit | L1 | D/H |
| نظارت | Privacy/Compliance Reviewer | بررسی داده/ادعاهای مالی/قانونی | DLP violations | DLP, content drafts | L1 | H |
| منابع انسانی | HR/Agent Ops Lead | تعریف شغل، آزمون، پیشنهاد ارتقا | eval-pass adjusted performance | Agent registry, Evals | L1 | M |
| منابع انسانی | Workforce Planner | ادغام/تقسیم نقش و کنترل ظرفیت | $/task و queue wait | Workload stats | L1 | M |
| جلسات | Debate Moderator **سیستمی** | نوبت‌دهی، سقف هزینه، خروجی جلسه | budget compliance | Deterministic workflow | L0 | D |
| ارتباطات | Briefing Producer | گزارش صبحگاهی متنی/صوتی | accuracy، time saved | Report API, TTS | L1 | S |

**قواعد فعال‌سازی:**

- *روز افتتاح:* ۸ تا ۱۲ نقش از جمله CTO، سه SRE، Security، AI Safety، Evidence Auditor، Briefing، CMO و یک SEO آزمایشی. تعداد «Templateهای موجود در بازار استخدام» می‌تواند بیش از تعداد «Agentهای فعال» باشد.
- *ماه ۳:* ۲۰ تا ۳۰ instance ثبت‌شده، نه الزاماً اجرای هم‌زمان. ابتدا فقط ۳ SEO/GEO پس از دریافت مجوز دادهٔ مربوط فعال شوند.
- *ماه ۶:* ۳۵ تا ۵۰ نقش/instance در صورت موفقیت Eval و توجیه اقتصادی؛ تعداد Workerها با اندازهٔ queue و هزینه تنظیم شود.
- *همهٔ زمان‌ها:* AI Safety Officer و Inspector هیچ مجوز معامله، برداشت دارایی یا دسترسی secret خام ندارند؛ حتی CTO Agent هم ندارد.
- *عنوان‌های مدیریتی:* «H» فقط برای جلسات مهم/تصمیم دشوار؛ مدیر در کارهای روتین باید با D/S کار کند، نه مدل قوی به‌طور دائمی.

## 5. سیستم جلسات (اصلاحات و افزوده‌ها)

### 5.1 قالب جلسه به‌صورت Workflow

`Trigger → Agenda Builder → Evidence Freeze → Role Briefs → Independent Challenge → Decision Options → Policy Gate → CEO Approval if needed → Tasks → Outcome Check`

- **Evidence Freeze:** هر شرکت‌کننده از یک snapshot با `as_of` مشخص استفاده کند تا تضاد داده در جلسات کم شود.
- **ادعای بی‌منبع:** برچسب `UNVERIFIED` و عدم‌استناد در مصوبه. عدد مثال، عدد واقعی تلقی نشود.
- **حفظ مخالفت:** Red Team مستقل از مدیر جلسه حداقل یک توضیح جایگزین و یک ریسک شکست بدهد؛ مجبور نیست نظر منفی ساختگی تولید کند.
- **سقف مالی اولیه:** روزانه ۱ جلسهٔ غیرهمزمان/دپارتمان؛ جلسهٔ هیئت‌مدیره ۱ بار/هفته، حداکثر ۱۰–۱۵ دقیقه محتوای متنی و سقف ۸–۱۵ دلار *ماهانه* برای مدل‌های جلسات در پایلوت به‌عنوان Budget آزمایشی؛ پس از اندازه‌گیری تنظیم شود.
- **سقف مکانیزمی:** ۲ دور بحث، حداکثر ۶ شرکت‌کنندهٔ AI در یک نشست P1، ۱ داور مستقل و termination اجباری. اعداد قراردادیِ قابل تنظیم‌اند.

### 5.2 فرمت اجباری هر مصوبه

```yaml
id: DEC-000142
company_id: coine
product_id: tradeyar
question: "What should we do about organic traffic?"
facts:
  - metric_id: organic_sessions
    source_id: gsc_tfy
    observed_at: "<ISO-8601>"
    validity: verified
alternatives:
  - do_nothing_and_measure
  - fix_performance_after_root_cause_check
recommendation: investigate_first
estimated_cost_usd: 0
risk: low
confidence: 0.64 # subjective; evaluate calibration later
policy_required: read_only
human_approval: false
owner: cmo-agent
review_due: "<ISO-8601>"
status: proposed
```

این YAML **نمونهٔ ساختار** است و هیچ‌یک از فیلدهای عددی آن دادهٔ واقعی Coine نیست.

### 5.3 پیشنهاد اضافه برای انواع جلسه

| جلسه | زمان/Trigger | شرکت‌کنندگان | قاعده |
|---|---|---|---|
| Daily Ops Snapshot | هر روز | SRE، Data QA، CTO | داده‌محور، بدون مناظره |
| Weekly Board | هفتگی | CTO، CMO، CPO، CFO، Quant، Inspector | ۳ تصمیم حداکثر در نسخهٔ اول |
| Incident War Room | `SEV1/SEV2` | Incident Commander + مرتبط‌ها | توقف اقدامات پرخطر، Owner واحد |
| Monthly Strategy | ماهانه | مدیران + CEO اختیاری | OKR و بودجه، با مقایسهٔ ماه قبل |
| Experiment Review | پایان هر آزمایش | CMO/CPO/Data | uplift و guardrail؛ حذف cherry-picking |
| Access Review | ماهانه | AI Safety، Security، CEO برای ریسک بالا | revoke/renew هر grant |
| Forecast Calibration | ماهانه | CFO، Strategy، Inspector | مقایسهٔ پیش‌بینی و نتیجه، Brier Score در رخدادهای دودویی |
| Post-mortem | پس از incident مهم | مرتبط‌ها | اقدام پیشگیرانه، بدون تنبیه نمایشی |

### 5.4 تجربهٔ جلسه در اپ

جلسهٔ زنده باید `Live transcript`, `Evidence Drawer`, `Ask this Director`, `Object`, `Veto`, `Pause`, `Approve with conditions` و `Export minutes` داشته باشد. «تأیید صوتی در جلسه» **فقط بیان قصد است**؛ برای اکشن حساس باید در Cartable با MFA/biometric و نمایش دقیق Diff دوباره ثبت شود. تصمیم‌های پیشین با `Decision Outcome` بازسنجی شوند.

## 6. UI/UX اپ اندروید و وب (لیست صفحه‌ها + جریان‌های اصلی + اصول طراحی)

### 6.1 صفحات پیشنهادی

| صفحه | ارزش برای CEO | اولویت |
|---|---|---|
| **Command Center** | سه وضعیت اصلی: Product Health، Growth/Revenue، Agent Safety/Cost | P0 |
| **Cartable** | تأیید/رد/اصلاح با نمایش اثر و ریسک و منبع | P0 |
| **Direct Messages** | ارتباط مستقیم با هر Agent و گروه دپارتمان | P1 |
| **Active Work** | همهٔ Runها، Owner، Deadline، Cost، blocker | P0 |
| **Agents & Hiring** | بازار Template، رزومه، قابلیت، بودجه، hire/pause/fire | P1 |
| **Company/Product Switcher** | مرز شرکت/محصول در کل اپ | P0 |
| **Alerts & Incidents** | وضعیت، اثر بر کاربران، آنچه متوقف شده | P1 |
| **Decisions & Audit** | سوابق تصمیم، دلیل، شواهد، rollback | P0 |
| **Evidence & Metrics** | نمودار همراه با منبع و freshness | P1 |
| **Goals/OKRs** | نتایج کلان و نسبت پیشرفت به هزینه | P1 |
| **Meetings Room** | جلسات متنی، transcript، صورت‌جلسه | P1 |
| **Budget & FinOps** | burn rate و بودجهٔ هر دپارتمان | P0 |
| **Voice Inbox / Calls** | پیام صوتی و تماس زنده در مرحلهٔ بعد | P1/P2 |
| **Skills & Playbooks** | چرخهٔ دانش و نسخه‌های معتبر | P1 |
| **Policy & Access** | grants، محرمانگی، مجوزهای موقت | P0 |
| **Time Machine** | آنچه از آخرین حضور CEO تغییر کرده | P2 |
| **Company Onboarding** | شرکت جدید/دامنهٔ داده/پلن هزینه | P2 |
| **Virtual Office** | نمایش اختیاری 2D/3D | P3 |

### 6.2 جریان‌های اصلی

1. **هدف‌دهی:** CEO می‌نویسد «نرخ تبدیل ثبت‌نام TradeYar را بهبود بده» → سیستم Company/Product را تأیید می‌کند → مدیر برنامه با baseline، هزینه، خطر و روش سنجش می‌دهد → CEO سقف را یک‌بار تصویب می‌کند → Runهای محدود شروع می‌شوند → گزارش uplift با Evidence می‌آید.
2. **استخدام:** `Hire` → انتخاب Template → مشاهدهٔ Effective Permissions و هزینهٔ تقریبی → تعیین Scope/TTL → Trial L0/L1 → فعال‌سازی schedule → پیش‌نمایش اولین Run؛ **یک کلیک در UI، اما پشت صحنه دارای Policy Validation**.
3. **Incident:** هشدار → dedup → تشخیص شدت با منبع → Incident Card → پیشنهادهای safe read-only → اگر نوشتن لازم است Approval Card → verify بعد از اقدام → post-mortem.
4. **تصمیم سریع:** Push شامل عنوان و شدت بدون دادهٔ حساس → بازکردن اپ → نمایش Diff, affected products, reversibility, cost → approve/reject با step-up auth → confirmation receipt.
5. **گفتگوی ویس:** Press-to-talk → transcript قابل ویرایش → ارسال → Agent پاسخ با لینک منبع → TTS اختیاری → ذخیرهٔ محدود و قابل حذف.
6. **وقفه و خروج:** CEO روی `Pause Department` می‌زند → Scheduler جلوی Run جدید را می‌گیرد → Tool Gateway همهٔ action tokenهای مربوط را invalidate می‌کند → Runهای درحال‌اجرا safe cancel می‌شوند → وضعیت واقعی در UI نمایش داده می‌شود.

### 6.3 زبان طراحی

- **پالت:** Dark/Gold با طلایی برای برند و تأییدهای مهم، نه رنگ تمام نمودارها. Severity با متن/آیکون علاوه بر رنگ.
- **فارسی RTL واقعی:** navigation، digit formatting، تقویم انتخابی شمسی/میلادی؛ timestampهای پایگاه داده UTC و نمایش براساس timezone کاربر.
- **فونت:** IRANYekanX فقط در صورت وجود License استفادهٔ مجاز در پروژهٔ جدید؛ فونت جایگزین متن‌باز در صورت نبود مجوز.
- **Desktop:** پنل ۳ستونه `Navigation / Work / Evidence`؛ **Android:** Bottom Navigation چهار بخش Command/Cartable/Agents/Inbox + shortcut Voice.
- **نمودار:** همیشه `source`, `updated at`, unit و مقایسهٔ بازه؛ اعداد قدیمی با برچسب Stale.
- **دسترسی‌پذیری:** کنتراست مناسب، target لمسی حداقل حدود ۴۸dp، اندازهٔ فونت پویا، transcription به‌جای Voice اجباری.
- **امنیت UI:** no secrets in push؛ secure screens برای دادهٔ حساس؛ biometric تنها step-up محلی است و مجوز سرور را جایگزین نمی‌کند.
- **شاخص UX:** `time_to_decision`, `unnecessary_interruptions/day`, `time_to_find_evidence`, `false_approve_rate`, `daily CEO attention minutes`.

## 7. ویس (ورودی/خروجی/تماس زنده — گزینه‌های فنی برای فارسی)

### 7.1 پیشنهاد معماری سه‌مرحله‌ای

`Audio → VAD/Noise Control → STT(fa-IR) → Editable Transcript → Policy/Agent → Verified Text → TTS(fa-IR) → Audio`.

**اول از Push-to-talk استفاده کنید** تا CEO بتواند متن شناسایی‌شده را پیش از فرمان حساس اصلاح کند؛ «میکروفون همیشه روشن» در نسخهٔ اول ممنوع. پاسخ صوتی باید همراه Transcript و citations باقی بماند.

### 7.2 گزینه‌های فنی و روش انتخاب

| بخش | گزینه | دلیل و خطر | اولویت |
|---|---|---|---|
| STT | **Azure Speech** با پشتیبانی `fa-IR` | گزینهٔ رسمی برای تست فارسی؛ باید با لهجه و واژگان کریپتو/فارکس سنجیده شود [S2] | P1 |
| STT | **Google Cloud STT** با `fa-IR` | رقیب benchmark روی همان فایل‌های تست؛ availability براساس region/model بررسی شود [S3] | P1 |
| STT | مدل Whisper-family / APIهای Speech | گزینهٔ مقایسه؛ صحت فارسی تخصصی را از نام مدل نتیجه نگیرید | P1 |
| TTS | **Azure Neural TTS** با voiceهای `fa-IR-FaridNeural` و `fa-IR-DilaraNeural` | صدای فارسی آماده؛ ارزیابی طبیعی‌بودن، تلفظ و هزینه [S2] | P1 |
| TTS | سایر APIهای TTS با پشتیبانی فارسی اثبات‌شده | voice quality، license، latency و failover | P2 |
| Live | WebRTC + Realtime voice API یا STT streaming → LLM → TTS streaming | مکالمهٔ دوطرفه، قطع‌کردن صحبت، latency، هزینهٔ بیشتر و پیچیدگی auth | P2 |
| جلسهٔ چندصدا | server-side scripted TTS + پخش نوبتی | ارزان‌تر و قابل بررسی‌تر از چند جلسهٔ Realtime هم‌زمان | P2 |

### 7.3 پروتکل تست فارسی قبل از خرید/انتخاب

- مجموعهٔ دست‌کم **۱۰۰ فایل کوتاه** از لهجه‌های متفاوت، جملات فارسی/انگلیسی، اسم محصول، ارز، عدد و درصد؛ رضایت و حذف فایل خام مشخص شود.
- **STT:** WER/CER، خطای عدد/قیمت/دستور منفی، نرخ اصلاح دستی و p95 latency. برای **دستور حساس** هیچ WER متوسطی تضمین امنیت نمی‌کند: باید اعداد و نام عملیات با متن روی صفحه بازتأیید شوند.
- **TTS:** امتیاز طبیعی‌بودن با ۱۰ ارزیاب فارسی‌زبان (در صورت دسترسی)، تلفظ برندها و تأخیر اولین صدا.
- **هدف اولیهٔ محصولی:** دست‌کم ۹۵٪ فرمان‌های روزمره پس از بازبینی transcript قابل فهم باشند؛ پاسخ صوتی عادی در شرایط آزمون با `p95 < 5s` شروع شود. این‌ها اهداف آزمون‌اند، نه تضمین provider.
- **اجازهٔ نوشتن:** هیچ دستور گفتاری مستقیم به `deploy`, `trade`, `withdraw`, `delete`, `price change` وصل نشود. همیشه Preview + تأیید در UI.

### 7.4 بودجهٔ صوت

برای پایلوت، فرض **۲۰۰ دقیقه Voice در ماه** به‌صورت STT/TTS جدا؛ ذخیرهٔ کوتاه‌مدت فایل و هزینهٔ provider را در Cost Ledger جدا ثبت کنید. برای live call، قیمت براساس دقیقه یا audio token/provider متفاوت است؛ هیچ تخمین واحد را بدون نمونهٔ مصرف واقعی قطعی نکنید. منبع قیمت نمونهٔ Realtime: [S4].

## 8. امنیت، دسترسی و ریسک‌ها (با راهکار)

### 8.1 ماتریس ریسک

| خطر | اثر | کنترل الزامی | سطح |
|---|---|---|---|
| Prompt Injection از وب/پیام کاربر/لاگ | سرقت داده یا فرمان ناخواسته | همهٔ ورودی‌های خارجی untrusted، tool allowlist، output validation، عدم اجرای متن خام | بحرانی |
| دسترسی فراتر از Scope | تغییر/خواندن شرکت اشتباه | ABAC بر پایهٔ agent/action/product/data class + short-lived grants | بحرانی |
| Leakage کلید/API/PII | زیان امنیتی و حریم خصوصی | redaction، secret vault، outbound DLP، log scrubbing و no raw secret in prompt | بحرانی |
| اجرای مکرر یک اکشن | ارسال/انتشار/پرداخت تکراری | idempotency، outbox pattern، retries با condition | زیاد |
| عملیات ترید/برداشت | زیان پولی/حقوقی | default deny؛ حتی L4 حق معامله/برداشت ندارد مگر طراحی حقوقی و مجوزهای جداگانهٔ آینده | بحرانی |
| تغییر production بدون تأیید | قطعی/bug | GitHub PR-only، branch protection، CI، human approval و deploy gate | بحرانی |
| فشار روی سرورهای فعلی | اختلال مشتری | query budget، timeouts، circuit breaker، health gate، load tests با اجازه | زیاد |
| نشت بین شرکت‌ها | افشای داده | tenancy scoping در DB/search/cache/object storage؛ cross-tenant tests | بحرانی |
| سوءاستفاده از Push/Telegram | phishing یا approval spoof | signed deep links، push بدون دادهٔ محرمانه، step-up approval only in app | زیاد |
| سرور HQ تنها | توقف کل هلدینگ AI | backup مستقل، restore drill، observability بیرونی، manual fallback | زیاد |
| وابستگی به provider | توقف/افزایش هزینه | routing adapter، quota، fallback با eval، disable agent on failure | متوسط/زیاد |
| ادعای گمراه‌کنندهٔ مالی | ریسک مشتری/حقوقی | review حقوقی، claim library، evidence و ممنوعیت وعدهٔ بازده | زیاد |

### 8.2 سیاست اکشن‌ها — پیشنهادی

| کلاس | مثال | سیاست ابتدایی |
|---|---|---|
| A0: Observe | health metric، draft report | خودکار با rate limit و scope |
| A1: Propose | PR draft، content draft، campaign plan | خودکار؛ فقط پیش‌نویس |
| A2: Reversible Low-risk | ویرایش داخلی سند HQ، تنظیم زمان‌بندیِ غیرحساس | L2 با سقف و در صورت لزوم approval |
| A3: External/Production | انتشار پست، ارسال پیام به مشتری، restart، deploy، تغییر قیمت | نیاز به تأیید صریح موردی و policy فنی |
| A4: Irreversible/Financial | withdrawal، trade order، انتقال پول، حذف backup، تغییر IAM اصلی | **ممنوع برای AI در v1**؛ بازکردن آن پروژهٔ مستقل با review حقوقی/امنیتی است |

**قاعدهٔ افزایش استقلال:** L3/L4 فقط برای اکشن‌های A0–A2 در محدودهٔ دقیق؛ کلاس A3/A4 را Level نمی‌تواند دور بزند.

### 8.3 معماری IAM و Approval

- `CEO` یگانه owner نهایی؛ `Agent Manager` اجازهٔ تعریف تسک دارد، نه grant privilege جدید خارج از سقف.
- تفکیک `requester != approver` برای تغییرات پرخطر؛ در صورت تک‌نفره‌بودن شرکت، approval با `step-up MFA + cooling-off + exact diff` اجرا شود.
- Approval Token به **hash جزئیات همان اقدام** bind و پس از TTL، تغییر Diff یا یک بار مصرف باطل شود.
- **Kill Switch دو لایه:** توقف Scheduler و revoke همهٔ action grants در Gateway؛ فرآیندهای درحال‌اجرا cancellation و رسید نهایی بدهند. برای اقدام برگشت‌ناپذیر از پیش اجراشده، Kill Switch اثر گذشته را برنمی‌گرداند.
- session revocation، device inventory، auditهای غیرقابل‌ویرایش از اپ، secret rotation دوره‌ای و break-glass دستی با logging.

### 8.4 آزمایش و آمادگی Incident

- حداقل ۳۰ سناریوی adversarial شامل prompt injection، دادهٔ قدیمی، corrupt metric، server timeout، دوبار submit، recursive task، خرج بیش از سقف و دسترسی cross-company.
- تست `no direct SSH`, `no outbound except gateway`, `no prod DB mutation`, `no transaction execution` در CI و environment staging.
- **Backup != Restore:** ماهانه بازیابی آزمایشی از نسخهٔ مستقل و سنجش RTO/RPO.
- `SEV1` باعث freeze خودکار همهٔ عملیات نوشتنی مرتبط و Alert به CEO می‌شود؛ فرایند دستی برای incident واقعی مستندسازی شود.
- قانون و حوزهٔ فعالیت محصولات مالی ممکن است به مجوزها، privacy و disclosure نیاز داشته باشد. این بررسی فنی جای مشاورهٔ حقوقی منطقهٔ فعالیت کاربران را نمی‌گیرد.

## 9. نقشه‌ی راه ماه‌به‌ماه (۱۲ ماه، با خروجی و معیار موفقیت هر ماه)

**فرض زمان‌بندی:** شروع تنها پس از تصویب فاز صفر، تیم پایهٔ **۱ Senior Backend/AI، ۱ Full-stack، ۰٫۵ DevOps/Security و ۰٫۵ Android/UX** (حدود ۳ FTE). بدون این نیروها تاریخ‌های زیر صرفاً ترتیب مطلوب‌اند. ماه ۰ جداگانه دو هفتهٔ Discovery/Planning است. هیچ تیم یا دسترسی فعلی تأیید نشده است.

| ماه | خروجی عملیاتی | معیار عبور / KPI | وابستگی اصلی |
|---|---|---|---|
| **۰ — تصمیم** | Vision, ADR, asset inventory, risk charter, threat model, wireframes, budget cap | تأیید مکتوب CEO برای Scope، اتصال و ممنوعیت‌ها | پاسخ بخش ۱۲؛ بدون تغییر سرور |
| **۱ — HQ Observability Pilot** | Web shell، هویت، Cartable، Agent registry، Audit، یک connector read-only تأییدشده، health dashboard | ۱۰۰٪ اقدامات ثبت؛ ۰ تغییر بدون مجوز؛ گزارش حداقل ۱ منبع واقعی | دسترسی مجاز و بررسی شبکه |
| **۲ — سه محصول و کارتابل** | تکمیل connectorهای مجاز، source registry، alert grouping، briefing، budget ledger | حداقل ۹۵٪ health checks در پنجرهٔ تست معتبر؛ هر عدد دارای provenance | ظرفیت endpointهای واقعی |
| **۳ — Growth Cell** | CMO، ۳ SEO/GEO scoped، محتوا به‌شکل draft، KPI baseline و Android beta سبک | ۳ گزارش مستقل سایت؛ ۰ انتشار خودکار؛ نرخ خطای factual <۵٪ در نمونهٔ ممیزی | Search Console/Analytics مجاز |
| **۴ — Durable Operations** | Workflow long-running، recurring jobs، idempotency، trial L2 برای کارهای داخلی | >۹۸٪ job recovery در fault test؛ ۰ side effect تکراری در تست | تصمیم Temporal/Job Engine |
| **۵ — Quant & Product Insight** | Risk watcher، signal QA read-only، PMها، data contract monitoring | ۳ سنجهٔ validated/محصول؛ هشدارهای نادرست ثبت و کاهش روندی | metric definitions و data access |
| **۶ — Board & Eval Gate** | Weekly Board، Red Team، decision registry، Eval harness، role promotions | ۱۰۰٪ تصمیم‌های اقدام‌دار دارای Owner/Evidence؛ ۳۰ shadow-run/نقشِ ارتقا یافته | Evidence Ledger و policies |
| **۷ — Voice & CEO Experience** | Persian STT/TTS نهایی‌شده، voice briefing، Time Machine | تست ۱۰۰ نمونهٔ صوت؛ ثبت p95 latency و نرخ اصلاح؛ بدون اجرای صوتی حساس | privacy/voice vendors |
| **۸ — Revenue Experiments** | Funnel measurement، ۱–۲ تست A/B، Ads planner فقط پیشنهاد | حداقل ۱ آزمایش با guardrail و نتیجهٔ قابل‌استناد | حجم نمونهٔ کافی؛ no forced uplift |
| **۹ — Reliability & Access Review** | DR drill، capacity tests، permission simulator، grant expiry | بازیابی backup طبق RTO/RPO تصویب‌شده؛ ۰ grant منقضیِ فعال | off-site backups |
| **۱۰ — Multi-company Template** | Company onboarding template و boundary tests | شرکت آزمایشی synthetic بدون leakage؛ onboarding زیر ۱ روز | tenure/isolation readiness |
| **۱۱ — Limited Autonomy** | L3 محدود برای A0–A2، policy automation، cost optimization | کاهش ≥۲۰٪ زمان تأیید کارهای کم‌خطر نسبت به baseline؛ ۰ نقض policy | Eval + CEO sign-off |
| **۱۲ — Business Audit & v2** | P&L افزایشی، forecast calibration، ADRهای نسخهٔ ۲، تصمیم SaaS | ROI شفاف با holdout، burn control، فهرست stop/start/scale | گزارش درآمد/هزینهٔ معتبر |

**گیت‌های بدون تاریخ تضمینی:** انتقال از L1 به L2 صرفاً بعد از عبور از Eval؛ اضافه‌کردن موتور Signals فقط read-only؛ live voice/3D/Digital Twin تا زمانی که محصول هسته استفادهٔ واقعی و پایدار نداشته باشد، مؤخر است. اگر تیم یک توسعه‌دهنده باشد، نسخهٔ عملیاتی کامل احتمالاً **۹–۱۵ ماه یا بیشتر** لازم دارد؛ اگر تیم باتجربهٔ ۴–۶ نفره باشد، محدودهٔ ۶–۱۰ ماه برای بسیاری از قابلیت‌های `P0/P1` ممکن است، نه الزاماً کل vision.

## 10. بیزینس‌پلن و مدل هزینه (برآورد ماهانه با فرض‌های صریح)

### 10.1 فرض‌ها و مراجع قابل راستی‌آزمایی

- **محصول:** ابزار داخلی با ۱ CEO، نه SaaS عمومی. تعداد Agent Templateها هزینهٔ LLM ندارد؛ فقط Runهای انجام‌شده هزینه دارند.
- **مدل اجرا:** فراخوانی API خارجی؛ **GPU اختصاصی/مدل محلی در برآورد نیست**. محدودیت provider/region/حساب تجاری باید جدا تأیید شود.
- **مبنا:** دلار آمریکا، بدون مالیات/نیروی انسانی/هزینهٔ فعلی ۳ سرور؛ ارز و تعرفه ممکن است تغییر کنند.
- **Hetzner:** فهرست قیمت رسمی پس از تغییر ۱۵ ژوئن ۲۰۲۶ در منطقهٔ آلمان/فنلاند: `CPX32 = $41.99/mo` و `CPX42 = $81.99/mo` بدون IPv4 و مالیات. مشخصات نمونهٔ CPX32 برابر ۴ vCPU/۸GB و CPX42 برابر ۸ vCPU/۱۶GB است؛ مشخصات نهایی موقع سفارش کنترل شود [S5, S6].
- **Private Network:** خود feature رایگان است؛ TLS، ادمین و بکاپ هزینه/کار جدا دارند [S1]. Hetzner Backups در مستند FAQ با هزینهٔ حدود ۲۰٪ قیمت سرور توضیح داده شده [S7].
- **نمونهٔ تعرفهٔ LLM از Anthropic API:** Haiku 4.5 برابر `$1 input / $5 output`، Sonnet 4.6 برابر `$3 / $15`، Opus 4.8 برابر `$5 / $25` **به‌ازای هر یک‌میلیون token استاندارد**؛ caching و batch و long context جداگانه‌اند [S8]. این انتخاب صرفاً برای حساب‌کردن است، نه قفل معماری به Claude.

### 10.2 محاسبهٔ نمونهٔ واقعی‌نما و قابل تکرار API

**فرض نمونه:** ۴۰ Agent instance فعال، هرکدام میانگین ۱۵ Job در روز طی ۳۰ روز → `40 × 15 × 30 = 18,000 jobs/month`. این **فرض مصنوعی** است، نه ترافیک واقعی. برای ساده‌شدن حساب، هر Job در جدول فقط **یک فراخوانی LLM** دارد؛ در کار واقعی چند فراخوانی، tool loop و ارزیابی هزینه را افزایش می‌دهد.

| سطح مدل | سهم Job | Job/ماه | میانگین Input/Output به‌ازای Job | هزینهٔ Input | هزینهٔ Output | جمع |
|---|---:|---:|---|---:|---:|---:|
| S / Haiku 4.5 | ۸۰٪ | ۱۴٬۴۰۰ | ۲٬۰۰۰ / ۴۵۰ token | $28.80 | $32.40 | **$61.20** |
| M / Sonnet 4.6 | ۱۸٪ | ۳٬۲۴۰ | ۴٬۰۰۰ / ۱٬۰۰۰ token | $38.88 | $48.60 | **$87.48** |
| H / Opus 4.8 | ۲٪ | ۳۶۰ | ۸٬۰۰۰ / ۲٬۰۰۰ token | $14.40 | $18.00 | **$32.40** |
| **مجموع یک‌مرحله‌ای** | **۱۰۰٪** | **۱۸٬۰۰۰** | — | **$82.08** | **$99.00** | **$181.08** |

**تعبیر درست:** `$181.08` فقط قیمت توکن در **یک فراخوانی برای هر Job** با این حجم فرضی است. با متوسط ۲٫۵ فراخوانیِ مشابه/Job، هزینهٔ خام مدل تقریباً `$452.70` می‌شود؛ ابزارهای وب/جست‌وجو، Voice، retry، context طولانی و judge نیز اضافه می‌شوند. **مدل قوی برای «هر مدیر همیشه» می‌تواند هزینه را چندبرابر کند.** caching می‌تواند تخفیف بدهد، اما نباید برای بودجهٔ حداقلی تضمین شود.

### 10.3 سه سناریوی ماهانه، بدون توسعهٔ انسانی

| قلم / ماه | Pilot: ۸–۱۲ نقش، ≤۳٬۰۰۰ Job | Operating: ۳۰–۵۰ نقش، ۱۰–۲۰هزار Job | Expansion: ۷۰–۱۲۰ نقش، ۴۰–۸۰هزار Job |
|---|---:|---:|---:|
| Compute/DB/worker/backup/storage | $110–220 | $180–450 | $450–1,200 |
| LLM و AI judge و retries | $50–250 | $300–1,200 | $1,000–4,500 |
| STT/TTS و realtime | $5–40 | $20–150 | $100–500 |
| SEO/Analytics/notifications/other APIs | $20–100 | $50–200 | $150–600 |
| Security/monitoring/contingency cash | $15–90 | $50–200 | $150–500 |
| **مجموع برآورد** | **$200–700** | **$600–2,200** | **$1,850–7,300** |

این بازه‌ها **برآورد سناریو** و نه قیمت رسمی یک بسته‌اند؛ اختلاف با «میانگین» مثال ۱۸هزار Job به ناشناخته‌بودن تعداد فراخوانی، طول context و هزینهٔ سرویس‌های جانبی برمی‌گردد. برای بودجهٔ واقعی به Usage Log پایلوت ۱۴روزه نیاز است. برای MVP پیشنهاد می‌کنم **سقف پرداختی ماه اول $500** (در صورت توان مالی)، هشدار در $350 و $450 و توقف Runهای غیرفوری در $500 تعریف شود؛ این یک پیشنهاد تصمیم به مالک است، نه بودجهٔ تأییدشده.

### 10.4 سرمایه‌گذاری زمان/نیروی انسانی

| ترکیب فرضی تیم | ظرفیت | زمان محتمل P0/P1 | توضیح |
|---|---|---|---|
| ۱ Senior full-time | ~۱ FTE | ۹–۱۵+ ماه | خطر bus factor و تست امنیت ناکافی |
| ۲ Developer + DevOps پاره‌وقت | ~۲٫۵ FTE | ۶–۱۰ ماه | مناسب پایلوت و گسترش تدریجی |
| Backend/AI + Full-stack + Android + DevOps/Security + QA/UX نیمه‌وقت | ~۴–۵ FTE | ۴–۸ ماه | وابسته به اتصال و محدودیت محصول موجود |

**حقوق واقعی تیم** برحسب کشور/قرارداد بسیار متغیر است و از سند قابل تعیین نیست؛ به‌جای ساخت رقم حقوق، برای برنامه‌ریزی حسابداری `FTE-month × نرخ قرارداد واقعی` ثبت شود. ظرفیت بالا شامل معماری، QA، امنیت، عملیات و documentation است، نه فقط coding.

### 10.5 ROI و اقتصاد واحد

```text
Net Incremental Monthly Value
 = Verified incremental gross profit from experiments
 + Verified avoided external labor spend
 + Verified avoided incident loss (conservative)
 - AI/API/infra/tool spend
 - Human review and operation cost
 - Rework, refunds and incident impact
```

- برای **Revenue uplift** از A/B یا مقایسهٔ cohort با seasonality استفاده کنید؛ تعداد مقاله یا Impression را مستقیم دلار نکنید.
- `Cost per verified task`, `Cost per accepted decision`, `Owner minutes per week`, `Error-adjusted ROI` را داشبورد اصلی FinOps کنید.
- **مثال break-even (فرضی):** اگر هزینهٔ ثابت و متغیر HQ ماهانه `$1,000` و حاشیهٔ سود مشارکتی درآمد جدید `40%` باشد، برای سربه‌سرشدنِ بدون لحاظ حقوق و Incident به **`$2,500` درآمد افزایشی ماهانه** نیاز است (`1000 / 0.40`). با احتساب حقوق مقدار بالاتر می‌شود.
- KPI پایان سال: «ارزش افزایشی مستند بیش از هزینهٔ تمام‌شده»؛ **پیش‌فرض رشد ماهانهٔ تصاعدی نگذارید**. اگر سه ماه متوالی ROI منفی و علت نامعلوم بود، Scale متوقف و Scope محدود شود.
- **SaaS:** تصمیم‌گیری فقط بعد از اینکه `tenant isolation`, `billing`, `support SLA`, `legal/compliance`, `data portability`, `DR` و نرخ خطای policy در محیط آزمایشی ارزیابی شوند.

### 10.6 لینک منابع قیمت و معماری (بررسی‌شده در ۲۰۲۶-۱۰-۱۶)

- **[S1]** Hetzner Private Network FAQ: https://docs.hetzner.com/networking/networks/faq/ — ترافیک شبکهٔ خصوصی به‌صورت خودکار رمزگذاری نمی‌شود.
- **[S2]** Microsoft Azure Speech language support: https://learn.microsoft.com/azure/ai-services/speech-service/language-support — پشتیبانی Persian `fa-IR` و صداهای فارسی.
- **[S3]** Google Cloud STT supported languages: https://docs.cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages — مدل‌ها/Regionهای دارای Persian.
- **[S4]** OpenAI API Pricing (بخش Realtime/Audio): https://developers.openai.com/api/docs/pricing — شیوهٔ نرخ‌گذاری Audio/Text، متغیر با مدل.
- **[S5]** Hetzner June 2026 price adjustment: https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/ — نرخ‌های منطقه‌ای Cloud.
- **[S6]** Hetzner Cloud CPX specifications: https://www.hetzner.com/cloud/regular-performance/ — CPU/RAM/Disk؛ موجودی/قیمت نهایی در لحظهٔ سفارش بررسی شود.
- **[S7]** Hetzner billing/backup FAQ: https://docs.hetzner.com/cloud/billing/faq/ — تعرفهٔ backup.
- **[S8]** Claude API pricing: https://platform.claude.com/docs/en/about-claude/pricing — نرخ مدل‌ها و batch/cache.
- **[S9]** Temporal production/self-hosting: https://docs.temporal.io/production-deployment و https://docs.temporal.io/self-hosted-guide — نیازهای عملیات workflow.
- **[S10]** Hetzner Cloud Network/vSwitch: https://docs.hetzner.com/networking/networks/connect-dedi-vswitch/ — اگر سرورها dedicated باشند، مسیر اتصال متفاوت است.

## 11. پیشنهاد نام (حداقل ۱۰ گزینه، فارسی و لاتین، با معنی)

**این‌ها پیشنهاد خلاقانه هستند، نه نام‌های ثبت‌شده یا دامنه‌های بررسی‌شده.** پیشنهاد من برای حفظ پیوستگی برند: نام فعلی محصول `Coine HQ` موقتاً ثابت بماند تا بررسی حقوقی/بازار انجام شود.

| نام لاتین | نام فارسی | معنی/حس برند | کاربرد مناسب |
|---|---|---|---|
| **Coine HQ** | کوینه اچ‌کیو | مقر فرماندهی | محصول داخلی (اولویت ۱) |
| **Coine Holding** | هلدینگ کوینه | مجموعهٔ شرکت‌ها | نام کاری مادر |
| **Coine Nexus** | کوینه نکسوس | نقطهٔ اتصال شبکهٔ شرکت | پلتفرم و زیرساخت |
| **Coine Atlas** | کوینه اطلس | حمل و مدیریت مجموعهٔ بزرگ | هاب چندشرکتی |
| **Coine Command** | کوینه کامند | فرمان و پایش | مرکز فرمان CEO |
| **Coine Orbit** | کوینه اوربیت | شرکت‌های پیرامون هسته | ساختار هلدینگ |
| **Coine Core** | کوینه کور | هستهٔ مشترک شرکت | پلتفرم زیرساختی |
| **Coine Forge** | کوینه فورج | ساخت و بهبود مداوم | AI operations |
| **Coine Mesh** | کوینه مش | ارتباط شبکه‌ای ایجنت‌ها | Agent Platform |
| **Coine Citadel** | کوینه سیتادل | قلعهٔ امن / حاکمیت | Security-first |
| **Kian HQ** | کیان اچ‌کیو | «کیان»: ساختار/اقتدار | مادر فراگیرتر از مالی |
| **Aftab Nexus** | آفتاب نکسوس | روشنایی و مرکزیت | برند فارسی غیرفایننس |
| **Raha Command** | رها کامند | آزادی از کارهای تکراری | تجربهٔ CEO |
| **Hamraah OS** | همراه او‌اس | همراه مدیریتی سازمان | نام عام‌تر، نیازمند بررسی تعارض |

**Shortlist:** `Coine HQ` برای اپ، `Coine Nexus` برای نام پلتفرم سازمانی، و `Coine Holding` برای نام کاری مادر. به‌دلیل وجود نام‌های رایج مانند Orbit/Atlas/Command، پیش از استفادهٔ عمومی حتماً Trademark/DNS/Social Handle Search انجام شود.

## 12. سؤال‌هایی که باید از مالک پرسید

### تصمیم‌های لازم قبل از طراحی اجرایی (P0)

1. **حداکثر هزینهٔ ماهانهٔ API و زیرساخت چقدر است؟** (`$300`, `$500`, `$1,000`, `$2,000+` یا مقدار دیگر) و آیا توسعه‌دهنده هم در این سقف است؟
2. **سه سرور دقیقاً Hetzner Cloud هستند یا Dedicated یا ترکیبی؟** region، network zone، Cloud Project و روش اتصال vSwitch چیست؟ (اطلاعات حساس مانند IP عمومی/credential در گفتگو ارسال نشود.)
3. **آیا اجازهٔ جداگانه برای اتصال read-only به هر سه سرور داده می‌شود؟** اگر بله، برای کدام API/port/metric و توسط چه شخصی اجرا می‌شود؟
4. **آیا ساخت حتی read-only user، تغییر firewall، نصب exporter یا هر تغییر config فعلاً ممنوع است؟** مرزِ دقیق Change Approval چیست؟
5. **دامنهٔ عملیات مجاز بدون تأیید دوباره چیست؟** فقط گزارش، draft محتوا، ایجاد تسک HQ، یا اعمال تغییر داخلی؟
6. **چه عملیات‌هایی مطلقاً ممنوع‌اند؟** پیشنهاد من: برداشت پول، سفارش ترید، اجرای کد production، قیمت‌گذاری، ارسال انبوه، حذف داده.
7. **آیا قصد دارید هیچ دادهٔ مشتری، PII، کلید API یا سابقهٔ معاملاتی از سرور به LLM خارجی منتقل نشود؟** اگر بعضی داده‌ها مجازند، کدام طبقه با چه رضایتی؟
8. **سرورهای موجود production و دارای کاربران واقعی‌اند؟** پنجرهٔ مجاز برای تست بار، پشتیبان، تغییر شبکه و incident چیست؟
9. **منبع قطعی KPIهای کاربر/درآمد/سیگنال چیست؟** آیا تعریف Win Rate، Conversion، Revenue و Churn موجود و معتبر است؟
10. **چه کسی از مالک در اجرای اضطراری backup/restore و دسترسی break-glass پشتیبانی می‌کند؟**
11. **مالک ترجیح می‌دهد HQ روی سرور چهارم single-node با RPO/RTO سبک شروع شود یا از روز اول دو/چندنودی؟**
12. **تعداد اعضای تیم توسعه و میزان تخصصشان چیست؟** Claude قرار است توسعه‌دهنده باشد یا افراد انسانی هم کد و CI را بررسی می‌کنند؟

### تصمیم‌های محصولی و سازمانی (P1)

13. اولویت ۳ ماه اول چیست: Reliability، SEO، Sales/Retention، یا Quant Quality؟ **یک هدف اول** انتخاب شود.
14. اولین شرکتی که باید در هاب نمایش داده شود کدام است؟ یا همهٔ محصولات با حداقل KPI؟
15. سه کار تکراری با بالاترین ارزش که اکنون مالک شخصاً انجام می‌دهد چیست؟
16. روزانه چند دقیقه برای مرور Cartable مناسب است (۵، ۱۰ یا ۲۰ دقیقه)؟
17. اعلان‌های `SEV1` چه ساعتی باید حتی در Quiet Hours برسند؟ Telegram backup لازم است؟
18. آیا پاسخ خودکار به مشتریان مجاز است یا فقط draft پس از تأیید؟ محدودیت‌های قانونی پیام‌رسانی چیست؟
19. Search Console، GA4، Play Console، Telegram، GitHub و سایر ابزارها دسترسی مالک/API credential رسمی دارند؟
20. آیا SEO/GEO برای هر سایت دارای هدف اقتصادی مستقل است؟ صفحهٔ conversion اصلی چیست؟
21. بازاریابی چه ادعاهایی را **نباید** دربارهٔ سود، win rate، کپی‌ترید و تبلیغات مالی مطرح کند؟
22. Voice فارسی برای مکالمهٔ کوتاه مهم‌تر است یا جلسهٔ live چندنفره؟ لهجه و تلفظ برند چه اولویتی دارند؟
23. اندروید اپ کاملاً مستقل Coine HQ باشد یا تنها از design system موجود الگوبرداری کند؟ (با رعایت قانون عدم تغییر CoinePro-App.)
24. آیا گزارش‌های صوتی و transcripts در سرور نگهداری شوند؟ چند روز؟
25. مالک استفاده از providerهای AI خارجی و ارسال داده به محل پردازش آن‌ها را از نظر حقوقی/تجاری مجاز می‌داند؟

### تصمیم‌های رشد آینده (P2)

26. نام/برند Coine قرار است به تجارت غیرفایننس هم توسعه یابد؟
27. SaaS واقعاً هدف ۱۲–۲۴ ماهه است یا صرفاً احتمال آینده؟
28. یک شرکت زیرمجموعهٔ جدید چه داده‌ها و مجوزهایی باید جدا داشته باشد؟
29. چه زمانی هزینهٔ بیشتر برای Voice Live/Virtual Office پذیرفتنی است؟ معیار عملی ارزش آن چیست؟
30. سقف ریسک قابل‌قبول برای آزمایش‌های growth و هزینهٔ قابل‌سوزاندن در هر آزمایش چقدر است؟

**پیشنهاد ترتیب پرسش:** ابتدا پاسخ ۱ تا ۷ و ۱۲ را بگیرید؛ بقیه مانع تهیهٔ سند معماری نیستند، ولی برای اتصال و اجرای واقعی ضروری می‌شوند.

## 13. سه پیشنهاد «جسورانه» که هیچ‌کس به آن فکر نکرده

### 13.1 «Autonomy Escrow» — حساب امانی اختیار، نه فقط نردبان استقلال [P1، ماه ۵–۷]

**ایده:** وقتی CEO به یک Agent اختیار تکراری می‌دهد، سیستم برای آن نقش یک «پاکت اختیار» ایجاد می‌کند: `Action types + Budget + Time + Product + Maximum blast radius + Revocation`. هر اقدام قبل از اجرا مقداری از سهمیهٔ پاکت را مصرف می‌کند؛ استفاده از امتیاز/اختیار با رفتار ناموفق متوقف می‌شود.

**نوآوری عملی:** اختیار به‌جای «قابل اعتماد است یا نیست» یک **منبع محدود، قابل حسابرسی و قابل بازخرید** می‌شود. مثال: سه اصلاح داخلی غیرفوری در یک روز، در سقف ۵ دلار، بدون هیچ external publish. در اولین violation همهٔ grantهای این پاکت freeze می‌شوند.

**MVP:** جدول `capability_escrows`, Policy checks, daily limits، simulation و صفحهٔ `Why Was This Action Allowed?`. **KPI:** ۰ اقدام خارج از پاکت، کاهش زمان تأیید در کارهای کم‌خطر، امکان revoke زیر ۱۰ ثانیه.

### 13.2 «Agent SimGym» — باشگاه شبیه‌سازی خطا با دادهٔ مصنوعی [P1/P2، ماه ۶–۹]

**ایده:** به‌جای اینکه ارتقای Agent را صرفاً براساس ۳۰ کار موفق واقعی بدهیم، ماهانه نسخهٔ تازهٔ Role/Prompt/Tool Policy را در یک **محیط synthetic** با سناریوهای خصمانه آزمایش کنیم: سقوط ناگهانی سرور، متریک ساختگی، ابزار کند، کاربر عصبانی، تزریق prompt، هزینهٔ حلقه‌ای، دادهٔ cross-tenant.

**نوآوری عملی:** هر نقش «گواهی شایستگی برای یک کلاس اکشن» می‌گیرد و گواهی با تغییر مدل/ابزار/Policy منقضی می‌شود. AI می‌تواند سناریو پیشنهاد دهد، اما سنجه و نتیجه را تست deterministic می‌سنجد.

**MVP:** ۵۰ fixture، ۱۰ سناریوی امنیتی، scorecard و `promotion gate` در CI. **KPI:** بیش از ۹۵٪ عبور تست‌های مجاز، ۱۰۰٪ توقف سناریوهای forbidden، کاهش regression پس از تغییر provider.

### 13.3 «Opportunity Exchange» — بازار داخلی پروژه با مزایدهٔ محدود بر اساس ارزش اثبات‌شده [P2، ماه ۹–۱۲]

**ایده:** هر دپارتمان برای یک بودجهٔ آزمایشی محدود، **پروپوزال مستند** ارائه می‌دهد: فرضیه، ارزش انتظاری، cost ceiling، evidence و guardrail. یک سیستم غیرجانبدار (نه رأی مدیرهای ذی‌نفع) آنها را بر اساس `expected value × evidence quality / risk-adjusted cost` رتبه‌بندی می‌کند؛ CEO فقط سبد پروژه‌ها را تصویب می‌کند.

**نوآوری عملی:** به‌جای «مدیرهای پرحرف بودجه بگیرند»، بودجه بین پروژه‌هایی پخش می‌شود که **اثر قابل‌آزمایش** دارند. فرصت‌هایی که در تست کوچک شکست می‌خورند، زود قطع می‌شوند؛ برنده‌ها پس از holdout scale می‌شوند. این یک «بازار داخلی کار» است، نه تجارت خودکار مالی.

**MVP:** Proposal Board، budget escrow، experiment registry، scoring شفاف و outcome review پس از ۳۰ روز. **KPI:** هزینه به‌ازای فرصت موفق، درصد پروژه‌های آزمایش‌شده، و سود افزایشیِ قابل دفاع. **Guardrail:** هیچ انتخابی بدون سقف انسانی و بررسی bias/داده نباید بودجهٔ بی‌پایان بگیرد.

---

**جمع‌بندی نهایی برای ادغام با Claude:** از طراحی شرکت Agentic پشتیبانی می‌کنم؛ اما ابتدا آن را به یک **سیستم کنترل، شواهد و عملیات محدودشده** تبدیل کنید. سه اصلاح غیرقابل‌حذف عبارت‌اند از **(۱) Permission و Policy خارج از LLM، (۲) Evidence و Eval پیش از Autonomy، (۳) اقتصاد واحد و Safety Gate پیش از Scale**. در گام بعد Claude می‌تواند سندهای نهایی را در **ریپوی مجاز `CoinePro-Hub`** تهیه کند، ولی خودِ انجام تغییرات ریپو/سرور همچنان نیازمند دستور و تأیید مالک مطابق §1 است.
