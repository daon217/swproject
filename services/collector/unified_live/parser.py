"""JSON-LD first; reviewed CSS overrides. No currency, condition or stock guesses."""
import hashlib
import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from services.collector.marketplace_live.normalize import finish,money
from .policy import url
from .analysis import product_graph,value as native_value,labeled_food

def plain(value,limit=4000):
    return BeautifulSoup(value,'html.parser').get_text(' ',strip=True)[:limit] if isinstance(value,str) else None

def kind(obj,name):
    value=obj.get('@type',[])
    return any(str(t).rstrip('/').rsplit('/',1)[-1]==name for t in ([value] if isinstance(value,str) else value))

def structured(soup):
    return product_graph(soup)

def document(html):
    if len(html.encode('utf-8'))>2_000_000:raise ValueError('bounded_HTML_required')
    soup=BeautifulSoup(html,'html.parser')
    title=soup.title.get_text(' ',strip=True).lower() if soup.title else ''
    if any(s in title for s in ('captcha','access denied','just a moment','verify you are human','로그인 필요')) or soup.select_one('input[type="password"], iframe[src*="captcha"], .g-recaptcha'):
        raise ValueError('access_challenge_stop')
    return soup

def links(html,base,cfg):
    soup=document(html);found=[];sel=cfg.get('selectors',{})
    # Prefer declared product URLs; never follow arbitrary site navigation.
    for p in structured(soup):
        offers=p.get('offers') or {}
        candidate=p.get('url') or (offers.get('url') if isinstance(offers,dict) else None)
        if isinstance(candidate,str):found.append(urljoin(base,candidate))
    for script in soup.select('script[type="application/ld+json"]')[:100]:
        try:data=json.loads(script.string or script.get_text())
        except json.JSONDecodeError:continue
        stack=[data]
        for _ in range(1000):
            if not stack:break
            node=stack.pop()
            if isinstance(node,list):stack.extend(node)
            elif isinstance(node,dict):
                if kind(node,'ListItem'):
                    item=node.get('item',node)
                    target=item.get('url') or item.get('@id') if isinstance(item,dict) else item
                    if isinstance(target,str):found.append(urljoin(base,target))
                stack.extend(v for k,v in node.items() if k in ('@graph','itemListElement','item'))
    if sel.get('product_links'):
        found.extend(urljoin(base,n['href']) for n in soup.select(sel['product_links'])[:500] if n.get('href'))
    if not found:
        found.extend(urljoin(base,n['href']) for n in soup.select('[itemtype$="/Product"] a[href],a[itemprop="url"][href]')[:500])
    host=cfg['allowed_product_hosts'][0];valid=[]
    for target in found:
        try:target=url(target,host)
        except ValueError:continue
        if target not in valid:valid.append(target)
    next_node=soup.select_one(sel.get('next_page','a[rel~="next"]'))
    next_url=None
    if next_node and next_node.get('href'):next_url=url(urljoin(base,next_node['href']),host)
    return valid[:cfg['max_products_per_cycle']],next_url

def css_product(soup,selectors):
    def value(field):
        return native_value(soup,field,selectors)
    product={'@type':'Product','productID':value('id'),'name':value('name'),'description':value('description'),
        'category':value('category'),'image':value('image'),'brand':value('brand'),'manufacturer':value('manufacturer'),
        'itemCondition':value('condition'),'offers':{'@type':'Offer','price':value('price'),'priceCurrency':value('currency'),
        'availability':value('availability'),'seller':{'name':value('seller')}}}
    for field,key in (('model','model'),('model_number','modelNumber'),('mpn','mpn'),('gtin','gtin'),('color','color'),('size','size')):
        product[key]=value(field)
    food=labeled_food(soup)
    for k in ('ingredients','allergens','cross_contact'):product[k]=value(k) or food.get(k)
    if not product.get('manufacturer'):product['manufacturer']=food.get('manufacturer')
    return product

def native_money(raw,currency):
    if isinstance(raw,str):
        text=raw.strip();symbols={'KRW':'₩','USD':'$','AUD':'$','EUR':'€','GBP':'£','JPY':'¥','CNY':'¥','INR':'₹'}
        if currency:
            text=re.sub(r'^'+re.escape(currency)+r'\s*|\s*'+re.escape(currency)+r'$','',text)
            symbol=symbols.get(currency)
            if symbol and text.startswith(symbol):text=text[len(symbol):].strip()
            if currency=='KRW' and text.endswith('원'):text=text[:-1].strip()
        if re.fullmatch(r'\d{1,3}(?:,\d{3})+(?:\.\d{1,4})?',text):text=text.replace(',','')
        raw=text
    try:return money(raw)
    except ArithmeticError:raise ValueError('native_price_format_review') from None

def label(value):
    if isinstance(value,dict):value=value.get('name')
    return plain(value,500)

def normalize(html,base,at,cfg):
    soup=document(html);products=structured(soup)
    # Multiple independent products or variant offers require a site adapter.
    if len(products)>1 or not products and len(soup.select('[itemtype$="/Product"]'))>1:raise ValueError('multiple_product_details_require_adapter')
    p=products[0] if products else css_product(soup,cfg.get('selectors',{}))
    offers=p.get('offers') or {}
    if isinstance(offers,list):
        if len(offers)!=1:raise ValueError('multiple_offers_require_adapter')
        offers=offers[0]
    if not isinstance(offers,dict) or p.get('hasVariant') or kind(offers,'AggregateOffer'):raise ValueError('variant_offer_requires_adapter')
    target=url(urljoin(base,p.get('url') or offers.get('url') or base),cfg['allowed_product_hosts'][0])
    def code(value):return str(value or '').rstrip('/').rsplit('/',1)[-1]
    native_condition=code(p.get('itemCondition') or offers.get('itemCondition'))
    condition={'NewCondition':'new','UsedCondition':'used','new':'new','used':'used'}.get(native_condition)
    native_state=code(offers.get('availability'))
    state={'InStock':'available','LimitedAvailability':'available','OutOfStock':'out_of_stock','SoldOut':'ended',
           'available':'available','out_of_stock':'out_of_stock','ended':'ended'}.get(native_state)
    ident=p.get('productID') or 'url:'+hashlib.sha256(target.encode()).hexdigest()
    variant=str(p.get('sku') or ident)
    seller=offers.get('seller') or p.get('seller') or {}
    seller=seller.get('name') if isinstance(seller,dict) else seller if isinstance(seller,str) else None
    result=finish(cfg['source'],dict(source_listing_id=str(ident),variant_key=variant,name=plain(p.get('name'),500),
        price=native_money(offers['price'],offers.get('priceCurrency')) if offers.get('price') is not None else None,currency=offers.get('priceCurrency'),
        url=target,condition=condition,availability=state),plain(seller,200),native_state,at,cfg)
    if not seller:result['missing_fields'].append('seller');result['observation']=None
    if cfg.get('mode')=='used' and condition!='used':result['missing_fields'].append('used_condition_required');result['observation']=None
    image=p.get('image') or native_value(soup,'image',cfg.get('selectors',{}));image=image[0] if isinstance(image,list) and image else image
    image=image.get('url') if isinstance(image,dict) else image
    description=plain(p.get('description') or native_value(soup,'description',cfg.get('selectors',{})))
    if result['observation'] and description:
        from services.collector.marketplace_live.normalize import validate_body
        from .changes import rekey
        body=result['observation'];body['description']=description;body['field_presence'].append('description');rekey(body);validate_body(body,cfg)
    quantity=offers.get('inventoryLevel');quantity=quantity.get('value') if isinstance(quantity,dict) else None
    if type(quantity) is not int or quantity<0:quantity=None
    try:image=url(urljoin(base,image)) if isinstance(image,str) else None
    except ValueError:image=None
    category=label(p.get('category'));mapping=cfg.get('category_mapping',{})
    gtins=[];gtin_review=[]
    from .food_lookup import gtin
    for field in ('gtin','gtin8','gtin12','gtin13','gtin14'):
        if p.get(field) is None:continue
        try:canonical=gtin(str(p[field]))
        except ValueError:gtin_review.append(field)
        else:
            if canonical not in [g['value'] for g in gtins]:gtins.append({'value':canonical,'source_field':field})
    metadata={'seller':plain(seller,200),'image_url':image,'description':description,'category':category,
        'native_gtins':gtins,'gtin_fields_requiring_review':gtin_review,
        'category_mapped':mapping.get(category),'category_mapping_authority':'operator_supplied' if category in mapping else None,
        'brand':label(p.get('brand')),'manufacturer':label(p.get('manufacturer')),'region':cfg.get('region','unknown'),'country':cfg.get('country'),
        'condition_native':native_condition or None,'sale_status_native':native_state or None,'stock_quantity':quantity,
        'purchase_available':True if state=='available' else False if state in ('out_of_stock','ended') else None,
        'synthetic':False,'data_source':'registered_public_HTML','verified_at':at}
    from .matching import profile
    metadata['matching_profile']=profile(p,base,origin='jsonld_product' if products else 'native_page')
    result['metadata']=metadata
    labels=labeled_food(soup)
    result['food_input']={'name':result.get('name') or '', 'category':category or '', 'description':description,
        'ingredients':p.get('ingredients') or labels.get('ingredients'),'allergens':p.get('allergens') or labels.get('allergens'),
        'cross_contact':p.get('cross_contact') or labels.get('cross_contact')}
    return result
