"""Atomic local control writes; no data or credentials are committed to the repository."""
import json,os,time,uuid
from pathlib import Path
from .runtime import STATE_ROOT,read,now

def replace_with_retry(temporary,path):
    for attempt in range(6):
        try:os.replace(temporary,path);return
        except PermissionError:
            if attempt==5:raise
            time.sleep(.05*2**attempt)

def save(path,value):
    path=Path(path).resolve();path.relative_to(STATE_ROOT)
    if path.exists() and path.suffix=='.json':
        old=read(path)
        if path.name=='request_ledger.json' and len(value.get('requests',[]))<len(old.get('requests',[])):
            raise ValueError('request_ledger_cannot_shrink')
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    payload=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n' if path.suffix=='.json' else value
    with temporary.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(payload);stream.flush();os.fsync(stream.fileno())
    replace_with_retry(temporary,path)

def update(step,current_source=None,next_action=None,**changes):
    directory=STATE_ROOT/'control';state=read(directory/'status.json',{})
    state.update(updated_at=now(),last_completed_step=step,current_source=current_source,**changes)
    if next_action:state['next_action']=next_action
    save(directory/'status.json',state)
    text=(directory/'progress.md').read_text(encoding='utf-8') if (directory/'progress.md').exists() else '# Progress\n'
    save(directory/'progress.md',text+'\n- '+state['updated_at']+' '+step+'\n')
    save(directory/'resume.md','Last completed: '+step+'\nNext: '+state.get('next_action','')+'\n')
    return state
