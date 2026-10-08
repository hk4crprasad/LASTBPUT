"""Deterministic printable artifact from the same stored report facts as CSV/HTML."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

def render(facts):
    output=BytesIO();styles=getSampleStyleSheet();story=[]
    def paragraph(text,style='BodyText'):
        story.append(Paragraph(escape(str(text)),styles[style]));story.append(Spacer(1,8))
    o=facts['overview'];s=facts['sustainability']
    paragraph('Hospital GreenOps operations report','Title')
    paragraph('SYNTHETIC DEMONSTRATION — Operations and sustainability only','Heading2')
    paragraph(f"World: {o['world']} | Virtual cutoff UTC: {o['as_of']} | Display timezone: Asia/Kolkata")
    paragraph(f"Observation window: {o['start']} through {o['end']}. Usage is hourly interval consumption.")
    data=[['Metric','Value','Unit','Coverage']]+[[k,str(round(m['value'],3)) if m['value'] is not None else 'Unknown',m['unit'],f"{m['valid_rows']}/{m.get('expected_rows',m['rows'])}"] for k,m in o['metrics'].items()]
    table=Table(data,colWidths=[180,90,60,110],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5efe9')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#bdccc3')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]));story.extend([table,Spacer(1,16)])
    paragraph('Operating context and estimates','Heading2')
    paragraph(f"Occupied beds: {o['occupied_beds']} / {o['bed_capacity']}. Occupied inpatient bed-days: {s['occupied_bed_days']}. OPD counts are separate activity.")
    paragraph(f"Estimated cost INR: {s['cost_estimate_inr']}. Estimated carbon kgCO2e: {s['carbon_estimate_kgco2e']}. Factor IDs: {s['tariff']['id'] if s['tariff'] else 'Unavailable'} / {s['emission_factor']['id'] if s['emission_factor'] else 'Unavailable'}.")
    paragraph(s['boundary'])
    paragraph('Recorded risks and accountable actions','Heading2')
    for alert in o['active_alerts']:
        paragraph(f"Risk {alert['id']}: {alert['name']} | {alert['zone_code']} | {alert['severity']} | {alert['status']}")
    for action in o['actions']:
        paragraph(f"Action {action['id']}: {action['name']} | {action['status']} | owner {action['owner_id']} | due {action['due_at']}")
    paragraph('Waste ledger and resilience','Heading2')
    for c in facts['waste']['categories']:
        paragraph(f"{c['category']}: {c['stock_kg']} kg stock; oldest age {c['oldest_age_hours']} h; internal service deadline {c['deadline']}.")
    for resource in facts['reserves']['reserves']:
        paragraph(f"{resource['configuration']['name']}: {resource['state']['data']}")
    paragraph('Methodology and limitations','Heading2')
    for value in facts['methodology'].values():paragraph(value)
    for value in s['limitations']:paragraph(value)
    paragraph('No physical equipment operation, clinical advice, certified handover, or measured savings is established by this report.')
    SimpleDocTemplate(output,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=40,title='Hospital GreenOps synthetic report').build(story,canvasmaker=lambda *a,**kw:Canvas(*a,**{**kw,'invariant':1}))
    return output.getvalue()
