import tempfile
import threading
import time
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from home_assistant import HomeAssistant

def prop(i='2.1',name='on',fmt='bool',writable=True):
    return {'id':i,'siid':2,'piid':int(i.split('.')[1]),'name':name,'service':'light','format':fmt,'writable':writable,'options':[],'range':None}

class FakeAPI:
    def __init__(self):self.value=False;self.source=True;self.commands=[];self.fail_ir=False
    def get_devices_prop(self,p):return {'code':0,'value':self.source if p['did']=='one' else self.value}
    def _request(self,url,payload):
        self.commands.append((url,payload))
        if self.fail_ir:raise TimeoutError()
        return {}

class FakeBridge:
    def __init__(self,path):
        self.private=Path(path);self.network=threading.Lock();self.lock=threading.Lock();self.api=FakeAPI();self.commands=[]
        self.registry={1:{'did':'one','model':'test.light','isOnline':True},2:{'did':'two','model':'test.light','isOnline':True},3:{'did':'ir','model':'miir.remote.ir01','isOnline':True}}
        self.rows={1:{'home':'A','name':'测试灯1'},2:{'home':'A','name':'测试灯2'},3:{'home':'A','name':'测试红外'}}
        self.specs={1:[prop()],2:[prop()],3:[]}
    def control(self,key,property,value,expected=None):
        if self.registry[key]['isOnline'] is not True:raise ValueError()
        if expected is not None and self.api.value!=expected:raise ValueError()
        self.commands.append((key,property,value));return {'ok':True,'confirmed':True,'message':'mock confirmed'}

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.b=FakeBridge(self.tmp.name);self.a=HomeAssistant(self.b);self.a.capabilities=lambda:None
    def tearDown(self):self.tmp.cleanup()
    def snap(self,source=False,target=False):
        return {'devices':{'1':{'online':True,'properties':[{**prop(),'value':source,'code':0,'read_at':time.time(),'update_time':time.time()}]},'2':{'online':True,'properties':[{**prop(),'value':target,'code':0,'read_at':time.time(),'update_time':time.time()}]}}}
    def rule(self,**extra):
        payload={'op':'create_rule','trigger_key':1,'trigger_property':'2.1','trigger_value':True,'target_key':2,'target_property':'2.1','target_value':True,'name':'测试规则',**extra}
        self.a.operate(payload);return self.a.db['rules'][-1]
    def pending(self):
        r=self.rule();self.a.operate({'op':'toggle_rule','id':r['id'],'enabled':True});self.a.ingest(self.snap());self.a.ingest(self.snap(True));return self.a.db['pending'][0]
    def test_no_startup_events_or_default_execution(self):
        self.rule();self.a.ingest(self.snap(True));self.assertEqual(self.a.db['events'],[]);self.assertEqual(self.a.db['pending'],[]);self.assertEqual(self.b.commands,[])
    def test_trigger_only_enqueues_and_confirmation_is_once(self):
        p=self.pending();self.assertEqual(self.b.commands,[])
        self.assertTrue(self.a.operate({'op':'confirm','id':p['id'],'accept':True})['confirmed']);self.assertEqual(len(self.b.commands),1)
        with self.assertRaises(ValueError):self.a.operate({'op':'confirm','id':p['id'],'accept':True})
    def test_reject_timeout_and_disable_never_control(self):
        p=self.pending();self.a.operate({'op':'confirm','id':p['id'],'accept':False});self.assertEqual(self.b.commands,[])
        p['status']='pending';p['expires']=time.time()-1
        with self.assertRaises(ValueError):self.a.operate({'op':'confirm','id':p['id'],'accept':True})
        p['expires']=time.time()+100;self.a.operate({'op':'toggle_rule','id':p['rule_id'],'enabled':False})
        with self.assertRaises(ValueError):self.a.operate({'op':'confirm','id':p['id'],'accept':True})
        self.assertEqual(self.b.commands,[])
    def test_changed_target_prevents_execution(self):
        p=self.pending();self.b.api.value=True
        with self.assertRaises(ValueError):self.a.operate({'op':'confirm','id':p['id'],'accept':True})
        self.assertEqual(self.b.commands,[]);self.assertEqual(p['status'],'failed')
    def test_changed_trigger_prevents_execution(self):
        p=self.pending();self.b.api.source=False
        with self.assertRaises(ValueError):self.a.operate({'op':'confirm','id':p['id'],'accept':True})
        self.assertEqual(self.b.commands,[])
    def test_restart_expires_pending(self):
        self.pending();other=HomeAssistant(self.b);self.assertEqual(other.db['pending'][0]['status'],'expired')
    def test_cross_home_and_invalid_values_rejected(self):
        self.b.rows[2]['home']='B'
        with self.assertRaises(ValueError):self.rule()
        self.b.rows[2]['home']='A'
        with self.assertRaises(ValueError):self.rule(target_value=1)
    def test_cooldown_prevents_duplicate_requests(self):
        self.pending();self.a.ingest(self.snap(False));self.a.ingest(self.snap(True));self.assertEqual(len(self.a.db['pending']),1)
    def test_numeric_threshold_crossing(self):
        self.b.specs[1]=[prop(name='temperature',fmt='float')]
        r=self.rule(trigger_value=25,comparison='gt');r['enabled']=True
        first=self.snap(20);first['devices']['1']['properties'][0].update(name='temperature',format='float')
        self.a.ingest(first);next=self.snap(26);next['devices']['1']['properties'][0].update(name='temperature',format='float');self.a.ingest(next)
        self.assertEqual(len(self.a.db['pending']),1);self.assertEqual(self.b.commands,[])
    def test_ir_projection_and_uncertain_delivery(self):
        self.a.ir_keys={3:[{'id':'1','label':'电源','meaning':'toggle'},{'id':'2','label':'打开','meaning':'on'},{'id':'3','label':'关闭','meaning':'off'}]}
        self.a.operate({'op':'ir_click','key':3,'key_id':'1'});self.assertIsNone(self.a.db['ir']['ir']['value'])
        self.a.operate({'op':'ir_correct','key':3,'value':False});self.a.operate({'op':'ir_click','key':3,'key_id':'1'});self.assertIs(self.a.db['ir']['ir']['value'],True)
        self.a.operate({'op':'ir_click','key':3,'key_id':'3'});self.assertIs(self.a.db['ir']['ir']['value'],False)
        self.b.api.fail_ir=True;self.a.operate({'op':'ir_click','key':3,'key_id':'2'});self.assertIsNone(self.a.db['ir']['ir']['value'])
    def test_no_fabricated_habits(self):
        self.a.ingest(self.snap());s=self.a.snapshot();self.assertEqual(s['habits'],[]);self.assertFalse(s['llm_connected']);self.assertFalse(s['voice_reply_connected'])
    def test_daily_time_queues_once_without_execution(self):
        r=self.rule(trigger_type='time',time=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M'));r['enabled']=True
        self.a.ingest(self.snap());self.a.ingest(self.snap())
        self.assertEqual(len(self.a.db['pending']),1);self.assertEqual(self.b.commands,[])
    def test_washer_cannot_start_when_already_busy(self):
        self.b.specs[2]=[{**prop('2.1'),'service':'washer'},{**prop('2.2','status','uint8'),'service':'washer','options':[{'value':1,'description':'Idle'},{'value':3,'description':'Busy'}]},{**prop('2.4','fault','uint8'),'service':'washer'}]
        self.a.actions={2:[{'name':'start-wash','siid':2,'aiid':1}]}
        self.b.api.get_devices_prop=lambda queries:[{'code':0,'siid':q['siid'],'piid':q['piid'],'value':{1:True,2:3,4:0}[q['piid']]} for q in queries]
        self.b.api.run_action=lambda p:self.b.commands.append(p)
        with self.assertRaises(ValueError):self.a.action(2,'start-wash')
        self.assertEqual(self.b.commands,[])

if __name__=='__main__':unittest.main()
