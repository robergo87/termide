import copy

from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, viewsets, mixins, status
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ViewSet, \
    ReadOnlyModelViewSet
from django.dispatch import receiver
from django_rest_passwordreset.signals import reset_password_token_created

from captive_portal.models import Location
from core.api.serializers import UserDetailsReadSerializer
from core.utils import getLogger, render_template_from_db, send_mail
from my_portal_api.authentication import MUserTokenAuthentication
from my_portal_api.mixins import LocationProxyMixin, MUserPermissionMixin, \
    TigaCreateModelMixin, PaginationMixin
from my_portal_api.models import UserToken
from my_portal_api.parameters import request_body_change_password, \
    request_body_limit_ui_rows
from my_portal_api.serializers import (
    EntryReadOnlySerializer,
    LocationSelectBoxSerializer,
    PasswordChangeSerializer,
    BrandingSerializer,
    BrandingPublicSerializer,
    LocationGroupSerializer,
)
from my_tool_faq.models import Entry
from my_wifitiger.models import Branding, MUser, LocationGroup
from my_wifitiger.permissions import MUSER_PERMISSION_LABEL_AND_PREFIX

log = getLogger(__name__)


class LocationUpdateActionMixin(object):

    def update_location(self, request, location_id, serializer):
        location = self.location_proxy.get()
        serializer = serializer(location, data=request.data, partial=True)
        response_code = status.HTTP_200_OK
        if not serializer.is_valid():
            return Response(
                serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )
        '''
        POST: is only supported for compatibility reasons.
        PATCH: should be used
        '''
        if request.method in ('POST', 'PATCH'):
            serializer.save()
            response_code = status.HTTP_201_CREATED
        return Response(serializer.data, status=response_code)


class LocationGenericViewSet(MUserPermissionMixin, LocationProxyMixin,
                             PaginationMixin, GenericViewSet):
    def get_queryset(self):
        queryset = super(LocationGenericViewSet, self).get_queryset()
        return queryset.filter(**self.location_proxy.get_selector())

    def get_serializer_context(self):
        context = super(LocationGenericViewSet, self).get_serializer_context()
        if 'location_id' in self.request.parser_context['kwargs']:
            context['location_id'] = \
                self.request.parser_context['kwargs']['location_id']
        return context


class LocationReadOnlyModelViewSet(LocationGenericViewSet,
                                   viewsets.ReadOnlyModelViewSet):
    pass


class LocationListModelViewSet(LocationGenericViewSet, mixins.ListModelMixin):
    pass


class LocationCreateAndReadModelViewSet(LocationGenericViewSet,
                                        TigaCreateModelMixin,
                                        mixins.RetrieveModelMixin,
                                        mixins.ListModelMixin):
    pass


class LocationCRUModelViewSet(LocationGenericViewSet,
                              mixins.RetrieveModelMixin, mixins.ListModelMixin,
                              mixins.UpdateModelMixin,
                              mixins.CreateModelMixin):
    pass


class LocationModelViewSet(LocationGenericViewSet, viewsets.ModelViewSet):
    pass


class LoginViewSet(ObtainAuthToken, ViewSet):
    @action(detail=False, methods=['post'])
    def login(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        if user.type != MUser.USER_TYPE:
            msg = _('Unable to log in with provided credentials.')
            raise serializers.ValidationError(msg, code='authorization')
        token, created = UserToken.objects.update_or_create(
            user=user, defaults={'user': user}
        )
        return Response({'token': token.key})


class UserDetailsViewSet(ViewSet):
    serializer_class = UserDetailsReadSerializer
    authentication_classes = (MUserTokenAuthentication, )

    @action(detail=False, methods=['get'])
    def me(self, request, format=None):
        data = self.serializer_class(instance=request.user).data
        return Response(data)

    @swagger_auto_schema(method='post',
                         request_body=request_body_limit_ui_rows)
    @action(detail=False, methods=['post'])
    def limit_ui_rows(self, request, format=None):
        serializer = self.serializer_class(request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(method='post',
                         request_body=request_body_change_password)
    @action(detail=False, methods=['post'])
    def change_password(self, request, *args, **kwargs):
        user = MUser.objects.get(id=self.request.user.id)
        serializer = PasswordChangeSerializer(user, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutViewSet(ViewSet):
    authentication_classes = (MUserTokenAuthentication, )

    @action(detail=False, methods=['post'])
    def logout(self, request, format=None):
        auth = MUserTokenAuthentication().authenticate(request)
        if auth:
            token = auth[1]
            key = copy.copy(token.key)
            token.delete()
            return Response({'token': key})
        return Response({})


class FaqViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet
):
    serializer_class = EntryReadOnlySerializer
    queryset = Entry.objects.filter(published=True).order_by('order')
    permission_classes = (IsAuthenticated,)
    authentication_classes = (MUserTokenAuthentication,)


class UserLocationViewSet(
    mixins.ListModelMixin,
    MUserPermissionMixin,
    GenericViewSet
):
    serializer_class = LocationSelectBoxSerializer
    pagination_class = None

    def get_queryset(self):
        muser = MUser.objects.get(id=self.request.user.id)
        if muser.has_access_to_all_locations:
            return Location.objects.only_enabled()
        return muser.location_set.all()


class UserLocationGroupViewSet(LocationReadOnlyModelViewSet):
    serializer_class = LocationGroupSerializer

    def get_queryset(self):
        muser = MUser.objects.get(id=self.request.user.id)
        return muser.locationgroup_set.all()


class DashboardViewSet(LocationProxyMixin, MUserPermissionMixin, ViewSet):
    @action(detail=False, methods=['get'])
    def dashboard(self, request, location_id):
        return Response({
            'currently_active_users':
                self.location_proxy.count_currently_active_users(),
            'active_users_today':
                self.location_proxy.count_active_users_today(),
            'active_users_this_month':
                self.location_proxy.count_active_users_this_month(),
            'new_users': self.location_proxy.count_new_users_today(),
            'reoccurring_users':
                self.location_proxy.count_reoccurring_users_today(),
        }, status=status.HTTP_200_OK)


class MenuViewSet(LocationProxyMixin, MUserPermissionMixin, ViewSet):
    @action(detail=False, methods=['get'])
    def menu(self, request, location_id):
        location = self.location_proxy.get()
        branding = location.branding
        permissions = [p.replace(MUSER_PERMISSION_LABEL_AND_PREFIX, '').upper()
                       for p in request.user.get_all_permissions()]
        is_stuff = request.user.has_access_to_all_locations
        is_single = self.location_proxy.is_single_location()
        is_basic = is_single and location.wifi_settings.is_wifi_basic

        return Response({
            'show_menu_dashboard':
                not is_basic
                and location.has_wifi_product,

            'show_menu_currently_active':
                'MENU_CURRENTLY_ACTIVE' in permissions
                and is_single
                and not is_basic
                and location.has_wifi_product,

            'show_menu_statistics':
                'MENU_STATISTICS' in permissions
                and location.has_wifi_product,
            'show_submenu_facebook_statistics': not is_basic,
            'show_submenu_old_statistics':
                location.has_old_statistics()
                and not is_basic,

            'show_menu_users': 'MENU_USERS' in permissions,
            'show_submenu_wifi_users':
                not is_basic
                and location.has_wifi_product,
            'show_submenu_website_users': location.has_newsletter_product,
            'show_submenu_blocked_devices':
                is_single
                and not is_basic
                and location.has_wifi_product,
            'show_submenu_authorize_device':
                is_single
                and not is_basic
                and location.has_wifi_product,
            'show_submenu_logo_and_cover':
                is_single
                and location.has_wifi_product,
            'show_menu_newsletter': bool(
                'MENU_NEWSLETTER' in permissions
                and location.newsletter_settings.is_newsletter_enabled
                if is_single else location.is_newsletter_enabled
                and location.sendgrid_asm_group_id
                and not is_basic),

            'show_menu_landing_page':
                'MENU_LANDING_PAGE' in permissions
                and location.wifi_settings.is_landing_page_fully_available
                if is_single else location.is_landing_page_fully_available
                and not is_basic,

            'show_menu_feedback':
                'MENU_FEEDBACK' in permissions
                and is_single
                and not is_basic
                and location.has_wifi_product,

            'show_menu_settings': 'MENU_SETTINGS' in permissions,
            'show_menu_tripadvisor_settings':
                not is_basic and location.has_wifi_product,
            'show_menu_widget_integration': location.has_reservations_product,
            'show_submenu_wifi_settings':
                is_single
                and location.has_wifi_product,
            'show_submenu_bandwidth_settings':
                is_single
                and location.has_wifi_product,
            'show_submenu_alarm_settings':
                is_single
                and location.has_wifi_product,
            'show_submenu_time_restriction_settings':
                is_single
                and not is_basic
                and location.has_wifi_product,
            'show_submenu_login_options_settings':
                is_single
                and not is_basic
                and location.has_wifi_product,

            'show_menu_gastronews': bool(
                'MENU_GASTRONEWS' in permissions
                and settings.TIGAELEVEN_GASTRONEWS_ENABLED
                and branding.name == settings.TIGAELEVEN_GASTROMEDIA_BRAND_NAME
                and location.gastronews_id
                and is_single
                and not is_basic),

            'show_menu_welcome_page':
                'MENU_WELCOME_PAGE' in permissions
                and location.has_wifi_product,

            'show_menu_financial':
                'MENU_FINANCIAL' in permissions
                and not is_basic,

            'show_menu_router_config': is_stuff and is_single,
            'show_menu_monitoring': is_stuff,
            'show_menu_faq':
                not is_basic
                and location.has_wifi_product,
            'show_menu_password_change': True,
        }, status=status.HTTP_200_OK)


@receiver(reset_password_token_created)
def password_reset_token_created(sender, reset_password_token, *args, **kwargs):
    user_email = reset_password_token.user.email
    context = {
        'current_user': reset_password_token.user,
        'email': user_email,
        'protocol': 'https'
    }

    to_email = user_email.lower()
    first_location = Location.objects.filter(musers__email=to_email). \
        select_related('branding').first()
    branding = first_location.branding if first_location else \
        MUser.objects.filter(
            email=to_email,
            has_access_to_all_locations=True
        ).exists() and Branding.objects.first()
    if not branding:
        log.error('PasswordResetForm: Either email %s does not have location '
                  'assigned or does not have access to all locations or does '
                  'not exists', to_email)
        return
    context['branding'] = branding
    context['imprint'] = branding.imprint
    context['site_name'] = context['domain'] = branding.my_portal_domain
    context['reset_password_path'] = f'/password-reset/check/?token=' \
        f'{reset_password_token.key}'
    template = branding.email_template_my_portal_password_reset
    send_mail(
        render_template_from_db(template.subject, context),
        render_template_from_db(template.txt, context),
        from_email=
        template.get_email_sender(settings.TIGAELEVEN_MYPORTAL_EMAIL_FROM),
        recipient_list=[to_email, ],
        html_message=render_template_from_db(template.html, context),
        allow_unverified_recipient=True,
    )


class BrandingViewSet(MUserPermissionMixin,
                      mixins.RetrieveModelMixin, mixins.ListModelMixin,
                      GenericViewSet):
    serializer_class = BrandingSerializer
    queryset = Branding.objects.all()


class BrandingPublicViewSet(ReadOnlyModelViewSet):
    serializer_class = BrandingPublicSerializer
    queryset = Branding.objects.all()
