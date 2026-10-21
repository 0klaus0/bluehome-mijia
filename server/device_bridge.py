"""MIoT property reads and narrowly scoped card controls. Never executes actions."""
import json
import math
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
from home_assistant import HomeAssistant

METRICS = {'on','brightness','color-temperature','temperature','target-temperature','relative-humidity','humidity','pm2.5-density','pm10-density','battery-level','battery','power','electric-power','power-consumption','voltage','electric-current','status','fault','mode','fan-level','speed-level','water-level','water-shortage-fault','filter-life-level','filter-used-time','tds','illumination','motion-state','occupancy-status','occupancy','no-one-duration','washing-left-time','left-time','volume','mute','temperature-humidity-index'}
CONTROL_NAMES = {'on','brightness','color-temperature','target-temperature','mode','fan-level','speed-level'}
CONTROL_SERVICES = {'light','air-conditioner','fan','fan-control','outlet','switch','humidifier','air-purifier'}

class DeviceBridge:
    def __init__(self, api, raw_devices, public_rows, private):
        self.api, self.private = api, Path(private)
        self.token = secrets.token_urlsafe(32)
        # Match in original DID dedup order, identical to the connector's row construction.
        unique, seen = [], set()
        for device in raw_devices:
            did = str(device.get('did',''))
            if did not in seen:
                unique.append(device)
                seen.add(did)
        self.registry = {row['key']: raw for row,raw in zip(public_rows,unique)}
        self.rows = {r['key']:r for r in public_rows}
        self.specs, self.values = {}, {}
        self.lock, self.network = threading.RLock(), threading.Lock()
        self.reading, self.last_read, self.error = True, None, None
        self.online_read_at = None
        self.assistant = HomeAssistant(self)
        threading.Thread(target=self.initialize, daemon=True).start()

    def load_spec(self, urn):
        if not urn:return []
        cache=self.private/('raw-spec-'+str(urn).replace(':','_')+'.json')
        try:
            if cache.exists(): content=json.loads(cache.read_text(encoding='utf-8'))
            else:
                response=requests.get('https://miot-spec.org/miot-spec-v2/instance',params={'type':urn},timeout=20)
                response.raise_for_status();content=response.json()
                cache.write_text(json.dumps(content,ensure_ascii=False),encoding='utf-8')
            props=[]
            for svc in content.get('services',[]):
                service=svc.get('type','').split(':')[3]
                if service=='device-information':continue
                for p in svc.get('properties',[]):
                    name=p.get('type','').split(':')[3]
                    if name not in METRICS:continue
                    access=p.get('access',[])
                    if 'read' not in access:continue
                    allowed = name in CONTROL_NAMES and service in CONTROL_SERVICES
                    if name in ('brightness','color-temperature'):allowed = service=='light'
                    if service in ('switch','outlet'):allowed = name=='on'
                    props.append({'id':f"{svc['iid']}.{p['iid']}",'siid':svc['iid'],'piid':p['iid'],'name':name,'service':service,'service_description':svc.get('description',service),'description':p.get('description',name),'unit':p.get('unit',''),'format':p.get('format',''),'range':p.get('value-range'),'options':p.get('value-list',[]),'writable':'write' in access and allowed})
            return props
        except Exception:return []

    def initialize(self):
        urns={d.get('spec_type') for d in self.registry.values() if d.get('spec_type') and not d.get('model','').startswith('miir.')}
        with ThreadPoolExecutor(max_workers=5) as pool:
            results=dict(zip(urns,pool.map(self.load_spec,urns)))
        with self.lock:
            self.specs={k:results.get(d.get('spec_type'),[]) if not d.get('model','').startswith('miir.') else [] for k,d in self.registry.items()}
        self.assistant.discover_ir()
        self.refresh()
        while True:
            time.sleep(60)
            self.refresh()

    def refresh(self):
        with self.network:
            with self.lock:self.reading=True
            try:
                latest = {str(d['did']):d for d in self.api.get_devices_list()+self.api.get_shared_devices_list()}
                with self.lock:
                    for key,d in self.registry.items():
                        new=latest.get(str(d['did']))
                        if new is not None:d['isOnline']=new.get('isOnline');self.rows[key]['online']=new.get('isOnline')
                    self.online_read_at=time.time()
            except Exception:pass
            queries=[]; lookup={}
            for k,d in self.registry.items():
                for p in self.specs.get(k,[]):
                    q={'did':str(d['did']),'siid':p['siid'],'piid':p['piid']}
                    queries.append(q);lookup[(q['did'],q['siid'],q['piid'])]=(k,p['id'])
            error=None
            for offset in range(0,len(queries),30):
                batch=queries[offset:offset+30]
                try:
                    result=self.api.get_devices_prop(batch)
                    if isinstance(result,dict):result=[result]
                    now=time.time(); returned={}
                    for item in result:
                        match=lookup.get((str(item.get('did')),item.get('siid'),item.get('piid')))
                        if match:returned[match]={'value':item.get('value') if item.get('code')==0 else None,'code':item.get('code',-1),'read_at':now,'update_time':item.get('updateTime')}
                    with self.lock:
                        for q in batch:
                            match=lookup[(q['did'],q['siid'],q['piid'])]
                            self.values[match]=returned.get(match,{'value':None,'code':-1,'read_at':now})
                except Exception:
                    error='部分设备属性读取失败'
                    with self.lock:
                        for q in batch:
                            match=lookup[(q['did'],q['siid'],q['piid'])]
                            prior=self.values.get(match,{})
                            self.values[match]={**prior,'code':-1,'stale':True}
            with self.lock:self.reading=False;self.last_read=time.time();self.error=error
        try:self.assistant.ingest(self.snapshot())
        except Exception:
            with self.lock:self.error='本地助手记录失败，设备读取仍可用'

    def snapshot(self):
        with self.lock:
            return {'reading':self.reading,'last_read':self.last_read,'online_read_at':self.online_read_at,'error':self.error,'devices':{str(k):{'online':d.get('isOnline'),'properties':[{**p,**self.values.get((k,p['id']),{'value':None,'code':None})} for p in self.specs.get(k,[])],'ir':d.get('model','').startswith('miir.')} for k,d in self.registry.items()}}

    def validate(self,key,prop_id,value):
        if key not in self.registry:raise ValueError('设备不存在')
        if self.registry[key].get('model','').startswith('miir.'):raise ValueError('红外控制尚未适配')
        if self.registry[key].get('isOnline') is not True:raise ValueError('设备离线或在线状态未知')
        p=next((p for p in self.specs.get(key,[]) if p['id']==prop_id and p['writable']),None)
        if not p:raise ValueError('此属性不支持快捷控制')
        fmt=p['format']
        if fmt=='bool':
            if type(value) is not bool:raise ValueError('开关值无效')
        elif fmt.startswith(('int','uint')) or fmt=='float':
            if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('数值无效')
            if fmt!='float' and int(value)!=value:raise ValueError('需要整数')
            if p['range']:
                lo,hi,step=p['range']
                if not lo<=value<=hi or (step and abs((value-lo)/step-round((value-lo)/step))>1e-5):raise ValueError('数值超出范围或步长')
        else:raise ValueError('不支持此控制类型')
        if p['options'] and value not in [x['value'] for x in p['options']]:raise ValueError('无效选项')
        return p

    def control(self,key,prop_id,value,expected=None):
        p=self.validate(key,prop_id,value)
        d=self.registry[key]
        with self.network:
            if d.get('isOnline') is not True:raise ValueError('设备离线或在线状态未知')
            if expected is not None:
                check=self.api.get_devices_prop({'did':str(d['did']),'siid':p['siid'],'piid':p['piid']})
                if isinstance(check,list):check=check[0] if check else {}
                if check.get('code')!=0 or check.get('value')!=expected:raise ValueError('目标状态已变化')
            response=self.api.set_devices_prop({'did':str(d['did']),'siid':p['siid'],'piid':p['piid'],'value':value})
            if isinstance(response,list):response=response[0] if response else {}
            if response.get('code') not in (0,1):return {'ok':False,'message':'设备未接受指令，状态未更新'}
            try:
                result=self.api.get_devices_prop({'did':str(d['did']),'siid':p['siid'],'piid':p['piid']})
                if isinstance(result,list):result=result[0] if result else {}
            except Exception:result={}
            confirmed=result.get('code')==0 and result.get('value')==value
            with self.lock:self.values[(key,p['id'])]={'value':result.get('value') if result.get('code')==0 else None,'code':result.get('code',-1),'read_at':time.time(),'update_time':result.get('updateTime')}
        outcome = {'ok':True,'confirmed':confirmed,'message':'已读取到目标状态' if confirmed else '指令已提交，尚未确认目标状态'}
        if hasattr(self,'assistant'):
            with self.assistant.lock:
                self.assistant.event('command',str(d['did']),property=prop_id,value=value,result=outcome)
                self.assistant.persist()
        return outcome
