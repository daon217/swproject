"""Bounded same-origin HTML navigation; framework evidence never grants data rights."""
import re
import json
from urllib.parse import urljoin,urlsplit,parse_qs
from .policy import url

PLATFORMS={
 'cafe24':(r'cafe24|xans-product|ec-base-product',{'name':'.xans-product-detail .headingArea h2','price':'#span_product_price_text','image':'.xans-product-image .BigImage'}),
 'godomall':(r'godomall|godo\.co\.kr|gd_goods_view',{'name':'.item_detail_tit h3','price':'.item_price dd strong','image':'#mainImage img'}),
 'makeshop':(r'makeshop|shopdetail\.html|shopbrand\.html',{'name':'.thumb-info .tit-prd','price':'#pricevalue','image':'.thumb-wrap img'}),
 'shopify':(r'cdn\.shopify\.com|Shopify\.shop|name=["\']generator["\'][^>]+Shopify',{'name':'.product__title h1','price':'.product__info-container .price-item--regular','image':'.product__media img'}),
}

def platform(soup):
 text=str(soup)[:2_000_000];hits=[k for k,(pattern,_) in PLATFORMS.items() if re.search(pattern,text,re.I)]
 return hits[0] if len(hits)==1 else 'ambiguous' if hits else 'unknown'

def selectors(soup,configured):
 result=dict(configured);name=platform(soup)
 for field,selector in PLATFORMS.get(name,('',{}))[1].items():
  if field not in result and len(soup.select(selector))==1:result[field]=selector
 # Semantic product containers only. Conflicting cards/prices do not become a detail.
 generic={'name':'.product-info-wrapper .title,.product_main h1,h1.product-title,h2.product-title,h3.product-title','price':'.product-info-wrapper .price,.product_main .price_color'}
 for field,selector in generic.items():
  from .analysis import value
  if field=='price' and value(soup,'price',configured):continue
  if field not in result and len(soup.select(selector))==1:result[field]=selector
 if 'image' not in result:
  from .analysis import value
  name=value(soup,'name',result)
  matched=[n for n in soup.select('img[alt]') if name and ' '.join(n['alt'].split()).casefold()==' '.join(name.split()).casefold()]
  if len(matched)==1:result['image']='img[alt='+json.dumps(matched[0]['alt'],ensure_ascii=False)+']'
 return result

DENY=re.compile(r'(?:^|/)(?:cart|checkout|login|logout|account|accounts|member|wishlist|compare|search|admin|api|privacy|terms|contact|about)(?:/|\.|$)',re.I)
def classify(target):
 p=urlsplit(target);path=p.path.lower();q=parse_qs(p.query)
 if DENY.search(path) or re.search(r'\.(?:jpg|jpeg|png|gif|webp|svg|pdf|zip|js|css|json)$',path):return None
 if (path.endswith('/product/detail.html') and q.get('product_no') or path.endswith('/goods/goods_view.php') and q.get('goodsNo') or path.endswith('/shop/shopdetail.html') and q.get('branduid')):return 'detail'
 if (path.endswith('/product/list.html') and q.get('cate_no') or path.endswith('/goods/goods_list.php') and q.get('cateCd') or path.endswith('/shop/shopbrand.html')):return 'auto'
 if re.search(r'/(?:category|categories)(?:/|$)',path):return 'auto'
 if re.search(r'/(?:products?|item|items|p)/[^/]+',path) or re.search(r'/catalogue/(?!category/).+/index\.html$',path):return 'detail'
 if re.search(r'/(?:category|categories|collections?|catalogue|catalog|products|shop)(?:/|$)',path):return 'auto'
 return None

def navigation(soup,base):
 host=urlsplit(base).hostname;details=[];categories=[]
 # Ignore rel=nofollow and account/cart navigation. Never submit forms.
 for a in soup.select('a[href]')[:2000]:
  if 'nofollow' in a.get('rel',[]):continue
  try:target=url(urljoin(base,a['href']),host)
  except ValueError:continue
  if target==url(base,host):continue
  kind=classify(target)
  path=urlsplit(target).path
  if kind is None and not DENY.search(path) and not re.search(r'\.[a-z0-9]{2,5}$',path,re.I):
   if a.find_parent(['nav']) or a.find_parent(attrs={'role':'navigation'}) or a.find_parent(class_=re.compile(r'^(?:category|gnb|menu)$')):kind='auto'
  if kind:
   bucket=details if kind=='detail' else categories
   if target not in bucket:bucket.append(target)
 for a in soup.select('[data-product-id] a[href],article.product_pod h3 a,.product-card a[href],.prdList .name a,.goods_list_item .item_photo_box a')[:500]:
  if 'nofollow' in a.get('rel',[]):continue
  try:target=url(urljoin(base,a['href']),host)
  except ValueError:continue
  if target!=url(base,host) and not DENY.search(urlsplit(target).path) and target not in details:details.append(target)
 # Only explicit next controls; don't enumerate numeric/calendar parameter spaces.
 next_url=None
 for a in soup.select('a[href]')[:2000]:
  if 'nofollow' in a.get('rel',[]):continue
  label=(a.get('aria-label') or a.get('title') or a.get_text(' ',strip=True)).strip().casefold()
  classes=' '.join(a.get('class',[]));parent=a.parent
  next_control='next' in a.get('rel',[]) or label in ('next','next page','다음','다음 페이지','›','»') and (re.search(r'pagination|paginate|paging|pager',classes+' '+' '.join(parent.get('class',[])),re.I) or a.find_parent('nav'))
  if not next_control:continue
  try:target=url(urljoin(base,a['href']),host)
  except ValueError:continue
  if target!=url(base,host) and not DENY.search(urlsplit(target).path):next_url=target;break
 return details[:100],categories[:100],next_url

def is_detail(soup,base,products,selected):
 from .analysis import value
 if soup.select_one('meta[property="og:type"][content="product"]'):return True
 if len(products)==1:
  p=products[0];offer=p.get('offers') or {};target=p.get('url') or (offer.get('url') if isinstance(offer,dict) else None)
  if isinstance(target,str):
   try:
    if url(urljoin(base,target),urlsplit(base).hostname)!=url(base):return False
   except ValueError:return False
  return True
 if soup.select_one('[itemtype$="/Product"]'):return True
 return bool(value(soup,'name',selected) and value(soup,'price',selected) and (value(soup,'id',selected) or value(soup,'sku',selected) or value(soup,'condition',selected)))
