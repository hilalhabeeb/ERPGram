"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path
from django.utils.translation import gettext_lazy as _

admin.site.site_header = _("Erpgram back office")
admin.site.site_title = _("Erpgram back office")

# Non-localised URLs: admin and the language-switch endpoint.
urlpatterns = [
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
]

# Localised URLs. The default language (en) is served without a prefix; Arabic
# lives under /ar/. Auth pages are included here too so they are translatable and
# switch to RTL — with prefix_default_language=False a non-prefixed URL is always
# forced to the default language, so anything outside this block can't be Arabic.
urlpatterns += i18n_patterns(
    path("", include("apps.accounts.urls")),
    path("", include("apps.tenancy.urls")),
    path("", include("apps.manpower.urls")),
    path("", include("apps.billing.urls")),
    path("", include("apps.comments.urls")),
    path("", include("apps.ui.urls")),
    prefix_default_language=False,
)

# Serve user uploads (worker photos, documents) in development. WhiteNoise
# handles static files but not MEDIA, so without this /media/... 404s and every
# uploaded photo renders broken. In production the web server / object store
# serves MEDIA_ROOT instead.
if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "apps.ui.views.error_403"
handler404 = "apps.ui.views.error_404"
handler500 = "apps.ui.views.error_500"
