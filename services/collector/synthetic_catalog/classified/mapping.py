"""Future official taxonomy is a reviewed link table, not rewritten legacy data."""


def validate_mapping(taxonomy,official,mapping):
    if not official.get('revision') or not official.get('source_reference'):raise ValueError('official_provenance_required')
    nodes={}
    for node in official['nodes']:
        ident=node['id']
        if not isinstance(ident,str) or not ident or ident.startswith('SYN-CAT-') or ident in nodes:
            raise ValueError('unique_official_ID_required')
        if node['level'] not in (1,2,3) or not node.get('name'):raise ValueError('official_three_levels_required')
        nodes[ident]=node
    for node in nodes.values():
        if node['level']==1:
            if node.get('parent_id') is not None:raise ValueError('official_parent_invalid')
        elif node.get('parent_id') not in nodes or nodes[node['parent_id']]['level']!=node['level']-1:
            raise ValueError('official_parent_invalid')
    for provisional,target in mapping.items():
        if provisional not in taxonomy.profiles or nodes.get(target,{}).get('level')!=3:
            raise ValueError('leaf_mapping_required')
    return nodes


def link_record(row,taxonomy,official,mapping):
    nodes=validate_mapping(taxonomy,official,mapping)
    target=mapping.get(row['category_ids'][2])
    if target is None:return {'record_id':row['record_id'],'status':'unmapped','team_category_id':None}
    leaf=nodes[target];mid=nodes[leaf['parent_id']];major=nodes[mid['parent_id']]
    return {'record_id':row['record_id'],'status':'mapped_pending_team_acceptance',
            'provisional_leaf_id':row['category_ids'][2],'team_category_id':target,
            'official_category_path':[major['name'],mid['name'],leaf['name']],
            'official_category_ids':[major['id'],mid['id'],leaf['id']],
            'revision':official['revision'],'source_reference':official['source_reference']}
