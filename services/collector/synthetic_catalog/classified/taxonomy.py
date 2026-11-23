"""Provisional synthetic IDs never masquerade as official team category IDs."""
import json
from pathlib import Path

DEFAULT=Path(__file__).with_name('taxonomy.provisional.json')


class Taxonomy:
    def __init__(self,path=DEFAULT):
        self.path=Path(path);self.data=json.loads(self.path.read_text(encoding='utf-8'))
        if (self.data.get('namespace')!='synthetic_provisional' or self.data.get('status')!='pending_team_approval'
                or self.data.get('team_category_ids_authoritative') is not False):raise ValueError('provisional_namespace_required')
        self.nodes={}
        for node in self.data['nodes']:
            key=node['id']
            if not isinstance(key,str) or not key.startswith('SYN-CAT-') or key in self.nodes:
                raise ValueError('unique_provisional_ID_required')
            if node['level'] not in (1,2,3) or not isinstance(node['name'],str) or not node['name'].strip():
                raise ValueError('three_level_category_required')
            self.nodes[key]=node
        for node in self.nodes.values():
            if node['level']==1:
                if node['parent_id'] is not None or node.get('team_domain') not in ('product','food'):raise ValueError('team_domain_required')
            elif node['parent_id'] not in self.nodes or self.nodes[node['parent_id']]['level']!=node['level']-1:
                raise ValueError('category_parent_mismatch')
        self.profiles={};self.legacy={}
        for profile in self.data['profiles']:
            key=profile['leaf_id']
            if key in self.profiles or self.nodes.get(key,{}).get('level')!=3:raise ValueError('unique_leaf_profile_required')
            if type(profile['used_allowed']) is not bool or not profile['specifications'] or not profile['spec_label']:
                raise ValueError('explicit_profile_rules_required')
            if not profile['brands'] or any(not b.startswith('SYNTHETIC-') for b in profile['brands']):raise ValueError('synthetic_brands_required')
            for bounds in profile['price_ranges_minor_units'].values():
                if len(bounds)!=2 or any(type(v) is not int or v<=0 for v in bounds) or bounds[0]>bounds[1]:raise ValueError('valid_price_range_required')
            self.profiles[key]=profile
            if profile['legacy_category']:self.legacy.setdefault(profile['legacy_category'],[]).append(key)
        if set(self.profiles)!={k for k,n in self.nodes.items() if n['level']==3}:raise ValueError('all_leaf_profiles_required')
        self.majors=sorted(k for k,n in self.nodes.items() if n['level']==1)
        self.paths={key:self.path_for(key) for key in self.profiles}
    def path_for(self,key):
        leaf=self.nodes[key];mid=self.nodes[leaf['parent_id']];major=self.nodes[mid['parent_id']]
        return [major,mid,leaf]
    def select_legacy(self,category,rank):
        options=self.legacy.get(category)
        if not options:raise ValueError('unmapped_legacy_category')
        # Latin rotation avoids tying a leaf to domestic/overseas or new/used.
        return options[(rank//4+rank%4)%len(options)]
