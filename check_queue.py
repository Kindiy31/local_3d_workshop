"""Persistent queue and dependency checks; never invokes GPU generation."""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import service
class StopLoop(BaseException): pass
def once():
 with patch.object(service.time,'sleep',side_effect=StopLoop):
  try: service._dispatch()
  except StopLoop: pass
with tempfile.TemporaryDirectory() as tmp, patch.object(service,'JOBS',Path(tmp)):
 a=Path(tmp)/('a'*32);b=Path(tmp)/('b'*32);a.mkdir();b.mkdir()
 assert service._launch(a,'shape')['state']=='queued'
 assert service._launch(b,'paint',depends_on=a.name)['state']=='queued'
 with patch.object(service.subprocess,'Popen') as proc, patch.object(service,'_active_job',return_value='busy'):
  once();proc.assert_not_called()
 (a/'shape.glb').write_bytes(b'fixture');(a/'exit_code.txt').write_text('0')
 meta=service._meta(a);meta['queued']=False;(a/'job.json').write_text(json.dumps(meta))
 with patch.object(service.subprocess,'Popen') as proc, patch.object(service,'_notify_n8n',return_value=True):
  proc.return_value.pid=123456;once();assert proc.call_count==1
 assert (b/'shape.glb').read_bytes()==b'fixture'
 assert not service._meta(b)['queued'] and 'started_at' in service._meta(b)
 # Dependency failure blocks Paint instead of starting it.
 (a/'exit_code.txt').write_text('1');(b/'pid.txt').unlink();meta=service._meta(b);meta['queued']=True;(b/'job.json').write_text(json.dumps(meta))
 with patch.object(service.subprocess,'Popen') as proc:
  once();proc.assert_not_called()
 assert service._status(b)['state']=='failed'
print('PASS: persistent queued state, busy GPU exclusion, dependent mesh copy, dispatch, failed dependency')
