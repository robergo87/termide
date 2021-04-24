from django.core.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework import mixins, status as http_status
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema

from captive_portal.models import Location
from management_portal.models import (
    SalesLocation,
    InstallationComment,
    ParcelServiceTracking,
    ContactPerson,
    SalesProductAtLocation,
    SalesProduct,
)
from mgmt_portal_api.model_endpoints.serializers import ContactPersonSerializer
from mgmt_portal_api.views import BaseLocationViewSet
from mgmt_portal_api.location.serializers import (
    InstallationCommentSerializer,
    ParcelServiceTrackingSerializer,
)
from management_portal.utils import generate_and_send_my_portal_password
from management_portal.utils import create_main_menu, send_order_email, \
    send_training_confirmation_mails
from management_portal.aftership import create_tracking
from mgmt_portal_api.location.parameters import (
    request_body_location_status,
    request_body_installation_comments,
    request_body_send_my_portal_password,
)


class LocationStatusViewSet(BaseLocationViewSet, mixins.RetrieveModelMixin,
                            mixins.UpdateModelMixin, mixins.ListModelMixin):

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        sales_products_at_location = SalesProductAtLocation.objects.filter(
            location=instance)
        for product in serializer.data.get('products'):
            product_deactivated_on = sales_products_at_location.get(
                product__id=product['id']).deactivated_on or ''
            if product_deactivated_on:
                serializer.data.get('products').remove(product)
/branding                continue
            product.update(
                {'activated_on': sales_products_at_location.
                    get(product__id=product['id']).activated_on,
                 'deactivated_on': product_deactivated_on})
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        product_ids = request.data.get('products')
        if not product_ids:
            return super(LocationStatusViewSet, self).update(request, *args, **kwargs)
        try:
            products_ids_list = [int(i) for i in product_ids.split(',')]
        except ValueError:
            return Response(status=http_status.HTTP_400_BAD_REQUEST)
        sales_products = SalesProductAtLocation.objects\
            .filter(location=instance, deactivated_on__isnull=True)\
            .values_list('product', flat=True)

        for sales_product in sales_products:
            if sales_product not in products_ids_list:
                SalesProductAtLocation.objects\
                    .filter(location=instance, product_id=sales_product)\
                    .update(deactivated_on=timezone.now())

        for product_id in products_ids_list:
            if product_id not in sales_products:
                try:
                    sales_product = SalesProduct.objects.get(id=product_id)
                except SalesProduct.DoesNotExist as e:
                    message = {'error': str(e)}
                    return Response(message, http_status.HTTP_400_BAD_REQUEST)
                new_product = SalesProductAtLocation(
                    location=instance, product=sales_product
                )
                try:
                    new_product.check_category_uniqueness()
                except ValidationError as e:
                    message = {'error': str(e)}
                    return Response(message, http_status.HTTP_400_BAD_REQUEST)
                new_product.save()

        return super(LocationStatusViewSet, self).update(request, *args, **kwargs)

    @swagger_auto_schema(method='post',
                         request_body=request_body_location_status)
    @action(detail=True, methods=['get', 'post'])
    def location_status(self, request, pk):
        location = get_object_or_404(Location, id=pk)
        sales_location = location.sales_location
        status = request.data.get('status', '')
        if request.method == 'POST':
            next_status = status
            if status == 'welcome_call_needed' \
                    and sales_location.welcome_call_done_at:
                sales_location.welcome_call_done_by = request.user
                sales_location.welcome_status = \
                    SalesLocation.WELCOME_STATUS_CALL_DONE
                if sales_location.tripadvisor_url:
                    sales_location.data_status = \
                        SalesLocation.DATA_STATUS_TRIPADVISOR_OPT_IN
                if sales_location.training_scheduled_at:
                    sales_location.training_status = \
                        SalesLocation.TRAINING_STATUS_PLANNED
                    send_training_confirmation_mails(sales_location)
                for comment in ('installation_comment', 'general_comment'):
                    comment_string = request.data.get('comment', None)
                    if comment_string:
                        InstallationComment(
                            location=location,
                            user=request.user,
                            comment=comment
                        ).save()
                next_status = 'welcome_call_done'
            elif status == 'ready_to_deliver' \
                    and sales_location.parcel_sent_at:
                if sales_location.parcel_tracking_code:
                    create_tracking(sales_location.parcel_tracking_code)
                sales_location.self_installation_status = \
                    SalesLocation.SELF_INSTALLATION_STATUS_IN_DELIVERY
                next_status = 'in_delivery'
            elif status in ('in_delivery', 'delivery_problem') \
                    and sales_location.parcel_delivered_at:
                sales_location.parcel_delivered(save=False)
                next_status = 'delivered'
            elif status == 'delivered' \
                    and sales_location.router_active_since:
                sales_location.self_installation_status = \
                    SalesLocation.SELF_INSTALLATION_STATUS_INSTALLED
                next_status = 'self_installed'
            elif status == 'new_installation' \
                    and sales_location.installation_by:
                sales_location.sys_op_installation_status = \
                    SalesLocation.SYS_OP_INSTALLATION_STATUS_IN_PLANNING
                next_status = 'in_planning'
            elif status == 'in_planning' and sales_location.installation_date \
                    and sales_location.installation_by:
                sales_location.sys_op_installation_status = \
                    SalesLocation.SYS_OP_INSTALLATION_STATUS_DATE_SET
                next_status = 'date_set'
            elif status in ('date_set', 'provisioning', 'provisioned') \
                    and sales_location.real_installation_date:
                sales_location.sys_op_installation_status = \
                    SalesLocation.SYS_OP_INSTALLATION_STATUS_APPROVAL
                next_status = 'approval'
            elif status == 'approval' \
                    and sales_location.ready_for_invoicing:
                sales_location.sys_op_installation_status = \
                    SalesLocation.SYS_OP_INSTALLATION_STATUS_INSTALLED
                sales_location.invoice_status = \
                    SalesLocation.INVOICING_STATUS_READY_TO_INVOICE
                if location.branding.send_order_summary:
                    send_order_email(location)
                    sales_location.invoice_status = \
                        SalesLocation.INVOICING_STATUS_DONE
                    sales_location.invoiced_at = timezone.now()
                sales_location.installation_approved_by = request.user
                next_status = 'installed'
            elif status == 'tripadvisor_opt_in':
                sales_location.data_status = SalesLocation.DATA_STATUS_APPROVED
                next_status = 'data_approved'
            elif status == 'training_in_planning' \
                    and sales_location.training_scheduled_at:
                sales_location.training_status = \
                    SalesLocation.TRAINING_STATUS_PLANNED
                send_training_confirmation_mails(sales_location)
                next_status = 'training_planned'
            elif status == 'training_planned' \
                    and sales_location.training_done:
                sales_location.training_status = \
                    SalesLocation.TRAINING_STATUS_DONE
                next_status = 'training_done'
            elif status == 'accounting_approval' \
                    and sales_location.ready_for_invoicing:
                sales_location.invoice_status = \
                    SalesLocation.INVOICING_STATUS_READY_TO_INVOICE
                sales_location.installation_approved_by = request.user
                next_status = 'ready_to_invoice'
                if location.branding.send_order_summary:
                    send_order_email(location)
                    sales_location.invoice_status = \
                        SalesLocation.INVOICING_STATUS_DONE
                    sales_location.invoiced_at = timezone.now()
                    next_status = 'invoicing_done'
            elif status == 'ready_to_invoice' \
                    and sales_location.invoiced_at \
                    and sales_location.order_code:
                sales_location.invoice_status = \
                    SalesLocation.INVOICING_STATUS_DONE
                next_status = 'invoicing_done'

            location.save()
            sales_location.save()
            return Response({'next_status': next_status},
                            status=http_status.HTTP_201_CREATED)
        dashboard = False
        if hasattr(request.user, 'installation_agent') \
                and status not in ('in_planning', 'date_set'):
            dashboard = True
        return Response({'dashboard': dashboard},
                        status=http_status.HTTP_200_OK)

    @swagger_auto_schema(method='post',
                         request_body=request_body_installation_comments)
    @action(detail=True, methods=['get', 'post'])
    def installation_comments(self, request, pk):
        location = get_object_or_404(Location, id=pk)
        if request.method == 'POST':
            serializer = InstallationCommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(location=location, user=request.user)
            return Response(serializer.data,
                            status=http_status.HTTP_201_CREATED)
        comments = InstallationComment.objects \
            .filter(location=location) \
            .order_by('-created') \
            .select_related('user')
        serializer = InstallationCommentSerializer(comments, many=True)
        return Response(serializer.data, status=http_status.HTTP_200_OK)

    @swagger_auto_schema(method='post',
                         request_body=request_body_send_my_portal_password)
    @action(detail=True, methods=['post'])
    def send_my_portal_password(self, request, pk):
        location = get_object_or_404(Location, id=pk)
        generate_and_send_my_portal_password(location)
        return Response(status=http_status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def parcel_tracking_updates(self, request, pk):
        location = get_object_or_404(Location, id=pk)
        sales_location = location.sales_location
        parcel_tracking_updates = ParcelServiceTracking.objects \
            .filter(tracking_code=sales_location.parcel_tracking_code) \
            .order_by('-created')
        serializer = ParcelServiceTrackingSerializer(
            parcel_tracking_updates, many=True)
        return Response(serializer.data, status=http_status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def contact_persons(self, request, pk):
        location = get_object_or_404(Location, id=pk)
        contact_persons = ContactPerson.objects.filter(location=location)
        serializer = ContactPersonSerializer(contact_persons, many=True)
        return Response(serializer.data, status=http_status.HTTP_200_OK)
