import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ProductHTML(HTMLParser):
    def __init__(self, base_url=''):
        super().__init__(convert_charrefs=True)
        self.text=[];self.images=[];self.skip=0;self.base_url=base_url;self.tables=[];self.excluded_tables=[]

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag in ('script','style','noscript','iframe','svg'):
            self.skip+=1
        if self.skip:return
        if tag=='table':
            if self.tables:self.tables[-1]['nested']=True
            self.tables.append({'start':len(self.text),'row_headers':0,'wide_header':False,'nested':False})
        if tag=='tr' and self.tables:self.tables[-1]['row_headers']=0
        if tag=='th' and self.tables:
            self.tables[-1]['row_headers']+=1
            if self.tables[-1]['row_headers']>=3:self.tables[-1]['wide_header']=True
        if tag in ('p','br','div','li','tr','h1','h2','h3','h4','section'):
            self.text.append('\n')
        if tag=='img':
            value=attrs.get('data-src') or attrs.get('src')
            if value:
                url=urljoin(self.base_url,value)
                u=urlsplit(url)
                if u.scheme in ('https','http') and u.hostname and not u.username and not u.password:
                    self.images.append({'url':url,'alt':attrs.get('alt') or None})

    def handle_endtag(self, tag):
        if tag in ('script','style','noscript','iframe','svg'):
            self.skip=max(0,self.skip-1);return
        if self.skip:return
        if tag=='table' and self.tables:
            table=self.tables.pop()
            if table['wide_header'] and not table['nested']:
                self.excluded_tables.append({'reason':'multi_product_comparison_table_requires_column_matching','text':''.join(self.text[table['start']:])})
                del self.text[table['start']:]
                self.text.append('\n')
            return
        if tag=='th':self.text.append(': ')
        elif tag=='td':self.text.append(' | ')
        elif tag in ('p','div','li','tr','h1','h2','h3','h4','section'):self.text.append('\n')

    def handle_data(self, value):
        if not self.skip:
            if not value.strip():
                if '\n' not in value:self.text.append(' ')
            else:self.text.append(value)


PURCHASE=re.compile(r'\b(shipping|delivery|ships|warranty|guarantee|returns?|included|accessories|compatibility|compatible|revision|condition|factory reset|commissioning|not included|warning|caution|requires?)\b|배송|보증|보장|품질보증|반품|구성품|포함|호환|전시|리퍼|중고|주의|반드시|별도|구매\s*시|봉당|개당',re.I)
PROMO=re.compile(r'\b(shop now|buy now|add to cart|subscribe|newsletter|coupon|promo code|limited[- ]time|flash sale|follow us|customer (?:service|support)|contact us|best price|hurry|sale ends|sign up|compare the modules|find your next module)\b|쿠폰|이벤트|타임딜|고객센터|상담전화|구매하러|지금 구매|알림받기|최저가|카카오톡|무료상담',re.I)
META=re.compile(r'^(?:(?:catalog-listed brand|this listing[’\']s format|vendor|type)\s*:|price\s*:\s*(?:\d|$)|this description uses supplier listing details\b|we do not have verified scent notes\b|review shipping and return terms before ordering\b)',re.I)
TECHNICAL_FACT=re.compile(r'\d\s*(?:V|mA|A|W|GB|MB|mm|cm|kg|ml|Hz)\b|USB|processor|memory|material|supports?|compatible|warranty|소재|규격|호환|보증|구성품',re.I)
KO_PROMO=re.compile(r'덕후를 위해 준비|실속팩으로 만나|어디서나 돋보이는|완벽한 데일리룩|최고급 퀄리티|하나하나 완벽하게|매번 새것처럼|언제 어디서나 간편',re.I)
SPECLABELS=re.compile(r'^(?:processor|cpu|ram|memory|storage|flash|power|voltage|current|dimensions?|size|weight|material|capacity|interface|connectivity|compatibility|resolution|battery|contents?|includes?|warranty|shipping|보증|배송|구성품|소재|크기|무게|용량|전압)\b',re.I)
RULES={
    'dimensions':r'\b\d+(?:\.\d+)?\s*(?:cm|mm|inches|inch)?\s*[x×]\s*\d+(?:\.\d+)?(?:\s*(?:cm|mm|inches|inch)?\s*[x×]\s*\d+(?:\.\d+)?)?\s*(?:mm|cm|inches|inch)\b',
    'weight':r'\b\d+(?:\.\d+)?\s*(?:kg|grams?|kilograms?)\b',
    'voltage':r'\b\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*(?:VDC|VAC|volts?|V)\b',
    'power':r'\b\d+(?:\.\d+)?\s*(?:mW|kW|W|watts?)\b',
    'frequency':r'\b\d+(?:\.\d+)?\s*(?:MHz|GHz|kHz|Hz)\b',
    'memory_storage':r'\b\d+(?:\.\d+)?\s*(?:GB|MB|KB|TB)\b',
    'volume':r'\b\d+(?:\.\d+)?(?:\s*[/]\s*\d+)?\s*(?:ml|mL|litres?|liters?|fl\.?\s*oz|oz)\b',
    'connectivity':r'\b(?:Wi-Fi(?:\s*\d)?|Bluetooth(?:\s*\d(?:\.\d)?)?|Zigbee(?:\s*\d(?:\.\d)?)?|USB[- ]?[ABC]|Z-Wave|Ethernet|I2C|SPI|UART|HDMI)\b',
    'material':r'\b(?:MDF|birch|pine|oak|beech|cotton|polyester|stainless steel|alumin(?:i)?um|silicone|ABS|jute|leather|linen)\b|원목|(?<![가-힣])면(?![가-힣])|폴리에스터|스테인리스|알루미늄|실리콘',
    'concentration':r'\b(?:Eau de Parfum|Eau de Toilette|Eau de Cologne|Concentr[eé]e? de Parfum|Extrait de Parfum)\b',
    'pack_quantity':r'\b\d+[- ]?(?:pack|pcs|pieces)\b',
    'pins':r'\b\d+[- ]?pins?\b',
    'pitch':r'\b\d+(?:\.\d+)?\s*(?:"|mm)\s*pitch\b',
    'color':r'\b(?:black|white|beige|navy)\b|블랙|화이트|베이지|네이비',
    'fit':r'\b(?:wide|slim)\b|와이드',
    'construction':r'\bknit\b|니트',
}
PROFILES={
    'electronics':{'dimensions','weight','voltage','power','frequency','memory_storage','connectivity','material','pack_quantity','pins','pitch'},
    'furniture':{'dimensions','weight','material'},
    'fragrance':{'volume','concentration'},
    'general':{'dimensions','weight','material','volume'},
    'fashion':{'dimensions','weight','material','color','fit','construction'},
}


def profile(category, name):
    text=str(category or '')+' '+str(name or '')
    if re.search(r'parfum|perfume|toilette|cologne|fragrance',text,re.I):return 'fragrance'
    if re.search(r'원피스|팬츠|셔츠|양말|드레스|\b(?:dress|pants|shirt|socks)\b',text,re.I):return 'fashion'
    if re.search(r'furniture|cot\b|crib\b|dresser|mattress|bed\b|가구|침대|매트리스|토퍼|옷장|의자',text,re.I):return 'furniture'
    if re.search(r'electronic|board|sensor|switch|controller|header|connector|development|automation|cable|socket|USB|RAM|노트북|스마트폰|이어폰',text,re.I):return 'electronics'
    return 'general'


def refine(text, name, category, base_url='', source_field='description'):
    original=text or ''
    parser=ProductHTML(base_url);parser.feed(original);parser.close()
    plain=''.join(parser.text)
    if not re.search(r'<[a-zA-Z][^>]*>',original):plain=original
    # Plain text may have flattened source section headers: retain the original spans.
    plain=re.sub(r'[ \t\r\f\v]+',' ',plain)
    segments=[]
    for line in re.split(r'\n|\s+-\s+(?=[가-힣A-Za-z])|[✔✅✨💡🤍]',plain):
        for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z가-힣])',line):
            sentence=sentence.strip(' |\t')
            if sentence:segments.append(sentence)
    kept=[];removed=list(parser.excluded_tables);purchase=[];seen=set();specs={};evidence=[]
    category_profile=profile(category,name)
    for field,content in [('product_name',name or ''),(source_field,plain)]:
        for key in sorted(PROFILES[category_profile]):
            for match in re.finditer(RULES[key],content,re.I):
                if key=='material' and field!= 'product_name':
                    context=re.split(r'[.!?\n]|\b(?:Care|Clean|Cleaning|wipe|관리|청소)\b',content[:match.start()],flags=re.I)[-1]
                    if not re.search(r'\bmaterial|made (?:of|from)|constructed (?:of|from)|소재|재질',context,re.I):continue
                value=match.group(0)
                if value not in specs.setdefault(key,[]):
                    specs[key].append(value)
                    evidence.append({'attribute':key,'value':value,'source_field':field,'text':value,'start':match.start(),'end':match.end(),'offset_basis':'HTML-stripped text' if field==source_field else 'original field'})
        # Explicit labelled specifications preserve raw values rather than guessing a schema.
        for line in content.splitlines():
            if SPECLABELS.search(line) and ':' in line:
                label,value=line.split(':',1);value=value.strip(' |')
                if value and len(label)<45 and not PROMO.search(value):
                    key='label:'+label.strip().lower()
                    specs.setdefault(key,[])
                    if value not in specs[key]:
                        specs[key].append(value);evidence.append({'attribute':key,'value':value,'source_field':field,'text':line,'offset_basis':'HTML-stripped line'})
    for segment in segments:
        reason=None
        if segment.casefold() in seen:reason='duplicate'
        seen.add(segment.casefold())
        if PURCHASE.search(segment):
            purchase.append({'text':segment,'source_field':source_field})
        if PROMO.search(segment):
            reason='promotion_or_contact'
            if TECHNICAL_FACT.search(segment) or PURCHASE.search(segment):
                retained=re.sub(r'\b(?:buy now|shop now|add to cart|subscribe(?: to (?:our )?newsletter)?)\b[!:,. ]*','',segment,flags=re.I)
                retained=re.sub(r'(?:\b(?:contact us|customer service|customer support|follow us|sign up)\b|고객센터|상담전화|카카오톡|쿠폰|최저가).*$','',retained,flags=re.I).strip(' ,;.-')
                if retained and retained!=segment and not PROMO.search(retained):
                    removed.append({'text':segment,'reason':'promotional_clause_removed','retained':retained})
                    kept.append(retained);continue
        elif META.search(segment):reason='catalogue_wrapper_or_general_notice'
        elif KO_PROMO.search(segment) and not (TECHNICAL_FACT.search(segment) or PURCHASE.search(segment) or re.search(r'수작업|제작|원산지',segment)):reason='promotional_korean_sentence'
        elif re.fullmatch(r'[\d., ]+',segment):reason='unlabelled_numeric_fragment'
        if reason:
            removed.append({'text':segment,'reason':reason});continue
        cleaned=re.sub(r'\b(?:(?:the )?world[’\']s smallest,?|amazing|stunning|incredible|best-in-class|brilliant|perfect for)\b[, ]*','',segment,flags=re.I).strip()
        cleaned=re.sub(r'고급스러운\s*|부드럽고 여성스러운\s*|차분하고 시크한\s*|슬림해 보이는 시크\s*','',cleaned)
        cleaned=re.sub(r'최고급 퀄리티를 추구하며\s*|가격대 최고의 디자인과 기술력으로\s*|하나하나 완벽하게\s*','',cleaned)
        if cleaned!=segment:removed.append({'text':segment,'reason':'promotional_phrase_removed','retained':cleaned})
        if cleaned:kept.append(cleaned)
    images=[];seen_images=set()
    for img in parser.images:
        if img['url'] in seen_images:continue
        seen_images.add(img['url'])
        marker=img['alt'] or ''
        role='detail_candidate_needs_review'
        if PROMO.search(marker) or re.search(r'banner|advert|coupon|event',marker,re.I):role='advertisement'
        elif re.search(r'specification|dimension|size chart|features|상세|사양|규격|사이즈',marker,re.I):role='detail_image_explicit_marker'
        images.append(dict(img,role=role,classification_basis='native img alt; otherwise description placement only',download_status='not_authorized'))
    # Important purchasing caveats are also retained when a mixed advertising sentence is removed.
    shipping=[p for p in purchase if re.search(r'ship|delivery|배송',p['text'],re.I)]
    warranty=[p for p in purchase if re.search(r'warranty|guarantee|보증',p['text'],re.I)]
    return {'clean_description':'\n'.join(kept) or None,'specifications':specs or None,
            'profile':category_profile,'specification_evidence':evidence,'removed':removed,
            'purchase_information':purchase,'shipping_evidence':shipping,'warranty_evidence':warranty,
            'description_images':images,'source_text_sha256':sha(original.encode()),'plain_text':plain}
