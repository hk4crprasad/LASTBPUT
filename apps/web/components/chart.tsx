'use client';
import {useEffect,useRef} from 'react';
import * as echarts from 'echarts';
export default function Chart({items,unit,forecast=[]}:{items:any[];unit:string;forecast?:any[]}){
 const ref=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(!ref.current)return;const chart=echarts.init(ref.current);const zones=Array.from(new Set(items.map(r=>r.zone)));const times=Array.from(new Set(items.map(r=>r.time))).sort();
 const palette=['#167553','#6b9e88','#253f63','#c48a37','#ac6577','#6889a0'];
 chart.setOption({color:palette,animation:false,textStyle:{fontFamily:'sans-serif'},tooltip:{trigger:'axis',valueFormatter:(v:any)=>v===null?'Missing':`${Number(v).toFixed(2)} ${unit}`},legend:{bottom:0},grid:{left:60,right:25,top:30,bottom:70},xAxis:{type:'time',axisLabel:{color:'#73817a'},splitLine:{show:false}},yAxis:{type:'value',name:unit,axisLabel:{color:'#73817a'},splitLine:{lineStyle:{color:'#edf1ef'}}},series:[...zones.map(z=>({name:z,type:'line',connectNulls:false,showSymbol:false,lineStyle:{width:2},data:times.map(t=>{const r=items.find(r=>r.time===t&&r.zone===z);return [t,r?.value??null]})})),...forecast.filter(f=>f.data.lower!==null&&f.data.upper!==null).map(f=>({name:`${f.zone_code} residual interval`,type:'line',showSymbol:true,symbol:'rect',symbolSize:5,lineStyle:{width:2,type:'dashed'},data:[[f.data.target_time,f.data.lower],[f.data.target_time,f.data.upper]],tooltip:{formatter:()=>`${f.zone_code}: ${f.data.lower} – ${f.data.upper} ${unit}<br/>Validation-residual interval; shift coverage unverified`}})),...forecast.map(f=>({name:`${f.zone_code} forecast`,type:'scatter',symbol:'diamond',symbolSize:10,data:[[f.data.target_time,f.data.value]],tooltip:{formatter:()=>`${f.name}: ${f.data.value} ${unit}<br/>${f.data.status} • hourly target`}}))]});
 const observer=new ResizeObserver(()=>chart.resize());observer.observe(ref.current);return()=>{observer.disconnect();chart.dispose()};},[items,unit,forecast]);
 return <div ref={ref} className="chart" role="img" aria-label={`Observed time series in ${unit}; missing values shown as gaps`}/>;
}
