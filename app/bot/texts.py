"""Interface text selected independently of subtitle preferences."""

from app.bot.localization import current_interface_language
from app.bot.translations_de_ru import TRANSLATIONS
from app.domain.languages import LANGUAGE_NAMES, InterfaceLanguage, LanguageCode

TEXTS = {
    "similar_titles": (
        "No exact results. Did you mean one of these?",
        "نتیجهٔ دقیقی پیدا نشد. منظورتان یکی از این عنوان‌هاست؟",
    ),
    "season_pack": ("Download season ZIP", "دانلود ZIP فصل"),
    "season_pack_sent": ("Season ZIP sent.", "فایل ZIP فصل ارسال شد."),
    "season_pack_next": ("What would you like to do next?", "می‌خواهید بعدش چه کار کنید؟"),
    "season_pack_back_episodes": ("⬅️ Back to episodes", "⬅️ برگشت به قسمت‌ها"),
    "season_pack_working": (
        "Checking episode coverage and building the ZIP…",
        "در حال بررسی قسمت‌ها و ساخت فایل ZIP…",
    ),
    "season_pack_ready": (
        "Season {season} · {count} episode subtitles · {language}\nSource: SubDL",
        "فصل {season} · زیرنویس {count} قسمت · {language}\nمنبع: SubDL",
    ),
    "season_pack_missing": (
        "No complete SRT pack was found for this season and language. "
        "Choose an episode below or change language.",
        "بستهٔ کامل SRT برای این فصل و زبان پیدا نشد. یک قسمت انتخاب کنید یا زبان را تغییر دهید.",
    ),
    "season_pack_uncertain": (
        "Telegram did not confirm the ZIP upload. Check the chat before requesting it again.",
        "تلگرام ارسال ZIP را تأیید نکرد. پیش از درخواست دوباره، گفتگو را بررسی کنید.",
    ),
    "home_settings": ("⚙️ Settings", "⚙️ تنظیمات"),
    "source": ("Source", "منبع"),
    "received": ("I received the file", "فایل را دریافت کردم"),
    "resend_confirm": ("Not received — send again", "دریافت نشد؛ دوباره بفرست"),
    "receipt_resolved": ("Thanks. Choose your next action.", "ممنون؛ گزینهٔ بعدی را انتخاب کنید."),
    "upload_failed": (
        "Telegram rejected this upload. Retry or choose another subtitle.",
        "تلگرام ارسال فایل را نپذیرفت؛ دوباره تلاش کنید یا نسخهٔ دیگری انتخاب کنید.",
    ),
    "invalid_malformed": (
        "This file has malformed or empty SRT cues. It was removed; choose another version.",
        "ساختار یا زمان‌بندی SRT این فایل خراب یا خالی است؛ حذف شد. نسخهٔ دیگری انتخاب کنید.",
    ),
    "invalid_unsupported": (
        "This file is an archive or unsupported format. It was removed; choose an SRT version.",
        "این فایل آرشیو یا قالب پشتیبانی‌نشده است؛ حذف شد. یک نسخهٔ SRT انتخاب کنید.",
    ),
    "invalid_decoding": (
        "This file cannot be decoded safely. It was removed; choose another version.",
        "رمزگشایی متن این فایل ممکن نیست؛ حذف شد. نسخهٔ دیگری انتخاب کنید.",
    ),
    "invalid_unsafe_content": (
        "This file contains unsafe content. It was removed; choose another version.",
        "این فایل محتوای ناامن دارد؛ حذف شد. نسخهٔ دیگری انتخاب کنید.",
    ),
    "privacy_notice": (
        "Privacy: the bot stores your Telegram user ID and separate subtitle/interface-language "
        "preferences. Your display name is used for the welcome and is not stored. "
        "Searches are held temporarily in memory/cache and are not intentionally logged or stored "
        "in preference tables. TMDb and the subtitle provider receive the identifiers and subtitle "
        "language needed for your request.\n\nCopyright: subtitles belong to their authors. "
        "SubDL or OpenSubtitles.com supplies files for personal, lawful use, with attribution "
        "when available.",
        "حریم خصوصی: شناسهٔ تلگرام و ترجیحات جداگانهٔ زبان رابط و زیرنویس ذخیره می‌شوند. "
        "نام نمایشی فقط برای خوشامدگویی استفاده می‌شود و ذخیره نمی‌شود. جست‌وجوها موقتاً "
        "در حافظه یا کش نگه داشته می‌شوند و عمداً در لاگ یا جدول ترجیحات ثبت نمی‌شوند. "
        "شناسهٔ اثر و زبان موردنیاز به TMDb و ارائه‌دهندهٔ زیرنویس ارسال می‌شود.\n\n"
        "حق نشر: زیرنویس‌ها متعلق به نویسندگانشان هستند. فایل‌ها از SubDL یا OpenSubtitles.com "
        "برای استفادهٔ شخصی و قانونی دریافت می‌شوند و نام منبع زیر فایل نمایش داده می‌شود.",
    ),
    "back_list": ("⬅️ Back to subtitle list", "⬅️ برگشت به لیست زیرنویس‌ها"),
    "back_episodes": ("⬅️ Choose another episode", "⬅️ برگشت به انتخاب قسمت"),
    "back_seasons": ("⬅️ Back to seasons", "⬅️ برگشت به انتخاب فصل"),
    "language": ("🌐 Change language", "🌐 تغییر زبان"),
    "search": ("🔎 New search", "🔎 جست‌وجوی جدید"),
    "retry": ("Retry", "تلاش مجدد"),
    "another": ("📄 Another version", "📄 نسخهٔ دیگر"),
    "more": ("More results", "نسخه‌های بیشتر"),
    "cancel": ("Cancel", "لغو"),
    "season": ("Season", "فصل"),
    "episode": ("Episode", "قسمت"),
    "seasons": ("Choose a season:", "یک فصل انتخاب کنید:"),
    "episodes": ("Choose an episode:", "یک قسمت انتخاب کنید:"),
    "no_episodes": (
        "No episodes available. Choose another season or title.",
        "قسمتی در دسترس نیست. فصل یا عنوان دیگری را انتخاب کنید.",
    ),
    "empty": (
        "No usable subtitles remain. Choose another option below.",
        "نسخهٔ قابل استفاده‌ای باقی نمانده است. گزینهٔ دیگری را انتخاب کنید.",
    ),
    "title": ("Send the name of a movie or TV series.", "نام فیلم یا سریال را بفرستید."),
    "picker": (
        "Choose your subtitle language, or type its name (e.g. Arabic or العربية). "
        "For a movie title, choose New search.",
        "زبان زیرنویس را انتخاب کنید یا نامش را بنویسید؛ مثلاً فارسی، عربی یا ترکی. "
        "برای نوشتن نام فیلم، «جست‌وجوی جدید» را بزنید.",
    ),
    "language_not_found": (
        "No supported language matched. Try its native name, English name, or code (e.g. ar).",
        "این زبان در فهرست پیدا نشد. نام فارسی، نام اصلی یا کد آن را امتحان کنید؛ مثلاً ar.",
    ),
    "sent": ("Subtitle sent. What next?", "زیرنویس ارسال شد. مرحلهٔ بعد را انتخاب کنید."),
    "upload": (
        "Telegram could not confirm file delivery. Check the chat before retrying.",
        "تلگرام دریافت فایل را تأیید نکرد. پیش از تلاش دوباره، پیام‌های گفتگو را بررسی کنید.",
    ),
    "unsafe": (
        "This file was removed because it is unsafe, corrupt, or not valid SRT.",
        "این فایل به دلیل خرابی، ناامن‌بودن یا SRT نامعتبر از پیشنهادها حذف شد.",
    ),
    "home_search": ("🔎 Subtitle search", "🔎 جست‌وجوی زیرنویس"),
    "home_language": ("🌐 Subtitle language", "🌐 زبان زیرنویس"),
    "home_help": ("❓ Help", "❓ راهنما"),
    "home_about": ("ℹ️ About SubMate", "ℹ️ دربارهٔ SubMate"),
    "other_episode": ("📺 Another episode", "📺 انتخاب قسمت دیگر"),
    "back_titles": ("⬅️ Back to titles", "⬅️ برگشت به عنوان‌ها"),
    "back": ("⬅️ Back", "⬅️ برگشت"),
    "titles": ("Choose the correct title:", "عنوان درست را انتخاب کنید:"),
    "previous": ("Previous", "قبلی"),
    "next": ("Next", "بعدی"),
    "processing": ("Downloading subtitle…", "در حال دریافت زیرنویس…"),
    "busy": ("Please wait for this delivery to finish.", "دریافت در حال انجام است؛ کمی صبر کنید."),
    "stale": (
        "This button expired. Use the latest buttons or New search.",
        "این دکمه قدیمی است؛ از دکمه‌های فعلی یا جست‌وجوی جدید استفاده کنید.",
    ),
    "no_titles": (
        "No titles found. Check the spelling or try a shorter part of the title.",
        "عنوانی پیدا نشد؛ املای نام را بررسی کنید یا بخش کوتاه‌تری از آن را بفرستید.",
    ),
    "not_set": ("Not set", "هنوز انتخاب نشده"),
    "greeting_named": ("Hi {name} 👋", "سلام {name} 👋"),
    "greeting": ("Hi 👋", "سلام 👋"),
    "welcome": ("Welcome to SubMate!", "به SubMate خوش اومدی!"),
    "welcome_search": (
        "Send a movie or TV series name to find subtitles.",
        "اسم فیلم یا سریالت رو بفرست تا زیرنویسش رو پیدا کنیم.",
    ),
    "saved_subtitle": ("Saved subtitle language", "زبان زیرنویس ذخیره‌شده"),
    "interface_picker": ("Choose your interface language:", "زبان رابط را انتخاب کنید:"),
    "interface_stale": (
        "This language picker expired. Open /settings or send /start.",
        "این انتخاب‌گر قدیمی است؛ /settings یا /start را بفرستید.",
    ),
    "settings": ("⚙️ Settings", "⚙️ تنظیمات"),
    "preference_error": (
        "Settings are unavailable. Please try again.",
        "تنظیمات در دسترس نیست؛ دوباره تلاش کنید.",
    ),
    "demo_notice": (
        "DEMO MODE: files are original test samples, not movie subtitles.",
        "حالت نمایشی فعال است؛ فایل‌ها نمونهٔ آزمایشی‌اند.",
    ),
    "search_placeholder": ("Movie or TV series name…", "نام فیلم یا سریال…"),
    "subtitle_language": ("Subtitle language", "زبان زیرنویس"),
    "choose_version": ("Choose a subtitle version:", "نسخهٔ زیرنویس را انتخاب کنید:"),
    "forced": ("Forced", "اجباری"),
    "cancel_done": (
        "Action cancelled. Select Subtitle search to continue.",
        "عملیات لغو شد. برای ادامه جست‌وجوی زیرنویس را بزنید.",
    ),
    "quota_error": (
        "The provider quota is exhausted. Try later or choose another title.",
        "سهمیهٔ ارائه‌دهنده تمام شده است؛ بعداً تلاش کنید یا عنوان دیگری انتخاب کنید.",
    ),
    "auth_error": (
        "Provider access was rejected. The operator must check account settings.",
        "دسترسی ارائه‌دهنده رد شد؛ تنظیمات حساب باید بررسی شود.",
    ),
    "config_error": (
        "The provider is not configured. The operator must check settings.",
        "ارائه‌دهنده تنظیم نشده است؛ مدیر ربات باید تنظیمات را بررسی کند.",
    ),
    "rate_error": (
        "Too many requests. Please try again later.",
        "درخواست‌ها زیاد است؛ کمی بعد دوباره تلاش کنید.",
    ),
    "rate_wait": (" Wait about {seconds} seconds.", " حدود {seconds} ثانیه صبر کنید."),
    "not_found_error": (
        "This version is no longer available. Choose another version.",
        "این نسخه دیگر در دسترس نیست؛ نسخهٔ دیگری انتخاب کنید.",
    ),
    "link_error": (
        "The download link is unavailable. Retry or choose another version.",
        "لینک دانلود در دسترس نیست؛ دوباره تلاش کنید یا نسخهٔ دیگری بگیرید.",
    ),
    "service_auth_error": (
        "Service access was rejected. Account settings need review.",
        "دسترسی سرویس رد شد؛ تنظیمات حساب باید بررسی شود.",
    ),
    "provider_error": (
        "Could not connect to the provider. Please try again.",
        "ارتباط با ارائه‌دهنده موقتاً برقرار نشد؛ دوباره تلاش کنید.",
    ),
    "request_error": (
        "Request failed. Try another input or option.",
        "درخواست انجام نشد؛ ورودی یا گزینهٔ دیگری را امتحان کنید.",
    ),
}


def ui(key: str, interface_language: InterfaceLanguage | None = None) -> str:
    language = interface_language or current_interface_language()
    if language in {InterfaceLanguage.GERMAN, InterfaceLanguage.RUSSIAN}:
        return TRANSLATIONS[key][0 if language is InterfaceLanguage.GERMAN else 1]
    return TEXTS[key][1 if language is InterfaceLanguage.PERSIAN else 0]


def subtitle_language_label(language: LanguageCode | None) -> str:
    if language is None:
        return ui("not_set")
    return LANGUAGE_NAMES[language][0]
