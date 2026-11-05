import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const values=new Map();
const properties={getProperty:key=>values.get(key) ?? null,setProperty:(key,value)=>values.set(key,value),deleteProperty:key=>values.delete(key),getProperties:()=>Object.fromEntries(values)};
let calendarCalls=0;
let upstream;
const context=vm.createContext({
  console,
  Utilities:{newBlob:text=>({getBytes:()=>[...Buffer.from(text,'utf8')]}),getUuid:()=>crypto.randomUUID()},
  PropertiesService:{getScriptProperties:()=>properties},
  LockService:{getScriptLock:()=>({tryLock:()=>true,releaseLock:()=>{}})},
  Calendar:{Freebusy:{query:()=>{calendarCalls++;return upstream;}}},
});
// The VM deliberately has no TextEncoder, Buffer, Web Crypto, or Node require.
for(const file of ['Crypto.gs','Config.gs','Code.gs'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context,{filename:file});
const password='test-only-'+crypto.randomUUID()+'密碼';
const salt=crypto.randomBytes(16);
const encoded='pbkdf2_sha256$600000$'+salt.toString('hex')+'$'+crypto.pbkdf2Sync(password,salt,600000,32,'sha256').toString('hex');
values.set('WEB_USERNAME','test-only-user');values.set('WEB_PASSWORD_HASH',encoded);
const started=Date.now();
assert.equal(context.verifyPassword_(password,encoded),true,'Python-compatible UTF-8 PBKDF2');
assert.equal(context.apiLogin({username:'test-only-user',password:'incorrect'}).code,401);
const login=context.apiLogin({username:'test-only-user',password});
assert.equal(login.status,'success');assert.equal(login.config.people.length,6);
const token=login.token;
assert.equal(context.apiSession({token}).status,'success');
assert.equal(context.apiAvailability({token:'invalid',criteria:{}}).code,401);
assert.equal(calendarCalls,0,'Unauthenticated calls must not read Calendar');
const base={selected:['dean','deputy'],dateStart:'2026-12-01',dateEnd:'2026-12-01',dailyStart:'08:00',dailyEnd:'17:00',minimumMinutes:240,workdays:true,holidays:false};
upstream={calendars:{'deanoaa2018@gmail.com':{busy:[{start:'2026-12-01T00:00:00Z',end:'2026-12-01T02:00:00Z'}]},'oaancu2017@gmail.com':{busy:[{start:'2026-12-01T09:00:00+08:00',end:'2026-12-01T13:00:00+08:00'}]}}};
let response=context.apiAvailability({token,criteria:base});
assert.equal(response.status,'success');assert.deepEqual([...response.rows[0].slots],['13:00–17:00']);
assert.equal(response.rows[0].accounts.length,2);
upstream.calendars['oaancu2017@gmail.com']={errors:[{reason:'notFound'}]};
assert.equal(context.apiAvailability({token,criteria:base}).code,424,'Calendar errors must fail closed');
delete upstream.calendars['oaancu2017@gmail.com'];
assert.equal(context.apiAvailability({token,criteria:base}).code,424,'Missing calendars must fail closed');
upstream.calendars['oaancu2017@gmail.com']={busy:[]};
assert.equal(context.apiAvailability({token,criteria:{...base,selected:['unknown']}}).code,400);
assert.equal(context.apiAvailability({token,criteria:{...base,dateStart:'2026-02-30'}}).code,400);
assert.equal(context.apiAvailability({token,criteria:{...base,dateEnd:'2028-12-31'}}).code,400);
assert.equal(context.apiAvailability({token,criteria:{...base,minimumMinutes:240.1}}).code,400);
let criteria=context.criteria_({...base,dateStart:'2026-12-25',dateEnd:'2026-12-26'});
assert.equal(context.rows_(criteria,[]).length,0,'Known holiday/weekend excluded');
criteria=context.criteria_({...base,dateStart:'2026-12-25',dateEnd:'2026-12-26',workdays:false,holidays:true});
assert.equal(context.rows_(criteria,[]).length,2,'Holiday option includes known holiday/weekend');
criteria=context.criteria_(base);
const registrarCriteria=context.criteria_({...base,selected:['registrar'],dateStart:'2026-12-03',dateEnd:'2026-12-03',minimumMinutes:180});
assert.equal(registrarCriteria.accounts[0].calendarId,'uk56hs13bgj775u2s9n8gf0i9k@group.calendar.google.com');
assert.deepEqual([...context.rows_(registrarCriteria,[['2026-12-03T10:00:00+08:00','2026-12-03T12:00:00+08:00'],['2026-12-03T15:00:00+08:00','2026-12-03T18:00:00+08:00']].map(w=>w.map(Date.parse)))[0].slots],['12:00–15:00'],'Registrar shared-calendar regression');
assert.equal(context.rows_(criteria,[[Date.parse('2026-11-30T22:00:00Z'),Date.parse('2026-12-01T01:00:00Z')],[Date.parse('2026-12-01T05:00:00Z'),Date.parse('2026-12-01T10:00:00Z')]])[0].slots[0],'09:00–13:00');
assert.equal(context.apiLogout({token}).status,'success');assert.equal(context.apiSession({token}).code,401);
const expiring=context.apiLogin({username:'test-only-user',password});
const key='SESSION_'+context.digest_(expiring.token);values.set(key,JSON.stringify({expires:0,version:context.credentials_().version}));
assert.equal(context.apiSession({token:expiring.token}).code,401,'Expired sessions rejected');
values.set('LOGIN_RATE',JSON.stringify({bucket:Math.floor(Date.now()/60000),count:20}));
assert.equal(context.apiLogin({username:'test-only-user',password}).code,429);
values.delete('WEB_PASSWORD_HASH');assert.equal(context.apiLogin({username:'test-only-user',password}).code,503);
const html=fs.readFileSync(path.join(root,'Index.html'),'utf8');
new Function(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
assert.ok(!html.includes('fetch('),'Trial UI must use Apps Script RPC, not local API');
assert.ok(!html.includes('deanoaa2018@gmail.com'),'Calendar targets live only in server config');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'appsscript.json'),'utf8'));
assert.deepEqual(manifest.oauthScopes,['https://www.googleapis.com/auth/calendar.events.freebusy']);
console.log('Apps Script local checks passed: password compatibility, login/logout/expiry, rate limits, authorization, time zones, merged intervals, holidays, date validation, and inaccessible calendars.');
console.log('Local test duration: '+((Date.now()-started)/1000).toFixed(1)+'s. Hosted authorization and Calendar reads remain to be checked.');
