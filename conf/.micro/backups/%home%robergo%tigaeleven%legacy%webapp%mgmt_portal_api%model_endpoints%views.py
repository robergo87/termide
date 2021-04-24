from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from captive_portal.models import Location, RouterDevice
from mgmt_portal_api.views import MgmtReadOnlyModelViewSet, MgmtModelViewSet
from mgmt_portal_api.model_endpoints.serializers import \
    SalesProductSerializer, BrandingSerializer, \
    CouponCodeHelpTextSerializer, RouterDeviceSerializer, \
    InstallationAgentSerializer, ManagementUserSerializer, \
    ContactPersonSerializer, SupportAgentSerializer
from management_portal.models import InstallationAgent, \
    ManagementUser, ContactPerson, SupportAgent, SalesProduct
from my_tool_internet_access.models import CouponCodeHelpText
from my_wifitiger.models import Branding


class SalesProductModelViewSet(MgmtReadOnlyModelViewSet):
    serializer_class = SalesProductSerializer
    queryset = SalesProduct.objects.all()


class BrandingModelViewSet(MgmtReadOnlyModelViewSet):
    serializer_class = BrandingSerializer
    queryset = Branding.objects.all()

    def get_queryset(self):
        if not self.request.user.has_access_to_all_brandings:
            return self.request.user.available_brandings.all()
        return super(BrandingModelViewSet, self).get_queryset()


class CouponCodeHelpTextModelViewSet(MgmtReadOnlyModelViewSet):
    serializer_class = CouponCodeHelpTextSerializer
    queryset = CouponCodeHelpText.objects.all()


class RouterDeviceModelViewSet(MgmtReadOnlyModelViewSet):
    serializer_class = RouterDeviceSerializer
    queryset = RouterDevice.objects.all()

    @action(detail=False, methods=['get'])
    def online_and_not_provisioned(self, request):
        router_devices = self.get_queryset().online_and_not_provisioned()
        serializer = self.get_serializer_class()(router_devices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InstallationAgentModelViewSet(MgmtReadOnlyModelViewSet):
    serializer_class = InstallationAgentSerializer
    queryset = InstallationAgent.objects.all()

    def get_queryset(self):
        location_id = self.request.query_params.get('location_id')
        if location_id:
            location = get_object_or_404(Location, id=location_id)
            return InstallationAgent.objects.filter(
                management_user__available_brandings__in=[location.branding]
            )
        return super().get_queryset()


class ManagementUserModelViewSet(MgmtReadOnlyModelViewSet):
    serializer_class = ManagementUserSerializer
    queryset = ManagementUser.objects.filter(is_active=True)


class ContactPersonModelViewSet(MgmtModelViewSet):
    serializer_class = ContactPersonSerializer
    queryset = ContactPerson.objects.all()


class SupportAgentModelViewSet(MgmtReadOnlyModelViewSet):
    serializer_class = SupportAgentSerializer
    queryset = SupportAgent.objects.all()
