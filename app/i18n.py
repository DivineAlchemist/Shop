"""Lightweight site-wide translation + text direction.

The language comes from Store settings (`StoreSettings.locale`). Templates call `_('English text')`; the
dictionary below maps English source text to each language and falls back to English when a string is
missing, so a missing translation can never break a page. Add a language by adding it to LANGUAGES and
a dictionary to TRANSLATIONS.
"""
from flask import flash as _flash, g, has_request_context
from markupsafe import Markup

LANGUAGES = {
    'en': {'name': 'English', 'dir': 'ltr'},
    'fa': {'name': 'فارسی', 'dir': 'rtl'},
}

FA = {
    'Account': 'حساب کاربری', 'Active': 'فعال', 'Add': 'افزودن', 'Add images': 'افزودن تصویر',
    'Add sub-category': 'افزودن زیردسته', 'Add tags': 'افزودن برچسب', 'Add to cart': 'افزودن به سبد خرید',
    'Address': 'نشانی', 'Addresses': 'نشانی‌ها', 'Admin': 'مدیر', 'Admin panel': 'پنل مدیریت',
    'All categories': 'همه دسته‌بندی‌ها', 'All products': 'همه محصولات', 'Already registered?': 'قبلاً ثبت‌نام کرده‌اید؟',
    'Also show in': 'نمایش در', 'Alt text': 'متن جایگزین', 'Any status': 'هر وضعیت', 'Apply': 'اعمال',
    'Archive': 'بایگانی', 'Attributes': 'ویژگی‌ها', 'Back': 'بازگشت', 'Back to login': 'بازگشت به ورود',
    'Back to orders': 'بازگشت به سفارش‌ها', 'Basics': 'اطلاعات پایه', 'Brand': 'برند', 'Breadcrumb': 'مسیر صفحه',
    'Browse': 'مرور', 'Browse everything': 'مرور همه محصولات', 'Browse products': 'مشاهده محصولات',
    'Bulk import': 'ورود گروهی', 'Cancel': 'انصراف', 'Cancel order': 'لغو سفارش', 'Cart': 'سبد خرید',
    'Catalog': 'کاتالوگ', 'Categories': 'دسته‌بندی‌ها', 'Category': 'دسته‌بندی', 'Category tree': 'درخت دسته‌بندی',
    'Checkout': 'تسویه حساب', 'Choose your options': 'گزینه‌های خود را انتخاب کنید', 'Choose…': 'انتخاب کنید…',
    'City': 'شهر', 'Clear all': 'پاک کردن همه', 'Clear filters': 'حذف فیلترها', 'Continue shopping': 'ادامه خرید',
    'Coupon code': 'کد تخفیف', 'Coupons': 'کدهای تخفیف', 'Create account': 'ایجاد حساب', 'Customer': 'مشتری',
    'DB panel': 'پنل پایگاه داده', 'Dark mode': 'حالت تاریک', 'Dashboard': 'داشبورد', 'Date': 'تاریخ',
    'Default': 'پیش‌فرض', 'Default address': 'نشانی پیش‌فرض', 'Delete': 'حذف', 'Description': 'توضیحات',
    'Details': 'جزئیات', 'Discount': 'تخفیف', "Don't have an account?": 'حساب ندارید؟',
    'Dry run — validate only, save nothing': 'اجرای آزمایشی — فقط بررسی، بدون ذخیره',
    'Edit': 'ویرایش', 'Enter your phone number and we will text you a recovery code.': 'شماره موبایل خود را وارد کنید تا کد بازیابی برایتان پیامک شود.',
    'Excel (.xlsx) or CSV file': 'فایل اکسل (.xlsx) یا CSV', 'Export products': 'خروجی محصولات',
    'Filter': 'فیلتر', 'Filters': 'فیلترها', 'Forgot password?': 'رمز عبور را فراموش کرده‌اید؟',
    'Forgot password · Raven': 'فراموشی رمز عبور', 'Go home': 'بازگشت به صفحه اصلی', 'History': 'تاریخچه',
    'Home': 'خانه', 'Homepage': 'صفحه اصلی', 'Homepage sections': 'بخش‌های صفحه اصلی',
    'I received my package': 'بسته را دریافت کردم', 'Image': 'تصویر', 'Images': 'تصاویر', 'Import': 'ورود اطلاعات',
    'Import — create/update products': 'ورود اطلاعات — ایجاد/به‌روزرسانی محصولات', 'In stock only': 'فقط موجود',
    'Internal only': 'فقط داخلی', 'Items': 'اقلام', 'Joined': 'تاریخ عضویت', 'Label': 'برچسب', 'Login': 'ورود',
    'Login · Raven': 'ورود', 'Logout': 'خروج', 'Make default': 'انتخاب به عنوان پیش‌فرض', 'Manage': 'مدیریت',
    'Mark as refunded': 'ثبت به عنوان بازپرداخت‌شده', 'Max': 'حداکثر', 'Maximum price': 'حداکثر قیمت', 'Menu': 'منو',
    'Min': 'حداقل', 'Minimum price': 'حداقل قیمت', 'Mock payment gateway': 'درگاه پرداخت آزمایشی',
    'My addresses': 'نشانی‌های من', 'My orders': 'سفارش‌های من', 'My profile': 'پروفایل من', 'Name': 'نام',
    'New category': 'دسته‌بندی جدید', 'New product': 'محصول جدید', 'New tags, comma separated': 'برچسب‌های جدید، با ویرگول جدا کنید',
    'Next': 'بعدی', 'Next product': 'محصول بعدی', 'No categories yet.': 'هنوز دسته‌بندی‌ای وجود ندارد.',
    'No orders yet.': 'هنوز سفارشی ثبت نشده است.', 'No orders.': 'سفارشی وجود ندارد.', 'No products found.': 'محصولی یافت نشد.',
    'No products match these filters.': 'محصولی با این فیلترها پیدا نشد.', 'No reviews yet.': 'هنوز نظری ثبت نشده است.',
    'No saved addresses.': 'نشانی ذخیره‌شده‌ای وجود ندارد.', 'No sub-categories': 'بدون زیردسته',
    'No tags yet.': 'هنوز برچسبی وجود ندارد.', 'Note (optional)': 'یادداشت (اختیاری)', 'Nothing saved yet.': 'هنوز چیزی ذخیره نشده است.',
    'Options': 'گزینه‌ها', 'Options &amp; variants': 'گزینه‌ها و تنوع‌ها', 'Order': 'سفارش', 'Order summary': 'خلاصه سفارش',
    'Orders': 'سفارش‌ها', 'Out of stock': 'ناموجود', 'Overview': 'نمای کلی', 'Pages': 'صفحه‌ها',
    'Parent category': 'دسته‌بندی والد', 'Pay': 'پرداخت', 'Pay now': 'پرداخت',
    'Pay on delivery': 'پرداخت در محل', 'Pay online': 'پرداخت آنلاین', 'Payment': 'پرداخت', 'Payment:': 'پرداخت:',
    'Pending': 'در انتظار', 'Phone': 'تلفن', 'Place order': 'ثبت سفارش', 'Postal code': 'کد پستی', 'Preview': 'پیش‌نمایش',
    'Previous': 'قبلی', 'Previous product': 'محصول قبلی', 'Price': 'قیمت', 'Primary category': 'دسته‌بندی اصلی',
    'Problem': 'مشکل', 'Product': 'محصول', 'Products': 'محصولات', 'Progress': 'روند سفارش',
    'Promotional SMS': 'پیامک تبلیغاتی', 'Publish': 'انتشار', 'Qty': 'تعداد', 'Quantity': 'تعداد',
    'Recent orders': 'سفارش‌های اخیر', 'Recipient name': 'نام گیرنده', 'Register': 'ثبت‌نام', 'Register · Raven': 'ثبت‌نام',
    'Remove': 'حذف', 'Rename': 'تغییر نام', 'Resend code': 'ارسال مجدد کد', 'Reserved': 'رزروشده',
    'Reset filters': 'بازنشانی فیلترها', 'Reset password': 'بازنشانی رمز عبور', 'Reset password · Raven': 'بازنشانی رمز عبور',
    'Returns:': 'بازگشت کالا:', 'Revenue': 'درآمد', 'Reviews': 'نظرات', 'Role': 'نقش', 'Row': 'ردیف', 'SKU': 'کد کالا',
    'Sale': 'حراج', 'Sale price': 'قیمت حراج', 'Sales': 'فروش', 'Save': 'ذخیره', 'Save product': 'ذخیره محصول',
    'Save this address': 'ذخیره این نشانی', 'Search': 'جستجو', 'Search products...': 'جستجوی محصولات...',
    'Send a new code': 'ارسال کد جدید', 'Send code': 'ارسال کد', 'Send me offers by SMS': 'پیشنهادها را پیامک کنید',
    'Set': 'تنظیم', 'Settings': 'تنظیمات', 'Sheet': 'برگه', 'Ship to': 'ارسال به', 'Shipped via': 'ارسال با',
    'Shipping': 'هزینه ارسال', 'Shipping &amp; returns': 'ارسال و بازگشت کالا', 'Shipping address': 'نشانی ارسال',
    'Shipping method': 'روش ارسال', 'Shipping to': 'ارسال به', 'Shipping:': 'ارسال:', 'Shop': 'فروشگاه',
    'Shop by category': 'خرید بر اساس دسته‌بندی', 'Shopping cart': 'سبد خرید', 'Show more': 'نمایش بیشتر',
    'Show results': 'نمایش نتایج', 'Slider banners': 'بنرهای اسلایدر', 'Slug (URL)': 'نشانی (اسلاگ)',
    'Something went wrong': 'مشکلی پیش آمد', 'Sort': 'مرتب‌سازی', 'Sort order': 'ترتیب', 'Staff': 'کارمند',
    'Staff panel': 'پنل کارکنان', 'Start shopping': 'شروع خرید', 'Status': 'وضعیت', 'Stock': 'موجودی',
    'Stop promotional SMS?': 'دریافت پیامک تبلیغاتی متوقف شود؟', 'Store settings': 'تنظیمات فروشگاه',
    'Storefront': 'ویترین فروشگاه', 'Submit review': 'ثبت نظر', 'Subtotal': 'جمع جزء', 'Tag': 'برچسب', 'Tags': 'برچسب‌ها',
    "The page you're looking for doesn't exist.": 'صفحه‌ای که دنبالش هستید وجود ندارد.',
    'This link is not valid.': 'این پیوند معتبر نیست.', 'Total': 'جمع کل', 'Upload': 'بارگذاری',
    'Use a new address': 'استفاده از نشانی جدید', 'Users': 'کاربران', 'Variant': 'تنوع', 'Verify': 'تأیید',
    'Verify phone · Raven': 'تأیید شماره موبایل', 'View': 'مشاهده', 'View all categories': 'مشاهده همه دسته‌بندی‌ها',
    'View product': 'مشاهده محصول', 'Visibility': 'نمایش', 'Visible to customers': 'نمایش برای مشتریان',
    'We logged the problem. Please try again.': 'مشکل ثبت شد. لطفاً دوباره تلاش کنید.', 'Wishlist': 'علاقه‌مندی‌ها',
    'Write a review (optional)': 'نظر خود را بنویسید (اختیاری)', 'Yes, unsubscribe me': 'بله، لغو اشتراک',
    "You don't have permission to access this page.": 'شما به این صفحه دسترسی ندارید.',
    'You have been unsubscribed.': 'اشتراک شما لغو شد.', 'You need to login to view this page.': 'برای مشاهده این صفحه باید وارد شوید.',
    'You will no longer receive promotional SMS. Order messages are unaffected.': 'دیگر پیامک تبلیغاتی دریافت نخواهید کرد. پیامک‌های سفارش تغییری نمی‌کنند.',
    'Your cart is empty.': 'سبد خرید شما خالی است.', 'Your rating': 'امتیاز شما', 'development only': 'فقط توسعه',
    'hidden': 'پنهان', 'internal': 'داخلی', 'public': 'عمومی', 'primary': 'اصلی', 'remove': 'حذف',
    '— None —': '— هیچ —', '— Top level —': '— سطح اول —', 'Slider': 'اسلایدر',
    '401 . Not Logged In': '۴۰۱ . وارد نشده‌اید', '403 - Access Denied.': '۴۰۳ - دسترسی ممنوع.', '404 — Page not found': '۴۰۴ — صفحه پیدا نشد',
    'Category tree': 'درخت دسته‌بندی', 'Products only in internal categories are not visible to shoppers.': 'محصولاتی که فقط در دسته‌بندی‌های داخلی هستند برای مشتریان نمایش داده نمی‌شوند.',
    'Search name, SKU, brand': 'جستجوی نام، کد کالا، برند', 'Order #, phone or tracking code': 'شماره سفارش، تلفن یا کد رهگیری',
    'products': 'محصول', 'Results for': 'نتایج برای', 'Sort by': 'مرتب‌سازی', 'Newest': 'جدیدترین',
    'Price: low to high': 'قیمت: کم به زیاد', 'Price: high to low': 'قیمت: زیاد به کم', 'Name A–Z': 'نام (الف تا ی)',
    'In stock': 'موجود', 'New address': 'نشانی جدید', 'Edit address': 'ویرایش نشانی', 'Save for later': 'ذخیره برای بعد', 'Saved': 'ذخیره شد',
    'No description provided.': 'توضیحاتی ثبت نشده است.', 'verified purchase': 'خرید تأییدشده', 'Unavailable': 'ناموجود', 'Language': 'زبان', 'Delivered': 'تحویل شد',
    'preparing': 'در حال آماده‌سازی', 'pending': 'در انتظار', 'shipped': 'ارسال شد', 'received': 'تحویل گرفته شد',
    'cancelled': 'لغو شد', 'failed': 'ناموفق', 'paid': 'پرداخت شده', 'unpaid': 'پرداخت نشده', 'refunded': 'بازپرداخت شد',
    'See all in': 'مشاهده همه در', 'Home / Shop': 'خانه / فروشگاه',
    '(purchase-time snapshot)': '(ثبت‌شده در زمان خرید)', 'Alt text for new images (defaults to the product name)': 'متن جایگزین تصاویر جدید (پیش‌فرض: نام محصول)',
    'Any depth is allowed. A category cannot be moved under itself or its own sub-categories.': 'هر عمقی مجاز است. دسته‌بندی را نمی‌توان زیر خودش یا زیردسته‌هایش برد.',
    'Existing products are matched by SKU and updated; blank cells keep current values. Download the template for the exact columns (Products + optional Variants sheet).': 'محصولات موجود بر اساس کد کالا پیدا و به‌روزرسانی می‌شوند؛ خانه‌های خالی مقدار فعلی را نگه می‌دارند. برای ستون‌های دقیق، قالب را دانلود کنید.',
    'Home, Work…': 'خانه، محل کار…', 'New tags, comma separated (e.g. summer, cotton, sale)': 'برچسب‌های جدید، با ویرگول جدا کنید (مثلاً تابستان، نخی، حراج)',
    'No tags yet — add some below.': 'هنوز برچسبی نیست — در پایین اضافه کنید.', 'One per line:': 'هر مورد در یک خط:', 'one per line:': 'هر مورد در یک خط:',
    'Shipment provider (for “shipped”)': 'شرکت حمل (برای «ارسال شد»)', 'Tracking code (for “shipped”)': 'کد رهگیری (برای «ارسال شد»)',
    'Street, building, unit…': 'خیابان، پلاک، واحد…', 'Sub': 'زیردسته', 'Template (.xlsx)': 'قالب (.xlsx)',
    "With options, every combination becomes its own variant (save once, then edit each variant's stock/SKU/price below).": 'با تعریف گزینه‌ها، هر ترکیب یک تنوع مجزا می‌شود (یک بار ذخیره کنید، سپس موجودی/کد/قیمت هر تنوع را در پایین ویرایش کنید).',
    'auto from name': 'خودکار از نام', '… or image URLs, one per line': 'یا نشانی تصاویر، هر کدام در یک خط', '…or image URLs, one per line': '…یا نشانی تصاویر، هر کدام در یک خط',
    '— leave empty for a simple product': '— برای محصول ساده خالی بگذارید',
    '— never shown in menus, search or browsing; use it to group products for homepage sections': '— هرگز در منو، جستجو یا مرور نمایش داده نمی‌شود؛ برای گروه‌بندی محصولات در بخش‌های صفحه اصلی استفاده کنید',
    '— tracking code': '— کد رهگیری', 'Used for filters and search.': 'برای فیلتر و جستجو استفاده می‌شود.', '. Used for filters and search.': '. برای فیلتر و جستجو استفاده می‌شود.',
    # flash / server messages
    'Logged in successfully.': 'با موفقیت وارد شدید.', 'Logged out.': 'خارج شدید.',
    'Invalid phone number or password.': 'شماره موبایل یا رمز عبور نادرست است.',
    'Added to cart.': 'به سبد خرید اضافه شد.', 'Please choose all options (e.g. size and colour).': 'لطفاً همه گزینه‌ها (مثلاً اندازه و رنگ) را انتخاب کنید.',
    'Out of stock.': 'ناموجود.', 'Your cart is empty.': 'سبد خرید شما خالی است.', 'Order cancelled.': 'سفارش لغو شد.',
    'Thanks for confirming delivery.': 'از تأیید دریافت سفارش سپاسگزاریم.', 'Address saved.': 'نشانی ذخیره شد.',
    'Address removed.': 'نشانی حذف شد.', 'Saved to wishlist.': 'در علاقه‌مندی‌ها ذخیره شد.', 'Removed from wishlist.': 'از علاقه‌مندی‌ها حذف شد.',
    'Thanks for your review!': 'از نظر شما سپاسگزاریم!', 'SMS preferences updated.': 'تنظیمات پیامک به‌روزرسانی شد.',
    'Shipping address is required.': 'نشانی ارسال الزامی است.', 'Please choose a valid address.': 'لطفاً یک نشانی معتبر انتخاب کنید.',
    'Choose a rating from 1 to 5.': 'امتیازی از ۱ تا ۵ انتخاب کنید.', 'Selected payment method is not available.': 'روش پرداخت انتخابی در دسترس نیست.',
    'Invalid coupon code.': 'کد تخفیف نامعتبر است.', 'Phone verified. Please log in.': 'شماره موبایل تأیید شد. لطفاً وارد شوید.',
    'Please verify your phone number first.': 'ابتدا شماره موبایل خود را تأیید کنید.', 'Incorrect code.': 'کد نادرست است.',
    'We sent a verification code by SMS.': 'کد تأیید برایتان پیامک شد.', 'A new code was sent.': 'کد جدید ارسال شد.',
    'Password updated. Please log in.': 'رمز عبور به‌روزرسانی شد. لطفاً وارد شوید.',
    'If that number has an account, a recovery code was sent by SMS.': 'اگر این شماره حساب داشته باشد، کد بازیابی پیامک شد.',
    'Too many failed attempts. Try again later or reset your password.': 'تلاش ناموفق زیاد. بعداً دوباره تلاش کنید یا رمز عبور را بازنشانی کنید.',
    'Payment successful. Thank you!': 'پرداخت موفق بود. سپاسگزاریم!', 'This payment was already confirmed.': 'این پرداخت قبلاً تأیید شده است.',
    'Payment was cancelled. You can try again from your order page.': 'پرداخت لغو شد. از صفحه سفارش می‌توانید دوباره تلاش کنید.',
    'Unknown payment reference.': 'شناسه پرداخت نامعتبر است.', 'Account created! Please log in.': 'حساب ایجاد شد! لطفاً وارد شوید.',
    'The code is invalid or has expired. Request a new one.': 'کد نامعتبر است یا منقضی شده. کد جدیدی درخواست کنید.',
    'Too many codes requested. Try again later.': 'درخواست کد بیش از حد مجاز. بعداً تلاش کنید.',
    'Not enough stock.': 'موجودی کافی نیست.',
}
TRANSLATIONS = {'fa': FA}


def current_locale():
    if has_request_context():
        if not hasattr(g, '_locale'):
            from . import get_settings
            s = get_settings()
            loc = (s.locale if s else 'en') or 'en'
            g._locale = loc if loc in LANGUAGES else 'en'
        return g._locale
    return 'en'


def text_dir():
    return LANGUAGES[current_locale()]['dir']


def tr(text):
    """Translate plain text (used for flash messages / server strings)."""
    return TRANSLATIONS.get(current_locale(), {}).get(text, text)


def gettext(text):
    """Template `_()`: returns Markup because source strings are trusted template literals."""
    return Markup(tr(text))


def flash(message, category='message'):
    _flash(tr(message) if isinstance(message, str) else message, category)
