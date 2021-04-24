""" my.wifitigier.com API view
"""
import csv

from django.conf import settings
from django.db import transaction
from django.http import (HttpResponseBadRequest, HttpResponseNotFound,
                         HttpResponseRedirect, HttpResponse)
from django.utils import timezone
from django.urls import reverse

from captive_portal.models import RouterDevice, Location
from core.utils import getLogger
from management_portal.models import SalesLocation
from my_tool_currently_active.models import LocationUserDeviceToAuth
from my_tool_routerconfig.utils import get_config_url
from my_wifitiger.decorators import require_access_token
from .decorators import json_api
from . import forms


log = getLogger(__name__)
ACCESS_TOKEN = settings.WIFITIGER_MY_API_ACCESSTOKEN


@require_access_token(ACCESS_TOKEN)
@json_api
@transaction.atomic
def register_router_device(request, json_body, nas_id):
    """Register pushed router device

    Example:
    POST /api/v1/router/5e62d5ec-0ca4-42db-8859-96bcf0c567aa/register/
    {
        certificate_id_0: C=ZA, ST=Enlightenment, L=Overall, (…),
        certificate_id_1: C=ZA, ST=Enlightenment, (…),
        certificate_digest_0: 1b:27:a6:b4:5f:7a:9c:3f:17:fb:ff:(…),
        certificate_digest_1: e4:f1:43:37:34:51:de:99:7a:dc:e3:(…),
        system_version: '15.05',
        model: 'ZBT WR8305RT',
        first_mac_address': 'FF:FF:FF:FF:FF:FF'
    }

    --- Response
    {
        "status": "ok"
    }
    """
    form = forms.RegisterRouterDeviceForm(data=json_body)

    if not form.is_valid():
        return HttpResponseBadRequest(
            'Validation failed: {}'.format(form.errors.as_json()))

    now = timezone.now()
    router_data = form.cleaned_data.copy()
    router_data.update({
        'installed': now,
        'last_seen': now,
        'uuid': nas_id,
        'last_seen_on_vpn': now,
    })

    RouterDevice.objects.create(**router_data)

    return {'status': 'ok'}


@require_access_token(ACCESS_TOKEN)
@json_api
def update_router_device_list(request, json_body):
    """
    Read routers list and return:
    - "finish-provisioning": finalize router provisioning by
      setting new client (router) name


    Example:
    POST /api/v1/routers/update/
    {               // NAS-ID, is-in-the-office {bool or int}
        "router": [ ("5e62d5ec-0ca4-42db-8859-96bcf0c567aa", true)
                    ("96584b60-8b58-4214-9494-03f3772af556", 0) ],
    }

    --- Response
    {
        "finish-provisioning": {
            "3e62d5ec-0ca4-42db-8859-(…)": "location-foo--3e62d5ec"
        },
        "login": {
            'location1-11111111': ['11-11-11-11-11-01', ],
            'location1-22222222': ['11-11-11-11-11-01', ],
            'location2-33333333': ['22-22-22-22-22-01', '22-22-22-22-22-02']
        },
        "office_ip": "192.168.31.25",
        "add_to_monitoring": ['location-foo--3e62d5ec']
        }
    }
    """
    try:
        json_body['router']
    except (KeyError, TypeError, ValueError, ):
        return HttpResponseBadRequest('Validation failed')
    inactive_routers_with_location_set = RouterDevice.objects.filter(
        status='INITIALIZED',
        location__isnull=False,
        replace_router_device__isnull=True
    )
    to_provision = dict(
        (str(router.uuid), router.nas_id)
        for router in inactive_routers_with_location_set
    )
    routers_with_router_to_replace = RouterDevice.objects.filter(
        replace_router_device__isnull=False,
        status='INITIALIZED',
    )
    if routers_with_router_to_replace:
        router_ids_to_reset_config_version = set()
        for router in routers_with_router_to_replace:
            router_to_replace = router.replace_router_device
            to_provision[router.nas_id] = router_to_replace.nas_id
            if router_to_replace.model != router.model or \
               router_to_replace.system_version != router.system_version:
                # Hardware / OS mismatch
                log.debug('Router replacement %s => %s: hardware / OS '
                          'mismatch (%s vs %s, %s vs %s)',
                          router.nas_id, router_to_replace.nas_id,
                          router.model, router_to_replace.model,
                          router.system_version,
                          router_to_replace.system_version,
                          extra={'request': request})
                router_to_replace.model = router.model
                router_to_replace.system_version = router.system_version
                router_to_replace.config_version = '0'
                router_to_replace.save()
            else:
                router_ids_to_reset_config_version.add(router.id)
        routers_with_router_to_replace.update(status='DISABLED')
        if router_ids_to_reset_config_version:
            RouterDevice.objects.filter(
                id__in=router_ids_to_reset_config_version
            ).update(config_version='0')
    if inactive_routers_with_location_set:
        inactive_routers_with_location_set.update(status='ENABLED')
    to_login = LocationUserDeviceToAuth.get_routers('-')

    # Temporary backstop
    if settings.TIGAELEVEN_PROVISIONER_LOCATION_BACKSTOP:
        return {
            # Define message for (partially) failed updates, temporary
            # assuming `fail`
            'finish-provisioning': to_provision,
            'login': to_login,
            'office_ip': settings.TIGAELEVEN_OFFICE_IP,
        }

    # :TODO: move this function somewhere else
    def manage_locations(routers, field, source_status, target_status,
                         extra_update=None):
        to_update = {
            field: target_status,
            'router_active_since': timezone.now(),
        }
        if extra_update:
            to_update.update(extra_update)
        sales_locations_to_update = routers and RouterDevice.objects \
            .filter_by_nas_ids(routers) \
            .filter(**{'location__sales_location__' + field: source_status}) \
            .values_list('location__sales_location__id', flat=True)
        updated = sales_locations_to_update and SalesLocation.objects \
            .filter(id__in=sales_locations_to_update) \
            .update(**to_update)
        if updated:
            log.info('update_router_device_list: manage_locations '
                     '(%s=>%s)=%s', source_status, target_status, updated)
        return updated

    routers = tuple(router for router, in_office in json_body['router'])
    manage_locations(
        routers,
        'self_installation_status',
        SalesLocation.SELF_INSTALLATION_STATUS_PROVISIONING,
        SalesLocation.SELF_INSTALLATION_STATUS_READY_TO_DELIVER
    )
    manage_locations(
        routers,
        'sys_op_installation_status',
        SalesLocation.SYS_OP_INSTALLATION_STATUS_PROVISIONING,
        SalesLocation.SYS_OP_INSTALLATION_STATUS_PROVISIONED,
    )
    routers_not_in_the_office = tuple(router for router, in_office
                                      in json_body['router']
                                      if not in_office)
    manage_locations(
        routers_not_in_the_office,
        'self_installation_status',
        SalesLocation.SELF_INSTALLATION_STATUS_DELIVERED,
        SalesLocation.SELF_INSTALLATION_STATUS_INSTALLED
    )
    routers_without_monitoring = RouterDevice.objects.filter_by_nas_ids(
        routers_not_in_the_office
    ).waiting_for_monitoring()
    add_to_monitoring = tuple(i.nas_id for i in routers_without_monitoring)
    routers_without_monitoring.update(is_added_to_monitoring=True)
    if add_to_monitoring:
        log.info('Routers to be added to the monitoring: %s',
                 add_to_monitoring)
    return {
        # Define message for (partially) failed updates, temporary
        # assuming `fail`
        'finish-provisioning': to_provision,
        'login': to_login,
        'office_ip': settings.TIGAELEVEN_OFFICE_IP,
        'add_to_monitoring': add_to_monitoring,
    }


@require_access_token(ACCESS_TOKEN)
@json_api
def router_config_check(request, json_body):
    """
    Example:
    POST /api/v1/router/config/
    {
        "location-x--5e62d5e": "0",
        "<client-id>": "<config-version>"
    }

    --- Response
    [
        {
            "id": "location-x--5e62d5e",
            "config_version": 1,
            "url": "https://my.wifitiger.com/api/v1/router/
                    location-x--5e62d5e/config/"
            "vpn_ip": "10.200.0.2"
        }
    ]
    """
    try:
        routers_in = list(json_body.items())
        list(map(lambda x: int(x[1]), routers_in))
    except (AttributeError, ValueError, ):
        return HttpResponseBadRequest('Validation failed')
    if not routers_in:
        return []
    for nas_id, version in routers_in:
        try:
            int(version)
        except ValueError:
            return HttpResponseBadRequest('Validation failed')
    # Log the contact
    RouterDevice.objects.set_last_seen_on_vpn(list(json_body.keys()))
    config_status_updated \
        = RouterDevice.objects.set_config_status_updated(routers_in)
    routers = RouterDevice.objects.find_updatable(routers_in)
    res = []
    for router in routers:
        res.append({
            'id': router.nas_id,
            'config_version': router.config_version,
            'url': request.build_absolute_uri(
                reverse('router_config_download',
                        kwargs={'nas_id': router.nas_id, }
                       ) + '?access_token={}'.format(ACCESS_TOKEN)),
            'vpn_ip': None,
        })
    config_status_sent_to_router \
        = routers.update(config_status='SENT_TO_ROUTER')
    if config_status_updated or config_status_sent_to_router:
        log.info('router_config_check: Changed RouterDevice.config_status - '
                 'set UPDATED on %d objects and SENT_TO_ROUTER on %d objects',
                 config_status_updated, config_status_sent_to_router,
                 extra={'request': request})
    return res


@require_access_token(ACCESS_TOKEN)
@json_api
def router_config_download(request, json_body, nas_id):
    """Redirect to S3 location with current config package
    """
    try:
        router = RouterDevice.objects.filter_by_nas_id(nas_id).get()
    except RouterDevice.DoesNotExist():
        return HttpResponseNotFound('Router not found')
    config_url = get_config_url(nas_id)
    log.info('RouterDeviceConfigDownload:%s, %s, %s, %s', router,
             router.config_version,
             request.META.get('HTTP_X_FORWARDED_FOR',
                              'REMOTE_ADDR').split(',')[0],
             config_url,
             extra={
                 'request': request,
             })
    return HttpResponseRedirect(config_url)


@require_access_token(ACCESS_TOKEN)
def tripadvisor_matching(request):
    """
    Generates the CSV file that needs to be uploaded to TripAdvisor. The file
    will contain all locations that where created with the management portal
    and where TripAdvisor is activated.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="%s"' % \
        settings.TIGAELEVEN_TRIPADVISOR_MATCHING_CSV_FILE_NAME

    writer = csv.writer(response)
    writer.writerow(['TA Property ID', 'Partner Property ID'])
    for location in Location.objects\
            .filter(sales_location__tripadvisor_url__isnull=False)\
            .select_related('sales_location'):
        tripadvisor_id = location.sales_location.get_tripadvisor_id_from_url()
        if not tripadvisor_id:
            log.warning('Can not get tripadvisor id for sales location %s',
                        location)
            continue
        if not location.tripadvisor_id:
            log.warning('Location has no tripadvisor id %s', location)
            continue
        writer.writerow([tripadvisor_id, location.tripadvisor_id])

    return response
