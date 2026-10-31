'use strict';
const $=id=>document.getElementById(id);
let token='', devices=[], selected='', history={events:[],notes:[],commands:[]}, busy=false;
function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
async function api(path,method='GET',body){
 const headers={'Content-Type':'application/json'};if(token)headers.Authorization='Bearer '+token;
 const res=await fetch('/api/v1'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
 const data=await res.json();if(!res.ok){if(res.status===401&&token)signout();throw Error(data.error||'Request failed');}return data;
}
function signout(){token='';$('dashboard').hidden=true;$('loginPanel').hidden=false;$('logout').hidden=true;$('pairResult').textContent='';}
function node(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}
function current(){return devices.find(d=>d.id===selected);}
function telemetryAge(d){return d?.last_seen ? Math.max(0,Math.floor(Date.now()/1000-d.last_seen)) : Infinity;}
function dispenseBlockReason(d){
 const t=d?.telemetry, age=telemetryAge(d);
 if(!d?.online || age>30) return 'Device offline or telemetry is stale.';
 if(!t) return 'No telemetry received.';
 if(t.clock_trusted!==true) return 'Device clock is not trusted.';
 if(t.calibrated!==true) return 'Load-cell calibration is incomplete.';
 if(t.actuation_verified!==true) return 'Actuation commissioning is incomplete.';
 if(t.faults?.length) return 'Device reports faults: '+t.faults.join(', ');
 if(t.docked!==false) return t.docked===true ? 'Portable unit is docked. Undock it before dispensing.' : (t.limit_switch?.role&&t.limit_switch.role!=='dock_detect' ? 'Dock state is not sensed (limit switch role is '+t.limit_switch.role+').' : 'Dock state is unknown; dispensing remains blocked.');
 if(!t.limit_switch || t.limit_switch.ready!==true) return 'Dock limit switch is not ready.';
 if(t.limit_switch.active!==false) return t.limit_switch.active===true ? 'Dock limit switch indicates docked.' : 'Dock limit-switch state is unknown.';
 if(t.lid_closed!==true) return 'Lid-closed interlock is not confirmed. Check the required lid sensor/configuration.';
 if(!Array.isArray(t.current_occurrences) || !t.current_occurrences.includes($('occurrence').value)) return 'No valid current reminder occurrence.';
 const occ=$('occurrence').value;
 if(!occ) return 'Select a reminder occurrence.';
 if(history.events.some(e=>e.occurrence===occ&&e.kind==='attempt')) return 'An attempt is already recorded for this occurrence.';
 return '';
}
function endpoint(action){if(!selected)throw Error('Register or select a device first');return '/devices/'+encodeURIComponent(selected)+'/'+action;}
async function refresh(show=true){
 if(!token||busy)return;busy=true;
 try{
  devices=(await api('/devices')).devices;
  if(!devices.some(d=>d.id===selected))selected=devices[0]?.id||'';
  $('device').replaceChildren(...devices.map(d=>{const o=node('option',d.id);o.value=d.id;return o;}));$('device').value=selected;
  history=selected?await api(endpoint('history')):{events:[],notes:[],commands:[]};render();
  if(show)message(selected?'Updated from backend. Device readings show their last received state.':'Register your first device to begin.');
 }catch(e){message('Offline / request failed: '+e.message,true);$('connection').textContent='Backend unreachable';$('dispense').disabled=true;$('snooze').disabled=true;}
 finally{busy=false;}
}
function render(){
 const d=current(),t=d?.telemetry;
 $('connection').textContent=d?.online?'Device online':'Device offline';
 $('status').replaceChildren();
 const age=telemetryAge(d), fresh=Number.isFinite(age)&&age<=30;
 const sw=t?.limit_switch;
 const dock=t?.docked===true?'DOCKED':t?.docked===false?'UNDOCKED':'UNKNOWN';
 const switchState=!sw||sw.ready!==true?'UNKNOWN / NOT READY':sw.active===true?(sw.role==='dock_detect'?'PRESSED (docked)':'PRESSED'):sw.active===false?'RELEASED':'UNKNOWN';
 const gps=t?.gps, gpsText=!gps?'Unknown':gps.state==='fix'?('Fix · '+gps.lat+', '+gps.lon+' · '+(gps.satellites??'?')+' sats'):gps.state==='nmea_no_fix'?'Receiving data, NO satellite fix':gps.state==='disabled'?'Disabled':'No GPS data (check wiring/baud)';
 const fields=[['Dispenser state',t?.state||'Unknown'],['Dock attachment',dock],['Limit switch ('+(sw?.role||'role unknown')+')',switchState],['Telemetry freshness',fresh ? ('Fresh ('+age+'s ago)') : 'STALE / UNKNOWN'],['Load cell',t?.weight_g==null?'Uncalibrated / unknown':Number(t.weight_g).toFixed(2)+' g'],['Weight stable',t?.stable===true?'Stable':t?.stable===false?'Unstable':'Unknown'],['GPS',gpsText],['Clock',t?.clock_trusted===true?'Trusted':'Untrusted'],['Calibration',t?.calibrated===true?'Complete':'Incomplete'],['Commissioning',t?.actuation_verified===true?'Complete':'Locked'],['Lid interlock',t?.lid_closed===true?'Confirmed closed':t?.lid_closed===false?'Open':'UNKNOWN / NOT CONFIRMED'],['Faults',t?.faults?.length?t.faults.join(', '):(t?'None reported':'No telemetry')]];
 for(const [label,value] of fields){const box=node('div','');box.className='metric';box.append(node('span',label),node('strong',value));$('status').append(box);}
 $('updated').textContent=d?.last_seen?'Last received: '+new Date(d.last_seen*1000).toLocaleString()+' ('+(fresh?'fresh':'stale')+')':'No real device has reported yet.';
 const blockReason=dispenseBlockReason(d); $('dispenseSafety').textContent=blockReason?'DISPENSING BLOCKED: '+blockReason:'Preflight telemetry checks passed. Firmware must still enforce every interlock.'; $('dispenseSafety').className=blockReason?'safety-block':'safety-ok';
 if(!['morning','afternoon','night'].includes(document.activeElement?.id))for(const s of ['morning','afternoon','night'])$(s).value=d?.schedule[s]||'';
 const occ=t?.current_occurrences||[],old=$('occurrence').value;
 $('occurrence').replaceChildren(...occ.map(x=>{const o=node('option',x);o.value=x;return o;}));if(occ.includes(old))$('occurrence').value=old;
 const active=$('occurrence').value,attempted=history.events.some(e=>e.occurrence===active&&e.kind==='attempt');
 $('dispense').disabled=!!blockReason;
 $('snooze').disabled=!d?.online||!fresh||!active;
 const snooze=history.events.find(e=>e.occurrence===active&&e.kind==='snoozed');
 $('reminderState').textContent=attempted?'An attempt is already recorded for this occurrence.':snooze?'Last snooze until '+new Date((snooze.at+300)*1000).toLocaleTimeString():'Reminders alone never move the tray.';
 $('diagnostics').textContent=JSON.stringify(t||{status:'No telemetry received'},null,2);
 $('servos').replaceChildren();
 const ROLE={portable_flap:'Portable flap open',daily_compartment:'Daily compartment rotation',storage_360:'360° storage',dock_flap:'Dock flap open'};
 for(const sv of (t?.servos||[])){const tr=node('tr','');const cmd=sv.commanded==null?'Never commanded since boot':(sv.kind==='continuous'?sv.commanded+'% speed':sv.commanded+'° (commanded)');
  for(const v of ['Servo '+sv.n,ROLE[sv.role]||sv.role+' (unconfirmed)',sv.kind,cmd,sv.fault||'None'])tr.append(node('td',v));$('servos').append(tr);}
 if(!(t?.servos||[]).length)$('servos').append(node('tr','No servo data received.'));
 $('issues').replaceChildren(...((t?.commissioning_issues||[]).length?t.commissioning_issues.map(i=>node('li',i)):[node('li',t?'None reported by firmware.':'No telemetry received.')]));
 $('history').replaceChildren();
 for(const e of history.events){const tr=node('tr','');for(const v of [new Date(e.at*1000).toLocaleString(),e.occurrence,e.kind,e.detail])tr.append(node('td',v));const td=node('td','');
 if(e.kind==='sensor_confirmed'||e.kind==='uncertain'){const b=node('button','Record human intake report');b.onclick=()=>record(e.occurrence,'intake_report');td.append(b);}tr.append(td);$('history').append(tr);}
 for(const n of history.notes){const tr=node('tr','');for(const v of [new Date(n.at*1000).toLocaleString(),n.occurrence,n.kind,n.note,'Human report'])tr.append(node('td',v));$('history').append(tr);}
 if(!history.events.length)$('history').append(node('tr','No device events received.'));
 $('alerts').replaceChildren();
 const alertKinds=['reminder','blocked','uncertain','fault'];
 const seen=new Set();
 for(const e of history.events.filter(e=>alertKinds.includes(e.kind))){if(seen.has(e.occurrence))continue;seen.add(e.occurrence);
 if(history.notes.some(n=>n.kind==='alert_ack'&&n.occurrence===e.occurrence&&n.at>=e.at))continue;
 const a=node('div',e.kind+' · '+e.occurrence+' — '+e.detail);a.className='alert';const b=node('button','Acknowledge');b.onclick=()=>record(e.occurrence,'alert_ack');a.append(document.createElement('br'),b);$('alerts').append(a);}
 if(!$('alerts').children.length)$('alerts').append(node('p','No unacknowledged alerts received.'));
}
async function record(occurrence,kind){const note=prompt(kind==='intake_report'?'Enter your observation. This is a human report, not sensor proof of ingestion.':'Add a caregiver acknowledgement:');if(!note)return;try{await api(endpoint('notes'),'POST',{occurrence,kind,note});await refresh(false);message('Caregiver report saved.');}catch(e){message(e.message,true);}}
$('login').onsubmit=async e=>{e.preventDefault();try{message('Signing in…');token=(await api('/login','POST',{password:$('password').value})).token;$('password').value='';$('loginPanel').hidden=true;$('dashboard').hidden=false;$('logout').hidden=false;await refresh();}catch(err){message(err.message,true);}};
$('logout').onclick=async()=>{try{await api('/logout','POST',{});}finally{signout();message('Signed out.');}};
$('device').onchange=()=>{selected=$('device').value;refresh();};$('occurrence').onchange=render;$('refresh').onclick=()=>refresh();
$('pairToggle').onclick=()=>{$('pairPanel').hidden=!$('pairPanel').hidden;};
$('pair').onsubmit=async e=>{e.preventDefault();try{const result=await api('/devices','POST',{device_id:$('newId').value});$('pairResult').textContent=JSON.stringify(result,null,2)+'\nCopy this key into config.py now. It will not be shown again.';selected=result.device_id;await refresh(false);message('Registered. Waiting for the configured device to connect.');}catch(err){message(err.message,true);}};
$('schedule').onsubmit=async e=>{e.preventDefault();try{const body={};for(const s of ['morning','afternoon','night'])body[s]=$(s).value||null;await api(endpoint('schedule'),'PUT',body);message('Schedule saved on backend; awaiting device synchronization.');}catch(err){message(err.message,true);}};
async function request(type){try{if(type==='dispense'){const reason=dispenseBlockReason(current());if(reason){message('Dispense blocked: '+reason,true);render();return;}if(!confirm('Request one physical attempt for this occurrence? Use inert objects only. A mass change cannot prove ingestion.'))return;}if(type==='snooze'&&(!current()?.online||telemetryAge(current())>30))throw Error('Cannot snooze: device is offline or telemetry is stale.');await api(endpoint('commands'),'POST',{type,occurrence:$('occurrence').value});message('Command queued for up to 60 seconds. This is not confirmation of a dispense.');await refresh(false);}catch(e){message(e.message,true);}}
$('dispense').onclick=()=>request('dispense');$('snooze').onclick=()=>request('snooze');setInterval(()=>refresh(false),5000);
