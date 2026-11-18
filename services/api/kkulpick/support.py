"""Support conversations in the independent support database."""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Depends,Query,Request
from pydantic import Field
from .access import access
from .members import Strict,member,row,execute,fail,wrap,throttle

router=APIRouter()

class Message(Strict):
    body:str=Field(min_length=1,max_length=10000)
    client_message_id:UUID

class StateChange(Strict):
    status:Literal['open','pending_customer','pending_agent','resolved','closed']
    expected_version:int=Field(ge=1)


def conversation(r):
    return {k:r[k] for k in ('conversation_id','status','version','created_at','updated_at')}|{'agent_name':None}


def message(r):
    return {k:r[k] for k in ('message_id','sequence_no','sender','body','created_at')}|{'sender_name':'상담원' if r['sender']=='agent' else None}


@router.post('/v2/support/conversations',status_code=201)
async def create_conversation(req:Request,uid=Depends(member)):
    await throttle(req,'support')
    async with access(req,uid):
        async with req.app.state.support_engine.begin() as c:
            await execute(c,'INSERT INTO app.conversations(owner_id) VALUES(:u) ON CONFLICT DO NOTHING',u=uid)
            r=await row(c,"SELECT * FROM app.conversations WHERE owner_id=:u AND status IN ('open','pending_customer','pending_agent')",u=uid)
    return wrap(conversation(r),req)


@router.get('/v2/support/conversations')
async def list_conversations(req:Request,limit:int=Query(20,ge=1,le=100),uid=Depends(member)):
    async with access(req,uid):
        async with req.app.state.support_engine.connect() as c:
            rows=(await execute(c,'''SELECT * FROM app.conversations WHERE owner_id=:u
                ORDER BY CASE WHEN status IN ('open','pending_customer','pending_agent') THEN 0 ELSE 1 END,
                updated_at DESC,conversation_id DESC LIMIT :n''',u=uid,n=limit)).mappings().all()
    return wrap([conversation(r) for r in rows],req)


@router.get('/v2/admin/support/conversations')
async def admin_conversations(req:Request,limit:int=Query(20,ge=1,le=100),after:UUID|None=None,uid=Depends(member)):
    async with access(req,uid,{'admin','support'}) as member_conn:
        async with req.app.state.support_engine.connect() as support_conn:
            rows = (await execute(support_conn, '''SELECT c.*, reply.sender_id AS last_agent_id
                FROM app.conversations c
                LEFT JOIN LATERAL (
                    SELECT sender_id FROM app.messages
                    WHERE conversation_id=c.conversation_id AND sender='agent'
                    ORDER BY sequence_no DESC LIMIT 1
                ) reply ON true
                WHERE CAST(:a AS uuid) IS NULL OR c.conversation_id>CAST(:a AS uuid)
                ORDER BY c.conversation_id LIMIT :n''', a=after, n=limit)).mappings().all()

        agent_ids = list({r['last_agent_id'] for r in rows if r['last_agent_id'] is not None})
        agent_names = {}
        if agent_ids:
            agents = (await execute(member_conn, '''SELECT user_id, login_id FROM app.members
                WHERE user_id=ANY(CAST(:ids AS uuid[])) AND deleted_at IS NULL''',
                ids=agent_ids)).mappings().all()
            agent_names = {agent['user_id']: agent['login_id'] for agent in agents}

    return wrap([conversation(r) | {'owner_id': r['owner_id'],
        'agent_name': agent_names.get(r['last_agent_id'])} for r in rows], req)


async def read_messages(cid,req,uid,limit,after,admin=False):
    async with access(req,uid,{'admin','support'} if admin else None):
        async with req.app.state.support_engine.connect() as c:
            conv=await row(c,'SELECT owner_id FROM app.conversations WHERE conversation_id=:id',id=cid)
            if not conv or (not admin and conv['owner_id']!=uid):fail(404,'CONVERSATION_NOT_FOUND')
            order='ASC' if after is not None else 'DESC'
            rows=(await execute(c,f'''SELECT * FROM app.messages WHERE conversation_id=:id
                AND (CAST(:after AS bigint) IS NULL OR sequence_no>:after)
                ORDER BY sequence_no {order} LIMIT :n''',id=cid,after=after,n=limit)).mappings().all()
    return wrap([message(r) for r in sorted(rows,key=lambda r:r['sequence_no'])],req)


@router.get('/v2/support/conversations/{conversation_id}/messages')
async def messages(conversation_id:UUID,req:Request,limit:int=Query(50,ge=1,le=100),after_sequence:int|None=Query(None,ge=0),uid=Depends(member)):
    return await read_messages(conversation_id,req,uid,limit,after_sequence)


@router.get('/v2/admin/support/conversations/{conversation_id}/messages')
async def admin_messages(conversation_id:UUID,req:Request,limit:int=Query(50,ge=1,le=100),after_sequence:int|None=Query(None,ge=0),uid=Depends(member)):
    return await read_messages(conversation_id,req,uid,limit,after_sequence,True)


async def send(cid,data,req,uid,admin=False):
    await throttle(req,'support')
    if not data.body.strip():fail(422,'INVALID_INPUT')
    async with access(req,uid,{'admin','support'} if admin else None):
        async with req.app.state.support_engine.begin() as c:
            conv=await row(c,'SELECT * FROM app.conversations WHERE conversation_id=:id FOR UPDATE',id=cid)
            if not conv or (not admin and conv['owner_id']!=uid):fail(404,'CONVERSATION_NOT_FOUND')
            old=await row(c,'SELECT * FROM app.messages WHERE conversation_id=:id AND client_message_id=:k',id=cid,k=data.client_message_id)
            if old:
                if old['sender_id']!=uid or old['body']!=data.body:fail(409,'MESSAGE_KEY_CONFLICT')
                return wrap(message(old),req)
            if conv['status'] in {'closed','resolved'}:fail(409,'CONVERSATION_CLOSED')
            r=await row(c,'''INSERT INTO app.messages(conversation_id,client_message_id,sequence_no,sender,sender_id,body)
                VALUES(:id,:k,:seq,:sender,:u,:body) RETURNING *''',id=cid,k=data.client_message_id,seq=conv['next_sequence'],
                sender='agent' if admin else 'member',u=uid,body=data.body)
            await execute(c,'''UPDATE app.conversations SET next_sequence=next_sequence+1,version=version+1,
                status=:s,updated_at=now() WHERE conversation_id=:id''',id=cid,s='pending_customer' if admin else 'pending_agent')
    return wrap(message(r),req)


@router.post('/v2/support/conversations/{conversation_id}/messages')
async def send_message(conversation_id:UUID,data:Message,req:Request,uid=Depends(member)):
    return await send(conversation_id,data,req,uid)


@router.post('/v2/admin/support/conversations/{conversation_id}/messages')
async def reply_message(conversation_id:UUID,data:Message,req:Request,uid=Depends(member)):
    return await send(conversation_id,data,req,uid,True)


@router.patch('/v2/admin/support/conversations/{conversation_id}')
async def state(conversation_id:UUID,data:StateChange,req:Request,uid=Depends(member)):
    async with access(req,uid,{'admin','support'}):
        async with req.app.state.support_engine.begin() as c:
            old=await row(c,'SELECT * FROM app.conversations WHERE conversation_id=:id FOR UPDATE',id=conversation_id)
            if not old:fail(404,'CONVERSATION_NOT_FOUND')
            if old['version']!=data.expected_version:fail(409,'VERSION_CONFLICT')
            if old['status']=='closed' and data.status!='closed':fail(409,'CONVERSATION_CLOSED')
            r=await row(c,'''UPDATE app.conversations SET status=:s,version=version+1,updated_at=now()
                WHERE conversation_id=:id RETURNING *''',id=conversation_id,s=data.status)
    return wrap(conversation(r),req)

class SupportSettings(Strict):
    days:str=Field(min_length=1,max_length=100)
    startTime:str=Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    endTime:str=Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    awayMessage:str=Field(max_length=2000)
    expected_version:int=Field(ge=1)

async def settings_row(c):
    r=await row(c,'SELECT * FROM app.support_settings WHERE singleton')
    return {'days':r['days'],'startTime':r['start_time'],'endTime':r['end_time'],
        'awayMessage':r['away_message'],'version':r['version']}

@router.get('/v2/admin/support/settings')
async def get_settings(req:Request,uid=Depends(member)):
    async with access(req,uid,{'admin','support'}):
        async with req.app.state.support_engine.connect() as c:
            return wrap(await settings_row(c),req)

@router.put('/v2/admin/support/settings')
async def save_settings(data:SupportSettings,req:Request,uid=Depends(member)):
    if data.startTime>=data.endTime:fail(422,'INVALID_HOURS')
    async with access(req,uid,{'admin','support'}):
        async with req.app.state.support_engine.begin() as c:
            changed=await row(c,'''UPDATE app.support_settings SET days=:d,start_time=:s,end_time=:e,
                away_message=:a,version=version+1,updated_at=now() WHERE singleton AND version=:v RETURNING version''',
                d=data.days,s=data.startTime,e=data.endTime,a=data.awayMessage,v=data.expected_version)
            if not changed:fail(409,'VERSION_CONFLICT')
            return wrap(await settings_row(c),req)
