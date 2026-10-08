import type {components} from './generated-api';
export type ActionRequest=components['schemas']['ActionInput'];
export type TransitionRequest=components['schemas']['Transition'];
export type ScenarioRequest=components['schemas']['Scenario'];
export type Row={id:string;name:string;zone_code:string|null;category:string;status:string;severity:string;version:number;owner_id:string|null;parent_id:string|null;event_at:string;due_at:string|null;value:number|null;unit:string|null;source_type:string;data:Record<string,any>};
export type World={id:string;code:string;name:string;facility_id:string;organization_id:string;as_of:string;version:number;paused:boolean};
export type Principal={id:string;name:string;role:string;organization_id:string;llm:{enabled:boolean;configured:boolean;tools:boolean;monitor_writes:boolean}};
export function csrf(){return decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith('greenops_csrf='))?.split('=')[1]||'')}
export async function api<T=any>(path:string,options:RequestInit={}) :Promise<T>{
 const response=await fetch('/api/v1'+path,{credentials:'include',...options,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf(),...options.headers}});
 if(!response.headers.get('content-type')?.includes('application/json'))throw new Error(`API returned an unexpected response (${response.status}). Refresh or inspect the server logs.`);
 const body=await response.json();if(!response.ok)throw new Error(body.error?.message||`Request failed (${response.status})`);return body;
}
export function scoped(path:string,world:string,query:Record<string,string|number>={}){const params=new URLSearchParams({world_id:world});for(const [k,v]of Object.entries(query))params.set(k,String(v));return path+'?'+params.toString()}
export async function mutation<T=any>(path:string,world:string,data:unknown,method='POST'):Promise<T>{return api<T>(scoped(path,world),{method,body:JSON.stringify(data),headers:{'Idempotency-Key':crypto.randomUUID()}})}
export function number(value:unknown,digits=1){return value===null||value===undefined?'Unknown':Number(value).toLocaleString('en-IN',{maximumFractionDigits:digits})}
export function time(value:string,zone='Asia/Kolkata'){return new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:zone}).format(new Date(value))}

export function createAction(world:string,body:ActionRequest){return mutation<Row>('/actions',world,body)}
export function transitionAction(world:string,id:string,body:TransitionRequest){return mutation<Row>(`/actions/${id}/transition`,world,body)}
