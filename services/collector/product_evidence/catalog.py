"""Service product policy is independent of native condition and food domain.
These are local/draft contract values; current backend v2 has no service_type field.
"""
GENERAL={'domeggook','elevenst','11st','artmu','bestpen','도매꾹','11번가','아트뮤','베스트펜'}
USED={'joongna','junggonara','bunjang','중고나라','번개장터'}
OVERSEAS={'ebay','ebay_browse','amazon','aliexpress','etsy'}


def service_classification(source,condition='unknown',shipping_region='unknown',platform_region='unknown',override=None):
    key=str(source).removeprefix('html_')
    value='general' if key in GENERAL else 'used' if key in USED else 'overseas' if key in OVERSEAS else 'unknown'
    basis='source_policy:'+key
    if platform_region=='overseas':value='overseas';basis='declared_platform_region'
    if shipping_region=='overseas':value='overseas';basis='explicit_shipping_origin'
    elif value!='overseas' and condition in ('new','used'):
        value='used' if condition=='used' else 'general';basis='explicit_item_condition'
    if isinstance(override,dict) and override.get('value') in ('general','used','overseas') and override.get('path') and override.get('raw'):
        value=override['value'];basis='explicit_item_evidence:'+override['path']
    service_region='overseas' if value=='overseas' else 'domestic' if key in GENERAL|USED else 'unknown'
    return {'service_region':service_region,'service_type':value,'service_type_basis':basis,'condition':condition,
            'backend_status':'local_only_pending_service_type_contract'}
