"""Attach category and food evidence in RAM without changing a v2 event/key."""
from services.collector.food_evidence.extract import extract


class EvidenceAdapter:
    def __init__(self, adapter, observer=None):
        self.adapter=adapter;self.cfg=adapter.cfg;self.observer=observer;self.accepting=False
    def search(self,*args):return self.adapter.search(*args)
    def detail(self,*args):return self.adapter.detail(*args)
    def normalize(self,row,at):
        result=self.adapter.normalize(row,at)
        category=row.get('category')
        native_category_id=row.get('categoryId')
        if isinstance(category,dict):
            native_category_id=category.get('id',native_category_id)
            category=category.get('name')
        if not isinstance(category,str):category=row.get('categoryPath') or row.get('categoryName')
        if not isinstance(category,str):
            categories=row.get('categories')
            category=' > '.join(c['categoryName'] for c in categories
                               if isinstance(c,dict) and isinstance(c.get('categoryName'),str)) if isinstance(categories,list) else None
        result['category']=category
        result['category_native_id']=str(native_category_id) if isinstance(native_category_id,(str,int)) and not isinstance(native_category_id,bool) else None
        result['category_semantics']='provider_native_label_and_ID; no_invented_global_taxonomy'
        field=next((f for f in ('description','shortDescription','description_html') if isinstance(row.get(f),str)),None)
        try:
            result['food_evidence']=extract(row.get(field) if field else None,source=self.cfg['source'],source_url=result.get('url'),
                observed_at=at,name=result.get('name') or '',category=category or '',source_field=field)
        except ValueError:
            result['food_evidence']={'status':'evidence_processing_held','safe_to_consume':None,
                'API_contract_ready':False,'allergen_status':'not_reported'}
        if (result['food_evidence']['status'] in ('food_evidence','evidence_processing_held')
                and self.cfg.get('food_policy','hold_until_contract')!='base_product_only'):
            result['observation']=None
            result['missing_fields']=sorted(set(result['missing_fields'])|{'food_contract_required'})
        if self.accepting and self.observer:self.observer(result,row)
        return result
