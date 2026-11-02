# ruff: noqa: RUF001 - the lines are written in the app's languages (Turkish dotless i, Cyrillic)
"""The line saved under a reply whose picture was not drawn, in the app's language.

"I couldn't draw the picture (a fox) this time: …" is part of the saved reply, so the
server writes it in ``user.locale``, as the To-do line is (``todos.chat_language``).
Its English showed under a reply in any language. The reason is chosen by the
refusal's ``code`` (``generation.ImageGenerationError``), never by its English, and a
refusal's own text is never pasted in: a code with no line of its own says "failed".
"""

from __future__ import annotations

from typing import Literal

from app.core.validation import normalize_locale_code

Reason = Literal["paused", "not_in_plan", "daily_limit", "content_blocked", "too_slow", "failed"]

# Every code ``generation`` raises, and the line it gets (``test_reply_picture_lines``
# reads the codes off ``generation.py``). The spend cap and drawing switched off share
# the cap's line, as ``turn_intercepts.start_reply_picture`` does before a turn draws.
REASON_BY_CODE: dict[str, Reason] = {
    "spend_cap": "paused",
    "not_available": "paused",
    "not_in_plan": "not_in_plan",
    "daily_limit": "daily_limit",
    "content_blocked": "content_blocked",
    # Storage or attachments off, the chat gone, a bad reference, the provider's bytes.
    "unavailable": "failed",
    "not_found": "failed",
    "invalid": "failed",
    "upstream_failed": "failed",
}

# The whole line, with the reason after the colon (German starts a sentence there).
_NOT_DRAWN = {
    "en": "I couldn't draw the picture ({subject}) this time: {reason}",
    "es": "Esta vez no pude dibujar la imagen ({subject}): {reason}",
    "fr": "Je n'ai pas pu dessiner l'image ({subject}) cette fois : {reason}",
    "de": "Das Bild ({subject}) konnte ich diesmal nicht zeichnen: {reason}",
    "it": "Questa volta non sono riuscito a disegnare l'immagine ({subject}): {reason}",
    "pt": "Desta vez não consegui desenhar a imagem ({subject}): {reason}",
    "tr": "Bu sefer resmi ({subject}) çizemedim: {reason}",
    "ru": "В этот раз не удалось нарисовать картинку ({subject}): {reason}",
    "am": "ምስሉን ({subject}) በዚህ ጊዜ መሳል አልቻልኩም፦ {reason}",
}

# The English is the server's own (``services.quota.messages``, ``generation``), unchanged.
_REASONS: dict[str, dict[str, str]] = {
    "paused": {
        "en": "Image generation is temporarily unavailable. Try again later.",
        "es": "la generación de imágenes no está disponible temporalmente. Inténtalo más tarde.",
        "fr": "la génération d'images est temporairement indisponible. Réessayez plus tard.",
        "de": "Die Bilderstellung ist vorübergehend nicht verfügbar. Versuche es später erneut.",
        "it": "la generazione di immagini non è temporaneamente disponibile. Riprova più tardi.",
        "pt": "a geração de imagens está temporariamente indisponível. Tente novamente mais tarde.",
        "tr": "görsel oluşturma geçici olarak kullanılamıyor. Daha sonra tekrar deneyin.",
        "ru": "создание изображений временно недоступно. Попробуйте позже.",
        "am": "ምስል መፍጠር ለጊዜው አይገኝም። ቆይተው እንደገና ይሞክሩ።",
    },
    "not_in_plan": {
        "en": "Image generation isn't part of your plan. Upgrade for it.",
        "es": "la generación de imágenes no está incluida en tu plan. Mejora tu plan para usarla.",
        "fr": "la génération d'images n'est pas incluse dans votre offre. "
        "Passez à une offre supérieure pour l'utiliser.",
        "de": "Die Bilderstellung ist in deinem Tarif nicht enthalten. "
        "Mit einem Upgrade bekommst du sie.",
        "it": "la generazione di immagini non è inclusa nel tuo piano. "
        "Passa a un piano superiore per usarla.",
        "pt": "a geração de imagens não faz parte do seu plano. Faça upgrade para usá-la.",
        "tr": "görsel oluşturma planınıza dahil değil. Kullanmak için planınızı yükseltin.",
        "ru": "создание изображений не входит в ваш тариф. "
        "Перейдите на тариф выше, чтобы им пользоваться.",
        "am": "ምስል መፍጠር በእቅድዎ ውስጥ አልተካተተም። ለማግኘት ያሻሽሉ።",
    },
    "daily_limit_free": {
        "en": "You've reached today's image generation limit. "
        "Upgrade for more — or try again after midnight UTC.",
        "es": "alcanzaste el límite de imágenes generadas de hoy. Mejora tu plan para más, "
        "o inténtalo de nuevo después de la medianoche UTC.",
        "fr": "vous avez atteint la limite de génération d'images du jour. Passez à une offre "
        "supérieure pour en avoir plus, ou réessayez après minuit UTC.",
        "de": "Du hast das heutige Limit für Bilderstellung erreicht. Upgrade für mehr, "
        "oder versuche es nach Mitternacht UTC erneut.",
        "it": "hai raggiunto il limite di generazione di immagini di oggi. Passa a un piano "
        "superiore per averne altre, o riprova dopo la mezzanotte UTC.",
        "pt": "você atingiu o limite de geração de imagens de hoje. Faça upgrade para mais, "
        "ou tente novamente depois da meia-noite UTC.",
        "tr": "bugünkü görsel oluşturma sınırına ulaştınız. Daha fazlası için planınızı "
        "yükseltin ya da UTC gece yarısından sonra tekrar deneyin.",
        "ru": "вы достигли дневного лимита на создание изображений. Перейдите на платный "
        "план, чтобы получить больше, или попробуйте после полуночи по UTC.",
        "am": "የዛሬን የምስል መፍጠር ገደብ ደርሰዋል። ለተጨማሪ ያሻሽሉ፣ ወይም ከUTC እኩለ ሌሊት በኋላ እንደገና ይሞክሩ።",
    },
    "daily_limit_paid": {
        "en": "You've reached today's image generation limit. Try again after midnight UTC.",
        "es": "alcanzaste el límite de imágenes generadas de hoy. "
        "Inténtalo de nuevo después de la medianoche UTC.",
        "fr": "vous avez atteint la limite de génération d'images du jour. "
        "Réessayez après minuit UTC.",
        "de": "Du hast das heutige Limit für Bilderstellung erreicht. "
        "Versuche es nach Mitternacht UTC erneut.",
        "it": "hai raggiunto il limite di generazione di immagini di oggi. "
        "Riprova dopo la mezzanotte UTC.",
        "pt": "você atingiu o limite de geração de imagens de hoje. "
        "Tente novamente depois da meia-noite UTC.",
        "tr": "bugünkü görsel oluşturma sınırına ulaştınız. "
        "UTC gece yarısından sonra tekrar deneyin.",
        "ru": "вы достигли дневного лимита на создание изображений. "
        "Попробуйте после полуночи по UTC.",
        "am": "የዛሬን የምስል መፍጠር ገደብ ደርሰዋል። ከUTC እኩለ ሌሊት በኋላ እንደገና ይሞክሩ።",
    },
    "content_blocked": {
        "en": "That picture can't be made: it breaks the image service's content rules.",
        "es": "no se puede crear esa imagen: va contra las normas de contenido "
        "del servicio de imágenes.",
        "fr": "impossible de créer cette image : elle enfreint les règles de contenu "
        "du service d'images.",
        "de": "Dieses Bild kann nicht erstellt werden: "
        "Es verstößt gegen die Inhaltsregeln des Bilddienstes.",
        "it": "non è possibile creare questa immagine: va contro le regole sui contenuti "
        "del servizio di immagini.",
        "pt": "não é possível criar essa imagem: ela vai contra as regras de conteúdo "
        "do serviço de imagens.",
        "tr": "bu görsel oluşturulamıyor: görsel hizmetinin içerik kurallarına aykırı.",
        "ru": "это изображение нельзя создать: оно нарушает правила контента сервиса изображений.",
        "am": "ያ ምስል ሊሠራ አይችልም፤ የምስል አገልግሎቱን የይዘት ደንቦች ይቃረናል።",
    },
    "too_slow": {
        "en": "the picture took too long. Ask for it again on its own.",
        "es": "la imagen tardó demasiado. Pídela de nuevo en un mensaje aparte.",
        "fr": "l'image a pris trop de temps. Redemandez-la dans un message à part.",
        "de": "Das Bild hat zu lange gedauert. "
        "Bitte frag in einer eigenen Nachricht noch einmal danach.",
        "it": "l'immagine ha richiesto troppo tempo. Chiedila di nuovo in un messaggio a parte.",
        "pt": "a imagem demorou demais. Peça de novo em uma mensagem separada.",
        "tr": "resim çok uzun sürdü. Ayrı bir mesajla tekrar isteyin.",
        "ru": "картинка рисовалась слишком долго. Попросите её снова отдельным сообщением.",
        "am": "ምስሉ በጣም ረጅም ጊዜ ወሰደ። ለብቻው እንደገና ይጠይቁ።",
    },
    "failed": {
        "en": "something went wrong. Ask for it again on its own.",
        "es": "algo salió mal. Pídela de nuevo en un mensaje aparte.",
        "fr": "une erreur s'est produite. Redemandez-la dans un message à part.",
        "de": "Etwas ist schiefgelaufen. Bitte frag in einer eigenen Nachricht noch einmal danach.",
        "it": "qualcosa è andato storto. Chiedila di nuovo in un messaggio a parte.",
        "pt": "algo deu errado. Peça de novo em uma mensagem separada.",
        "tr": "bir şeyler ters gitti. Ayrı bir mesajla tekrar isteyin.",
        "ru": "что-то пошло не так. Попросите её снова отдельным сообщением.",
        "am": "የሆነ ችግር ተፈጥሯል። ለብቻው እንደገና ይጠይቁ።",
    },
}


def reason_for_code(code: str) -> Reason:
    """The line a refusal's code gets; one with no line of its own is "failed"."""
    return REASON_BY_CODE.get(code, "failed")


def not_drawn_line(reason: Reason, subject: str, locale: str | None, *, paid: bool = False) -> str:
    """The whole line in ``locale`` (English for none or one the app lacks).

    ``paid`` picks the daily limit's wording, as ``quota.plan_message`` does: only a
    free plan is offered an upgrade. The subject goes in as an argument, so braces in
    it are kept as written.
    """
    key = f"daily_limit_{'paid' if paid else 'free'}" if reason == "daily_limit" else reason
    lang = normalize_locale_code(locale)
    if lang not in _NOT_DRAWN:
        lang = "en"
    return _NOT_DRAWN[lang].format(subject=subject, reason=_REASONS[key][lang])
