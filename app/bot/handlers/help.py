"""Localized Help and About, with an explicit interface-settings entry."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, Message

from app.bot.keyboards.common import button
from app.bot.keyboards.home import home_keyboard
from app.bot.localization import current_interface_language
from app.domain.languages import InterfaceLanguage

router = Router(name=__name__)

HELP_FA = (
    "نام فیلم یا سریال را بفرستید و عنوان درست را انتخاب کنید.\n"
    "برای سریال، فصل و قسمت را مشخص کنید؛ سپس نسخهٔ زیرنویس را بگیرید.\n"
    "با قبلی، بعدی و برگشت بین انتخاب‌ها حرکت کنید.\n"
    "SRT قالب فایل، HI زیرنویس مناسب ناشنوایان و ↓ تعداد دانلود گزارش‌شده است.\n"
    "امتیاز و آمار فقط وقتی ارائه‌دهنده گزارش کند نمایش داده می‌شوند.\n\n"
    "/start منوی اصلی · /search جست‌وجوی جدید\n"
    "/settings زبان رابط · /language زبان زیرنویس\n"
    "/cancel لغو · /help راهنما · /about درباره · /privacy حریم خصوصی"
)
HELP_EN = (
    "Send a movie or TV series name and choose the correct title.\n"
    "For TV, choose a season and episode, then a subtitle version.\n"
    "Use Previous, Next and Back to navigate.\n"
    "SRT is the file format; HI means hearing-impaired; ↓ is the provider download count.\n"
    "Ratings and statistics appear only when provided.\n\n"
    "/start Home · /search New search\n"
    "/settings Interface language · /language Subtitle language\n"
    "/cancel Cancel · /help Help · /about About · /privacy Privacy"
)
ABOUT_FA = (
    "SubMate\n"
    "جست‌وجوی زیرنویس فیلم و سریال با اطلاعات TMDb و ارائه‌دهندهٔ تنظیم‌شده.\n"
    "زیرنویس فارسی و انگلیسی با بررسی محتوای SRT.\n"
    "زبان رابط و زبان زیرنویس جداگانه انتخاب و ذخیره می‌شوند.\n"
    "دسترسی به نسخه‌ها و سهمیه به ارائه‌دهنده بستگی دارد.\n"
    "حقوق زیرنویس متعلق به نویسندگان آن است."
)
ABOUT_EN = (
    "SubMate\n"
    "Find movie and TV subtitles using TMDb and the configured subtitle provider.\n"
    "English and Persian subtitles with SRT validation.\n"
    "Interface and subtitle languages are separate preferences.\n"
    "Availability and quotas depend on the provider.\n"
    "Subtitle rights belong to their respective authors."
)


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        HELP_EN if current_interface_language() is InterfaceLanguage.ENGLISH else HELP_FA,
        reply_markup=home_keyboard(),
    )


@router.message(Command("about"))
async def about_command(message: Message) -> None:
    await message.answer(
        ABOUT_EN if current_interface_language() is InterfaceLanguage.ENGLISH else ABOUT_FA,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button("settings", "settings:open")]]),
    )
