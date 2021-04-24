import copy

from django_filters.rest_framework import DjangoFilterBackend
from django.utils.translation import ugettext_lazy as _
from django.db.models import Count, Case, When, IntegerField, Avg, \
    F, DateTimeField
from django.db.models.expressions import Value
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, status
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet, \
    ModelViewSet, ViewSet

from captive_portal.models import Location
from core.api.serializers import UserDetailsReadSerializer
from management_portal.models import ManagementUser, SalesLocation, SalesProductAtLocation
from management_portal.permissions import \
    MANAGEMENT_USER_PERMISSION_LABEL_AND_PREFIX
from mgmt_portal_api.authentication import MgmtUserTokenAuthentication
from mgmt_portal_api.filters import LocationFilter
from mgmt_portal_api.mixins import PaginationMixin, MgmtUserPermissionMixin
from mgmt_portal_api.models import UserToken
from mgmt_portal_api.serializers import LocationSerializer
from my_portal_api.parameters import request_body_limit_ui_rows


class BaseLocationViewSet(MgmtUserPermissionMixin, PaginationMixin,
                          GenericViewSet):
    serializer_class = LocationSerializer
    queryset = Location.objects.all()
    filter_backends = (DjangoFilterBackend,)
    filter_class = LocationFilter

    def list_queryset(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        if not self.request.user.has_access_to_all_brandings:
            queryset = queryset.filter(branding__in=self.request.user.available_brandings.all())
        return self.paginated_response(queryset,
                                       BaseLocationViewSet.serializer_class)


class MgmtReadOnlyModelViewSet(MgmtUserPermissionMixin, PaginationMixin,
                               ReadOnlyModelViewSet):
    pass


class MgmtModelViewSet(MgmtUserPermissionMixin, PaginationMixin, ModelViewSet):
    pass


class LoginViewSet(ObtainAuthToken, ViewSet):
    @action(detail=False, methods=['post'])
    def login(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        if user.type != ManagementUser.USER_TYPE:
            msg = _('Unable to log in with provided credentials.')
            raise serializers.ValidationError(msg, code='authorization')
        token, created = UserToken.objects.update_or_create(
            user=user, defaults={'user': user}
        )
        return Response({'token': token.key})


class UserDetailsViewSet(MgmtUserPermissionMixin, ViewSet):
    serializer_class = UserDetailsReadSerializer

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


class LogoutViewSet(MgmtUserPermissionMixin, ViewSet):
    @action(detail=False, methods=['post'])
    def logout(self, request, format=None):
        auth = MgmtUserTokenAuthentication().authenticate(request)
        if auth:
            token = auth[1]
            key = copy.copy(token.key)
            token.delete()
            return Response({'token': key})
        return Response({})


class DashboardViewSet(MgmtUserPermissionMixin, ViewSet):
    @action(detail=False, methods=['get'])
    def dashboard(self, request, format=None):
        permissions = \
            [p.replace(MANAGEMENT_USER_PERMISSION_LABEL_AND_PREFIX, '')
             for p in request.user.get_all_permissions()]
        sections = (
            (SalesLocation.get_non_final_statuses('WELCOME_STATUS_CHOICES'),
             _('New Locations'), 'menu_new_location', 'welcome_status'),
            (SalesLocation
             .get_non_final_statuses('SELF_INSTALLATION_STATUS_CHOICES'),
             _('Self installations'),
             'menu_self_installation', 'self_installation_status'),
            (SalesLocation
             .get_non_final_statuses('SYS_OP_INSTALLATION_STATUS_CHOICES'),
             _('Tigaeleven installations'), 'menu_sys_op_installation',
             'sys_op_installation_status'),
            (SalesLocation.get_non_final_statuses('DATA_STATUS_CHOICES'),
             _('Data disclosure'), 'menu_data', 'data_status'),
            (SalesLocation.get_non_final_statuses('TRAINING_STATUS_CHOICES'),
             _('Training'), 'menu_training', 'training_status'),
            (SalesLocation.get_non_final_statuses('INVOICING_STATUS_CHOICES'),
             _('Invoicing'), 'menu_invoicing', 'invoice_status')
        )
        sections = [s for s in sections if s[2] in permissions]

        args = {}
        for choices, translation, name, field in sections:
            for choice in choices:
                # Count the number of locations in this status
                args[choice[0]] = Count(Case(
                    When(then=1, **{field: choice[0]}),
                    output_field=IntegerField())
                )
        counts = SalesLocation.objects.only_active_clients().aggregate(**args)
        locations_per_sections = []
        for section in sections:
            data = {
                'name': section[1],
                'total': 0,
                'subsections': [],
            }
            for choice in section[0]:
                for key, value in counts.items():
                    if key == choice[0]:
                        data['total'] += value
                        data['subsections'].append((choice[1], value))
                        break
            locations_per_sections.append(data)
        kpis = []
        args = {}
        for field_from, field_to in (
                ('contract_signed_date', 'welcome_call_done_at'),
                ('welcome_call_done_at', 'installation_date'),
                ('installation_date', 'real_installation_date'),
                ('welcome_call_done_at', 'training_done'),
                ('welcome_call_done_at', 'parcel_sent_at'),
                ('parcel_sent_at', 'parcel_delivered_at'),
                ('parcel_delivered_at', 'router_active_since'),
                ('welcome_call_done_at', 'invoiced_at'),
        ):
            kpis.append({
                'from': field_from,
                'to': field_to,
            })
            key = field_from + field_to
            # Get the average duration for the locations
            args[key] = \
                Avg(F(field_to) - F(field_from), output_field=DateTimeField())
            # Count the number of locations
            args['count_' + key] = \
                Count(Case(When(
                    then=Value(1),
                    **{field_to + '__isnull': False,
                       field_from + '__isnull': False}
                )))
        for key, value in SalesLocation.objects.only_active_clients() \
                .aggregate(**args).items():
            for kpi in kpis:
                _key = kpi['from'] + kpi['to']
                if _key == key:
                    kpi['duration'] = value
                elif 'count_' + _key == key:
                    kpi['locations'] = value
        return Response({'kpis': kpis,
                         'locations_per_sections': locations_per_sections})
