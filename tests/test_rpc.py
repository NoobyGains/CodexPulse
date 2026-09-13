import sys
import unittest
from codexpulse.rpc import Client, RpcError

SERVER = '''
import sys,json
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m: continue
 print(json.dumps({'method':'account/updated','params':{}}),flush=True)
 if m['method']=='initialize':
  print(json.dumps({'id':m['id'],'result':{}}),flush=True)
 elif m['method']=='broken':
  print(json.dumps({'id':m['id'],'error':{'code':-1,'message':'private details'}}),flush=True)
 else:
  print(json.dumps({'id':m['id'],'result':{'ok':True}}),flush=True)
'''

class Transport(unittest.TestCase):
    def test_notification_interleaving_and_redacted_errors(self):
        with Client([sys.executable, '-u', '-c', SERVER], timeout=2) as c:
            self.assertEqual(c.call('read'), {'ok': True})
            self.assertTrue(c.notifications)
            with self.assertRaises(RpcError) as error:
                c.call('broken')
            self.assertNotIn('private details', str(error.exception))
        self.assertIsNotNone(c.process.poll())
    def test_timeout_terminates_process(self):
        c = Client([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=.1)
        with self.assertRaises(RpcError):
            c.__enter__()
        self.assertIsNotNone(c.process.poll())

if __name__ == '__main__': unittest.main()
