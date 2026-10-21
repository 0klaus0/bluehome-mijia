import threading
import unittest
from device_bridge import DeviceBridge

class FakeAPI:
    def __init__(self,code=0,reported=True):self.code=code;self.reported=reported;self.calls=[]
    def set_devices_prop(self,p):self.calls.append(p);return {'code':self.code}
    def get_devices_prop(self,p):return {'code':0,'value':self.reported}

class ControlsTest(unittest.TestCase):
    def bridge(self,code=0,reported=True):
        b=DeviceBridge.__new__(DeviceBridge)
        b.registry={1:{'did':'test-only','model':'test.light','isOnline':True}}
        b.specs={1:[{'id':'2.1','siid':2,'piid':1,'name':'on','format':'bool','writable':True,'range':None,'options':[]}, {'id':'2.2','siid':2,'piid':2,'name':'brightness','format':'uint8','writable':True,'range':[1,100,1],'options':[]}]}
        b.network=threading.Lock();b.lock=threading.Lock();b.values={};b.api=FakeAPI(code,reported)
        return b
    def test_confirmed_requires_readback(self):
        b=self.bridge(reported=False);r=b.control(1,'2.1',True)
        self.assertTrue(r['ok']);self.assertFalse(r['confirmed']);self.assertIs(b.values[(1,'2.1')]['value'],False)
    def test_rejection_does_not_change_state(self):
        b=self.bridge(code=-1);r=b.control(1,'2.1',True)
        self.assertFalse(r['ok']);self.assertEqual(b.values,{})
    def test_invalid_values_never_sent(self):
        b=self.bridge()
        for p,v in [('2.1',1),('2.2',101),('2.2',10.5),('2.2',float('nan')),('9.9',True)]:
            with self.assertRaises(ValueError):b.control(1,p,v)
        self.assertEqual(b.api.calls,[])
    def test_ir_and_offline_never_sent(self):
        b=self.bridge();b.registry[1]['model']='miir.tv.ir01'
        with self.assertRaises(ValueError):b.control(1,'2.1',True)
        b.registry[1]['model']='test.light';b.registry[1]['isOnline']=False
        with self.assertRaises(ValueError):b.control(1,'2.1',True)
        self.assertEqual(b.api.calls,[])
    def test_confirmed_success(self):
        b=self.bridge();self.assertTrue(b.control(1,'2.1',True)['confirmed'])

if __name__=='__main__':unittest.main()
