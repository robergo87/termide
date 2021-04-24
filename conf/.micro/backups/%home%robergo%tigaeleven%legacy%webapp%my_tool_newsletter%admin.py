from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import TextInput
from django.utils.translation import ugettext_lazy as _

from my_tool_newsletter.models import NewsletterContent, NewsletterTemplate, \
    NewsletterTemplateTag, SendGridSubUser
from my_wifitiger.models import Branding


class NewsletterTemplateAdminMixin(object):

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == 'brandings' and \
                not request.user.has_access_to_all_brandings:
            queryset = request.user.available_brandings
            if not queryset:
                raise ValidationError(
                    _('Please set branding or grant access to all brandings'))
            kwargs['queryset'] = queryset
        return super(NewsletterTemplateAdminMixin, self)\
            .formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(NewsletterTemplate)
class CoreUserAdmin(NewsletterTemplateAdminMixin, admin.ModelAdmin):
    list_display = ('__str__', 'language', 'get_brandings', )
    fieldsets = (
        (None, {
            'fields': ('brandings', 'language', 'name', 'tags', 'description',
                       'default_event', 'html', 'design', 'priority'),
        }),
    )
    filter_horizontal = ('tags', 'brandings')

    def get_queryset(self, obj):
        qs = super(CoreUserAdmin, self).get_queryset(obj)
        if not obj.user.has_access_to_all_brandings:
agement_portal/views.py
            qs = qs.filter(brandings__in=[branding.pk for branding in obj.user.available_brandings.all()])
        return qs.prefetch_related('brandings')

    def get_brandings(self, obj):
        return tuple(obj.brandings.all())


@admin.register(NewsletterTemplateTag)
class NewsletterTemplateTagAdmin(NewsletterTemplateAdminMixin, admin.ModelAdmin):
    list_display = ('__str__', 'get_brandings', )
    formfield_overrides = {
        models.TextField: {'widget': TextInput(attrs={'size': '50'})},
    }
    filter_horizontal = ('brandings', )

    def get_queryset(self, obj):
        qs = super(NewsletterTemplateTagAdmin, self).get_queryset(obj)
        if not obj.user.has_access_to_all_brandings:
            qs = qs.filter(brandings__in=[branding.pk for branding in obj.user.available_brandings.all()])
        return qs.prefetch_related('brandings')

    def get_brandings(self, obj):
        return tuple(obj.brandings.all())


@admin.register(NewsletterContent)
class NewsletterContentAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super(NewsletterContentAdmin, self).get_queryset(request)
        # Exclude models which inherit from NewsletterContent to show
        # 'pure' NewsletterContent models only
        return qs.filter(gastronewsrequestcontent__isnull=True,
                         newslettertemplate__isnull=True)


@admin.register(SendGridSubUser)
class SendGridSubUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email_address', 'password', 'ip_addresses')
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permision(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]
