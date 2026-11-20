# infra/backup — پشتیبان‌گیری

- `backup.sh`: backup شبانه‌ی محلی، ساعت ۰۲:۳۰ UTC با `coinepro-hq-backup.timer`، **نگهداری روی دیسک: یک مجموعه** (`HQ_BACKUP_RETENTION_DAYS=1` در unit، از ۲۰۲۶-۱۱-۲۰؛ پیش‌فرض اسکریپت ۷)؛ مجموعه‌ی قبلی فقط بعد از کامل شدن مجموعه‌ی تازه پاک میشود:
  - یک `pg_dump -Fc` جدا برای هر دیتابیس، به‌علاوه‌ی نقش‌ها (`globals.sql`)
  - `manifest.json` و `SHA256SUMS`
  - مقصد: `/home/Hub/backups/<زمان UTC>/`
- `hourly.sh` (`make backup-hourly`، پرامپت ۷): backup ساعتی رمزنگاری‌شده با restic، با `coinepro-hq-backup-hourly.timer`:
  - مجموعه‌ی dumpها (`pg_dump -Fc -Z0`؛ restic خودش فشرده میکند)، آرشیو WAL، فایل‌های api و لنگرها
  - مقصد: مخزن محلی، بعد Google Drive، و اگر روشن باشد Hetzner
  - base backup روزانه‌ی WAL-G (روز تقویمی UTC؛ روی دیسک ۳ عدد با `HQ_WAL_KEEP_FULL=3` در unit از ۲۰۲۶-۱۱-۲۰، پیش‌فرض ۹؛ لحظه‌های قدیمی‌تر در snapshotهای Drive)، و علامت پایان PITR پیش از هر snapshot
  - `status/hourly.json` برای worker، و `hq_backup.prom` برای dead-man's switch در Prometheus
- `pitr.sh` (`make pitr-test at=...`): بازیابی تا یک لحظه، در یک Postgres موقت و بدون شبکه. شکست فقط وقتی replay بایستد (۱۲۰ ثانیه) یا از ۴۵ دقیقه بگذرد.
- `restore-test.sh` (`make restore-test`): آخرین مجموعه را در یک Postgres موقت و بدون شبکه بازیابی و چک میکند، بعد کانتینر را پاک میکند.
- `restore-weekly.sh` (`make restore-weekly`): تست هفتگی، یکشنبه ۰۶:۰۰ تهران:
  - آخرین snapshot بازیابی میشود.
  - همه‌ی بررسی‌های `restore-test.sh` روی آن اجرا میشود.
  - sha256 فایل‌ها چک میشود.
  - PITR به یک لحظه‌ی تصادفی در ۲۴ ساعت گذشته انجام میشود.
  - یک اجرا در هر لحظه (`flock` پیش از trap)، `--retry-lock 30m`، و مقایسه‌ی اندازه‌ی بازیابی با جای دیسک.
- `gdrive-auth.sh` (`make gdrive-auth`): یک لینک Google و بعد آدرسی که مرورگر بعد از Allow به آن میرسد (`step=link` و `step=code` برای دو مرحله؛ `own=1` برای client اختصاصی مالک). همه با scope ‏`drive.file`. `show-password.sh` (`make backup-password`): فقط در ترمینال خود مالک.
- `restic-lib.sh`: بخش مشترک. رمزها فقط برای همان اجرا در `RuntimeDirectory=` همان unit (tmpfs) میمانند و هرگز در argv یا env نمیروند. فقط پاسخ 404 ‏OpenBao یعنی «پیکربندی نشده».
- رمز restic را `infra/openbao/restic-password.sh` (از `make up`) فقط یک بار و با KV check-and-set میسازد.
- `offsite.sh`: Hetzner حالا یک مخزن restic دوم است، به‌جای کپی خام. با `HQ_BACKUP_S3_ENABLED=true` روشن میشود.
- جزئیات: `docs/ops/RUNBOOK.md` §۱۸.

- **نگهبان دیسک** (`infra/maintenance/disk_guard.py`، هر ۱۵ دقیقه، از ۲۰۲۶-۱۱-۲۰): ویدیوی منتشرشده بعد از تأیید انتشار (و آپلود شورت/ویدیوی بلند یوتیوب) از دیسک میرود، پوشه‌ی کارهای تمام‌شده‌ی کارگاه هم؛ در ۹۰٪ همه‌ی مجموعه‌های pg_dump جز تازه‌ترین. گزارش هر حذف: `/var/lib/coinepro-hq/disk-guard.jsonl`.
