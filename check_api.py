"""Upload/dependency routing tests with synthetic images; no model generation."""
import asyncio,io,tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from fastapi import UploadFile,HTTPException
import service
buf=io.BytesIO();Image.new('RGBA',(16,16),(200,120,30,255)).save(buf,format='PNG')
def photo():return UploadFile(filename='view.png',file=io.BytesIO(buf.getvalue()))
async def run():
 with tempfile.TemporaryDirectory() as tmp,patch.object(service,'JOBS',Path(tmp)):
  for mode in ['bad','multiview']:
   try:await service.shape(front=photo(),mode=mode,left=None,back=None,auto_paint=False)
   except HTTPException as exc:assert exc.status_code==400
   else:raise AssertionError('Missing views accepted')
  job=await service.shape(front=photo(),mode='multiview',left=photo(),back=photo(),auto_paint=True)
  paint=service._folder(job['paint_job_id']);shape=service._folder(job['id'])
  assert job['state']=='queued' and service._meta(paint)['depends_on']==job['id']
  for a,b in [('front','front'),('left','side'),('back','back')]:assert (shape/(a+'.png')).read_bytes()==(paint/(b+'.png')).read_bytes()
  assert not (paint/'shape.glb').exists()
  assert not (shape/'pid.txt').exists() and not (paint/'pid.txt').exists()
  try:service._folder('../unsafe')
  except HTTPException as exc:assert exc.status_code==400
  else:raise AssertionError('Unsafe id accepted')
  print('PASS: API validation, persistent two-stage queue, all three photos, no premature GPU/mesh, safe IDs')
asyncio.run(run())
