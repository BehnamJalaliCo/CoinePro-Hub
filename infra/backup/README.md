# infra/backup — پشتیبان‌گیری

- `backup.sh`: برای **هر دیتابیس** یک `pg_dump -Fc` جدا، به‌علاوه‌ی نقش‌ها (`globals.sql`)، `manifest.json` و `SHA256SUMS`، در `/home/Hub/backups/<زمان UTC>/` با **نگهداری ۷ روز**. هر شب ساعت ۰۲:۳۰ UTC با `coinepro-hq-backup.timer` اجرا میشود.
- `restore-test.sh` (`make restore-test`): آخرین backup را در یک Postgres موقت و بدون شبکه بازیابی و چک میکند، بعد کانتینر را پاک میکند.
- `offsite.sh`: ارسال به Hetzner Object Storage با rclone. **خاموش** است تا `HQ_BACKUP_S3_*` در `.env` پر شود.
