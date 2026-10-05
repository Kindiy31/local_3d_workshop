"""Isolated real HTTP server smoke test; no weights, references or GPU work."""
import os,socket,subprocess,sys,tempfile,time,urllib.request,json
from pathlib import Path
root=Path(__file__).resolve().parent
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
with tempfile.TemporaryDirectory() as tmp:
 env=dict(os.environ,WORKSHOP_DATA=tmp,HUNYUAN_MODELS=str(Path(tmp)/'models'),HUNYUAN_N8N_WEBHOOK='')
 proc=subprocess.Popen([sys.executable,'-m','uvicorn','service:app','--app-dir',str(root),'--host','127.0.0.1','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 try:
  url=f'http://127.0.0.1:{port}'
  for i in range(60):
   if proc.poll() is not None:raise RuntimeError(proc.stderr.read().decode())
   try:
    with urllib.request.urlopen(url+'/api/health',timeout=2) as r:health=json.load(r)
    break
   except OSError:time.sleep(.5)
  else:raise RuntimeError('Server startup timed out')
  assert health['ok'] and not health['multiview_ready'] and not health['gpu_busy_job']
  with urllib.request.urlopen(url+'/api/jobs') as r:assert json.load(r)==[]
  with urllib.request.urlopen(url+'/') as r:html=r.read().decode()
  assert 'Local 3D Workshop' in html and 'auto_paint' in html
  with urllib.request.urlopen(url+'/openapi.json') as r:api=json.load(r)
  assert '/api/shape' in api['paths'] and '/api/paint' in api['paths']
  print('PASS: isolated real HTTP health, empty history, web form, OpenAPI; no private data or GPU run')
 finally:
  proc.terminate()
  try:proc.wait(timeout=10)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
