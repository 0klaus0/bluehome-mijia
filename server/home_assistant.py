"""Local event ledger, evidence-based habits and confirmation-only rules. No LLM calls."""
import json
import secrets
import threading
import time
import uuid
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

class HomeAssistant:
    def __init__(self,bridge):
        self.b=bridge;self.path=bridge.private/'assistant.json';self.lock=threading.RLock()
        try:self.db=json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.db={}
        for name in ('events','rules','pending','ir'):self.db.setdefault(name,[] if name!='ir' else {})
        self.previous={};self.last_sample={};self.actions={};self.speakers={};self.ir_keys={}
        self.db.setdefault('ir_meanings',{})
        # Pending confirmations never survive a process restart.
        for p in self.db['pending']:
            if p['status']=='pending':p['status']='expired'

    def persist(self):
        self.db['events']=self.db['events'][-3000:];self.db['pending']=self.db['pending'][-100:]
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.db,ensure_ascii=False),encoding='utf-8');tmp.replace(self.path)

    def did(self,key):
        if key not in self.b.registry:raise ValueError('设备不存在')
        return str(self.b.registry[key]['did'])

    def key(self,did):return next((k for k,d in self.b.registry.items() if str(d['did'])==did),None)

    def capabilities(self):
        actions={};speakers={}
        for key,d in self.b.registry.items():
            urn=d.get('spec_type')
            if not urn:continue
            path=self.b.private/('raw-spec-'+urn.replace(':','_')+'.json')
            try:spec=json.loads(path.read_text(encoding='utf-8'))
            except (OSError,ValueError):continue
            for svc in spec.get('services',[]):
                category=svc.get('type','').split(':')[3]
                for action in svc.get('actions',[]):
                    name=action['type'].split(':')[3]
                    if category=='washer' and name in ('start-wash','pause') and not action.get('in'):
                        actions.setdefault(key,[]).append({'id':f"{svc['iid']}.{action['iid']}",'name':name,'label':'开始洗涤' if name=='start-wash' else '暂停洗涤','siid':svc['iid'],'aiid':action['iid']})
                    if category=='intelligent-speaker' and name=='play-text' and len(action.get('in',[]))==1:
                        speakers[key]={'siid':svc['iid'],'aiid':action['iid']}
        self.actions=actions;self.speakers=speakers

    def discover_ir(self):
        for key,d in self.b.registry.items():
            if not d.get('model','').startswith('miir.'):continue
            try:
                with self.b.network:data=self.b.api._request('/v2/irdevice/controller/keys',{'did':self.did(key)})
                keys=data.get('keys',[]) if isinstance(data,dict) else []
                if not isinstance(keys,list):continue
                rows=[]
                for item in keys:
                    kid=item.get('id',item.get('key_id'))
                    if kid is None:continue
                    name=str(item.get('display_name') or item.get('name') or kid)
                    name={'HOMEPAGE':'主页','NAVIGATE_LEFT':'左','NAVIGATE_RIGHT':'右','NAVIGATE_UP':'上','NAVIGATE_DOWN':'下','BACK':'返回','MENU':'菜单','OK':'确认'}.get(name,name)
                    raw_name=str(item.get('name','')).lower()
                    default={'on':'on','power_on':'on','turn_on':'on','off':'off','power_off':'off','turn_off':'off','power':'toggle','power_toggle':'toggle','开机':'on','关机':'off','电源':'toggle'}.get(raw_name)
                    if default is None:
                        default='on' if name.startswith('开') and len(name)>1 else 'off' if name.startswith('关') and len(name)>1 else 'other'
                    rows.append({'id':str(kid),'label':name,'meaning':self.db['ir_meanings'].get(self.did(key)+':'+str(kid),default)})
                self.ir_keys[key]=rows
            except Exception:self.ir_keys[key]=[]

    def event(self,kind,did,**data):
        self.db['events'].append({'id':uuid.uuid4().hex,'at':time.time(),'kind':kind,'did':did,**data})

    def ingest(self,snapshot):
        with self.lock:
            self.capabilities();changed=False;now=time.time()
            for key,device in snapshot['devices'].items():
                k=int(key);did=self.did(k)
                if device.get('online') is not True:continue
                for p in device['properties']:
                    if p.get('code')!=0 or p.get('stale') or p.get('value') is None:continue
                    ident=(did,p['id']);current=p['value'];previous=self.previous.get(ident,current)
                    old_sample=self.last_sample.get(ident)
                    self.previous[ident]=current;self.last_sample[ident]=now
                    # Startup/reconnect baselines never become usage events.
                    if previous==current or old_sample is None or now-old_sample>180:continue
                    if p.get('update_time') and now-p['update_time']>300:continue
                    self.event('state_change',did,property=p['id'],name=p['name'],service=p['service'],before=previous,value=current);changed=True
                    for rule in self.db['rules']:
                        if not rule['enabled'] or rule.get('trigger_type')=='time' or rule['trigger_did']!=did or rule['trigger_property']!=p['id']:continue
                        threshold=rule['trigger_value'];comparator=rule.get('comparison','eq')
                        matches = current==threshold if comparator=='eq' else (type(current) in (int,float) and type(previous) in (int,float) and (previous<=threshold<current if comparator=='gt' else previous>=threshold>current))
                        if not matches:continue
                        if now-rule.get('last_trigger',0)<600:continue
                        if any(x['rule_id']==rule['id'] and x['status']=='pending' and x['expires']>now for x in self.db['pending']):continue
                        rule['last_trigger']=now
                        target_key=self.key(rule['target_did'])
                        if target_key is None:continue
                        target=next((x for x in snapshot['devices'].get(str(target_key),{}).get('properties',[]) if x['id']==rule.get('target_property')),None)
                        request={'id':secrets.token_urlsafe(18),'rule_id':rule['id'],'created':now,'expires':now+300,'status':'pending','target_before':target.get('value') if target and target.get('code')==0 else None,'voice':'未播报'}
                        self.db['pending'].append(request)
                        self.event('suggestion',rule['target_did'],rule_id=rule['id'],message=rule['name'])
                        if rule.get('speaker_did'):
                            # Fixed non-command announcement: never sends a voice device instruction.
                            threading.Thread(target=self.announce,args=(request['id'],),daemon=True).start()
            local=datetime.fromtimestamp(now,ZoneInfo('Asia/Shanghai'))
            for rule in self.db['rules']:
                if not rule['enabled'] or rule.get('trigger_type')!='time' or rule.get('time')!=local.strftime('%H:%M') or rule.get('last_date')==local.date().isoformat():continue
                rule['last_date']=local.date().isoformat();key=self.key(rule['target_did'])
                if key is None:continue
                target=next((x for x in snapshot['devices'].get(str(key),{}).get('properties',[]) if x['id']==rule.get('target_property')),None)
                p={'id':secrets.token_urlsafe(18),'rule_id':rule['id'],'created':now,'expires':now+300,'status':'pending','target_before':target.get('value') if target and target.get('code')==0 else None,'voice':'未播报'}
                self.db['pending'].append(p);self.event('suggestion',rule['target_did'],rule_id=rule['id'],message=rule['name']);changed=True
                if rule.get('speaker_did'):threading.Thread(target=self.announce,args=(p['id'],),daemon=True).start()
            for p in self.db['pending']:
                if p['status']=='pending' and p['expires']<=now:p['status']='expired';changed=True
            if changed:self.persist()

    def rule_payload(self,payload):
        trigger_key=int(payload['trigger_key']);target_key=int(payload['target_key'])
        tdid,adid=self.did(trigger_key),self.did(target_key)
        if self.b.rows[trigger_key]['home']!=self.b.rows[target_key]['home']:raise ValueError('触发和执行设备必须属于同一家庭')
        trigger_type=payload.get('trigger_type','state');comparison=payload.get('comparison','eq');clock=payload.get('time')
        tp=None;tv=payload.get('trigger_value')
        if trigger_type=='time':
            import re
            if not isinstance(clock,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',clock):raise ValueError('时间无效')
        else:
            if trigger_type!='state' or comparison not in ('eq','gt','lt'):raise ValueError('触发条件无效')
            tp=next((p for p in self.b.specs.get(trigger_key,[]) if p['id']==payload.get('trigger_property')),None)
            if not tp:raise ValueError('触发属性不存在')
            self.validate_value(tp,tv)
            if comparison!='eq' and (tp['format']=='bool' or tp.get('options')):raise ValueError('阈值条件只适用于数值属性')
        action=payload.get('action')
        if action:
            if action not in [a['name'] for a in self.actions.get(target_key,[])]:raise ValueError('动作不支持')
        else:
            # Specification check; an offline target can be configured, never executed.
            prop=next((p for p in self.b.specs.get(target_key,[]) if p['id']==payload.get('target_property') and p['writable']),None)
            if not prop:raise ValueError('执行属性不支持')
            value=payload.get('target_value')
            self.validate_value(prop,value)
        speaker=payload.get('speaker_key');sdid=None
        if speaker:
            speaker=int(speaker)
            if speaker not in self.speakers or self.b.rows[speaker]['home']!=self.b.rows[target_key]['home']:raise ValueError('播报音箱必须属于同一家庭')
            sdid=self.did(speaker)
        return {'id':uuid.uuid4().hex,'name':str(payload.get('name','设备状态建议'))[:80], 'trigger_type':trigger_type,'comparison':comparison,'time':clock,'trigger_did':tdid,'trigger_property':tp['id'] if tp else None,'trigger_value':tv,'target_did':adid,'target_property':payload.get('target_property') if not action else None,'target_value':payload.get('target_value') if not action else None,'action':action,'speaker_did':sdid,'enabled':False,'last_trigger':0}

    @staticmethod
    def validate_value(p,value):
        import math
        if p['format']=='bool':
            if type(value) is not bool:raise ValueError('开关值必须为布尔值')
        elif type(value) not in (int,float) or not math.isfinite(value):raise ValueError('数值无效')
        elif p['format']!='float' and int(value)!=value:raise ValueError('数值必须为整数')
        if p.get('range'):
            lo,hi,step=p['range']
            if not lo<=value<=hi or (step and abs((value-lo)/step-round((value-lo)/step))>1e-5):raise ValueError('数值超出范围')
        if p.get('options') and value not in [o['value'] for o in p['options']]:raise ValueError('选项无效')

    def announce(self,request_id):
        with self.lock:
            p=next((p for p in self.db['pending'] if p['id']==request_id),None)
            if not p or p['status']!='pending' or p['expires']<=time.time():return
            rule=next((r for r in self.db['rules'] if r['id']==p['rule_id']),None)
            if not rule or not rule['enabled']:return
            key=self.key(rule.get('speaker_did'));target=self.key(rule['target_did'])
            if key not in self.speakers or target is None:return
            text=f"家庭助手有一条待确认建议：{rule['name']}。涉及设备{self.b.rows[target]['name']}。请在栖居应用中核对操作并确认，五分钟内未确认将取消。当前不接收语音回答。"
        result='播报未确认'
        try:
            with self.b.network:
                if self.b.registry[key].get('isOnline') is not True:raise ValueError()
                r=self.b.api.run_action({'did':self.did(key),**self.speakers[key],'value':[text]})
                if isinstance(r,list):r=r[0] if r else {}
                if r.get('code') in (0,1):result='播报指令已提交，尚未取得你的确认'
        except Exception:result='播报失败，请在应用查看'
        with self.lock:p['voice']=result;self.persist()

    def action(self,key,name):
        action=next((a for a in self.actions.get(key,[]) if a['name']==name),None)
        if not action:raise ValueError('动作不支持')
        with self.b.network:
            if self.b.registry[key].get('isOnline') is not True:raise ValueError('设备不在线')
            checks=[p for p in self.b.specs.get(key,[]) if p['service']=='washer' and p['name'] in ('on','status','fault')]
            if len(checks)!=3:raise ValueError('缺少洗衣机状态反馈')
            result=self.b.api.get_devices_prop([{'did':self.did(key),'siid':p['siid'],'piid':p['piid']} for p in checks])
            if isinstance(result,dict):result=[result]
            returned={(r.get('siid'),r.get('piid')):r for r in result}
            values={p['name']:returned.get((p['siid'],p['piid']),{}) for p in checks}
            if any(v.get('code')!=0 for v in values.values()) or values['on'].get('value') is not True or values['fault'].get('value')!=0:raise ValueError('设备未开机、状态未知或存在故障')
            status_prop=next(p for p in checks if p['name']=='status')
            status=next((o.get('description','').lower() for o in status_prop.get('options',[]) if o['value']==values['status'].get('value')),'')
            if name=='start-wash' and status not in ('idle','standby'):raise ValueError('仅允许从待机开始洗涤')
            if name=='pause' and status not in ('run','busy'):raise ValueError('设备当前没有在洗涤')
            r=self.b.api.run_action({'did':self.did(key),'siid':action['siid'],'aiid':action['aiid'],'value':[]})
            if isinstance(r,list):r=r[0] if r else {}
            return {'ok':r.get('code') in (0,1),'confirmed':False,'message':'动作指令已提交，等待设备状态反馈' if r.get('code') in (0,1) else '设备拒绝动作'}

    def operate(self,payload):
        op=payload.get('op')
        if op=='create_rule':
            with self.lock:
                if len(self.db['rules'])>=50:raise ValueError('最多保存50条规则')
                self.db['rules'].append(self.rule_payload(payload));self.persist()
            return {'ok':True,'message':'规则已保存，默认关闭'}
        if op=='toggle_rule':
            with self.lock:
                r=next((r for r in self.db['rules'] if r['id']==payload.get('id')),None)
                if not r:raise ValueError('规则不存在')
                r['enabled']=payload.get('enabled') is True
                for p in self.db['pending']:
                    if p['rule_id']==r['id'] and p['status']=='pending':p['status']='cancelled'
                self.persist()
            return {'ok':True,'message':'规则已启用，触发后仍需确认' if r['enabled'] else '规则已关闭，待确认建议已取消'}
        if op=='ir_correct':
            key=int(payload['key']);did=self.did(key);value=payload.get('value')
            if not self.b.registry[key].get('model','').startswith('miir.') or (value is not None and type(value) is not bool):raise ValueError('红外校正参数无效')
            with self.lock:self.db['ir'][did]={'value':value,'source':'manual','at':time.time()};self.event('ir_manual',did,value=value);self.persist()
            return {'ok':True,'message':'已手动校正推测状态，未发送红外'}
        if op=='ir_meaning':
            key=int(payload['key']);kid=str(payload['key_id']);meaning=payload['meaning']
            button=next((k for k in self.ir_keys.get(key,[]) if k['id']==kid),None)
            if not button or meaning not in ('on','off','toggle','other'):raise ValueError('按键映射无效')
            with self.lock:
                self.db['ir_meanings'][self.did(key)+':'+kid]=meaning;button['meaning']=meaning;self.persist()
            return {'ok':True,'message':'按键含义已保存，不发送红外'}
        if op=='ir_click':
            key=int(payload['key']);kid=str(payload['key_id']);did=self.did(key)
            button=next((k for k in self.ir_keys.get(key,[]) if k['id']==kid),None)
            if not button:raise ValueError('红外按键不可用')
            with self.b.network:
                if self.b.registry[key].get('isOnline') is not True:raise ValueError('红外遥控器不在线')
                try:
                    result=self.b.api._request('/v2/irdevice/controller/key/click',{'did':did,'key_id':int(kid)})
                except Exception as exc:
                    from mijiaAPI.errors import APIError
                    with self.lock:
                        uncertain=not isinstance(exc,APIError) or str(exc).startswith('code: 0,')
                        if uncertain:self.db['ir'][did]={'value':None,'source':'uncertain','at':time.time()}
                        self.event('ir_failed',did,key_label=button['label'],uncertain=uncertain);self.persist()
                    return {'ok':False,'message':'红外发送未确认，请检查电器并校正状态'}
                if result is False or (isinstance(result,dict) and result.get('success') is False):return {'ok':False,'message':'云端拒绝红外指令，推测状态未更新'}
                with self.lock:
                    old=self.db['ir'].get(did,{}).get('value');meaning=button['meaning'];value=True if meaning=='on' else False if meaning=='off' else (not old if type(old) is bool else None) if meaning=='toggle' else old
                    if meaning!='other':self.db['ir'][did]={'value':value,'source':'command','at':time.time(),'key_label':button['label']}
                    self.event('ir_command',did,key_label=button['label'],meaning=meaning,value=value);self.persist()
            return {'ok':True,'confirmed':False,'message':'云端已接受红外指令，状态仅作推测'}
        if op=='confirm':
            if type(payload.get('accept')) is not bool:raise ValueError('请明确确认或拒绝')
            with self.lock:
                p=next((p for p in self.db['pending'] if p['id']==payload.get('id')),None)
                if not p or p['status']!='pending' or p['expires']<=time.time():raise ValueError('建议已失效或已处理')
                rule=next((r for r in self.db['rules'] if r['id']==p['rule_id']),None)
                if not rule or not rule['enabled']:raise ValueError('规则已关闭')
                if not payload.get('accept'):
                    p['status']='rejected';self.event('rejected',rule['target_did'],rule_id=rule['id']);self.persist();return {'ok':True,'message':'已拒绝，不执行'}
                key=self.key(rule['target_did'])
                if rule.get('action')=='start-wash' and payload.get('load_confirmed') is not True:raise ValueError('请先确认衣物、洗涤剂、程序与机盖已准备好')
                p['status']='executing';self.persist()
            try:
                if rule.get('trigger_type')!='time':
                    source_key=self.key(rule['trigger_did'])
                    source_prop=next((x for x in self.b.specs.get(source_key,[]) if x['id']==rule['trigger_property']),None)
                    if source_key is None or source_prop is None or self.b.registry[source_key].get('isOnline') is not True:raise ValueError('触发设备不可用')
                    with self.b.network:
                        source=self.b.api.get_devices_prop({'did':self.did(source_key),'siid':source_prop['siid'],'piid':source_prop['piid']})
                    if isinstance(source,list):source=source[0] if source else {}
                    value=source.get('value');condition=rule.get('comparison','eq')
                    matches=value==rule['trigger_value'] if condition=='eq' else (type(value) in (int,float) and (value>rule['trigger_value'] if condition=='gt' else value<rule['trigger_value']))
                    if source.get('code')!=0 or not matches:raise ValueError('触发条件已变化')
                if rule.get('action'):result=self.action(key,rule['action'])
                else:
                    prop=next((x for x in self.b.specs.get(key,[]) if x['id']==rule['target_property']),None)
                    if not prop:raise ValueError('目标属性不存在')
                    with self.b.network:
                        check=self.b.api.get_devices_prop({'did':self.did(key),'siid':prop['siid'],'piid':prop['piid']})
                    if isinstance(check,list):check=check[0] if check else {}
                    if check.get('code')!=0 or p['target_before'] is None or check.get('value')!=p['target_before']:raise ValueError('目标状态已变化或无法确认，请重新评估')
                    result=self.b.control(key,rule['target_property'],rule['target_value'],expected=p['target_before'])
            except Exception as e:
                with self.lock:p['status']='failed';self.event('execution_failed',rule['target_did'],rule_id=rule['id']);self.persist()
                raise ValueError('执行未确认：设备状态可能已变化或条件不满足') from e
            with self.lock:p['status']='confirmed' if result.get('ok') and result.get('confirmed') else 'submitted' if result.get('ok') else 'failed';self.event('execution',rule['target_did'],rule_id=rule['id'],result=result);self.persist()
            return result
        raise ValueError('不支持的助手操作')

    def snapshot(self):
        with self.lock:
            now=time.time();public=lambda did:self.key(did)
            rules=[{**{k:v for k,v in r.items() if not k.endswith('_did')},'trigger_key':public(r['trigger_did']),'target_key':public(r['target_did']),'speaker_key':public(r.get('speaker_did'))} for r in self.db['rules']]
            pending=[]
            for p in self.db['pending'][-30:]:
                status='expired' if p['status']=='pending' and p['expires']<=now else p['status']
                pending.append({**p,'status':status})
            events=[{**{k:v for k,v in e.items() if k!='did'},'key':public(e['did'])} for e in self.db['events'][-80:]]
            habits=[]
            samples=[e for e in self.db['events'] if e['kind']=='state_change' and e.get('name')=='on' and e.get('value') is True and e.get('service') in ('light','fan','air-conditioner','washer','outlet','switch','humidifier','air-purifier','kettle','fish-tank','camera-control')]
            for did in {e['did'] for e in samples}:
                group=[e for e in samples if e['did']==did];days={datetime.fromtimestamp(e['at'],ZoneInfo('Asia/Shanghai')).date() for e in group}
                if len(group)<5 or len(days)<3:continue
                buckets=Counter(datetime.fromtimestamp(e['at'],ZoneInfo('Asia/Shanghai')).hour//2 for e in group);hour,count=buckets.most_common(1)[0]
                if count<3 or count/len(group)<0.5:continue
                habits.append({'key':public(did),'samples':len(group),'days':len(days),'time':f'{hour*2:02d}:00—{hour*2+2:02d}:00','hour':hour*2,'ratio':round(count/len(group),2)})
            return {'rules':rules,'pending':pending,'events':events,'habits':habits,'samples':len(samples),'actions':self.actions,'speakers':list(self.speakers),'ir_keys':self.ir_keys,'ir':{str(public(did)):v for did,v in self.db['ir'].items() if public(did) is not None},'engine':'local-statistics','llm_connected':False,'voice_reply_connected':False,'monitoring':'本机服务运行期间约每分钟采样，短暂操作可能漏记；不是米家完整历史'}
