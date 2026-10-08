import asyncio
import json
from dataclasses import dataclass
from typing import Protocol
from openai import AsyncOpenAI
from app.core.settings import settings

class ProviderUnavailable(RuntimeError):
    pass
class CapabilityUnavailable(RuntimeError):
    pass
@dataclass
class Reply:
    message:dict
    usage:dict
class LLMProvider(Protocol):
    async def chat_with_tools(self,messages:list,tools:list,model:str,budget:int)->Reply:...

class OpenAICompatible:
    def __init__(self,client=None):
        s=settings()
        if client is None and (not s.llm_enabled or not s.openai_api_key or not s.openai_chat_model):
            raise ProviderUnavailable('LLM configuration required: enable LLM, set server-side OPENAI_API_KEY and OPENAI_CHAT_MODEL')
        self.client=client or AsyncOpenAI(api_key=s.openai_api_key,base_url=s.openai_base_url,
                                         timeout=s.llm_timeout_seconds,max_retries=0)
    async def chat_with_tools(self,messages,tools,model,budget):
        s=settings()
        args={'model':model,'messages':messages}
        if s.llm_token_limit_parameter not in {'none','max_tokens','max_completion_tokens'}:
            raise CapabilityUnavailable('Unsupported token limit parameter configuration')
        if s.llm_token_limit_parameter!='none':
            args[s.llm_token_limit_parameter]=min(budget,s.agent_max_output_tokens)
        if s.llm_reasoning_effort:
            args['reasoning_effort']=s.llm_reasoning_effort
        if tools:
            if not s.llm_supports_tools:raise CapabilityUnavailable('Selected endpoint/model is configured without function calling; agent unavailable')
            if s.llm_supports_strict_schema:
                from copy import deepcopy
                tools=deepcopy(tools)
                def strictify(node):
                    if isinstance(node,dict):
                        if node.get('type')=='object':
                            node['additionalProperties']=False;node['required']=list(node.get('properties',{}))
                        for value in node.values():strictify(value)
                    elif isinstance(node,list):
                        for value in node:strictify(value)
                for tool in tools:
                    tool['function']['strict']=True;strictify(tool['function']['parameters'])
            args['tools']=tools;args['tool_choice']='auto'
            if s.llm_supports_parallel_tool_calls:args['parallel_tool_calls']=True
        if s.llm_supports_streaming:
            args['stream']=True
            if s.llm_stream_include_usage:args['stream_options']={'include_usage':True}
            stream=await self.client.chat.completions.create(**args)
            content=[];calls={};usage={'reported':False}
            async for chunk in stream:
                if chunk.usage:usage=chunk.usage.model_dump()
                if not chunk.choices:continue
                delta=chunk.choices[0].delta
                if delta.content:content.append(delta.content)
                for tc in delta.tool_calls or []:
                    item=calls.setdefault(tc.index,{'id':'','type':'function','function':{'name':'','arguments':''}})
                    if tc.id:item['id']=tc.id
                    if tc.function:
                        if tc.function.name:item['function']['name']+=tc.function.name
                        if tc.function.arguments:item['function']['arguments']+=tc.function.arguments
            message={'role':'assistant','content':''.join(content) or None}
            if calls:message['tool_calls']=[calls[k] for k in sorted(calls)]
            return Reply(message,usage)
        response=await self.client.chat.completions.create(**args)
        msg=response.choices[0].message.model_dump(exclude_none=True)
        usage=response.usage.model_dump() if response.usage else {'reported':False}
        return Reply(msg,usage)

async def check_provider():
    try:provider=OpenAICompatible()
    except ProviderUnavailable as exc:
        raise SystemExit('BLOCKED real-provider check: '+str(exc))
    model=settings().openai_agent_model or settings().openai_chat_model
    text=await provider.chat_with_tools([{'role':'user','content':'Reply with a short greeting.'}],[],model,100)
    if not text.message.get('content'):raise RuntimeError('Real text check returned no content')
    if not settings().llm_supports_tools:raise SystemExit('Text passed; BLOCKED tool round trip: function calling disabled')
    tools=[{'type':'function','function':{'name':'read_demo_clock','description':'Read harmless synthetic demo clock','parameters':{'type':'object','properties':{},'additionalProperties':False}}}]
    messages=[{'role':'user','content':'Call read_demo_clock once and report its result. Do not answer before calling.'}]
    first=await provider.chat_with_tools(messages,tools,model,200)
    calls=first.message.get('tool_calls',[])
    if not calls:raise CapabilityUnavailable('Endpoint did not call declared read tool')
    messages.append(first.message)
    for call in calls:
        if call['function']['name']!='read_demo_clock' or json.loads(call['function']['arguments'])!={}:raise CapabilityUnavailable('Invalid read-tool contract from provider')
        messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps({'as_of':'2025-06-29T23:00:00Z','source_type':'synthetic_capability_fixture'})})
    last=await provider.chat_with_tools(messages,tools,model,200)
    if not last.message.get('content'):raise RuntimeError('Provider did not finish read-tool round trip')
    parallel_verified=False
    if settings().llm_supports_parallel_tool_calls:
        second={'type':'function','function':{'name':'read_demo_boundary','description':'Read harmless operational scope boundary','parameters':{'type':'object','properties':{},'additionalProperties':False}}}
        parallel=await provider.chat_with_tools([{'role':'user','content':'Call both read_demo_clock and read_demo_boundary together in one assistant response. Do not answer before both calls.'}],tools+[second],model,300)
        parallel_calls=parallel.message.get('tool_calls',[])
        parallel_verified={c['function']['name'] for c in parallel_calls}=={'read_demo_clock','read_demo_boundary'}
        if parallel_verified:
            msgs=[{'role':'user','content':'Read the clock and boundary.'},parallel.message]
            for call in parallel_calls:
                if json.loads(call['function']['arguments'])!={}:raise CapabilityUnavailable('Malformed parallel read-tool arguments')
                msgs.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps({'as_of':'2025-06-29T23:00:00Z','boundary':'synthetic operations only'})})
            final=await provider.chat_with_tools(msgs,tools+[second],model,200)
            parallel_verified=bool(final.message.get('content'))
    return {'status':'passed_real_provider','endpoint':settings().openai_base_url,'model':model,
            'checks':['real_text','declared_read_tool','matching_tool_result','final_response']+(['streaming_chunks'] if settings().llm_supports_streaming else [])+(['parallel_tool_calls_parameter_accepted'] if settings().llm_supports_parallel_tool_calls else [])+(['multiple_parallel_read_calls_and_matching_results'] if parallel_verified else []),'parallel_read_calls_verified':parallel_verified,'token_limit_parameter':settings().llm_token_limit_parameter,'usage':[text.usage,first.usage,last.usage]}
