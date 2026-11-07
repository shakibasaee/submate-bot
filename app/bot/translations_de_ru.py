"""German and Russian UI copy; subtitle names remain native."""

TRANSLATIONS = {
    "similar_titles": (
        "Kein genauer Treffer. Meinten Sie einen dieser Titel?",
        "Точного совпадения нет. Вы имели в виду один из этих вариантов?",
    ),
    "season_pack": ("Staffel als ZIP laden", "Скачать сезон ZIP"),
    "season_pack_sent": ("Staffel-ZIP gesendet.", "ZIP сезона отправлен."),
    "season_pack_next": ("Wie möchten Sie fortfahren?", "Что хотите сделать дальше?"),
    "season_pack_back_episodes": ("⬅️ Zurück zu den Folgen", "⬅️ К списку серий"),
    "season_pack_working": (
        "Folgen werden geprüft und ZIP erstellt…",
        "Проверяем серии и создаём ZIP…",
    ),
    "season_pack_ready": (
        "Staffel {season} · {count} Folgen · {language}\nQuelle: SubDL",
        "Сезон {season} · {count} серий · {language}\nИсточник: SubDL",
    ),
    "season_pack_missing": (
        "Kein vollständiges SRT-Paket gefunden. Wählen Sie eine Folge oder eine andere Sprache.",
        "Полного комплекта SRT нет. Выберите серию или другой язык.",
    ),
    "season_pack_uncertain": (
        "Telegram hat die ZIP-Zustellung nicht bestätigt. Prüfen Sie zuerst den Chat.",
        "Telegram не подтвердил отправку ZIP. Сначала проверьте чат.",
    ),
    "home_settings": ("⚙️ Einstellungen", "⚙️ Настройки"),
    "uploader": ("Hochgeladen von", "Автор загрузки"),
    "received": ("Datei erhalten", "Файл получен"),
    "resend_confirm": ("Nicht erhalten – erneut senden", "Не получен — отправить снова"),
    "receipt_resolved": (
        "Danke. Wählen Sie den nächsten Schritt.",
        "Спасибо. Выберите следующее действие.",
    ),
    "upload_failed": (
        "Telegram hat die Datei abgelehnt. Versuchen Sie es erneut oder wählen Sie "
        "eine andere Version.",
        "Telegram отклонил файл. Повторите попытку или выберите другую версию.",
    ),
    "invalid_malformed": (
        "Ungültige oder leere SRT-Zeitmarken. Datei entfernt; wählen Sie eine andere Version.",
        "Пустая или некорректная структура SRT. Файл исключён; выберите другую версию.",
    ),
    "invalid_unsupported": (
        "Archiv oder nicht unterstütztes Format. Wählen Sie eine SRT-Version.",
        "Архив или неподдерживаемый формат. Выберите версию SRT.",
    ),
    "invalid_decoding": (
        "Der Text konnte nicht sicher dekodiert werden. Wählen Sie eine andere Version.",
        "Не удалось корректно декодировать текст. Выберите другую версию.",
    ),
    "invalid_unsafe_content": (
        "Unsicherer Inhalt. Datei entfernt; wählen Sie eine andere Version.",
        "Небезопасное содержимое. Файл исключён; выберите другую версию.",
    ),
    "privacy_notice": (
        "Datenschutz: Gespeichert werden Ihre Telegram-ID und getrennte "
        "Sprachpräferenzen. Ihr Anzeigename wird nur für die Begrüßung verwendet "
        "und nicht gespeichert. Suchanfragen werden vorübergehend im Speicher oder "
        "Cache gehalten, nicht absichtlich protokolliert oder in Präferenztabellen "
        "gespeichert. TMDb und der Untertitelanbieter erhalten die benötigten "
        "Titelkennungen und Sprachangaben.\n"
        "\n"
        "Urheberrecht: Untertitel gehören ihren Autoren. Dateien stammen von SubDL "
        "oder OpenSubtitles.com zur persönlichen, rechtmäßigen Nutzung, mit "
        "Quellenangabe, soweit vorhanden.",
        "Конфиденциальность: сохраняются ваш Telegram ID и отдельные настройки "
        "языков. Имя используется только для приветствия и не сохраняется. Поиск "
        "временно хранится в памяти или кэше, но намеренно не записывается в "
        "журналы или таблицы настроек. TMDb и поставщик субтитров получают "
        "необходимые идентификаторы и язык.\n"
        "\n"
        "Авторские права: субтитры принадлежат их авторам. SubDL или "
        "OpenSubtitles.com предоставляет файлы для личного законного "
        "использования; источник указывается при наличии.",
    ),
    "back_list": ("⬅️ Zur Untertitelliste", "⬅️ К списку субтитров"),
    "back_episodes": ("⬅️ Andere Folge wählen", "⬅️ Выбрать другую серию"),
    "back_seasons": ("⬅️ Zu den Staffeln", "⬅️ К выбору сезона"),
    "language": ("🌐 Sprache ändern", "🌐 Изменить язык"),
    "search": ("🔎 Neue Suche", "🔎 Новый поиск"),
    "retry": ("Erneut versuchen", "Повторить"),
    "another": ("📄 Andere Version", "📄 Другая версия"),
    "more": ("Weitere Ergebnisse", "Ещё результаты"),
    "cancel": ("Abbrechen", "Отмена"),
    "season": ("Staffel", "Сезон"),
    "episode": ("Folge", "Серия"),
    "seasons": ("Staffel wählen:", "Выберите сезон:"),
    "episodes": ("Folge wählen:", "Выберите серию:"),
    "no_episodes": (
        "Keine Folgen verfügbar. Wählen Sie eine andere Staffel oder einen anderen Titel.",
        "Серии недоступны. Выберите другой сезон или название.",
    ),
    "empty": (
        "Keine verwendbaren Untertitel vorhanden. Wählen Sie eine andere Option.",
        "Подходящих субтитров не осталось. Выберите другое действие.",
    ),
    "title": (
        "Senden Sie den Namen eines Films oder einer Serie.",
        "Отправьте название фильма или сериала.",
    ),
    "picker": (
        "Untertitelsprache wählen oder ihren Namen eingeben, z. B. Deutsch. Für einen "
        "Filmtitel wählen Sie Neue Suche.",
        "Выберите язык субтитров или введите его название, например русский. Для поиска "
        "фильма нажмите Новый поиск.",
    ),
    "language_not_found": (
        "Sprache nicht gefunden. Versuchen Sie den ursprünglichen oder "
        "englischen Namen oder einen Code wie de.",
        "Язык не найден. Введите его родное или английское название либо код, например ru.",
    ),
    "sent": ("Untertitel gesendet. Wie geht es weiter?", "Субтитры отправлены. Что дальше?"),
    "upload": (
        "Telegram konnte die Zustellung nicht bestätigen. Prüfen Sie den Chat vor einem "
        "erneuten Versuch.",
        "Telegram не подтвердил доставку. Проверьте чат перед повторной отправкой.",
    ),
    "unsafe": (
        "Die Datei wurde als unsicher oder ungültig entfernt. Wählen Sie eine andere Version.",
        "Файл исключён как небезопасный или некорректный. Выберите другую версию.",
    ),
    "home_search": ("🔎 Untertitel suchen", "🔎 Поиск субтитров"),
    "home_language": ("🌐 Untertitelsprache", "🌐 Язык субтитров"),
    "home_help": ("❓ Hilfe", "❓ Помощь"),
    "home_about": ("ℹ️ Über SubMate", "ℹ️ О SubMate"),
    "other_episode": ("📺 Andere Folge", "📺 Другая серия"),
    "back_titles": ("⬅️ Zu den Titeln", "⬅️ К названиям"),
    "back": ("⬅️ Zurück", "⬅️ Назад"),
    "titles": ("Passenden Titel wählen:", "Выберите нужное название:"),
    "previous": ("Zurück", "Предыдущая"),
    "next": ("Weiter", "Следующая"),
    "processing": ("Untertitel werden geladen…", "Загружаем субтитры…"),
    "busy": (
        "Bitte warten Sie, bis die Übertragung beendet ist.",
        "Дождитесь завершения отправки.",
    ),
    "stale": (
        "Diese Schaltfläche ist abgelaufen. Verwenden Sie die aktuellen Schaltflächen oder "
        "Neue Suche.",
        "Эта кнопка устарела. Используйте последние кнопки или Новый поиск.",
    ),
    "no_titles": (
        "Keine Titel gefunden. Prüfen Sie die Schreibweise oder verwenden Sie einen kürzeren Teil.",
        "Ничего не найдено. Проверьте написание или введите часть названия.",
    ),
    "not_set": ("Nicht ausgewählt", "Не выбран"),
    "greeting_named": ("Hallo {name} 👋", "Привет, {name} 👋"),
    "greeting": ("Hallo 👋", "Привет 👋"),
    "welcome": ("Willkommen bei SubMate!", "Добро пожаловать в SubMate!"),
    "welcome_search": (
        "Senden Sie einen Film- oder Seriennamen, um Untertitel zu finden.",
        "Отправьте название фильма или сериала, чтобы найти субтитры.",
    ),
    "saved_subtitle": ("Gespeicherte Untertitelsprache", "Сохранённый язык субтитров"),
    "interface_picker": (
        "Menüsprache wählen oder eingeben: English, فارسی, Deutsch, Русский.",
        "Выберите или введите язык меню: English, فارسی, Deutsch, Русский.",
    ),
    "interface_stale": (
        "Diese Sprachauswahl ist abgelaufen. Verwenden Sie /settings oder /start.",
        "Этот выбор языка устарел. Отправьте /settings или /start.",
    ),
    "settings": ("⚙️ Einstellungen", "⚙️ Настройки"),
    "preference_error": (
        "Einstellungen sind nicht verfügbar. Bitte erneut versuchen.",
        "Настройки недоступны. Попробуйте ещё раз.",
    ),
    "demo_notice": (
        "DEMOMODUS: Dateien sind Testbeispiele, keine Filmuntertitel.",
        "ДЕМО: файлы — тестовые примеры, а не субтитры фильма.",
    ),
    "search_placeholder": ("Film- oder Serienname…", "Название фильма или сериала…"),
    "subtitle_language": ("Untertitelsprache", "Язык субтитров"),
    "choose_version": ("Untertitelversion wählen:", "Выберите версию субтитров:"),
    "forced": ("Erzwungen", "Форсированные"),
    "cancel_done": (
        "Abgebrochen. Wählen Sie Untertitel suchen.",
        "Действие отменено. Нажмите Поиск субтитров.",
    ),
    "quota_error": (
        "Das Anbieterkontingent ist aufgebraucht. Versuchen Sie es später.",
        "Лимит поставщика исчерпан. Попробуйте позже.",
    ),
    "auth_error": (
        "Der Anbieter hat den Zugriff abgelehnt. Der Betreiber muss die Kontoeinstellungen prüfen.",
        "Поставщик отклонил доступ. Администратору нужно проверить настройки аккаунта.",
    ),
    "config_error": (
        "Der Anbieter ist nicht eingerichtet. Der Betreiber muss die Einstellungen prüfen.",
        "Поставщик не настроен. Администратору нужно проверить настройки.",
    ),
    "rate_error": (
        "Zu viele Anfragen. Versuchen Sie es später erneut.",
        "Слишком много запросов. Попробуйте позже.",
    ),
    "rate_wait": (" Warten Sie etwa {seconds} Sekunden.", " Подождите примерно {seconds} сек."),
    "not_found_error": (
        "Diese Version ist nicht mehr verfügbar. Wählen Sie eine andere.",
        "Эта версия больше недоступна. Выберите другую.",
    ),
    "link_error": (
        "Download-Link nicht verfügbar. Erneut versuchen oder andere Version wählen.",
        "Ссылка недоступна. Повторите попытку или выберите другую версию.",
    ),
    "service_auth_error": (
        "Dienstzugriff abgelehnt. Die Kontoeinstellungen müssen geprüft werden.",
        "Доступ к сервису отклонён. Проверьте настройки аккаунта.",
    ),
    "provider_error": (
        "Der Anbieter ist nicht erreichbar. Bitte erneut versuchen.",
        "Не удалось связаться с поставщиком. Попробуйте ещё раз.",
    ),
    "request_error": (
        "Anfrage fehlgeschlagen. Versuchen Sie eine andere Eingabe oder Option.",
        "Запрос не выполнен. Попробуйте другой ввод или действие.",
    ),
    "help_text": (
        "Senden Sie einen Film- oder Seriennamen. Wählen Sie Titel, Staffel, Folge und "
        "Untertitel. Nutzen Sie Zurück und Weiter. SRT ist das Dateiformat, HI "
        "kennzeichnet Untertitel für Hörgeschädigte.\n"
        "/start Menü · /search Suche · /settings Menüsprache · /language "
        "Untertitelsprache · /cancel Abbrechen · /help Hilfe · /about Über SubMate · "
        "/privacy Datenschutz",
        "Отправьте название фильма или сериала. Выберите название, сезон, серию и "
        "субтитры. Используйте Назад и Следующая. SRT — формат файла, HI — субтитры для "
        "слабослышащих.\n"
        "/start Меню · /search Поиск · /settings Язык меню · /language Язык субтитров · "
        "/cancel Отмена · /help Помощь · /about О SubMate · /privacy "
        "Конфиденциальность",
    ),
    "about_text": (
        "SubMate\n"
        "Film- und Serienuntertitel mit TMDb und dem eingerichteten Anbieter. Zehn "
        "Untertitelsprachen mit SRT-Prüfung. Menü- und Untertitelsprache werden "
        "getrennt gespeichert. Verfügbarkeit und Kontingente hängen vom Anbieter ab. "
        "Untertitel gehören ihren Autoren.",
        "SubMate\n"
        "Субтитры к фильмам и сериалам через TMDb и настроенного поставщика. Десять "
        "языков субтитров с проверкой SRT. Языки меню и субтитров сохраняются "
        "отдельно. Наличие файлов и лимиты зависят от поставщика. Субтитры принадлежат "
        "их авторам.",
    ),
}
