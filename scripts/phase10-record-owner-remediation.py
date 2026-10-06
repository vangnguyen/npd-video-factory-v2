"""Record the actual Owner request-changes decisions once through Studio APIs."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('uat_render', ROOT/'scripts/phase10-final-uat-render.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CASES = [
 ('01','d3aa854ed0ed552091f513c66642d8a0','2cdfd4778c834bb68847e80397445626',18,
  'Ca 01: Vinhomes Green Paradise, đọc thiếu tên dự án'),
 ('02','206a81364b2e5d0d98fa0cfdf2b5bedb','f221cf0bbf7e480a9de40f65f96d8bf6',15,
  'Ca 02: cũng đọc sai tên dự án, khoảng lặng dài, độ dài video 45 giây nhưng lời thoại dừng ở giây 27'),
 ('04','ec5a3d1cf3cf5ec3a1debaf97c189139','87b374a1ae2f49969fb2b5646e2e8458',15,
  'Ca 04 cũng vậy'),
 ('06','5e9d204790f551eb8afadee33a67a8f6','9bd7e74329f542c3b859d98bceaecbc6',14,
  'Ca 06 cũng vậy'),
 ('08','7f13a515100d5c07aae9760d665ad2f8','8b2aeb294d144c5f8d7377357b7c5073',17,
  'Ca 08 cũng vậy, kích thước khung hình 1920x1080 full hd'),
]

def main():
 api = module.API('ux-remediation/owner-feedback')
 rows = []
 for case, project_id, job_id, revision, quote in CASES:
  project = api.request('GET', '/api/projects/'+project_id)
  job = next(j for j in project['jobs'] if j['id']==job_id)
  assert job['revision']==revision and job['status']=='succeeded'
  original = ROOT.parent/'phase10-uat'/'jobs'/job_id/'final.mp4'
  actual_sha = hashlib.sha256(original.read_bytes()).hexdigest()
  assert actual_sha==job['result']['qc']['final_sha256']
  before = {'project_revision':project['revision'], 'timeline':project.get('shot_timeline'),
            'render_revision':revision,'job_id':job_id,'sha256':actual_sha,
            'duration_seconds':job['result']['qc']['duration_seconds']}
  prior = job.get('final_review')
  if prior and prior['decision']=='reject':
   result = project
   action = 'PRESERVED_EXISTING_REJECTION'
  else:
   assert project['revision']==revision, 'Review only the exact current Owner-watched artifact'
   result = api.request('POST', '/api/jobs/'+job_id+'/review', {
    'revision':revision,'reviewer':'Owner','acknowledged':False,'decision':'reject',
    'note':'Owner yêu cầu sửa qua chat: '+quote+'; kiểm tra tên đầy đủ, phát âm, khoảng lặng và phần hình kéo dài sau lời đọc.'})
   action = 'RECORDED_OWNER_REQUEST_CHANGES'
  reviewed = next(j for j in result['jobs'] if j['id']==job_id)
  assert reviewed['final_review']['decision']=='reject'
  assert hashlib.sha256(original.read_bytes()).hexdigest()==actual_sha
  rows.append({'case':case,'feedback_verbatim':quote,'before':before,'action':action,
               'after_project_revision':result['revision'],'after_timeline':result.get('shot_timeline'),
               'actual_final_review':reviewed['final_review'],'original_mp4_preserved':True})
 api.ledger.save('owner-request-changes.json', {
  'captured_at':datetime.now(timezone.utc).isoformat(),
  'source':'Direct human Owner chat feedback after reviewing the five new Phase10 videos',
  'task':'VF-PHASE10-STUDIO-UX-STANDARDIZATION-02',
  'human_acceptance_count':0,'rows':rows,
  'gates':{'PRODUCTION_INTELLIGENCE_READY':'YES','DRAMAGIC_STUDIO_READY':'NO','PHASE10_READY':'NO'},
  'next':'Repair video UAT and Studio UX, then obtain distinct Owner review of both.'})
 print(json.dumps({'recorded':len(rows),'evidence':str(api.ledger.root),'accepted':0}))

if __name__=='__main__': main()
