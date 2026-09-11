"""Explicit offline smoke driver. Its timings are never performance evidence."""
from stack.api import Completion
from stack.workloads import FILES
import json


def fake_client():
    class FakeClient:
        def complete(self, messages, **kwargs):
            steps=[('read_file',{'path':'README.md'}),('read_file',{'path':'ledger.py'}),
                   ('read_file',{'path':'test_ledger.py'}),
                   ('write_file',{'path':'ledger.py','content':FILES['ledger.py'].replace('+ sum(refunds)','- sum(refunds)')}),
                   ('run_tests',{}),
                   ('write_file',{'path':'ledger.py','content':FILES['ledger.py'].replace('+ sum(refunds)','- sum(refunds)').replace('page * size + 1','page * size')}),
                   ('run_tests',{})]
            turn=sum(m['role']=='assistant' for m in messages)
            if turn<len(steps):
                name,args=steps[turn]
                message={'role':'assistant','content':None,'tool_calls':[{'id':f'call-{turn}','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
                finish='tool_calls'
            else:
                message={'role':'assistant','content':'Fixed refund sign and zero-based pagination. Tests pass.'};finish='stop'
            return Completion(message,{'request_seconds_client':0.0,'input_tokens':len(str(messages)), 'generated_tokens':1,'cached_prefix_tokens':None},finish)
    return FakeClient()
