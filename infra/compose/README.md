# infra/compose — Docker Compose (پروژه‌ی `coinepro-hq`)

- همیشه از `make` یا `infra/compose/hq.sh` استفاده کن، نه `docker compose` خالی. `hq.sh` پروفایل حافظه را انتخاب میکند و `profiles/<profile>.env` و `.env` را بار میکند.
- **پروفایل:** اگر `HQ_PROFILE` خالی باشد، خودکار از RAM انتخاب میشود: کمتر از ۱۲GB اسمی → `lean`، وگرنه `full`.
- **رمزها:** `.env` (دسترسی `600`، در gitignore) با `make env` ساخته میشود. `.env.example` فقط نام متغیرها را دارد.
- **قوانین هر سرویس** در سرآیند `compose.yaml` آمده‌اند و `make check` آن‌ها را چک میکند.
