"""Centralised message templates. Keys are used by notifications/verification only."""
TEMPLATES = {
    'verify_code': {
        'en': '{store}: your verification code is {code}. Valid for {minutes} minutes.',
        'fa': '{store}: کد تایید شما {code} است. تا {minutes} دقیقه معتبر است.',
    },
    'reset_code': {
        'en': '{store}: your password recovery code is {code}. Ignore this message if you did not request it.',
        'fa': '{store}: کد بازیابی رمز عبور شما {code} است. اگر درخواست نکرده‌اید نادیده بگیرید.',
    },
    'order_confirmed': {
        'en': '{store}: order #{order_id} was placed. Total: {total}.',
        'fa': '{store}: سفارش شماره {order_id} ثبت شد. مبلغ: {total}',
    },
    'order_preparing': {
        'en': '{store}: order #{order_id} was accepted and is being prepared.',
        'fa': '{store}: سفارش شماره {order_id} تایید شد و در حال آماده‌سازی است.',
    },
    'order_shipped': {
        'en': '{store}: order #{order_id} has shipped via {provider}. Tracking code: {tracking}.',
        'fa': '{store}: سفارش شماره {order_id} توسط {provider} ارسال شد. کد رهگیری: {tracking}',
    },
    'order_received': {
        'en': '{store}: delivery of order #{order_id} was confirmed. Thank you for shopping with us!',
        'fa': '{store}: تحویل سفارش شماره {order_id} ثبت شد. از خرید شما متشکریم.',
    },
    'order_cancelled': {
        'en': '{store}: order #{order_id} was cancelled.',
        'fa': '{store}: سفارش شماره {order_id} لغو شد.',
    },
    'marketing': {
        'en': '{store}: {message}\nOpt out: {optout_url}',
        'fa': '{store}: {message}\nلغو دریافت پیام: {optout_url}',
    },
}


def render(key, locale, **tokens):
    variants = TEMPLATES[key]
    text = variants.get(locale) or variants['en']
    return text.format(**tokens)
