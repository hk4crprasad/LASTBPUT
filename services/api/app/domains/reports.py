import csv
import html
import io
import json
from datetime import datetime,timedelta
from sqlalchemy import select
from app.core.models import TABLES
from app.core.records import insert,query,serialize
from app.core.storage import store
from app.domains.metrics import overview,sustainability,context
from app.domains.state import waste_state,assets_state,parking_safety,reserves_state

def create_report(db,scope,payload,key=None):
    scope.require('reports')
    if key:
        previous=db.scalar(select(TABLES['report_runs']).where(TABLES['report_runs'].world_id==scope.world.id,TABLES['report_runs'].idempotency_key==key))
        if previous:return serialize(previous)
    hours=int(payload.get('hours',24))
    if not 1<=hours<=720:raise ValueError('Report window 1–720 hours')
    end=scope.world.as_of;start=end-timedelta(hours=hours)
    facts={'overview':overview(db,scope,start,end),'sustainability':sustainability(db,scope,start,end),'operating_context':context(db,scope,start,end),
           'waste':waste_state(db,scope),'reserves':reserves_state(db,scope),'assets':assets_state(db,scope),'parking_safety':parking_safety(db,scope),
           'scenarios':[serialize(v) for v in query(db,scope,'simulation_runs',10)],'methodology':{'source_type':'synthetic','timezone':'Asia/Kolkata',
           'intervals':'Hourly usage interval ends at timestamp. Null readings remain missing; interval consumption is summed.',
           'estimates':'Versioned illustrative tariff and factor; no official carbon certification or measured savings.',
           'forecast':'Experimental supplied synthetic models; energy stress failures and weak generic detection remain disclosed.'}}
    output=io.StringIO();writer=csv.writer(output);writer.writerow(['metric','value','unit','valid_rows','rows','start_utc','end_utc','source_type'])
    for code,m in facts['overview']['metrics'].items():writer.writerow([code,m['value'],m['unit'],m['valid_rows'],m['rows'],start.isoformat(),end.isoformat(),'synthetic'])
    csv_file=store(db,scope,f'greenops-{scope.world.code}-{end.date()}.csv',output.getvalue().encode(),'text/csv','report')
    title=f'Hospital GreenOps | {scope.world.code} | {end.isoformat()}'
    rows=''.join('<tr>'+''.join(f'<td>{html.escape(str(value))}</td>' for value in [code,m['value'],m['unit'],f"{m['valid_rows']}/{m['rows']}"] )+'</tr>' for code,m in facts['overview']['metrics'].items())
    body=f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>body{{font:14px sans-serif;color:#162f27;max-width:1000px;margin:40px auto}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:10px;text-align:left}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}}@media print{{button{{display:none}}body{{margin:15px}}}}</style></head><body><h1>Hospital GreenOps operations report</h1><p>{html.escape(title)}</p><p><strong>SYNTHETIC DEMONSTRATION</strong> | Estimated and simulated results do not establish real savings.</p><p>Window: {start.isoformat()} to {end.isoformat()}. Print this document to PDF.</p><table><thead><tr><th>Metric</th><th>Value</th><th>Unit</th><th>Valid intervals</th></tr></thead><tbody>{rows}</tbody></table><h2>Operating context, risks, actions and methodology</h2><pre>{html.escape(json.dumps(facts,indent=2,default=str))}</pre></body></html>'''
    html_file=store(db,scope,f'greenops-{scope.world.code}-{end.date()}.html',body.encode(),'text/html','report')
    from app.domains.report_pdf import render
    pdf_file=store(db,scope,f'greenops-{scope.world.code}-{end.date()}.pdf',render(facts),'application/pdf','report')
    row=insert(db,scope,'report_runs',{'facts':facts,'csv_file_id':csv_file['id'],'html_file_id':html_file['id'],'pdf_file_id':pdf_file['id'],'window_hours':hours,
               'as_of':end.isoformat(),'source_type':'deterministic_report','llm_narrative':'not_requested'},name=payload.get('name','Operations daily brief'),status='completed',
               owner_id=scope.principal.user_id,idempotency_key=key,source_type='synthetic_report',zone_code=scope.zone_codes[0] if scope.zone_codes else None)
    return serialize(row)
