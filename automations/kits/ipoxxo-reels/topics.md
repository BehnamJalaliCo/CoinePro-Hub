# ipoxxo reels — the topic bank (owner 2026-11-17: gripping edutainment, ipoxxo the sponsor)

One topic per reel, never twice. Two lanes: **noon** (reel 1, 12:00 Tehran: science, curiosity, «how does this
really work», mind-blowing facts and scales, myths busted) and **evening** (reel 2: true stories, mysteries,
inventions by accident, history's strange moments, entertainment). Every row is a TRUE fact with a source; the
session checks it again before writing (README step 2) and notes the sources in NOTES.md.
No politics, sanctions, legal matters, wars as a subject, religion or fear-mongering; no medical advice.

## How the kit uses it (README step 1; only through `tools/topic.py`)
- `python3 -I KIT/tools/topic.py next --slot noon|evening` prints the first `free` row of the slot's lane (the
  other lane when it is used up), then `topic.claim` «ipoxxo: <topic>»; refused (said before) →
  `topic.py mark <#> taken` and `next` again.
- Claimed: `python3 -I KIT/tools/topic.py mark <#> --slot <slot> --publish "۲۸ آبان"` (the day and month of the
  order's «انتشار خودکار …») → `used:2026-11-19:noon`. That writes this file's status column on the workshop
  (the ONE kit file a session changes; `sync.sh` keeps every status that is not `free`).
- `topic.py day today` lists the topics published today, Tehran (the stories' 10:00 teaser reads it).
- Statuses: `free` · `used:<date>:<slot>` · `taken` (the hub's ledger refused it) · `sample:<date>`.
- New topics go at the END with the next number; never reorder, renumber or delete a row.

## The bank

| # | status | lane | topic | hook | payoff | source |
|---|---|---|---|---|---|---|
| 1 | sample:2026-11-17 | noon | عمیق‌ترین چاه دنیا (چاه فوق‌عمیق کولا) | این درپوش زنگ‌زده، درِ عمیق‌ترین چاهیه که آدم‌ها کندن | ۱۲٬۲۶۲ متر؛ دمای ۱۸۰ درجه و سنگی که مثل پلاستیک نرم می‌شد؛ فقط ۰٫۲٪ راه تا مرکز زمین | https://en.wikipedia.org/wiki/Kola_Superdeep_Borehole · https://www.earthdate.org/ |
| 2 | free | noon | آسمون چرا آبیه؟ | نور خورشید سفیده؛ پس این آبی از کجا میاد؟ | پراکندگی رِیلی: نور آبی بیشتر پخش می‌شه؛ بنفش هم پخش می‌شه ولی چشم ما به آبی حساس‌تره | https://en.wikipedia.org/wiki/Rayleigh_scattering |
| 3 | free | noon | یه موجود نیم‌میلی‌متری که توی فضا زنده موند | این موجود رو بی‌لباس فضایی بردن بیرون از زمین و زنده برگشت | خرس آبی (تاردیگرید)؛ آزمایش FOTON-M3 در ۲۰۰۷؛ خشک می‌شه و دوباره جون می‌گیره | https://en.wikipedia.org/wiki/Tardigrade |
| 4 | free | noon | چرا نمی‌تونی خودت رو قلقلک بدی؟ | هر چی تلاش کنی، خودت رو نمی‌تونی قلقلک بدی | مخچه حرکت دستت رو از قبل پیش‌بینی می‌کنه و حسش رو کم می‌کنه | https://en.wikipedia.org/wiki/Tickling |
| 5 | free | noon | داغ‌ترین سطح زمین توی ایرانه | داغ‌ترین زمینی که ماهواره‌ها اندازه گرفتن، کجاست؟ | دشت لوت؛ ۷۰٫۷ درجه در سال ۲۰۰۵ با ماهواره‌ی ناسا | https://en.wikipedia.org/wiki/Dasht-e_Lut |
| 6 | free | noon | هواپیمای ۵۷۵ تنی چطور پرواز می‌کنه؟ | یه هواپیمای ۵۷۵ تنی، فقط روی هوا | نیروی برا: بال هوا رو به پایین هل می‌ده و هوا هواپیما رو بالا نگه می‌داره | https://en.wikipedia.org/wiki/Lift_(force) · https://en.wikipedia.org/wiki/Airbus_A380 |
| 7 | free | noon | اختاپوس سه تا قلب داره | موجودی با سه قلب و خون آبی | دو قلب برای آبشش‌ها، یکی برای بدن؛ خونش با مس (هموسیانین) آبیه | https://en.wikipedia.org/wiki/Octopus |
| 8 | free | noon | ماه داره از ما دور می‌شه | ماه هر سال کمی ازمون دورتر می‌شه | حدود ۳٫۸ سانتی‌متر در سال؛ با لیزر و آینه‌هایی که فضانوردها روی ماه گذاشتن | https://en.wikipedia.org/wiki/Lunar_Laser_Ranging_experiments |
| 9 | free | noon | جی‌پی‌اس بدون انیشتین کار نمی‌کرد | اگه نظریه‌ی نسبیت نبود، مسیریابت هر روز کیلومترها خطا داشت | ساعت ماهواره‌ها روزی حدود ۳۸ میکروثانیه جلو می‌افته و اصلاحش می‌کنن | https://en.wikipedia.org/wiki/Error_analysis_for_the_Global_Positioning_System |
| 10 | free | noon | خورشیدی که می‌بینی، مال ۸ دقیقه پیشه | خورشیدی که الان می‌بینی، الان نیست | نور حدود ۸ دقیقه و ۲۰ ثانیه طول می‌کشه تا به ما برسه | https://en.wikipedia.org/wiki/Sunlight |
| 11 | free | noon | قنات ۲۷۰۰ ساله‌ی گناباد | تونلی که ۲۷۰۰ ساله بی‌وقفه آب میاره | چاه مادرش حدود ۳۰۰ متر عمق داره؛ میراث جهانی یونسکو | https://en.wikipedia.org/wiki/Qanats_of_Gonabad |
| 12 | free | noon | چرا یخ روی آب می‌مونه؟ | اگه یخ غرق می‌شد، دریاها از ته یخ می‌زدن | آب در ۴ درجه از همه چگال‌تره؛ یخ سبک‌تره و بالا می‌مونه | https://en.wikipedia.org/wiki/Properties_of_water |
| 13 | free | noon | قورباغه‌ای که خواب که می‌ره شفاف می‌شه | این قورباغه وقتی می‌خوابه تقریباً نامرئی می‌شه | گلبول‌های قرمزش رو توی کبدش قایم می‌کنه (پژوهش ۲۰۲۲) | https://en.wikipedia.org/wiki/Glass_frog |
| 14 | free | noon | روزِ زهره از سالش بلندتره | سیاره‌ای که یه روزش از یه سالش طولانی‌تره | چرخش به دور خودش ۲۴۳ روز زمینی، دور خورشید ۲۲۵ روز | https://en.wikipedia.org/wiki/Venus |
| 15 | free | noon | کیوآرکد پاره هم خونده می‌شه | یه تیکه از کیوآرکد رو پاره کن؛ هنوز کار می‌کنه | کد تصحیح خطا تا حدود ۳۰ درصد آسیب رو جبران می‌کنه | https://en.wikipedia.org/wiki/QR_code |
| 16 | free | noon | مشت میگوی آخوندکی | این میگو با یه مشت، شیشه‌ی آکواریوم رو می‌شکنه | ضربه با سرعت حدود ۲۳ متر بر ثانیه؛ حتی حباب‌ها هم ضربه‌ی دوم می‌زنن | https://en.wikipedia.org/wiki/Mantis_shrimp |
| 17 | free | noon | یک قاشق از ستاره‌ی نوترونی | یه قاشق چای‌خوری از این ستاره، میلیاردها تن وزن داره | جرمی بیشتر از خورشید، فشرده در کره‌ای به قطر حدود ۲۰ کیلومتر | https://en.wikipedia.org/wiki/Neutron_star |
| 18 | free | noon | دیوار چین از ماه دیده نمی‌شه | همه می‌گن از ماه دیده می‌شه؛ ولی… | دیوار باریکه؛ از ماه اصلاً، و از مدار نزدیک هم به‌سختی دیده می‌شه | https://en.wikipedia.org/wiki/Great_Wall_of_China |
| 19 | free | noon | فلفل داغ نیست، مغزت فکر می‌کنه داغه | فلفل تند هیچ گرمایی نداره؛ پس این سوزش چیه؟ | کپسایسین گیرنده‌ی گرما (TRPV1) رو روشن می‌کنه؛ جایزه‌ی نوبل ۲۰۲۱ | https://en.wikipedia.org/wiki/TRPV1 |
| 20 | free | noon | یخچال‌های بیابونی ایران | ایرانی‌ها هزاران سال پیش وسط کویر یخ می‌ساختن | یخچال: گنبد بلند، دیوار سایه‌انداز و شب‌های سرد کویر | https://en.wikipedia.org/wiki/Yakhch%C4%81l |
| 21 | free | noon | صاعقه از سطح خورشید داغ‌تره | یه رعد و برق، چند برابر سطح خورشید داغه | هوای مسیر صاعقه تا حدود ۳۰ هزار درجه داغ می‌شه؛ سطح خورشید حدود ۵۵۰۰ | https://en.wikipedia.org/wiki/Lightning |
| 22 | free | noon | حافظه‌ی ماهی قرمز سه ثانیه نیست | فکر می‌کنی ماهی قرمز همه‌چیز رو زود فراموش می‌کنه؟ | آزمایش‌ها نشون دادن ماهی قرمز چیزها رو ماه‌ها یادش می‌مونه | https://en.wikipedia.org/wiki/Goldfish |
| 23 | free | noon | ۱۶ طلوع در یک روز | فضانوردها هر روز ۱۶ بار طلوع می‌بینن | ایستگاه فضایی هر حدود ۹۰ دقیقه یک دور دور زمین می‌زنه | https://en.wikipedia.org/wiki/International_Space_Station |
| 24 | free | noon | الماس و نوک مداد از یک جنس‌ان | الماس گرون و نوک مداد، از یک ماده‌ان | هر دو کربن خالص‌ان؛ فرقشون فقط چیدمان اتم‌هاست | https://en.wikipedia.org/wiki/Allotropes_of_carbon |
| 25 | free | noon | کلاغ‌ها چهره‌ی تو رو یادشون می‌مونه | اگه یه کلاغ رو اذیت کنی، سال‌ها یادش می‌مونه | آزمایش ماسک دانشگاه واشینگتن: کلاغ‌ها چهره رو سال‌ها یادشون می‌مونه و به بقیه یاد می‌دن | https://en.wikipedia.org/wiki/John_Marzluff |
| 26 | free | noon | بادگیر: کولرِ بی‌برقِ یزد | خونه‌هایی که هزار سال پیش کولر داشتن | بادگیر هوای گرم رو بیرون می‌کشه و هوای خنک رو پایین می‌فرسته | https://en.wikipedia.org/wiki/Windcatcher |
| 27 | free | noon | یک میلیون زمین داخل خورشید | توی خورشید بیشتر از یک میلیون زمین جا می‌شه | حجم خورشید حدود ۱٫۳ میلیون برابر زمینه | https://en.wikipedia.org/wiki/Sun |
| 28 | free | noon | چرا صدات توی ضبط غریبه‌ست؟ | صدای خودت رو که ضبط می‌کنی، باورت نمی‌شه صدای خودته | خودت صدات رو از استخون جمجمه هم می‌شنوی؛ بقیه فقط از هوا | https://en.wikipedia.org/wiki/Bone_conduction |
| 29 | free | noon | کوسه‌ها از درخت‌ها قدیمی‌ترن | کوسه‌ها پیش از اولین درخت‌ها روی زمین بودن | کوسه‌ها حدود ۴۵۰ میلیون سال؛ درخت‌ها حدود ۳۸۵ میلیون سال | https://en.wikipedia.org/wiki/Shark |
| 30 | free | noon | هدفون نویزکنسلینگ با صدا سکوت می‌سازه | این هدفون با صدا، صدا رو خاموش می‌کنه | موجی برعکس می‌سازه و دو موج هم رو خنثی می‌کنن | https://en.wikipedia.org/wiki/Active_noise_control |
| 31 | free | noon | دورترین نقطه از مرکز زمین، اورست نیست | اگه بخوای به ستاره‌ها نزدیک‌تر باشی، برو اکوادور | قله‌ی چیمبورازو؛ چون زمین در استوا برآمده‌ست | https://en.wikipedia.org/wiki/Chimborazo |
| 32 | free | noon | مغز ۲۰ درصد انرژی بدن رو می‌خوره | مغزت ۲ درصد وزنته ولی ۲۰ درصد انرژی رو می‌خوره | پرمصرف‌ترین عضو بدن، حتی وقتی خوابی | https://en.wikipedia.org/wiki/Human_brain |
| 33 | free | noon | داغ‌ترین سیاره، نزدیک‌ترین نیست | عطارد نزدیک‌ترینه؛ ولی داغ‌ترین سیاره زهره‌ست | جوّ غلیظ دی‌اکسید کربن؛ حدود ۴۶۴ درجه | https://en.wikipedia.org/wiki/Venus |
| 34 | free | noon | آفتاب‌پرست رنگ نمی‌گیره، نور رو جابه‌جا می‌کنه | آفتاب‌پرست رنگ عوض نمی‌کنه؛ یه کار عجیب‌تر می‌کنه | بلورهای ریزی زیر پوستش که فاصله‌شون عوض می‌شه و نور دیگه‌ای برمی‌گردونن | https://en.wikipedia.org/wiki/Chameleon |
| 35 | free | noon | دماوند، بلندترین آتشفشان آسیا | بلندترین آتشفشان آسیا کنار تهرانه | دماوند، حدود ۵۶۰۰ متر؛ یه آتشفشان خفته | https://en.wikipedia.org/wiki/Mount_Damavand |
| 36 | free | noon | فاصله‌ی صاعقه رو با شمردن بفهم | از برق تا صدای رعد بشمار؛ فاصله‌ش رو می‌فهمی | نور تقریباً فوری می‌رسه؛ صدا هر ۳ ثانیه حدود یک کیلومتر | https://en.wikipedia.org/wiki/Thunder |
| 37 | free | noon | زحل روی آب شناور می‌مونه | اگه یه وان به اندازه‌ی کافی بزرگ داشتی، زحل توش شناور می‌موند | چگالی زحل از آب کمتره | https://en.wikipedia.org/wiki/Saturn |
| 38 | free | noon | فلامینگو صورتی به دنیا نمیاد | فلامینگو خاکستری به دنیا میاد | صورتی‌ش از غذاشه: میگوهای ریز و جلبک | https://en.wikipedia.org/wiki/Flamingo |
| 39 | free | noon | چرا صفحه‌ی گوشی با دستکش کار نمی‌کنه؟ | با دستکش هر چی بزنی، گوشی جواب نمی‌ده | صفحه‌ی خازنی؛ جریان ریز برق بدن تو رو حس می‌کنه | https://en.wikipedia.org/wiki/Touchscreen |
| 40 | free | noon | سرو ابرکوه | درختی توی یزد که شاید هزاران ساله‌ست | از کهن‌ترین درخت‌های زنده‌ی آسیا؛ سنش رو حدود ۴ هزار سال تخمین می‌زنن | https://en.wikipedia.org/wiki/Cypress_of_Abarkuh |
| 41 | free | noon | کوهی که دو و نیم برابر اورسته | بلندترین کوه منظومه‌ی شمسی روی زمین نیست | المپوس مونس در مریخ، حدود ۲۲ کیلومتر | https://en.wikipedia.org/wiki/Olympus_Mons |
| 42 | free | noon | توت‌فرنگی توت نیست، موز هست | از نظر گیاه‌شناسی، موز توته و توت‌فرنگی نه | تعریف گیاه‌شناختیِ «سته» با اسم خوراکی‌ها فرق داره | https://en.wikipedia.org/wiki/Berry_(botany) |
| 43 | free | noon | اینترنت از ته دریا میاد | اینترنت گوشیت بیشتر از ته اقیانوس رد می‌شه تا از ماهواره | کابل‌های فیبر نوری زیر دریا؛ نور با بازتاب کامل داخلی | https://en.wikipedia.org/wiki/Submarine_communications_cable |
| 44 | free | noon | پوست خرس قطبی سیاهه | خرس قطبی در واقع سفید نیست | پوستش سیاهه و موهاش شفاف و توخالی | https://en.wikipedia.org/wiki/Polar_bear |
| 45 | free | noon | زمانِ پاهات از سرت کندتر می‌گذره | ساعت پاهات از ساعت سرت عقب‌تره | اتساع زمانی گرانشی؛ با ساعت‌های اتمی حتی در ارتفاع کم اندازه گرفتن | https://en.wikipedia.org/wiki/Gravitational_time_dilation |
| 46 | free | noon | خاکی که توی هرمز می‌خورن | توی این جزیره‌ی ایران، خاک رو توی غذا می‌ریزن | خاک سرخ هرمز از اکسید آهن؛ اسمش گِلَکه | https://en.wikipedia.org/wiki/Hormuz_Island |
| 47 | free | noon | یه تیکه ورق، ترتیبی که تو تاریخ تکرار نشده | ترتیب ورق‌هایی که الان بُر زدی، احتمالاً هیچ‌وقت تکرار نشده | ۵۲ فاکتوریل، عددی ۶۸ رقمی | https://en.wikipedia.org/wiki/Factorial |
| 48 | free | noon | مرغ مگس‌خوار، قلب هزار ضربه‌ای | قلب این پرنده دقیقه‌ای بیش از هزار بار می‌زنه | تا حدود ۱۲۰۰ ضربه در دقیقه | https://en.wikipedia.org/wiki/Hummingbird |
| 49 | free | noon | فصل‌ها به خاطر فاصله از خورشید نیستن | تابستون چون به خورشید نزدیک‌تریم؟ نه! | کجی محور زمین؛ زمین ژانویه به خورشید نزدیک‌تره | https://en.wikipedia.org/wiki/Season |
| 50 | free | noon | کلئوپاترا به ما نزدیک‌تره تا به هرم‌ها | کلئوپاترا به فرود روی ماه نزدیک‌تر بود تا به ساخت هرم بزرگ | هرم حدود ۲۵۶۰ پیش از میلاد؛ کلئوپاترا ۳۰ پیش از میلاد؛ ماه ۱۹۶۹ | https://en.wikipedia.org/wiki/Cleopatra |
| 51 | free | noon | یخچال سرما نمی‌سازه | یخچال سرما نمی‌سازه؛ گرما رو بیرون می‌بره | گازی که فشرده و منبسط می‌شه، گرما رو از داخل به پشت یخچال می‌بره | https://en.wikipedia.org/wiki/Refrigerator |
| 52 | free | noon | ردپای فضانوردها روی ماه | این ردپا میلیون‌ها سال همین‌جا می‌مونه | ماه باد و بارون نداره که پاکش کنه | https://en.wikipedia.org/wiki/Moon |
| 53 | free | noon | غار علی‌صدر | غاری که توش با قایق می‌گردی | از بزرگ‌ترین غارهای آبی جهان، در همدان | https://en.wikipedia.org/wiki/Ali-Sadr_Cave |
| 54 | free | noon | آتشفشان‌ها صاعقه می‌سازن | یه آتشفشان، وسط فوران رعد و برق می‌زنه | ذره‌های خاکستر و یخ به هم می‌خورن و بار الکتریکی می‌سازن | https://en.wikipedia.org/wiki/Volcanic_lightning |
| 55 | free | noon | دوقلوهای همسان، اثرانگشت متفاوت | حتی دوقلوهای همسان هم اثرانگشت یکسان ندارن | اثرانگشت در رحم و با شرایط همون لحظه‌ها شکل می‌گیره | https://en.wikipedia.org/wiki/Fingerprint |
| 56 | free | noon | کوهی بلندتر از اورست که بیشترش زیر آبه | کوهی هست بلندتر از اورست؛ فقط بیشترش زیر آبه | مائونا کیا از کف اقیانوس حدود ۱۰ کیلومتر | https://en.wikipedia.org/wiki/Mauna_Kea |
| 57 | free | noon | چرا پیاز اشکت رو درمیاره؟ | پیاز با یه برش، تو رو به گریه می‌ندازه | بریدن پیاز گازی آزاد می‌کنه که به چشم می‌رسه | https://en.wikipedia.org/wiki/Onion |
| 58 | free | noon | سردترین جای جهان روی زمینه | سردترین نقطه‌ی جهان توی یه آزمایشگاهه | آزمایشگاه‌ها به کسری از میلیاردم درجه بالای صفر مطلق رسیدن | https://en.wikipedia.org/wiki/Absolute_zero |
| 59 | free | noon | جغد سرش رو ۲۷۰ درجه می‌چرخونه | جغد می‌تونه تقریباً پشت سرش رو ببینه | مهره‌های گردن بیشتر و رگ‌هایی که موقع چرخش بسته نمی‌شن | https://en.wikipedia.org/wiki/Owl |
| 60 | free | noon | صحرای آفریقا یه روز سبز بود | بزرگ‌ترین بیابون گرم دنیا یه روز پر از دریاچه بود | دوره‌ی مرطوب آفریقا، حدود ۱۱ تا ۵ هزار سال پیش | https://en.wikipedia.org/wiki/African_humid_period |
| 61 | free | noon | گوشیت از کامپیوتر آپولو قوی‌تره | کامپیوتری که آدم رو برد ماه، از ماشین‌حسابت ضعیف‌تر بود | کامپیوتر هدایت آپولو حدود ۴ کیلوبایت حافظه داشت | https://en.wikipedia.org/wiki/Apollo_Guidance_Computer |
| 62 | free | noon | قطره‌ی بارون شکل اشک نیست | همه قطره‌ی بارون رو اشکی می‌کشن؛ ولی اشتباهه | قطره‌ی کوچیک کرویه؛ بزرگ‌ترها مثل نون همبرگر پهن می‌شن | https://en.wikipedia.org/wiki/Drop_(liquid) |
| 63 | free | noon | بامبو روزی تا ۹۰ سانت قد می‌کشه | گیاهی که می‌شه رشدش رو با چشم دید | بعضی گونه‌های بامبو در ۲۴ ساعت تا حدود ۹۰ سانتی‌متر رشد می‌کنن | https://en.wikipedia.org/wiki/Bamboo |
| 64 | free | noon | لکه‌ی سرخ مشتری | طوفانی بزرگ‌تر از کل زمین | لکه‌ی سرخ بزرگ؛ دست‌کم ۱۵۰ ساله می‌چرخه و داره کوچیک می‌شه | https://en.wikipedia.org/wiki/Great_Red_Spot |
| 65 | free | noon | چرا نمک یخ رو آب می‌کنه؟ | زمستون روی جاده نمک می‌ریزن؛ چرا؟ | نمک نقطه‌ی انجماد آب رو پایین میاره | https://en.wikipedia.org/wiki/Freezing-point_depression |
| 66 | free | noon | مور مور شدن، یادگار اجداد | این واکنش بدنت هیچ فایده‌ای نداره؛ یا داشت؟ | برای پرپشت‌کردن موی بدن بود؛ ما مو رو از دست دادیم ولی واکنش موند | https://en.wikipedia.org/wiki/Goose_bumps |
| 67 | free | noon | داغ‌ترین دمایی که بشر ساخته | آدم‌ها چیزی ساختن صدها هزار برابر داغ‌تر از مرکز خورشید | پلاسمای کوارک-گلوئون در LHC، حدود ۵٫۵ تریلیون درجه | https://en.wikipedia.org/wiki/Quark%E2%80%93gluon_plasma |
| 68 | free | noon | بادام‌زمینی آجیل نیست | بادام‌زمینی بیشتر با لوبیا فامیله تا با گردو | از خانواده‌ی حبوبات؛ زیر خاک رشد می‌کنه | https://en.wikipedia.org/wiki/Peanut |
| 69 | free | noon | پلوتو هنوز یه دور کامل نزده | از روزی که پلوتو رو پیدا کردن، هنوز یه دور هم دور خورشید نزده | کشف ۱۹۳۰؛ هر دورش ۲۴۸ سال | https://en.wikipedia.org/wiki/Pluto |
| 70 | free | noon | صدای ترق انگشت از کجاست؟ | این صدا از شکستن استخون نیست | حبابی که توی مایع مفصل ساخته می‌شه (تصویربرداری ۲۰۱۵) | https://en.wikipedia.org/wiki/Cracking_joints |
| 71 | free | noon | غروب مریخ آبیه | روی مریخ غروب‌ها آبی‌ان | گرد و غبار ریز مریخ نور آبی رو به سمت خورشید پخش می‌کنه | https://en.wikipedia.org/wiki/Mars |
| 72 | free | noon | عروس دریایی جاودان | موجودی که پیر نمی‌شه؛ برمی‌گرده به بچگی | توریتوپسیس به مرحله‌ی پولیپ برمی‌گرده و دوباره رشد می‌کنه | https://en.wikipedia.org/wiki/Turritopsis_dohrnii |
| 73 | free | noon | شطرنج: بازی‌های ممکن بیشتر از اتم‌های جهان | تعداد بازی‌های ممکن شطرنج از اتم‌های جهان بیشتره | عدد شانون، حدود ۱۰ به توان ۱۲۰ | https://en.wikipedia.org/wiki/Shannon_number |
| 74 | free | noon | تعداد درخت‌ها بیشتر از ستاره‌های کهکشان | روی زمین درخت بیشتره یا توی کهکشان ستاره؟ | حدود ۳ تریلیون درخت، در برابر صدها میلیارد ستاره | https://en.wikipedia.org/wiki/Tree |
| 75 | free | noon | سریع‌ترین موجود زمین | سریع‌ترین موجود دنیا یوزپلنگ نیست | شاهین در شیرجه بیش از ۳۰۰ کیلومتر در ساعت | https://en.wikipedia.org/wiki/Peregrine_falcon |
| 76 | free | noon | خفاش‌ها با صدا می‌بینن | خفاش توی تاریکی مطلق، یه پشه رو شکار می‌کنه | پژواک‌یابی: صدا می‌فرسته و از برگشتش نقشه می‌سازه | https://en.wikipedia.org/wiki/Animal_echolocation |
| 77 | free | noon | مکعب روبیک با ۲۰ حرکت | هر مکعب روبیکی، هر جوری به هم ریخته باشه | با ۲۰ حرکت یا کمتر حل می‌شه؛ «عدد خدا» | https://en.wikipedia.org/wiki/Optimal_solutions_for_the_Rubik%27s_Cube |
| 78 | free | noon | هسته‌ی زمین به داغی سطح خورشید | زیر پای تو، چیزی به داغی سطح خورشید | هسته‌ی داخلی زمین حدود ۵۴۰۰ درجه | https://en.wikipedia.org/wiki/Earth%27s_inner_core |
| 79 | free | noon | آکسولوتل دست و پاش رو دوباره می‌سازه | این موجود اگه دستش قطع بشه، دوباره درمیاد | آکسولوتل اندام و حتی بخش‌هایی از قلبش رو بازسازی می‌کنه | https://en.wikipedia.org/wiki/Axolotl |
| 80 | free | noon | پارادوکس تولد | توی یه کلاس ۲۳ نفره، احتمالش زیاده دو نفر یه روز به دنیا اومده باشن | بیش از ۵۰ درصد؛ چون جفت‌ها خیلی زیادن | https://en.wikipedia.org/wiki/Birthday_problem |
| 81 | free | noon | نور ۱۰۰ هزار سال طول می‌کشه از کهکشان رد بشه | سریع‌ترین چیز جهان، برای رد شدن از کهکشان ما حدود هزار قرن وقت لازم داره | قطر راه شیری حدود ۱۰۰ هزار سال نوری | https://en.wikipedia.org/wiki/Milky_Way |
| 82 | free | noon | چرا نعناع خنکه؟ | نعناع هیچ سرمایی نداره؛ پس چرا خنکه؟ | منتول گیرنده‌ی سرما (TRPM8) رو روشن می‌کنه | https://en.wikipedia.org/wiki/TRPM8 |
| 83 | free | noon | پاندو: جنگلی که یک درخته | این جنگل در واقع یه دونه درخته | ۴۷ هزار تنه با یک ریشه‌ی مشترک | https://en.wikipedia.org/wiki/Pando_(tree) |
| 84 | free | noon | قدیمی‌ترین آزمایش دنیا: قطره‌ی قیر | آزمایشی که از ۱۹۲۷ هنوز تموم نشده | قیر خیلی آروم چکه می‌کنه؛ هر چند سال یه قطره | https://en.wikipedia.org/wiki/Pitch_drop_experiment |
| 85 | free | noon | خاک صحرا جنگل آمازون رو کود می‌ده | بزرگ‌ترین جنگل دنیا از یه بیابون غذا می‌گیره | گرد و خاک صحرا از روی اقیانوس فسفر آمازون رو می‌رسونه | https://en.wikipedia.org/wiki/Saharan_dust |
| 86 | free | noon | مارماهی برقی ۸۶۰ ولت | این ماهی چهار برابر برق خونه‌ت ولتاژ می‌سازه | گونه‌ای از مارماهی برقی تا ۸۶۰ ولت | https://en.wikipedia.org/wiki/Electric_eel |
| 87 | free | noon | یک میلیارد ثانیه چقدره؟ | اگه از یک تا یک میلیارد بشمری، چقدر طول می‌کشه؟ | یک میلیارد ثانیه حدود ۳۱ سال و ۸ ماهه | https://en.wikipedia.org/wiki/Billion |
| 88 | free | noon | گودال ماریانا | اگه اورست رو بندازی ته این گودال، قله‌ش زیر آب می‌مونه | عمق حدود ۱۱ کیلومتر؛ فشاری بیش از هزار برابر سطح دریا | https://en.wikipedia.org/wiki/Challenger_Deep |
| 89 | free | noon | زنگی که از ۱۸۴۰ یکسره می‌زنه | یه زنگ برقی که نزدیک ۲۰۰ ساله خاموش نشده | زنگ برقی آکسفورد؛ هنوز کسی نمی‌دونه باتری‌هاش دقیقاً از چی ساخته شدن | https://en.wikipedia.org/wiki/Oxford_Electric_Bell |
| 90 | free | noon | فضا کاملاً ساکته | توی فضا هیچ انفجاری صدا نداره | صدا برای رفتن به هوا یا ماده نیاز داره | https://en.wikipedia.org/wiki/Outer_space |
| 91 | free | noon | ابرکلونی مورچه‌ها | مورچه‌هایی که یه «کشور» هزاران کیلومتری ساختن | کلونی مورچه‌ی آرژانتینی در اروپا، حدود ۶۰۰۰ کیلومتر | https://en.wikipedia.org/wiki/Argentine_ant |
| 92 | free | noon | برفک تلویزیون، صدای آغاز جهان | بخشی از برفک تلویزیون‌های قدیمی از آغاز جهان میاد | حدود یک درصدش تابش زمینه‌ی کیهانیه | https://en.wikipedia.org/wiki/Cosmic_microwave_background |
| 93 | free | noon | آفتابگردون فقط جوونیش دنبال خورشیده | آفتابگردون همیشه رو به خورشید نیست | فقط تا جوونه دنبال خورشید می‌چرخه؛ بالغ که شد رو به شرق می‌مونه | https://en.wikipedia.org/wiki/Heliotropism |
| 94 | free | noon | شیشه مایعِ کُند نیست | معروفه شیشه‌ی پنجره‌های قدیمی پایین ریخته؛ درسته؟ | نه؛ شیشه‌ها از اول ناهموار ساخته می‌شدن | https://en.wikipedia.org/wiki/Glass |
| 95 | free | noon | آب هم‌زمان می‌جوشه و یخ می‌زنه | یه جا هست که آب هم می‌جوشه هم یخ می‌زنه | نقطه‌ی سه‌گانه: دما و فشار خاص | https://en.wikipedia.org/wiki/Triple_point |
| 96 | free | noon | فضانوردها در فضا قد می‌کشن | توی فضا چند سانت بلندتر می‌شی | ستون مهره بدون جاذبه باز می‌شه؛ تا حدود ۳ درصد | https://en.wikipedia.org/wiki/Effect_of_spaceflight_on_the_human_body |
| 97 | free | noon | گاو نر از رنگ قرمز عصبانی نمی‌شه | پارچه‌ی قرمز گاو رو عصبانی نمی‌کنه | گاو قرمز رو مثل ما نمی‌بینه؛ حرکت پارچه‌ست که تحریکش می‌کنه | https://en.wikipedia.org/wiki/Cattle |
| 98 | free | noon | ساکت‌ترین اتاق دنیا | اتاقی که صدای قلب خودت رو توش می‌شنوی | اتاق بی‌پژواک مایکروسافت، زیر صفر دسی‌بل | https://en.wikipedia.org/wiki/Anechoic_chamber |
| 99 | free | noon | زمین قبلاً تندتر می‌چرخید | روزهای زمین یه زمانی کوتاه‌تر از ۲۴ ساعت بود | کشش ماه چرخش زمین رو کم‌کم کند می‌کنه | https://en.wikipedia.org/wiki/Tidal_acceleration |
| 100 | free | noon | چرا با دماغ گرفته نمی‌تونی زمزمه کنی؟ | همین الان امتحان کن: دماغت رو بگیر و زمزمه کن | زمزمه با دهن بسته هوا رو از بینی بیرون می‌ده | https://en.wikipedia.org/wiki/Humming |
| 101 | free | noon | دانه‌ی برف همیشه شش‌پره | هیچ دانه‌ی برفی پنج یا هفت پر نداره | ساختار بلوری یخ شش‌ضلعیه | https://en.wikipedia.org/wiki/Snowflake |
| 102 | free | noon | الماس می‌سوزه | «الماس ابدیه»؛ ولی توی آتیش نه | الماس کربنه و در دمای بالا با اکسیژن می‌سوزه | https://en.wikipedia.org/wiki/Diamond |
| 103 | free | noon | یخ‌زدگی مغز با بستنی | چرا یه قاشق بستنی سرت رو درد میاره؟ | سرمای ناگهانی کام، رگ‌ها رو تنگ و بعد گشاد می‌کنه | https://en.wikipedia.org/wiki/Cold-stimulus_headache |
| 104 | free | noon | روزِ عطارد ۱۷۶ روزه | روی عطارد از یه طلوع تا طلوع بعد، نصف سال زمین می‌گذره | روز خورشیدی عطارد حدود ۱۷۶ روز زمینی | https://en.wikipedia.org/wiki/Mercury_(planet) |
| 105 | free | noon | معمای مونتی هال | سه در، یه جایزه؛ عوض کنی یا نه؟ | عوض کنی، احتمال بردنت دو برابر می‌شه | https://en.wikipedia.org/wiki/Monty_Hall_problem |
| 106 | free | noon | سخت‌ترین ماده‌ی بدن | سخت‌ترین ماده‌ی بدنت توی دهنته | مینای دندان | https://en.wikipedia.org/wiki/Tooth_enamel |
| 107 | free | noon | ماه کنار افق بزرگ‌تره؟ | ماه کنار افق غول‌پیکره؛ ولی اندازه‌ش عوض نشده | خطای دید ماه؛ تو عکس همون اندازه‌ست | https://en.wikipedia.org/wiki/Moon_illusion |
| 108 | free | noon | چرا همیشه یه طرف ماه رو می‌بینیم؟ | پشت ماه رو هیچ‌وقت از زمین ندیدی | قفل گرانشی: ماه به همون اندازه که دور زمین می‌چرخه، دور خودش می‌چرخه | https://en.wikipedia.org/wiki/Tidal_locking |
| 109 | free | noon | رنگ پاییز تموم تابستون توی برگ بود | زردِ پاییز تازه نیست؛ زیر سبز قایم بوده | کلروفیل که تجزیه بشه، رنگدانه‌های زرد پیدا می‌شن | https://en.wikipedia.org/wiki/Autumn_leaf_color |
| 110 | free | noon | چرا دریا شوره ولی رود نه؟ | رودها شیرین‌ان؛ پس شوری دریا از کجا میاد؟ | رودها نمک سنگ‌ها رو به دریا می‌برن؛ آب بخار می‌شه، نمک می‌مونه | https://en.wikipedia.org/wiki/Seawater |
| 111 | free | evening | فینیاس گیج | یه میله‌ی آهنی از سرش رد شد و زنده موند | ۱۸۴۸؛ زنده موند ولی رفتارش عوض شد و علم مغز عوض شد | https://en.wikipedia.org/wiki/Phineas_Gage |
| 112 | free | evening | صفحه‌ی طلایی وویجر | ما یه صفحه‌ی موسیقی برای آدم‌فضایی‌ها فرستادیم | ۱۹۷۷؛ صدای زمین، موسیقی و سلام به ۵۵ زبان؛ فارسی هم توشه | https://en.wikipedia.org/wiki/Voyager_Golden_Record |
| 113 | free | evening | خانمِ غرق‌نشدنی | زنی که از تایتانیک و دو کشتی دیگه زنده بیرون اومد | وایولت جسوپ: المپیک، تایتانیک و بریتانیک | https://en.wikipedia.org/wiki/Violet_Jessop |
| 114 | free | evening | پنی‌سیلین، از یه ظرف کثیف | یه ظرف که شسته نشد، میلیون‌ها جون رو نجات داد | فلمینگ، ۱۹۲۸: کپک دور ظرف باکتری رو کشته بود | https://en.wikipedia.org/wiki/Penicillin |
| 115 | free | evening | کشتی ارواح مری سلست | کشتی سالم، غذا سر جاش؛ ولی هیچ‌کس روی عرشه نبود | ۱۸۷۲؛ هنوز کسی مطمئن نیست چه اتفاقی افتاد | https://en.wikipedia.org/wiki/Mary_Celeste |
| 116 | free | evening | قدیمی‌ترین چشم مصنوعی، شهر سوخته | یه زن ۵ هزار سال پیش، توی ایران چشم مصنوعی داشت | چشم طلاکاری‌شده‌ی شهر سوخته‌ی سیستان | https://en.wikipedia.org/wiki/Shahr-e_Sukhteh |
| 117 | free | evening | آپولو ۱۳ | «هیوستون، ما یه مشکل داریم» | فیلتر مربعی توی جای گرد، با نوار چسب و جلد دفترچه؛ هر سه برگشتن | https://en.wikipedia.org/wiki/Apollo_13 |
| 118 | free | evening | دختری که از آسمون افتاد | از ۳ کیلومتری افتاد و ۱۱ روز تنها توی جنگل زنده موند | جولیان کوپکه، ۱۹۷۱؛ با درسی که از پدر و مادرِ زیست‌شناسش یاد گرفته بود | https://en.wikipedia.org/wiki/Juliane_Koepcke |
| 119 | free | evening | مایکروویو از یه شکلات آب‌شده | یه شکلات توی جیب، آشپزخونه‌ها رو عوض کرد | پرسی اسپنسر کنار رادار دید شکلاتش آب شده | https://en.wikipedia.org/wiki/Microwave_oven |
| 120 | free | evening | مریم میرزاخانی | اولین زنی که بزرگ‌ترین جایزه‌ی ریاضی دنیا رو گرفت | مدال فیلدز ۲۰۱۴ | https://en.wikipedia.org/wiki/Maryam_Mirzakhani |
| 121 | free | evening | نقطه‌ی آبی کم‌رنگ | این نقطه‌ی کوچیک، همه‌ی ماست | عکس وویجر ۱ از حدود ۶ میلیارد کیلومتری، ۱۹۹۰ | https://en.wikipedia.org/wiki/Pale_Blue_Dot |
| 122 | free | evening | دریاچه‌ای که حیوون‌ها رو سنگ می‌کنه؟ | این عکس‌ها رو دیدی؟ حیوون‌هایی که سنگ شدن | دریاچه‌ی ناترون قلیاییه؛ عکاس حیوون‌های مرده‌ی آهکی‌شده رو خودش چیده بود | https://en.wikipedia.org/wiki/Lake_Natron |
| 123 | free | evening | مکانیزم آنتی‌کیترا | یه کامپیوتر ۲۰۰۰ ساله از ته دریا | چرخ‌دنده‌هایی برای پیش‌بینی گرفتگی خورشید و ماه | https://en.wikipedia.org/wiki/Antikythera_mechanism |
| 124 | free | evening | سیگنال «وای!» | ۷۲ ثانیه سیگنال از فضا که هیچ‌وقت تکرار نشد | ۱۹۷۷؛ دانشمند کنارش نوشت «Wow!» | https://en.wikipedia.org/wiki/Wow!_signal |
| 125 | free | evening | خوارزمی و کلمه‌ی الگوریتم | هر بار گوشیت کاری می‌کنه، اسم یه ایرانی رو تکرار می‌کنی | «الگوریتم» از اسم خوارزمی میاد | https://en.wikipedia.org/wiki/Muhammad_ibn_Musa_al-Khwarizmi |
| 126 | free | evening | انفجار تونگوسکا | ۸۰ میلیون درخت در یک لحظه خوابیدن | ۱۹۰۸؛ یه سنگ آسمانی پیش از رسیدن به زمین در هوا منفجر شد | https://en.wikipedia.org/wiki/Tunguska_event |
| 127 | free | evening | کاغذ یادداشت چسب‌دار | یه چسبِ شکست‌خورده، شد یکی از پرفروش‌ترین لوازم دنیا | چسبی که خوب نمی‌چسبید؛ سال‌ها بعد جای نشونه‌ی کتاب | https://en.wikipedia.org/wiki/Post-it_note |
| 128 | free | evening | دست‌نوشته‌ی ووینیچ | کتابی که هیچ‌کس نتونسته یه کلمه‌ش رو بخونه | ۶۰۰ ساله؛ خط و زبانش هنوز رمزگشایی نشده | https://en.wikipedia.org/wiki/Voynich_manuscript |
| 129 | free | evening | کشتی اندورنس | نزدیک دو سال سرگردان در یخ، و همه زنده برگشتن | شکلتون؛ لاشه‌ی کشتی ۲۰۲۲ در عمق ۳۰۰۸ متر پیدا شد | https://en.wikipedia.org/wiki/Endurance_(1912_ship) |
| 130 | free | evening | رازی، آبله و سرخک | پزشکی که هزار سال پیش دو بیماری رو از هم جدا کرد | زکریای رازی اولین توصیف دقیق آبله و سرخک رو نوشت | https://en.wikipedia.org/wiki/Abu_Bakr_al-Razi |
| 131 | free | evening | اوتزی، مرد یخی | یه جسد ۵۳۰۰ ساله با نوک یه تیر توی شونه‌ش | اوتزی در یخچال آلپ پیدا شد؛ تیر ۲۰۰۱ کشف شد | https://en.wikipedia.org/wiki/%C3%96tzi |
| 132 | free | evening | ولکرو از موی یه سگ | چسبِ پشمی کفش‌ها رو یه سگ اختراع کرد | خارهایی که به موی سگِ ژرژ دو مسترال چسبیده بودن (۱۹۴۱) | https://en.wikipedia.org/wiki/Hook-and-loop_fastener |
| 133 | free | evening | حادثه‌ی گذرگاه دیاتلوف | ۹ کوهنورد، و چادری که از داخل پاره شده بود | پژوهش ۲۰۲۱: یه بهمنِ ورقه‌ای کوچیک | https://en.wikipedia.org/wiki/Dyatlov_Pass_incident |
| 134 | free | evening | بیرونی شعاع زمین رو اندازه گرفت | هزار سال پیش، یه ایرانی با یه کوه زمین رو اندازه گرفت | ابوریحان بیرونی با زاویه‌ی افق از بالای کوه | https://en.wikipedia.org/wiki/Al-Biruni |
| 135 | free | evening | نفرین توت‌عنخ‌آمون | نفرین فرعون واقعی بود؟ | هاوارد کارتر سال‌ها بعد از باز کردن مقبره زنده بود | https://en.wikipedia.org/wiki/Curse_of_the_pharaohs |
| 136 | free | evening | اشعه‌ی ایکس و دستِ همسرِ رونتگن | اولین عکس اشعه‌ی ایکس، دست یه زن بود | رونتگن ۱۸۹۵ اتفاقی اشعه‌ی ایکس رو کشف کرد | https://en.wikipedia.org/wiki/Wilhelm_R%C3%B6ntgen |
| 137 | free | evening | ارتش سفالی | چند کشاورز دنبال آب بودن؛ یه ارتش پیدا کردن | ۱۹۷۴؛ هزاران سرباز سفالی ۲۲۰۰ ساله | https://en.wikipedia.org/wiki/Terracotta_Army |
| 138 | free | evening | هدی لامار | یه ستاره‌ی سینما که اختراعش هنوز توی ارتباطات بی‌سیمه | ثبت اختراع پرش فرکانس در ۱۹۴۲ | https://en.wikipedia.org/wiki/Hedy_Lamarr |
| 139 | free | evening | جنگِ امو | ارتشی که به چند پرنده باخت | استرالیا ۱۹۳۲؛ اموها نتیجه رو بردن | https://en.wikipedia.org/wiki/Emu_War |
| 140 | free | evening | مستعمره‌ی گمشده‌ی روانوک | ۱۱۵ نفر غیب شدن؛ فقط یک کلمه روی درخت موند | «CROATOAN»؛ هنوز معماست | https://en.wikipedia.org/wiki/Roanoke_Colony |
| 141 | free | evening | تقویم خیام | تقویمی که از تقویم میلادی دقیق‌تره، مال ماست | تقویم جلالی با سال‌های کبیسه‌ی دقیق | https://en.wikipedia.org/wiki/Jalali_calendar |
| 142 | free | evening | طاعونِ رقص ۱۵۱۸ | صدها نفر روزها بی‌وقفه رقصیدن و نمی‌تونستن بایستن | استراسبورگ ۱۵۱۸؛ دلیلش هنوز قطعی نیست | https://en.wikipedia.org/wiki/Dancing_plague_of_1518 |
| 143 | free | evening | غار لاسکو و یه سگ | یه سگ و چند نوجوون، یه موزه‌ی ۱۷ هزار ساله پیدا کردن | ۱۹۴۰؛ نقاشی‌های غار لاسکو | https://en.wikipedia.org/wiki/Lascaux |
| 144 | free | evening | پری‌های کاتینگلی | دو دختر عکس پری گرفتن و نویسنده‌ی شرلوک هلمز باور کرد | بیش از ۶۰ سال بعد اعتراف کردن پری‌ها کاغذی بودن | https://en.wikipedia.org/wiki/Cottingley_Fairies |
| 145 | free | evening | لطفی‌زاده و منطق فازی | ریاضی‌دانی که لباسشویی‌ها رو باهوش کرد | منطق فازیِ لطفی‌زاده، بزرگ‌شده‌ی تهران | https://en.wikipedia.org/wiki/Lotfi_A._Zadeh |
| 146 | free | evening | ترکِ مکانیکی | رباتی که ۸۰ سال آدم‌ها رو توی شطرنج برد | یه استاد شطرنج توی جعبه قایم بود | https://en.wikipedia.org/wiki/Mechanical_Turk |
| 147 | free | evening | هانسِ زرنگ | اسبی که حساب می‌کرد | هانس صورت آدم‌ها رو می‌خوند، نه عددها رو | https://en.wikipedia.org/wiki/Clever_Hans |
| 148 | free | evening | هاچیکو | سگی که ۹ سال هر روز منتظر صاحبش موند | ایستگاه شیبویا؛ مجسمه‌ش هنوز همون‌جاست | https://en.wikipedia.org/wiki/Hachik%C5%8D |
| 149 | free | evening | مردی که برج ایفل رو دو بار فروخت | یه نفر برج ایفل رو فروخت؛ دو بار! | ویکتور لاستیگ، ۱۹۲۵ | https://en.wikipedia.org/wiki/Victor_Lustig |
| 150 | free | evening | «اگه می‌تونی منو بگیر» چقدر راست بود؟ | فیلمش رو دیدی؟ ولی قصه‌ی واقعی یه پیچ داره | پژوهش‌های تازه نشون دادن بیشتر ماجراهای ابگنیل ساختگی بود | https://en.wikipedia.org/wiki/Frank_Abagnale |
| 151 | free | evening | دزدی مونالیزا | مونالیزا تا قبل از دزدیده شدنش این‌قدر معروف نبود | ۱۹۱۱؛ دو سال گم بود و همه‌ی دنیا دنبالش بودن | https://en.wikipedia.org/wiki/Mona_Lisa |
| 152 | free | evening | مثلث برمودا | جایی که کشتی‌ها و هواپیماها غیب می‌شن؟ | آمارها می‌گن اونجا بیشتر از جاهای پررفت‌وآمد دیگه حادثه نیست | https://en.wikipedia.org/wiki/Bermuda_Triangle |
| 153 | free | evening | خطوط نازکا | نقش‌هایی که فقط از آسمون دیده می‌شن | ۲۰۰۰ ساله؛ با جابه‌جا کردن سنگ‌های سطحی کشیده شدن | https://en.wikipedia.org/wiki/Nazca_Lines |
| 154 | free | evening | مجسمه‌های ایستر راه می‌رفتن؟ | مجسمه‌های چند تُنی، بدون چرخ و حیوون جابه‌جا شدن | یه نظریه: با طناب و تکون دادن، «راه» رفتن | https://en.wikipedia.org/wiki/Moai |
| 155 | free | evening | گوبکلی‌تپه | معبدی ۶ هزار سال قدیمی‌تر از استون‌هنج | حدود ۱۱ هزار سال؛ پیش از کشاورزی | https://en.wikipedia.org/wiki/G%C3%B6bekli_Tepe |
| 156 | free | evening | سنگ‌های رونده‌ی ریس‌ترک | سنگ‌هایی که توی بیابون خودشون راه می‌رن | ۲۰۱۴ حلش کردن: یخ نازک و باد | https://en.wikipedia.org/wiki/Sailing_stones |
| 157 | free | evening | آبشار خون در قطب جنوب | آبشاری قرمز وسط یخ‌های قطب جنوب | آب شور پر از آهن که به هوا می‌رسه و زنگ می‌زنه | https://en.wikipedia.org/wiki/Blood_Falls |
| 158 | free | evening | دروازه‌ی جهنم | گودالی که از ۱۹۷۱ یکسره می‌سوزه | دهانه‌ی گازی درواز در ترکمنستان | https://en.wikipedia.org/wiki/Darvaza_gas_crater |
| 159 | free | evening | لامپی که از ۱۹۰۱ روشنه | یه لامپ که بیش از ۱۲۰ ساله خاموش نشده | لامپ صدساله‌ی لیورمور | https://en.wikipedia.org/wiki/Centennial_Light |
| 160 | free | evening | کاغذ رو ۱۲ بار تا کرد | همه می‌گفتن کاغذ بیشتر از ۷ بار تا نمی‌شه | بریتنی گالیوان، ۲۰۰۲، با یه رول کاغذ بیش از یک کیلومتری | https://en.wikipedia.org/wiki/Britney_Gallivan |
| 161 | free | evening | اولین وب‌کم یه قوری قهوه رو نشون می‌داد | اولین وب‌کم دنیا برای دیدن یه قوری قهوه ساخته شد | دانشگاه کمبریج، ۱۹۹۱ | https://en.wikipedia.org/wiki/Trojan_Room_coffee_pot |
| 162 | free | evening | اولین باگ کامپیوتر یه شب‌پره بود | اولین «باگ» واقعی، یه حشره بود | ۱۹۴۷؛ تیم گریس هاپر شب‌پره رو توی دفترچه چسبوند | https://en.wikipedia.org/wiki/Software_bug |
| 163 | free | evening | وای‌فای از دل سیاه‌چاله | وای‌فای خونه‌ت از دنبال کردن سیاه‌چاله‌ها اومده | جان اوسالیوان و پژوهش نجوم رادیویی | https://en.wikipedia.org/wiki/John_O%27Sullivan_(engineer) |
| 164 | free | evening | لباس آبی-مشکی یا سفید-طلایی؟ | یه لباس که اینترنت رو دو نصف کرد | مغز هر کس نور عکس رو یه جور حدس می‌زنه | https://en.wikipedia.org/wiki/The_dress |
| 165 | free | evening | یانی یا لورل؟ | یه صدا، دو کلمه‌ی کاملاً متفاوت | گوش هر کس به فرکانس‌های متفاوتی تکیه می‌کنه | https://en.wikipedia.org/wiki/Yanny_or_Laurel |
| 166 | free | evening | صدای انفجار کراکاتوا | بلندترین صدایی که تاریخ ثبت کرده | ۱۸۸۳؛ تا حدود ۴۸۰۰ کیلومتر دورتر شنیده شد | https://en.wikipedia.org/wiki/1883_eruption_of_Krakatoa |
| 167 | free | evening | اراتوستن محیط زمین رو با سایه اندازه گرفت | ۲۲۰۰ سال پیش، یه نفر با یه چوب زمین رو اندازه گرفت | سایه‌ی دو شهر و کمی هندسه | https://en.wikipedia.org/wiki/Eratosthenes |
| 168 | free | evening | سیب نیوتن | داستان سیب نیوتن افسانه‌ست؟ | خود نیوتن این قصه رو برای دوستش تعریف کرده بود | https://en.wikipedia.org/wiki/Isaac_Newton%27s_apple_tree |
| 169 | free | evening | ابن‌سینا و کتاب قانون | کتابی که قرن‌ها توی دانشگاه‌های اروپا درس داده شد | «قانون» ابن‌سینا | https://en.wikipedia.org/wiki/The_Canon_of_Medicine |
| 170 | free | evening | اولین ویدیوی یوتیوب | اولین ویدیوی یوتیوب ۱۹ ثانیه و درباره‌ی فیل‌ها بود | «من در باغ‌وحش»، ۲۰۰۵ | https://en.wikipedia.org/wiki/Me_at_the_zoo |
| 171 | free | evening | انوشه انصاری | اولین ایرانی که به فضا رفت | ۲۰۰۶، ایستگاه فضایی بین‌المللی | https://en.wikipedia.org/wiki/Anousheh_Ansari |
| 172 | free | evening | ضربان‌ساز قلب با یه اشتباه | یه مقاومت اشتباه، میلیون‌ها قلب رو نجات داد | ویلسون گریت‌بچ، ۱۹۵۶ | https://en.wikipedia.org/wiki/Wilson_Greatbatch |
| 173 | free | evening | جام شهر سوخته، قدیمی‌ترین انیمیشن؟ | یه جام ۵ هزار ساله که یه بز روش می‌پره | پنج تصویر پشت سر هم روی جام شهر سوخته | https://en.wikipedia.org/wiki/Shahr-e_Sukhteh |
| 174 | free | evening | چشم صحرا | یه دایره‌ی ۴۰ کیلومتری وسط صحرا که از فضا دیده می‌شه | ساختار ریشات؛ فرسایش یه گنبد سنگی، نه آتلانتیس | https://en.wikipedia.org/wiki/Richat_Structure |
| 175 | free | evening | وحشتِ «جنگ دنیاها» | یه نمایش رادیویی که کل آمریکا رو ترسوند؟ | وحشتِ همگانی خیلی کمتر از چیزی بود که روزنامه‌ها نوشتن | https://en.wikipedia.org/wiki/The_War_of_the_Worlds_(1938_radio_drama) |
