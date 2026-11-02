"""Transactional email copy: one {subject, text, html} per kind and locale.

Keep copy short and plain-text-friendly. English is the source and the
fallback for any locale without its own entry, so adding a locale is a
data-only change here. ``transactional_email`` renders it.
"""

TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "welcome": {
        "en": {
            "subject": "Welcome to Phonia",
            "text": (
                "Hi {name},\n\n"
                "Welcome to Phonia — your personal AI chat that remembers what "
                "matters to you. Ask it anything, or jot down reminders.\n\n"
                "A few things to try first:\n"
                "  - Tell Phonia about yourself so its memory gets useful fast.\n"
                "  - Set your preferred language and emoji use in Settings.\n\n"
                "Cheers,\nThe Phonia team"
            ),
            "html": (
                "<p>Hi {name},</p>"
                "<p>Welcome to <strong>Phonia</strong> — your personal AI chat that "
                "remembers what matters to you. Ask it anything, or jot down reminders.</p>"
                "<p>A few things to try first:</p>"
                "<ul>"
                "<li>Tell Phonia about yourself so its memory gets useful fast.</li>"
                "<li>Set your preferred language and emoji use in Settings.</li>"
                "</ul>"
                "<p>Cheers,<br/>The Phonia team</p>"
            ),
        },
        "es": {
            "subject": "Bienvenido a Phonia",
            "text": (
                "Hola {name},\n\n"
                "Bienvenido a Phonia — tu chat de IA personal que recuerda lo que te "
                "importa. Pregúntale cualquier cosa, anota recordatorios o inicia un "
                "proyecto de aprendizaje.\n\n"
                "Algunas cosas para empezar:\n"
                "  - Cuéntale a Phonia sobre ti para que su memoria sea útil.\n"
                "  - Configura tu idioma, tono y longitud de respuesta en Ajustes.\n\n"
                "Saludos,\nEl equipo de Phonia"
            ),
            "html": (
                "<p>Hola {name},</p>"
                "<p>Bienvenido a <strong>Phonia</strong> — tu chat de IA personal que "
                "recuerda lo que te importa.</p>"
                "<p>Algunas cosas para empezar:</p>"
                "<ul>"
                "<li>Cuéntale a Phonia sobre ti.</li>"
                "<li>Configura idioma, tono y longitud en Ajustes.</li>"
                "</ul>"
                "<p>Saludos,<br/>El equipo de Phonia</p>"
            ),
        },
        "fr": {
            "subject": "Bienvenue sur Phonia",
            "text": (
                "Bonjour {name},\n\n"
                "Bienvenue sur Phonia — votre chat IA personnel qui se souvient de ce "
                "qui compte pour vous. Posez vos questions, notez vos rappels ou "
                "lancez un projet d'apprentissage.\n\n"
                "Quelques idées pour commencer :\n"
                "  - Parlez de vous à Phonia pour enrichir sa mémoire.\n"
                "  - Choisissez votre langue, ton et longueur de réponse.\n\n"
                "Cordialement,\nL'équipe Phonia"
            ),
            "html": (
                "<p>Bonjour {name},</p>"
                "<p>Bienvenue sur <strong>Phonia</strong> — votre chat IA personnel.</p>"
                "<p>Pour commencer :</p>"
                "<ul>"
                "<li>Parlez de vous à Phonia.</li>"
                "<li>Choisissez langue, ton et longueur.</li>"
                "</ul>"
                "<p>Cordialement,<br/>L'équipe Phonia</p>"
            ),
        },
        "de": {
            "subject": "Willkommen bei Phonia",
            "text": (
                "Hallo {name},\n\n"
                "Willkommen bei Phonia — deinem persönlichen KI-Chat, der sich an das "
                "erinnert, was dir wichtig ist. Frag alles, notiere Erinnerungen oder "
                "starte ein Lernprojekt.\n\n"
                "Ein paar Tipps zum Start:\n"
                "  - Erzähl Phonia über dich, damit das Gedächtnis nützlich wird.\n"
                "  - Stelle Sprache, Ton und Antwortlänge in den Einstellungen ein.\n\n"
                "Viele Grüße,\nDas Phonia-Team"
            ),
            "html": (
                "<p>Hallo {name},</p>"
                "<p>Willkommen bei <strong>Phonia</strong> — deinem persönlichen KI-Chat.</p>"
                "<p>Zum Start:</p>"
                "<ul>"
                "<li>Erzähl Phonia über dich.</li>"
                "<li>Stelle Sprache, Ton und Antwortlänge ein.</li>"
                "</ul>"
                "<p>Viele Grüße,<br/>Das Phonia-Team</p>"
            ),
        },
        "it": {
            "subject": "Benvenuto in Phonia",
            "text": (
                "Ciao {name},\n\n"
                "Benvenuto in Phonia — la tua chat IA personale che ricorda ciò che "
                "ti importa. Chiedi qualsiasi cosa, annota promemoria o inizia un "
                "progetto di apprendimento.\n\n"
                "Qualche idea per iniziare:\n"
                "  - Racconta a Phonia di te per arricchire la sua memoria.\n"
                "  - Imposta lingua, tono e lunghezza delle risposte.\n\n"
                "Saluti,\nIl team di Phonia"
            ),
            "html": (
                "<p>Ciao {name},</p>"
                "<p>Benvenuto in <strong>Phonia</strong> — la tua chat IA personale.</p>"
                "<p>Per iniziare:</p>"
                "<ul>"
                "<li>Racconta a Phonia di te.</li>"
                "<li>Imposta lingua, tono e lunghezza.</li>"
                "</ul>"
                "<p>Saluti,<br/>Il team di Phonia</p>"
            ),
        },
        "pt": {
            "subject": "Bem-vindo ao Phonia",
            "text": (
                "Olá {name},\n\n"
                "Bem-vindo ao Phonia — seu chat de IA pessoal que lembra do que "
                "importa para você. Pergunte qualquer coisa, anote lembretes ou inicie "
                "um projeto de aprendizado.\n\n"
                "Algumas dicas para começar:\n"
                "  - Conte ao Phonia sobre você para enriquecer a memória.\n"
                "  - Defina idioma, tom e tamanho das respostas.\n\n"
                "Abraços,\nEquipe Phonia"
            ),
            "html": (
                "<p>Olá {name},</p>"
                "<p>Bem-vindo ao <strong>Phonia</strong> — seu chat de IA pessoal.</p>"
                "<p>Para começar:</p>"
                "<ul>"
                "<li>Conte ao Phonia sobre você.</li>"
                "<li>Defina idioma, tom e tamanho.</li>"
                "</ul>"
                "<p>Abraços,<br/>Equipe Phonia</p>"
            ),
        },
        "ru": {
            "subject": "Добро пожаловать в Phonia",
            "text": (
                "Здравствуйте, {name}!\n\n"
                "Добро пожаловать в Phonia — ваш личный ИИ-чат, который запоминает то, "
                "что вам важно. Задавайте вопросы, делайте заметки и напоминания или "
                "начните учебный проект.\n\n"
                "С чего начать:\n"
                "  - Расскажите Phonia о себе, чтобы память стала полезной.\n"
                "  - Выберите язык, тон и длину ответов в Настройках.\n\n"
                "С уважением,\nКоманда Phonia"
            ),
            "html": (
                "<p>Здравствуйте, {name}!</p>"
                "<p>Добро пожаловать в <strong>Phonia</strong> — ваш личный ИИ-чат.</p>"
                "<p>С чего начать:</p>"
                "<ul>"
                "<li>Расскажите Phonia о себе.</li>"
                "<li>Выберите язык, тон и длину ответов.</li>"
                "</ul>"
                "<p>С уважением,<br/>Команда Phonia</p>"
            ),
        },
        "tr": {
            "subject": "Phonia'ya hoş geldiniz",
            "text": (
                "Merhaba {name},\n\n"
                "Phonia'ya hoş geldiniz — sizin için önemli olanları hatırlayan kişisel "
                "yapay zeka sohbetiniz. Soru sorun, hatırlatmalar not edin veya bir "
                "öğrenme projesi başlatın.\n\n"
                "Başlamak için birkaç öneri:\n"
                "  - Phonia'ya kendinizden bahsedin ki belleği yararlı olsun.\n"
                "  - Ayarlar'da dil, ton ve yanıt uzunluğunu seçin.\n\n"
                "Sevgiler,\nRecall ekibi"
            ),
            "html": (
                "<p>Merhaba {name},</p>"
                "<p>Phonia'ya hoş geldiniz — kişisel yapay zeka sohbetiniz.</p>"
                "<p>Başlamak için:</p>"
                "<ul>"
                "<li>Phonia'ya kendinizden bahsedin.</li>"
                "<li>Dil, ton ve yanıt uzunluğunu ayarlayın.</li>"
                "</ul>"
                "<p>Sevgiler,<br/>Phonia ekibi</p>"
            ),
        },
    },
    "receipt": {
        "en": {
            "subject": "Your Phonia receipt",
            "text": (
                "Hi {name},\n\n"
                "Thanks for subscribing to Phonia!\n\n"
                "{event_line}"
                "{expiration_line}"
                "\nYou can review or manage your subscription anytime from Settings "
                "in the app.\n\n"
                "Cheers,\nThe Phonia team"
            ),
            "html": (
                "<p>Hi {name},</p>"
                "<p>Thanks for subscribing to <strong>Phonia</strong>!</p>"
                "<p>"
                "{event_line_html}"
                "{expiration_line_html}"
                "</p>"
                "<p>You can review or manage your subscription anytime from Settings "
                "in the app.</p>"
                "<p>Cheers,<br/>The Phonia team</p>"
            ),
        },
        "es": {
            "subject": "Tu recibo de Phonia",
            "text": (
                "Hola {name},\n\n"
                "¡Gracias por suscribirte a Phonia!\n\n"
                "{event_line}"
                "{expiration_line}"
                "\nPuedes gestionar tu suscripción cuando quieras desde Ajustes.\n\n"
                "Saludos,\nEl equipo de Phonia"
            ),
            "html": (
                "<p>Hola {name},</p>"
                "<p>¡Gracias por suscribirte a <strong>Phonia</strong>!</p>"
                "<p>{event_line_html}{expiration_line_html}</p>"
                "<p>Gestiona tu suscripción desde Ajustes en la app.</p>"
                "<p>Saludos,<br/>El equipo de Phonia</p>"
            ),
        },
        "fr": {
            "subject": "Votre reçu Phonia",
            "text": (
                "Bonjour {name},\n\n"
                "Merci pour votre abonnement à Phonia !\n\n"
                "{event_line}"
                "{expiration_line}"
                "\nGérez votre abonnement à tout moment depuis les Réglages.\n\n"
                "Cordialement,\nL'équipe Phonia"
            ),
            "html": (
                "<p>Bonjour {name},</p>"
                "<p>Merci pour votre abonnement à <strong>Phonia</strong> !</p>"
                "<p>{event_line_html}{expiration_line_html}</p>"
                "<p>Gérez votre abonnement depuis les Réglages.</p>"
                "<p>Cordialement,<br/>L'équipe Phonia</p>"
            ),
        },
        "de": {
            "subject": "Deine Phonia-Quittung",
            "text": (
                "Hallo {name},\n\n"
                "Danke für dein Phonia-Abo!\n\n"
                "{event_line}"
                "{expiration_line}"
                "\nVerwalte dein Abo jederzeit in den Einstellungen.\n\n"
                "Viele Grüße,\nDas Phonia-Team"
            ),
            "html": (
                "<p>Hallo {name},</p>"
                "<p>Danke für dein <strong>Phonia</strong>-Abo!</p>"
                "<p>{event_line_html}{expiration_line_html}</p>"
                "<p>Verwalte dein Abo in den Einstellungen.</p>"
                "<p>Viele Grüße,<br/>Das Phonia-Team</p>"
            ),
        },
        "it": {
            "subject": "La tua ricevuta di Phonia",
            "text": (
                "Ciao {name},\n\n"
                "Grazie per l'abbonamento a Phonia!\n\n"
                "{event_line}"
                "{expiration_line}"
                "\nGestisci il tuo abbonamento dalle Impostazioni.\n\n"
                "Saluti,\nIl team di Phonia"
            ),
            "html": (
                "<p>Ciao {name},</p>"
                "<p>Grazie per l'abbonamento a <strong>Phonia</strong>!</p>"
                "<p>{event_line_html}{expiration_line_html}</p>"
                "<p>Gestisci l'abbonamento dalle Impostazioni.</p>"
                "<p>Saluti,<br/>Il team di Phonia</p>"
            ),
        },
        "pt": {
            "subject": "Seu recibo do Phonia",
            "text": (
                "Olá {name},\n\n"
                "Obrigado por assinar o Phonia!\n\n"
                "{event_line}"
                "{expiration_line}"
                "\nGerencie sua assinatura a qualquer momento nos Ajustes.\n\n"
                "Abraços,\nEquipe Phonia"
            ),
            "html": (
                "<p>Olá {name},</p>"
                "<p>Obrigado por assinar o <strong>Phonia</strong>!</p>"
                "<p>{event_line_html}{expiration_line_html}</p>"
                "<p>Gerencie sua assinatura nos Ajustes.</p>"
                "<p>Abraços,<br/>Equipe Phonia</p>"
            ),
        },
        "ru": {
            "subject": "Ваш чек Phonia",
            "text": (
                "Здравствуйте, {name}!\n\n"
                "Спасибо за подписку на Phonia!\n\n"
                "{event_line}"
                "{expiration_line}"
                "\nУправлять подпиской можно в Настройках приложения.\n\n"
                "С уважением,\nКоманда Phonia"
            ),
            "html": (
                "<p>Здравствуйте, {name}!</p>"
                "<p>Спасибо за подписку на <strong>Phonia</strong>!</p>"
                "<p>{event_line_html}{expiration_line_html}</p>"
                "<p>Управлять подпиской — в Настройках.</p>"
                "<p>С уважением,<br/>Команда Phonia</p>"
            ),
        },
        "tr": {
            "subject": "Phonia dekontunuz",
            "text": (
                "Merhaba {name},\n\n"
                "Phonia'ya abone olduğunuz için teşekkürler!\n\n"
                "{event_line}"
                "{expiration_line}"
                "\nAboneliğinizi Ayarlar'dan istediğiniz zaman yönetebilirsiniz.\n\n"
                "Sevgiler,\nRecall ekibi"
            ),
            "html": (
                "<p>Merhaba {name},</p>"
                "<p><strong>Phonia</strong>'a abone olduğunuz için teşekkürler!</p>"
                "<p>{event_line_html}{expiration_line_html}</p>"
                "<p>Aboneliğinizi Ayarlar'dan yönetin.</p>"
                "<p>Sevgiler,<br/>Phonia ekibi</p>"
            ),
        },
    },
}


TEMPLATES["todo_reminder"] = {
    "en": {
        "subject": "{title}: {content}",
        "text": ("Hi {name},\n\n{title}\n\n{content}\n\nOpen Phonia to mark it done.\n\n— Phonia"),
        "html": (
            "<p>Hi {name},</p>"
            "<p><strong>{title}</strong></p>"
            "<p>{content}</p>"
            "<p>Open Phonia to mark it done.</p>"
            "<p>— Phonia</p>"
        ),
    },
}
