"""Render and validate all README/workflow Mermaid diagrams using native Playwright."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
blocks=[]
for file in ['README.md','docs/workflow.md','docs/techstack-and-scopes.md']:
    for i,code in enumerate(re.findall(r'```mermaid\n(.*?)\n```',Path(file).read_text(),re.S),1):blocks.append((file,i,code))
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':2400,'height':1600},device_scale_factor=1)
    page.set_content('<html><body style="margin:0;background:white"><div id="diagram" style="padding:32px;width:2300px"></div></body></html>')
    page.add_script_tag(path=str(Path('.local/mermaid-validation/node_modules/mermaid/dist/mermaid.min.js').resolve()))
    page.evaluate("mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'default',fontFamily:'Arial',flowchart:{useMaxWidth:true}})")
    for n,(file,i,code) in enumerate(blocks):
        svg=page.evaluate('async ({id,code}) => (await mermaid.render(id,code)).svg',{'id':f'flow{n}','code':code})
        export_name = 'greenops-workflow' if n == 0 else ({1:'technology-stack',2:'user-scopes'}.get(i) if file == 'docs/techstack-and-scopes.md' else None)
        if export_name:
            Path(f'docs/diagrams/{export_name}.mmd').write_text(code+'\n')
            Path(f'docs/diagrams/{export_name}.svg').write_text(svg+'\n')
            page.locator('#diagram').evaluate('(element,svg)=>element.innerHTML=svg',svg)
            page.locator('#diagram svg').screenshot(path=f'docs/diagrams/{export_name}.png')
        print('PASS',file,'diagram',i,flush=True)
    browser.close()
print('PASS all',len(blocks),'Mermaid diagrams rendered')
