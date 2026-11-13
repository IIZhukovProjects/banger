"""The player's description is also the public caption; style instructions stay server-side."""

DEFAULT_IMAGE_MODEL = "openai/gpt-image-1.5"


def sticker_prompt(description: str) -> str:
    return f"""Создай квадратный PNG-стикер для пати-игры «Я за БЕНГЕР». Изобрази: {description.strip()}.

Сделай предмет похожим на фигурку, слепленную вручную из пластилина. Чуть кривые формы, преувеличенные детали, мягкий глянец, заметная фактура лепки и лёгкое зерно. Сними фигурку в ракурсе три четверти с мягким студийным светом. Палитра в духе клубной афиши: кислотный лайм, лавандовый, жвачно-розовый и сливочный. Если я прикрепил обложку, используй её как референс для материалов, цвета и света.

Один объект по центру, целиком в кадре, с запасом по краям. Силуэт должен хорошо читаться в маленькой карточке. Без надписей, логотипов, рамки и декораций. Итог — PNG с прозрачным фоном."""


def grok_image_prompt(description: str) -> str:
    subject = description.strip().rstrip(".")
    return (
        f"{subject}. Centered handmade clay figurine, full object in frame, "
        "plain studio background, soft lighting. No text, lettering or logos."
    )
