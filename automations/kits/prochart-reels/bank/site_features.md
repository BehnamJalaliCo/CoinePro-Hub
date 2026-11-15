# فهرست امکانات پرو چارت (pro-chart.com)

این فهرست فقط از فایل‌های خود اپ (index.js، chunks/*.js، strings.json، manifest.json، home.html) استخراج شده است. هر امکان یک خط «چه می‌کند» و فایل شاهد دارد. هرجا هدف از متن روشن نبود «نامشخص» نوشته شده. هیچ قیمتی در فایل‌ها به‌صورت عدد ثابت نبود (قیمت پلن‌ها از سرور می‌آید).

نام‌ها: پرو چارت (Pro Chart). حساب‌های وابسته: «تریدیار» برای رمزارز و «کوین‌پرو اف‌ایکس» (CoinePro-FX) برای فارکس.

## بازارها و نمادها

- **پنج دسته بازار (Crypto / Forex / Metals / Indices / Energy)** — نمادها در پنج دسته کریپتو، فارکس، فلزات، شاخص‌ها و انرژی فهرست و فیلتر می‌شوند. _[index.js; MarketsPage-Tl1tT3zK.js; HeatmapPage-BgpLIrz5.js]_
- **نمادهای پیش‌فرض دیده‌بان (Default watchlist symbols)** — فهرست پیش‌فرض: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, XAUUSD, XAGUSD. _[index.js]_
- **طلا و نقره (XAUUSD / XAGUSD)** — طلا و نقره در فهرست پیش‌فرض و در دسته‌ی فلزات هستند؛ اندازه‌ی قرارداد در پنل نماد: طلا 100 اونس، نقره 5,000 اونس. _[index.js]_
- **نوع ابزار هر دسته (Crypto spot / Metal CFD / Index CFD / Energy CFD)** — برچسب نوع نماد: «کریپتو اسپات»، «فلز CFD»، «شاخص CFD»، «انرژی CFD». _[index.js]_
- **نماد ترکیبی (اسپرد و فرمول) (Spread / formula symbols)** — می‌توان نماد ساخت مثل BTCUSDT/ETHUSDT یا XAUUSD*2 یا (EURUSD+GBPUSD)/2 و آن را چارت کرد. _[index.js]_
- **مقایسه‌ی نماد (Compare symbol)** — چند نماد روی یک چارت: هر کدام با مقیاس خودش، همه به درصد، یا شاخص ۱۰۰. _[index.js]_
- **ساعت بازار (Market hours)** — کریپتو ۲۴ ساعته؛ فارکس یکشنبه 22:00 تا جمعه 22:00 UTC؛ نشان «بازار باز/بسته». _[index.js]_
- **جلسه‌های معاملاتی (Trading sessions)** — سایه‌ی جلسه‌ی سیدنی، توکیو، لندن، نیویورک روی چارت، با نمایش هم‌پوشانی جلسه‌ها. _[index.js]_
- **پنل جزئیات نماد (Symbol details panel)** — قیمت خرید/فروش (Bid/Ask) و اسپرد، دامنه‌ی روز، بازه‌ی ۵۲ هفته، حجم، ATR ۱۴ روزه، «درباره‌ی نماد»، ساعت معامله و منبع داده. _[index.js]_
- **خلاصه‌ی تکنیکال نماد (Technical summary)** — جمع‌بندی نوسان‌گرها و میانگین‌های متحرک با برچسب «خرید قوی تا فروش قوی». _[index.js]_
- **نمای کلی بازار (Market overview)** — تعداد بازارهای صعودی/نزولی، میانه‌ی تغییر، گردش معاملات، سهم بیت‌کوین از گردش، برترین‌ها، پرطرفدار، پرنوسان. _[index.js; MarketsPage-Tl1tT3zK.js]_
- **صداقت داده‌ی بازار (No invented market-cap / Fear&Greed)** — اپ می‌گوید ارزش کل بازار، سهم بیت‌کوین (به ارزش بازار) و شاخص ترس و طمع را نمایش نمی‌دهد چون منبع داده‌اش عرضه/آن شاخص را نمی‌فرستد. _[MarketsPage-Tl1tT3zK.js]_
- **اخبار بازار (Market news)** — سرخط خبرها با منبع مشخص، تازه‌ترین در بالا؛ ترتیب زمانی است نه بر پایه‌ی اهمیت. _[index.js; MarketsPage-Tl1tT3zK.js]_
- **دیده‌بان چندفهرستی (Watchlists)** — فهرست‌های چندگانه، بخش‌بندی، پرچم رنگی، ستون‌های قابل انتخاب، مرتب‌سازی، افزودن چندنماد، خروجی txt/csv، یادداشت برای هر نماد، هشدار روی کل فهرست. _[index.js]_
- **پنجره‌ی داده و خط وضعیت (Data window)** — مقادیر OHLC و اندیکاتورها زیر نشانگر در «پنجره‌ی داده». _[index.js]_
- **حالت آفلاین (Offline cached data)** — اگر داده‌ی بازار قطع باشد، آخرین داده‌ی ذخیره‌شده با برچسب «آفلاین» نشان داده می‌شود. _[HomePage-Cqv_Fugc.js; index.js]_

## چارت

- **۱۸ نوع چارت (18 chart types)** — میله‌ای (Bars)، شمعی (Candles)، شمعی توخالی (Hollow candles)، شمعی حجمی (Volume candles)، خطی (Line)، خطی با نشانگر، پله‌ای (Step line)، ناحیه‌ای (Area)، خط مبنا (Baseline)، ناحیه‌ی HLC، ستونی (Columns)، سقف و کف (High-low)، هیکن آشی (Heikin Ashi)، رنکو (Renko)، شکست خط (Line break)، کاگی (Kagi)، نقطه و رقم (Point & figure)، رنج (Range). _[index.js]_
- **بازه‌های زمانی (Timeframes)** — فهرست آماده (دقیقه): 1، 2، 3، 5، 10، 15، 30، 45، 60، 120، 180، 240، 360، 480، 720؛ و 1D، 3D، 1W، 1M، 3M، 6M، 12M. نوار پیش‌فرض: 1، 5، 15، 60، 240، 1D. _[index.js]_
- **بازه‌ی دلخواه (Custom interval)** — با جستجو یا نوشتن مثل 45، 4h، 3D بازه‌ی خودتان را به نوار اضافه می‌کنید؛ اگر برای نماد ساخته نشود پیام می‌دهد. واحد ثانیه و تیک هم در تعریف بازه‌ها هست اما در دسترس بودنش برای هر نماد نامشخص است. _[index.js]_
- **نمایش با تنظیمات نوع چارت (Chart-type settings)** — تنظیم اندازه‌ی آجر رنکو، مقدار برگشت کاگی/نقطه و رقم، اندازه‌ی رنج، رنگ بدنه/حاشیه/فتیله، کندل توخالی. _[index.js]_
- **مقیاس قیمت (Price scale)** — خودکار، لگاریتمی، درصدی، پایه‌ی ۱۰۰، وارونه، قفل نسبت قیمت به میله، مقیاس چپ/راست. _[index.js]_
- **برچسب‌ها و خطوط قیمت (Labels and price lines)** — خط آخرین قیمت، بسته‌شدن روز قبل، سقف/کف روز قبل، خرید/فروش، میانگین پایانی، شمارش معکوس بسته‌شدن کندل. _[index.js]_
- **ظاهر چارت (Appearance)** — پوسته‌ی روشن/تیره/نیمه‌شب/سیستم، پالت مناسب کوررنگی، رنگ صعودی/نزولی، شبکه، نشانگر، واترمارک، پس‌زمینه‌ی یکدست یا گرادیان. _[index.js; ProfilePage-CfRa9DJJ.js]_
- **منطقه‌ی زمانی (Time zone)** — انتخاب منطقه‌ی زمانی از فهرست شهرها (از جمله تهران، دبی، استانبول، لندن، نیویورک)؛ قالب ۱۲/۲۴ ساعته. _[index.js]_
- **لایه‌های خودکار روی چارت (Auto overlays)** — واگرایی‌های RSI، الگوهای هارمونیک (گارتلی، خفاش، پروانه، خرچنگ) و گپ‌های قیمتی را خودکار روی چارت می‌کشد. _[index.js]_
- **رویدادهای اقتصادی روی چارت (Economic events on chart)** — رویدادهای تقویم و اخبار به صورت علامت زیر چارت؛ فیلتر فقط مهم / مهم و متوسط / فقط آینده. _[index.js]_
- **چرا این حرکت؟ (Why this move?)** — روی یک کندل بزرگ می‌گوید چقدر نسبت به معمول اخیر بزرگ است و کدام رویداد/خبر داخل همان کندل بوده؛ اگر چیزی نبوده صریحاً می‌گوید. _[index.js]_
- **چارت چه می‌گوید (Chart reading in plain language)** — خلاصه‌ی ساده‌ی روند، نوسان، حمایت و مقاومت و نظر ابزارهای روی چارت؛ می‌نویسد «خوانشی از گذشته است، نه توصیه». _[index.js]_
- **بازپخش کندل‌به‌کندل (Bar Replay)** — چارت را از یک نقطه‌ی گذشته کندل‌به‌کندل جلو ببرید (پخش/مکث، سرعت، Shift+←/→)؛ کندل‌های بعدی عمداً پنهان‌اند. _[index.js]_
- **معامله‌ی تمرینی در بازپخش (Replay practice trades)** — خرید/فروش تمرینی با Shift+B / Shift+S، حد ضرر و سود، گزارش همان جلسه (نرخ برد، ضریب سود، منحنی سرمایه) که جایی ذخیره نمی‌شود. _[index.js]_
- **میدان و دوئل با گذشته (Replay arena / Duel with the past)** — چالش روزانه روی یک لحظه از گذشته با ۲۰ کندل پنهان؛ «پنج دقیقه با امتیاز»: ۶۰ امتیاز شیوه‌ی معامله و ۴۰ امتیاز نتیجه؛ زنجیره‌ی روزهای پشت‌سرهم. _[index.js]_
- **چیدمان چندچارتی (Multi-chart layouts)** — چند چارت کنار هم؛ همگام‌سازی نماد، بازه، نشانگر (crosshair)، زمان، بازه‌ی تاریخ؛ پرمیوم تا ۱۶ چارت. _[index.js]_
- **ذخیره‌ی چیدمان و قالب (Saved layouts and templates)** — ذخیره، تغییر نام، رونوشت و بازکردن چیدمان‌ها، ذخیره‌ی خودکار، قالب اندیکاتور و قالب ابزار ترسیم؛ «ترسیم تازه کجا دیده شود» (همین چیدمان/همه). _[index.js]_
- **تصویر و اشتراک چارت (Chart snapshot)** — دانلود/کپی تصویر چارت، وضوح دوبرابر، واترمارک «Pro Chart» اختیاری، کپی لینک نماد و بازه (بدون میزبانی تصویر)، خروجی CSV داده‌ی چارت. _[index.js]_
- **رفتن به تاریخ (Go to date)** — پرش به تاریخ دلخواه؛ اگر تاریخچه نرسد، قدیمی‌ترین کندل را نشان می‌دهد. _[index.js]_
- **جستجوی سریع و میان‌برها (Quick search and shortcuts)** — جستجوی ابزار/نماد/صفحه با نام فارسی هم؛ میان‌برهای صفحه‌کلید و راهنمای لمسی (دو انگشت زوم، نگه‌داشتن برای نشانگر). _[index.js]_
- **معامله از روی چارت (Trading from chart)** — دکمه‌ی خرید/فروش، نمایش پوزیشن‌ها و سفارش‌ها روی چارت، کشیدن خط حد ضرر/سود؛ «معامله با یک کلیک» اختیاری. برای فارکس فقط سیگنال است. _[index.js]_

## اندیکاتورها (Indicators)

نام‌ها همان نام انگلیسی‌ای است که اپ در فهرست خودش دارد؛ مجموع 140 اندیکاتور/ابزار در دیکشنری نام‌ها + 44 الگوی شمعی. خود اپ در متن آغازین می‌گوید «بیش از ۲۴۰ ابزار» (اندیکاتور، ترسیم و نمااسکریپت). شاهد: index.js.

- **روند و میانگین‌ها** (38): Moving Average; Moving Average Exponential; Moving Average Weighted; Hull Moving Average; Smoothed Moving Average; Zero-Lag EMA; Kaufman Adaptive MA; Tillson T3; McGinley Dynamic; Linear Regression Curve; Least Squares Moving Average; Double EMA; Triple EMA; Volume Weighted Moving Average; Arnaud Legoux Moving Average; Moving Average Ribbon; Guppy Multiple Moving Average; MA Cross; Multi-timeframe EMA; VWAP; Anchored VWAP; Supertrend; Parabolic SAR; Ichimoku Cloud; Williams Alligator; Chande Kroll Stop; Chandelier Exit; Volatility Stop; Moving Median; Typical Price; Weighted Close; Rolling VWAP; Time Weighted Average Price; Visible Average Price; Trend Strength Index; Auto Trendlines; Ratio; Spread
- **باندها و کانال‌ها** (8): Bollinger Bands; Keltner Channels; Donchian Channels; Envelopes; Standard Error Bands; Linear Regression Channel; Bollinger Bars; Auto Pitchfork
- **نوسان‌گرها و مومنتوم** (46): Relative Strength Index; MACD; Stochastic; Stochastic RSI; Commodity Channel Index; Williams %R; Average Directional Index; Directional Movement Index; Aroon; Aroon Oscillator; Momentum; Rate Of Change; TRIX; Price Oscillator; Awesome Oscillator; Accelerator Oscillator; Accelerator Oscillator (classic); Ultimate Oscillator; Fisher Transform; Connors RSI; Stochastic Momentum Index; SMI Ergodic Indicator; True Strength Index; Chande Momentum Oscillator; Know Sure Thing; Coppock Curve; Schaff Trend Cycle; Relative Vigor Index; Balance of Power; Vortex Indicator; Detrended Price Oscillator; Choppiness Index; Mass Index; Elder Ray (Bull/Bear Power); Ease of Movement; Woodies CCI; Price Momentum Oscillator; Multi-timeframe RSI; Bollinger Bands %B; Chop Zone; Correlation Coefficient; Rank Correlation Index; BBTrend; SMI Ergodic Oscillator; Bull Bear Power; Technical Ratings
- **نوسان** (9): Average True Range; Standard Deviation; Historical Volatility; Chaikin Volatility; Average Day Range; Ulcer Index; Bollinger BandWidth; Bollinger BandWidth (%); Relative Volatility Index
- **حجم** (19): On Balance Volume; Money Flow Index; Chaikin Money Flow; Net Volume; Volume (with MA); Accumulation/Distribution; Chaikin Oscillator; Elder Force Index; Klinger Oscillator; Price Volume Trend; Positive Volume Index; Negative Volume Index; Volume Oscillator; Percentage Volume Oscillator; Volume Delta; Cumulative Volume Delta; Up/Down Volume; Relative Volume at Time; 24-hour Volume
- **سطوح خودکار** (13): Pivot Points Standard; Pivot Points (Multi); Pivot Points High Low; Williams Fractals; Zig Zag; Auto Fib Retracement; Auto Fib Extension; Support and Resistance; Supply and Demand Zones; Previous High, Low and Close; Performance; Seasonality; Moon Phases
- **الگوها** (2): Auto Chart Patterns; All Candlestick Patterns
- **پروفایل حجم** (5): Visible Range Volume Profile; Session Volume Profile; Periodic Volume Profile; Fixed Range Volume Profile; Anchored Volume Profile
- **الگوهای شمعی** (44): Abandoned Baby - Bearish; Abandoned Baby - Bullish; Dark Cloud Cover - Bearish; Doji; Doji Star - Bearish; Doji Star - Bullish; Downside Tasuki Gap - Bearish; Dragonfly Doji - Bullish; Engulfing - Bearish; Engulfing - Bullish; Evening Doji Star - Bearish; Evening Star - Bearish; Falling Three Methods - Bearish; Falling Window - Bearish; Gravestone Doji - Bearish; Hammer - Bullish; Hanging Man - Bearish; Harami - Bearish; Harami - Bullish; Harami Cross - Bearish; Harami Cross - Bullish; Inverted Hammer - Bullish; Kicking - Bearish; Kicking - Bullish; Long Lower Shadow - Bullish; Long Upper Shadow - Bearish; Marubozu Black - Bearish; Marubozu White - Bullish; Morning Doji Star - Bullish; Morning Star - Bullish; On Neck - Bearish; Piercing - Bullish; Rising Three Methods - Bullish; Rising Window - Bullish; Shooting Star - Bearish; Spinning Top Black; Spinning Top White; Three Black Crows - Bearish; Three White Soldiers - Bullish; Tri-Star - Bearish; Tri-Star - Bullish; Tweezer Bottom - Bullish; Tweezer Top - Bearish; Upside Tasuki Gap - Bullish
- نکته: اپ برای اندیکاتورها «برگه‌ی چرا»، نشان‌دادن repaint/عدم‌repaint و آمار «در X٪ از N بار درست بوده» دارد (index.js، HomePage-Cqv_Fugc.js).
- نام‌های فارسی نمونه از خود اپ: ابر ایچیموکو، سوپرترند، پارابولیک SAR، کانال کلتنر، کانال دونچیان، نوار میانگین‌ها (MA Ribbon)، گاپی (GMMA)، تمساح ویلیامز، تبدیل فیشر، منحنی کاپاک، چرخه‌ی روند شاف (STC)، دلتای حجم تجمعی (CVD)، پروفایل حجم ناحیه‌ی دیده‌شده (VPVR)، فازهای ماه، فصلی بودن.

## ابزارهای ترسیم

- **مجموعه‌ی ابزارهای ترسیم (Drawing toolbar)** — گروه‌ها: نشانگرها، ابزارهای روند، فیبوناچی و گان، الگوها، پیش‌بینی و اندازه‌گیری، شکل‌ها، متن و برچسب، آیکون‌ها؛ فهرست کامل در بخش ابزارهای ترسیم. _[index.js]_
- **قابلیت‌های ترسیم (Drawing features)** — آهنربا (ضعیف/قوی)، قفل و پنهان‌کردن، گروه‌بندی، لایه‌ها (جلو/عقب)، نمایش به تفکیک بازه، قالب سبک، نوار شناور ابزارهای منتخب، مختصات قابل‌ویرایش، هشدار روی ترسیم. _[index.js]_
- **موقعیت خرید/فروش با ریسک به ریوارد (Long/Short position tool)** — ابزار موقعیت: حد ضرر، هدف، اندازه‌ی حساب/لات، مبلغ ریسک، سود در هدف و نسبت ریسک به ریوارد؛ می‌توان آن را «معامله‌ی آزمایشی» باز کرد. _[index.js]_

### فهرست کامل ابزارهای ترسیم (حدود 91 مورد در ثبت‌نام ابزارها)
- **نشانگرها (Cursors)**: صلیب (Cross); انتخاب (Select)
- **ابزارهای روند (Trend line tools)**: خط روند (Trend line); پرتو (Ray); خط اطلاعاتی (Info line); خط امتدادیافته (Extended line); زاویه‌ی روند (Trend angle); خط افقی (Horizontal line); پرتو افقی (Horizontal ray); خط عمودی (Vertical line); خط صلیبی (Cross line); کانال موازی (Parallel channel); کانال رگرسیون (Regression trend); کانال سقف و کف صاف (Flat top/bottom); کانال ناپیوسته (Disjoint channel); چنگال اندروز (Pitchfork); چنگال شیف (Schiff pitchfork); چنگال شیف اصلاح‌شده (Modified Schiff pitchfork); چنگال داخلی (Inside pitchfork)
- **فیبوناچی و گان (Gann and Fibonacci tools)**: اصلاحی فیبوناچی (Fib retracement); گسترش فیبوناچی روندی (Trend-based fib extension); گسترش فیبوناچی (Fib extension); کانال فیبوناچی (Fib channel); منطقه‌ی زمانی فیبوناچی (Fib time zone); بادبزن فیبوناچی (Fib speed resistance fan); زمان فیبوناچی روندی (Trend-based fib time); دایره‌های فیبوناچی (Fib circles); مارپیچ فیبوناچی (Fib spiral); کمان‌های فیبوناچی (Fib speed resistance arcs); گوه‌ی فیبوناچی (Fib wedge); پیچ‌فن (Pitchfan); جعبه‌ی گان (Gann box); مربع ثابت گان (Gann square fixed); مربع گان (Gann square); بادبزن گان (Gann fan)
- **الگوها (Patterns)**: الگوی XABCD (XABCD pattern); الگوی سایفر (Cypher pattern); سر و شانه (Head and shoulders); الگوی ABCD (ABCD pattern); الگوی مثلث (Triangle pattern); الگوی سه حرکت (Three drives pattern); موج ایمپالس الیوت (1·2·3·4·5) (Elliott impulse wave (1·2·3·4·5)); موج اصلاحی الیوت (A·B·C) (Elliott correction wave (A·B·C)); مثلث الیوت (A·B·C·D·E) (Elliott triangle wave (A·B·C·D·E)); ترکیب دوگانه‌ی الیوت (W·X·Y) (Elliott double combo wave (W·X·Y)); ترکیب سه‌گانه‌ی الیوت (W·X·Y·X·Z) (Elliott triple combo wave (W·X·Y·X·Z)); خط‌های دوره‌ای (Cyclic lines); چرخه‌های زمانی (Time cycles); خط سینوسی (Sine line)
- **پیش‌بینی و اندازه‌گیری (Forecasting and measurement tools)**: موقعیت خرید (Long position); موقعیت فروش (Short position); پیش‌بینی موقعیت (Position forecast); الگوی کندل‌ها (Bars pattern); خوراک شبح (Ghost feed); پروجکشن (Projection); VWAP لنگرشده (Anchored VWAP); پروفایل حجم بازه‌ی ثابت (Fixed range volume profile); پروفایل حجم لنگرشده (Anchored volume profile); بازه‌ی قیمت (Price range); بازه‌ی زمان (Date range); بازه‌ی قیمت و زمان (Date and price range)
- **شکل‌ها (Geometric shapes)**: قلم‌مو (Brush); هایلایتر (Highlighter); نشانگر پیکان (Arrow marker); پیکان (Arrow); فلش بالا (Arrow mark up); فلش پایین (Arrow mark down); مستطیل (Rectangle); مستطیل چرخیده (Rotated rectangle); مسیر (Path); دایره (Circle); بیضی (Ellipse); خط چندتکه (Polyline); مثلث (Triangle); کمان (Arc); منحنی (Curve); منحنی دوگانه (Double curve)
- **متن و برچسب (Annotation tools)**: متن (Text); متن لنگرشده (Anchored text); یادداشت (Note); یادداشت قیمت (Price note); سنجاق (Pin); جدول (Table); کال‌اوت (Callout); دیدگاه (Comment); برچسب قیمت (Price label); تابلو (Signpost); پرچم (Flag mark)
- **آیکون‌ها (Icons)**: آیکون (Icon)
- **اندازه‌گیری و بزرگ‌نمایی (Measure and zoom)**: اندازه‌گیری (Measure); بزرگ‌نمایی (Zoom in)

## اسکرینر، هیت‌مپ و تقویم اقتصادی

- **اسکرینر (Screener)** — شرط می‌گذارید و نمادهای هم‌خوان فهرست می‌شوند: اشباع فروش/خرید، تقاطع طلایی، MACD صعودی، شکست باند، فشردگی (Squeeze)، بیشترین رشد/افت؛ با «کندل پیش». _[index.js; MarketsHub-dk0kxIjj.js]_
- **امتیاز رشد (Growth score)** — چک‌لیست وزن‌دار (روند، شتاب، قدرت، مشارکت حجم، الگوهای تازه، امتیاز تکنیکال)، نه پیش‌بینی؛ نرخ موفقیت بر پایه‌ی برگشت‌های تاریخی سوپرترند و زیر ۵ نمونه نشان داده نمی‌شود. _[ScreenerPage-Da4UHaDb.js]_
- **اعلان نمادهای تازه‌ی اسکن (Scan alerts)** — هر نیم‌ساعت، تا وقتی یک تب پرو چارت باز است، اسکن دوباره خوانده و فقط نمادهای تازه اعلام می‌شوند. _[ScreenerPage-Da4UHaDb.js]_
- **هیت‌مپ بازار (Heat map)** — نقشه‌ی رنگی بازارها؛ رنگ بر پایه‌ی تغییر روز، بازدهی ۷/۳۰/۹۰ روزه، نوسان، جای قیمت در دامنه یا شکاف بازگشایی؛ اندازه بر پایه‌ی نقدشوندگی، حجم یا گردش. _[HeatmapPage-BgpLIrz5.js; index.js]_
- **تنظیمات هیت‌مپ (Heat map settings)** — گروه‌بندی (دسته/ارز مظنه)، چگالی نقشه، پالت کلاسیک/کوررنگی/تک‌رنگ، کلیک روی خانه برای چارت، نگه‌داشتن برای جزئیات (قیمت، سقف/کف روز، حجم، نرخ فاندینگ). _[HeatmapPage-BgpLIrz5.js]_
- **تقویم اقتصادی (Economic calendar)** — رویدادها با مقدار واقعی، پیش‌بینی و قبلی؛ فیلتر ارز و اهمیت (زیاد/متوسط/کم)؛ جستجو؛ یادآور در زمان رویداد؛ کشورها شامل آمریکا، منطقه‌ی یورو، انگلیس، ژاپن، سوئیس، استرالیا، نیوزیلند، کانادا، چین، آلمان، هند، ترکیه، آفریقای جنوبی. _[CalendarPage-DUbm93Nh.js; CalendarPanel-CfaL7o_x.js; calendarExtras-BkuxVVTS.js]_
- **هشدار ریسک خبر روی سیگنال (High-impact news window)** — روی صفحه‌ی سیگنال رویدادهای نزدیک تقویم را نشان می‌دهد و تأکید می‌کند «هشدار ریسک است، نه پیش‌بینی». _[SignalPage-CzW8IJdR.js]_

## دفتر سفارش، عمق و DOM

- **دفتر سفارش (DOM) (Depth of Market ladder)** — نردبان قیمت با حجم خرید/فروش، حجم تجمعی، اسپرد؛ خرید/فروش بازار و محدود روی همان قیمت. فقط رمزارز؛ برای فارکس داده‌ی عمق نیست. _[DomPanel-Y5WQmeap.js]_
- **منحنی عمق بازار (Depth curve)** — نمودار عمق با حجم تجمعی خرید و فروش و بازه‌ی قیمتی. _[DepthExtras-BoRjUq8h.js]_
- **تجمیع قیمت (Price grouping)** — چند سطح مجاور در یک ردیف جمع می‌شوند؛ گرد کردن طوری که اسپرد فقط بازتر شود. _[DepthExtras-BoRjUq8h.js]_
- **سهم خرید (Buy share)** — سهم خرید روی چند سطح نزدیک اسپرد در هر سمت سنجیده می‌شود. _[DepthExtras-BoRjUq8h.js]_
- **هشدار روی قیمت دفتر (Alert from order book)** — از ردیف دفتر سفارش مستقیم هشدار قیمتی بسازید. _[DepthExtras-BoRjUq8h.js]_
- **دفتر سفارش در صفحه‌ی معامله (Order book in trade page)** — نمایش اسپرد، اندازه و تجمعی کنار سفارش زنده. _[TradePage-pDIyk3Nl.js]_

## سیگنال و کانال VIP

- **سیگنال‌ها (Signals)** — فهرست سیگنال رمزارز و فارکس با تب‌های فعال، اخیر، بسته‌شده؛ هر سیگنال جهت (خرید/فروش)، نماد، اعتماد، نتیجه و زمان دارد. سیگنال‌های فعال برای اعضاست. _[SignalsPage-BQFwfTdJ.js]_
- **کارنامه‌ی عمومی سیگنال‌ها (Public track record)** — نرخ برد و نتیجه‌ی سیگنال‌های بسته‌شده به‌صورت عمومی؛ در صفحه‌ی فعالیت هم برد/زیان/سربه‌سر، نرخ خوردن هدف، نرخ حد ضرر، میانگین ریسک به ریوارد. _[SignalsPage-BQFwfTdJ.js; ActivityPage-DWrFe_um.js]_
- **صداقت آمار (Unknown stays unknown)** — وقتی شواهد نیست، نرخ‌ها به‌جای صفر «—» (ناموجود) می‌شوند و پوشش شواهد جدا نشان داده می‌شود. _[ActivityPage-DWrFe_um.js]_
- **جزئیات سیگنال (Signal detail)** — ورود، حد ضرر، اعتماد، هدف‌ها (TP)، قیمت فعلی، نتیجه، دلیل، و «اجزای امتیاز»: تکنیکال، الگو، یادگیری ماشین؛ دکمه‌ی نمایش روی چارت. _[SignalPage-CzW8IJdR.js; index.js]_
- **سیگنال کانال VIP روی چارت (VIP signals on chart)** — هر سیگنال کانال با ناحیه‌ی ورود، حد ضرر و هدف‌ها روی چارت همان نماد می‌نشیند. _[index.js]_
- **اجرای سیگنال روی صرافی (Execute signal on exchange)** — با کلید API وصل‌شده سفارش از روی سیگنال ثبت می‌شود؛ فقط وقتی که سرور اتصال را تأیید کرده؛ هر سفارش تأیید صریح می‌خواهد. _[SignalPage-CzW8IJdR.js; SafetyPage-h7QQtdzI.js]_
- **کپی‌ترید روی LBank (Copy trade on LBank)** — کپی یک سیگنال: نماد، جهت، ورود، حد ضرر و هدف‌ها از سرور می‌آید و فقط اندازه را شما می‌دهید؛ نیاز به کلید API فیوچرز LBank؛ نسخه‌ی خودکار «اختیاری» ذکر شده است. _[index.js; VipStatusPage-9Msmn6vp.js]_
- **کانال VIP تلگرام (VIP Telegram channel)** — ورود با لینک یک‌بارمصرف؛ اتصال تلگرام به حساب؛ اعلان مرورگر برای سیگنال تازه. _[MembershipPage-5aB_IYyY.js; VipStatusPage-9Msmn6vp.js; index.js]_
- **شرط ماندن در VIP (VIP stay rules)** — موجودی صرافی هر چند دقیقه خوانده می‌شود؛ کمتر از حد هشدار اعلان، زیر حد بحرانی (دو بار پشت‌سرهم) مهلت ساعتی و سپس لغو دسترسی؛ شارژ دوباره خودکار برمی‌گرداند. اعداد از سرور می‌آیند و در فایل ثابت نیستند. _[VipStatusPage-9Msmn6vp.js; VipCard-B3PoZNhv.js]_
- **کارنامه‌ی اجراها (Execution record)** — وضعیت هر اجرا: در صف، فرستاده‌شده، باز، درخواست بستن، بسته، ناموفق، لغو؛ امکان درخواست بستن. _[ActivityPage-DWrFe_um.js]_
- **فارکس فقط سیگنال (Forex = signals only)** — اپ می‌گوید اکسپرت و معامله‌ی خودکار فارکس خاموش است؛ عضویت فارکس سیگنال و کانال VIP را باز می‌کند. _[MembershipPage-5aB_IYyY.js; index.js]_

## هوش مصنوعی

- **تحلیل هوشمند چارت (پنل AI) (AI chart analysis panel)** — روی چارت فعلی می‌پرسید و روند، ساختار بازار و ستاپ (ورود/حد ضرر/هدف) می‌گیرید؛ با دکمه‌ی نمایش روی چارت؛ فهرست «تحلیل‌های من»؛ سهمیه‌ی روزانه؛ برای اعضا/پرمیوم. _[AiPanel-DV3xX8vt.js; index.js]_
- **ستاپ‌ساز هوشمند (Smart setup builder)** — ورودی: نماد، تایم‌فریم، سبک (اسکالپ/روزانه/سوینگ)، جهت (خودکار/فقط خرید/فقط فروش)، ریسک‌پذیری (محتاط/متعادل/جسور)، حداقل R:R، درصد ریسک، موجودی، لات؛ خروجی: ورود، حد ضرر، هدف، اعتماد، لات، دلیل. _[AiSetupPage-CCTlBRc5.js]_
- **شواهد تکنیکال ستاپ‌ساز (Evidence given to the model)** — نشان می‌دهد چه مقادیری به مدل داده شد: قیمت لحظه، میانگین‌های متحرک، مومنتوم و نوسان، باند بولینگر، سقف/کف و تغییر ۲۰ کندل؛ مقدار محاسبه‌نشده «—» است نه صفر. _[AiSetupPage-CCTlBRc5.js; aiEvidence-BZaEyHT_.js]_
- **تحلیل تصویر چارت (Chart image analysis (Vision))** — تصویر چارت (زیر ۶ مگابایت) را بارگذاری می‌کنید و تحلیل می‌گیرید: روند، ساختار، ستاپ، ورود، حد ضرر، هدف‌ها، اعتماد، استدلال و ریسک؛ نمایش روی چارت. پردازش به‌صورت کار (job) با پیگیری وضعیت است. _[VisionPage-CkrynvfS.js; ai-D3TKCYlz.js]_
- **دستیار (Assistant)** — گفت‌وگوی پرسش و پاسخ درباره‌ی نماد (روند، سطوح، ریسک خبر، مدیریت سرمایه)؛ پرسش باقی‌مانده‌ی روزانه؛ منابع استفاده‌شده با نوع (سیگنال فعال، بازار، خبر، تقویم، ریسک، ابزار) و تازگی؛ نیاز به حساب کوین‌پرو اف‌ایکس. _[AssistantPage-orkFOZMy.js; ai-D3TKCYlz.js; aiEvidence-BZaEyHT_.js]_
- **اسکریپت از هوش مصنوعی (Script via external AI)** — اپ متنی آماده (پرامپت) با مشخصات زبان نمااسکریپت می‌دهد که «کپی کنید و به هر دستیاری بدهید» و جواب را با «چسباندن» برمی‌گردانید؛ فراخوانی مدل از داخل صفحه‌ی اسکریپت در فایل دیده نشد. _[ScriptPage-DHI4ifcp.js]_
- **هشدار درباره‌ی AI (AI disclaimer)** — اپ می‌نویسد خروجی هوش مصنوعی تضمین نتیجه نیست و پیش از هر معامله باید بررسی شود. _[AiSetupPage-CCTlBRc5.js; SafetyPage-h7QQtdzI.js]_

## بک‌تست، معامله آزمایشی، ژورنال و پرتفوی

- **بک‌تست (Backtest)** — اجرای یک قانون معاملاتی روی داده‌ی گذشته؛ نتیجه فقط درباره‌ی همان بازه است. _[BacktestPage-BbRg02pk.js; index.js]_
- **استراتژی‌های آماده‌ی بک‌تست (Built-in backtest strategies)** — تقاطع میانگین متحرک، بازگشت RSI، تقاطع MACD، بازگشت به باند بولینگر، شکست کانال دانچیان، سوپرترند، الگوهای رشد. _[BacktestPage-BbRg02pk.js]_
- **تنظیمات بک‌تست (Backtest options)** — جهت (خرید و فروش/فقط خرید/فقط فروش)، حد ضرر و سود درصدی، کارمزد هر طرف، سرمایه، سهم هر معامله، «ذره‌بین کندل» برای ترتیب لمس SL/TP. _[BacktestPage-BbRg02pk.js]_
- **گزارش بک‌تست و خروجی (Backtest report and export)** — سود خالص در برابر خرید و نگهداری، تعداد معامله، نرخ برد، ضریب سود، بیشترین افت، زمان در بازار؛ خروجی CSV و Excel رایگان؛ هشدار وقتی معامله‌ها کم است. _[BacktestPage-BbRg02pk.js; records-DNNYILE-.js]_
- **آزمون استراتژی نمااسکریپت (Strategy tester)** — نمای کلی، فهرست معامله‌ها، منحنی سرمایه، بهینه‌ساز، آزمون پیش‌رونده (walk-forward)، شارپ و سورتینو، ذخیره‌ی استراتژی، خروجی CSV معامله‌ها. _[index.js]_
- **معامله‌ی آزمایشی (Paper trading)** — حساب فرضی روی قیمت‌های واقعی: بازار، محدود، استاپ، استاپ‌محدود، حد ضرر متحرک؛ مدت اعتبار GTC/IOC/FOK؛ فقط کاهش موقعیت؛ اهرم ۱ تا ۵۰۰؛ بستن بخشی/برعکس‌کردن. _[PaperPage-H-z8wM59.js]_
- **قوانین پر شدن واقع‌گرایانه (Fill rules)** — کارمزد تیکر/میکر، لغزش، اسپرد فرضی قابل تنظیم؛ می‌گوید این‌ها فرض‌اند و فرق با صرافی ممکن است؛ سفارش در انتظار خوش‌بینانه پر می‌شود. _[PaperPage-H-z8wM59.js]_
- **گزارش و آمار معامله‌ی آزمایشی (Paper report)** — سود خالص، نرخ برد، ضریب سود، امید ریاضی، بهترین/بدترین، افت، هزینه‌ها، به تفکیک نماد و ماه؛ ثبت در ژورنال. _[PaperPage-H-z8wM59.js]_
- **ژورنال معاملات (Trading journal)** — ثبت دستی هر معامله با نماد، ورود/خروج، سود و زیان، احساس (آرام، ترس، طمع، انتقام، بی‌صبری، مطمئن)، برچسب (بریک‌اوت، ریتست، پولبک، ترند، دایورجنس، نیوز، اسکالپ، سوینگ، اوردرفلو)، یادداشت، درس و تصویر چارت. _[JournalPage-D12sQEvF.js; index.js]_
- **آمار ژورنال (Journal stats)** — نرخ برد، سود خالص، ضریب سود، انتظار هر معامله، میانگین برد/باخت؛ تفکیک بر اساس احساس، برچسب و نماد؛ «هفته‌ی من»؛ ورود از فایل و افزودن معاملات آزمایشی. _[JournalPage-D12sQEvF.js]_
- **پرتفوی (Portfolio)** — دارایی‌ها و معاملات بسته‌ی حساب رمزارز (تریدیار) و فارکس (کوین‌پرو اف‌ایکس)؛ ارزش کل و تغییر. _[PortfolioPage-CLkMedwd.js]_
- **گزارش کامل پرتفوی (Portfolio full report)** — منحنی سرمایه، بیشترین افت و رشد پیوسته، شارپ و سورتینو (به‌ازای هر معامله)، میانگین مدت نگهداری، بردهای/باخت‌های پیاپی، سهم هر نماد، ماه‌به‌ماه؛ سنجه‌های پیشرفته و خروجی فایل بدون اشتراک. _[PortfolioPage-CLkMedwd.js]_
- **معامله‌ی زنده (Live trading)** — فقط رمزارز و حساب تریدیار: موقعیت‌ها، سفارش‌ها، دفتر سفارش، بازار/محدود، حد ضرر و سود، اهرم اختیاری، فقط کاهشی؛ هر سفارش تأیید صریح؛ نتیجه را صرافی تعیین می‌کند. _[TradePage-pDIyk3Nl.js; index.js]_
- **اتصال صرافی با کلید API (Exchange connect)** — کلید API فیوچرز LBank؛ طبق متن اپ دسترسی برداشت لازم نیست و کلید روی گوشی ذخیره نمی‌شود. _[index.js]_
- **جعبه‌ابزار تریدر (Trader toolbox)** — ماشین‌حساب حجم، ریسک، حد ضرر و سود و زیان؛ از اینجا هیچ سفارشی ارسال نمی‌شود. حجمی را حساب می‌کند که با خوردن حد ضرر a٪ از موجودی از دست برود. _[index.js]_

## اسکریپت‌نویسی

- **نمااسکریپت (NamaScript)** — زبان اندیکاتور/استراتژی خود اپ، شبیه Pine؛ همه‌چیز سری کامل است (بدون حلقه‌ی هر کندل)، عملگر روی سری با add/sub/mul، شرط با iff. ورودی با input.int / input.float. _[ScriptPage-DHI4ifcp.js; index.js]_
- **ویرایشگر (Script editor)** — زبانه‌ها، جستجو و جایگزینی، کنسول، راهنمای توابع، تاریخچه‌ی نسخه‌ها، نمونه‌ها، اسکریپت‌های من، اجرای کندل‌به‌کندل یا سری‌محور. _[ScriptPage-DHI4ifcp.js; index.js]_
- **تبدیل از تریدینگ‌ویو (TradingView/Pine import)** — اسکریپت تریدینگ‌ویو را می‌چسبانید؛ اپ خوانده و ترجمه می‌کند و تغییرها را فهرست می‌کند (مثلا حذف نوع متغیر، نام ta.*، colour به color)؛ توابعی مثل کنترل جریان، تابع کاربر و آرایه در نمااسکریپت نیست. _[ScriptPage-DHI4ifcp.js]_
- **خروجی‌های رسم (Plot outputs)** — خط، ناحیه، فلش، برچسب، جعبه، جدول روی چارت (نُه جای), رنگ کندل، رنگ پس‌زمینه، پُرکردن ناحیه‌ی بین دو سری؛ alertcondition برای هشدار. _[index.js]_
- **کتابخانه‌ی توابع (Function library)** — میانگین‌ها، نوسان‌گرها، ATR، پیووت، همبستگی، ریاضی، رنگ‌ها، تایم‌فریم بالاتر (security)، strategy.entry و بستن پوزیشن. _[index.js]_
- **نمونه‌های آماده (Examples)** — مثلا ابر ایچیموکو، قدرت روند ADX، داشبورد چنداسیلاتوری، فشردگی کلتنر/بولینگر، ستاپ همگرایی سه‌گانه، کراس HMA، پولبک EMA200، مولتی‌تایم‌فریم. _[index.js]_
- **اجرای استراتژی با بک‌تست (Strategy run)** — استراتژی نمااسکریپت روی چارت در آزمون استراتژی و بک‌تست سنجیده می‌شود؛ اسکریپت خودش سفارشی ثبت نمی‌کند. _[index.js; BacktestPage-BbRg02pk.js]_
- **اشتراک اسکریپت (Share script)** — اسکریپت را در انجمن منتشر کنید یا از پست دیگران به چارت خودتان اضافه/در استودیو باز کنید. _[ThreadPage-BRJMiWkj.js; clipboard-wyZS0j0l.js]_

## آکادمی

- **آکادمی (Academy)** — درس‌های کوتاه درباره‌ی بازار و کار با اپ؛ نقشه‌ی راه، آزمون‌ها، سطح عضویت، پیشرفت و نشان‌ها، جدول برترین‌ها، واژه‌نامه، روزهای پیاپی. با حساب کوین‌پرو اف‌ایکس کار می‌کند؛ سطح‌های حرفه‌ای شماره‌ی موبایل می‌خواهند. _[AcademyPage-B6zsXTHP.js; index.js]_
- **درس و آزمون (Lesson and quiz)** — زمان مطالعه به دقیقه، «خواندم»، آزمون با نمره و قبول/رد، آزمون دوباره. _[LessonPage-D8-eMxQC.js]_
- **عنوان درس‌ها (Lesson titles)** — عنوان درس‌ها در فایل‌ها نیست و از سرور (آکادمی کوین‌پرو اف‌ایکس) خوانده می‌شود: نامشخص. _[academy-DO5dSbPH.js]_
- **تمرین‌های راهنما (Onboarding tasks)** — فهرست کارهای صفحه‌ی اصلی: باز کردن یک سیگنال و دیدن دلیلش، افزودن اندیکاتور، خواندن برگه‌ی «چرا»، اسکریپت، استراتژی کتابخانه، هشدار، ژورنال، معامله‌ی آزمایشی، بازپخش، مرتب‌سازی دیده‌بان، دو نماد کنار هم. _[HomePage-Cqv_Fugc.js]_

## انجمن، هشدار و یادداشت

- **انجمن (Community)** — نوشتن، گفتگوها، فعال‌ترین‌ها، دنبال‌شده‌ها، جستجو؛ انواع پست: تحلیل، سوال، تجربه، اخبار، عمومی؛ تصویر؛ دنبال‌کردن نویسنده؛ گزارش پست. _[CommunityPage-CguXeotA.js; index.js]_
- **ناشناس و بررسی‌شده (Anonymous, moderated)** — با نام نمایشی ۲ تا ۲۴ نویسه، نه شماره و ایمیل؛ پست پس از بررسی منتشر می‌شود. _[CommunityPage-CguXeotA.js]_
- **رشته‌ی گفتگو (Thread)** — پاسخ، پاسخ به پاسخ، بهترین پاسخ، گزارش؛ افزودن اسکریپت پست به چارت من. _[ThreadPage-BRJMiWkj.js]_
- **انتشار ایده (Publish idea)** — ایده‌ی چارت را از منوی چارت در انجمن منتشر کنید. _[index.js]_
- **هشدار قیمتی (Price alerts)** — بالاتر از، پایین‌تر از، عبور از؛ هشدار روی ترسیم‌ها (همراه با جابه‌جایی خط)؛ روی دکمه‌ی + کنار محور قیمت. _[index.js]_
- **شرط‌های هشدار (Alert conditions)** — ورود/خروج کانال، رشد/افت درصدی، تغییر ۲۴ ساعته، خروجی اندیکاتور، شرط اسکریپت، تا چند شرط هم‌زمان (عدد دقیق در کد نامشخص). _[index.js]_
- **تکرار و انقضا (Alert frequency and expiry)** — فقط یک بار، یک بار در هر کندل، در بسته‌شدن کندل، یک بار در دقیقه، روزی یک بار، هر بار؛ انقضا (یک ساعت تا یک ماه یا بدون انقضا). _[index.js]_
- **روش‌های اعلان (Alert delivery)** — پاپ‌آپ، صدا (زنگوله، زنگ، بوق کوتاه، آژیر، دیجیتال)، اعلان مرورگر، وب‌هوک (HTTPS با امضای اختیاری)، و برای حساب: گوشی (پوش) و تلگرام. _[index.js]_
- **مرکز هشدار و کارنامه‌ی هشدار (Alert center and log)** — جستجو، توقف همه، راه‌اندازی دوباره، گروه‌بندی، سیاهه‌ی هر رویداد و تحویل وب‌هوک. _[index.js]_
- **اعلان‌های حساب (Notifications)** — حرکت تند بیت‌کوین/طلا/جفت‌ارزها، نوسان نمادهای ستاره‌دار، خلاصه‌ی صبحگاهی، یادآور خبر مهم؛ سقف شش اعلان در روز و سکوت ۲۳:۰۰ تا ۰۸:۰۰. _[index.js]_
- **یادداشت‌ها (Notes)** — یادداشت برای هر نماد با فرمت ساده (پررنگ، کج، فهرست، عنوان) و پیش‌نمایش. _[NotesPanel-1kVXeOIT.js]_

## عضویت و پلن‌ها

- **پرو چارت پرمیوم (Pro Chart Premium)** — تا ۱۶ چارت کنار هم، اندیکاتور و هشدار بیشتر، چیدمان‌های ذخیره‌شده. پلن‌ها: ماهانه، سه‌ماهه، سالانه. قیمت در فایل‌ها نیست. _[index.js]_
- **پرداخت پرمیوم (Premium payment)** — پرداخت با تتر روی شبکه‌ی BEP20 و ثبت هش تراکنش (با 0x و ۶۴ نویسه). _[index.js]_
- **رایگان با عضویت VIP (Free with VIP)** — اپ می‌گوید تا وقتی عضو کانال VIP تریدیار (یا VIP فارکس) هستید همه‌ی امکانات پرو چارت رایگان و بی‌سقف است. _[index.js; MembershipPage-5aB_IYyY.js]_
- **مسیر عضویت رمزارز (Crypto VIP route)** — ورود، ساخت حساب صرافی (LBank) با لینک ما، شارژ تا حداقل واریز، ارسال UID؛ پول در حساب خود شماست و اپ می‌گوید درآمدش از کمیسیون صرافی است. _[MembershipPage-5aB_IYyY.js]_
- **عضویت فارکس (Forex VIP)** — فارکس فقط سیگنال و کانال VIP؛ متن «عضویت رایگان VIP فارکس دیگر فعال نیست» و پلن‌های ماهانه/آزمایشی در ربات هم آمده؛ قیمت‌ها از سرور می‌آید. وضعیت دقیق نامشخص. _[MembershipPage-5aB_IYyY.js]_
- **سطح نمایش (Display level)** — سه حالت نمایش «ساده / معامله‌گر / حرفه‌ای» برای تنظیم پیچیدگی رابط (در منو). _[index.js]_

## ایمنی، احراز هویت و حساب

- **ایمنی و نسخه (Safety page)** — توضیح مسیر سیگنال تا نتیجه، هشدار ریسک، تفاوت اتصال ذخیره‌شده و تأییدشده، حریم خصوصی، پشتیبانی تلگرام، نسخه‌ی وب و دریافت اپ اندروید. _[SafetyPage-h7QQtdzI.js]_
- **احراز هویت سطح ۱ (KYC level 1)** — نام، تاریخ تولد، موبایل، کد ملی (ایران) یا گذرنامه/کارت ملی/گواهینامه؛ وضعیت: شروع نشده، در حال بررسی، تأیید، رد؛ اطلاعات در مرورگر نمی‌ماند. _[VerifyPage-DoO7QGm4.js]_
- **حذف حساب (Delete account)** — فهرست آنچه حذف می‌شود و می‌ماند؛ صفحه‌ی حذف بدون ورود هم باز می‌شود؛ حذف از داخل اپ هنوز نیست. _[DeleteAccountPage-ZG8k4jLZ.js]_
- **پنل کاربری (User panel)** — نمای کلی، امنیت و نشست‌ها، فضای کار ابری (ذخیره/بازگردانی)، اعلان‌ها، معاملات، کپی‌ترید VIP، پشتیبانی (تیکت)، خروجی داده؛ پلتفرم‌های متصل تریدیار و کوین‌پرو اف‌ایکس. _[PanelPage-B_DLrXW5.js]_
- **نمایه (Profile)** — نام نمایشی، تصویر یا نشان (موشک، گاو، خرس، کندل، الماس، شعله، صاعقه، روند، سپر)، پنهان‌کردن موجودی‌ها، تم، خروجی/بازگردانی بایگانی مرورگر، «عضو بنیان‌گذار». _[ProfilePage-CfRa9DJJ.js; profileStore-Dlxv75LJ.js; profileFacts-BPc79XW9.js]_
- **ورود (Sign in)** — ایمیل و رمز، ادامه با گوگل، بازیابی رمز با کد ایمیلی، حالت مهمان. _[index.js]_

## سایر

- **بدون فیلترشکن و فارسی (Persian, no VPN)** — توضیح سایت: چارت حرفه‌ای کریپتو، فارکس و طلا به فارسی، بدون فیلترشکن. _[home.html; manifest.json]_
- **PWA و نصب (PWA / install)** — نمایش standalone، راست‌به‌چپ، نصب روی صفحه‌ی اصلی (راهنمای سافاری)، اپ اندروید. _[manifest.json; index.js; SafetyPage-h7QQtdzI.js]_
- **فارسی و انگلیسی (Persian and English UI)** — سوییچ زبان فارسی/English، رقم فارسی، تاریخ شمسی در خروجی‌ها. _[index.js; records-DNNYILE-.js]_
- **صفحه‌ی اصلی (Home)** — خلاصه‌ی حساب و بازار، سیگنال‌های باز، «وقتی نبودید»، روزهای پیاپی، وضعیت اتصال لحظه‌ای. _[HomePage-Cqv_Fugc.js]_
- **حریم خصوصی (Privacy claim)** — طبق متن اپ نسخه‌ی وب ابزار تحلیلی/تبلیغاتی/ردیابی ندارد و دیده‌بان، ترسیم‌ها، ژورنال و معامله‌ی آزمایشی فقط در همین مرورگر می‌مانند. _[SafetyPage-h7QQtdzI.js]_
- **کپی‌ترید و معرفی دوستان (Copy-trade / Referral)** — به‌عنوان بخش‌های منو و پروفایل آمده‌اند؛ جزئیات معرفی دوستان در فایل‌ها نامشخص است. _[index.js; ProfilePage-CfRa9DJJ.js]_
- **صفحه‌ی فعالیت (Activity)** — اعلان‌ها، اجراهای سیگنال و کارنامه‌ی سیگنال‌ها. _[ActivityPage-DWrFe_um.js]_

## نقاط قوتی که خود اپ می‌گوید

- چارت حرفه‌ای کریپتو، فارکس و طلا به فارسی، بدون فیلترشکن _[home.html]_
- «رایگان، فارسی، بدون واریز»؛ «اینجا چیزی پول نمی‌خواهد و چیزی پشت دیوار نیست» _[index.js]_
- «بیش از ۲۴۰ ابزار، و ابزار خودتان» (اندیکاتور، ترسیم، نمااسکریپت) _[index.js]_
- «چارتی که حرف می‌زند: هر خوانش چارت با دلیلش می‌آید، به زبان ساده» _[index.js]_
- «هشدار و عمق بازار: وقتی قیمت رسید خبردار شوید، و ببینید پشتش چه منتظر است» _[index.js]_
- «تمرین بدون ریسک: یک روز را کندل‌به‌کندل بازپخش کنید و روی کاغذ معامله کنید» _[index.js]_
- کانال سیگنال VIP و همه‌ی امکانات پرو چارت رایگان است؛ درآمد اپ از کمیسیون صرافی است نه از کاربر _[MembershipPage-5aB_IYyY.js]_
- خروجی CSV/Excel بک‌تست رایگان است («تریدینگ‌ویو برای همین خروجی اشتراک می‌گیرد»؛ ادعای خود اپ) _[BacktestPage-BbRg02pk.js]_
- پول در حساب صرافی خود کاربر می‌ماند؛ دسترسی برداشت برای کلید API لازم نیست _[MembershipPage-5aB_IYyY.js; index.js]_
- نسخه‌ی وب بدون ابزار تحلیلی/ردیابی؛ داده‌های شخصی ژورنال و ترسیم‌ها در مرورگر می‌ماند _[SafetyPage-h7QQtdzI.js]_
- آمار ناموجود صفر نشان داده نمی‌شود؛ زیر حداقل نمونه عدد برد نمی‌دهد _[ActivityPage-DWrFe_um.js; JournalPage-D12sQEvF.js]_
- اجرای سفارش همیشه تأیید صریح دارد و پرو چارت نتیجه‌ی صرافی را از خودش نمی‌سازد _[SafetyPage-h7QQtdzI.js]_

## موارد نامشخص یا مبهم

- عنوان درس‌های آکادمی: در فایل‌ها نیست (از سرور).
- قیمت پرمیوم و پلن‌های VIP فارکس: عدد ثابتی در فایل‌ها نیست.
- وضعیت عضویت رایگان VIP فارکس: صفحه‌ی عضویت هم از آن می‌گوید و هم می‌نویسد دیگر فعال نیست.
- معرفی دوستان و کپی‌ترید به‌عنوان صفحه فقط با نام آمده؛ جزئیات معرفی دوستان نامشخص.
- اینکه «چارت چه می‌گوید» با مدل هوش مصنوعی ساخته می‌شود یا قاعده‌محور: نامشخص.
- فهرست کامل نمادها از سرور می‌آید؛ در فایل‌ها فقط نمادهای پیش‌فرض و مثال‌ها هست.
