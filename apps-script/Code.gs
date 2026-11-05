function doGet() {
  const template = HtmlService.createTemplateFromFile('Index');
  template.appTitle = DEFAULT_CONFIG_.title;
  const page = template.evaluate().setTitle(DEFAULT_CONFIG_.title);
  // Optional Google Sites embedding; leave off for the standalone trial.
  if (PropertiesService.getScriptProperties().getProperty('ENABLE_SITES_EMBED') === 'true') {
    page.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  }
  return page;
}

function error_(code, message) {
  const error = new Error(message);
  error.publicCode = code;
  return error;
}

function result_(callback) {
  try { return callback(); }
  catch (error) {
    if (!error.publicCode) console.error('Operation failed: ' + (error.name || 'Error'));
    return {status:'error',code:error.publicCode || 500,message:error.publicCode ? error.message : '服務暫時無法完成查詢，請稍後再試。'};
  }
}

function bytes_(text) {
  return new Uint8Array(Utilities.newBlob(text).getBytes().map(function(value) {return value & 255;}));
}

function digest_(text) { return LoginCrypto.bytesToHex(LoginCrypto.sha256(bytes_(text))); }

function equal_(a, b) {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let i=0;i<a.length;i++) mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return mismatch === 0;
}

function credentials_() {
  const properties = PropertiesService.getScriptProperties();
  const username = properties.getProperty('WEB_USERNAME');
  const hash = properties.getProperty('WEB_PASSWORD_HASH');
  if (!username || !hash) throw error_(503,'管理者尚未設定查詢帳號密碼。');
  return {username:username,hash:hash,version:digest_(username+'\n'+hash)};
}

function verifyPassword_(password, encoded) {
  const parts = encoded.split('$');
  if (parts.length !== 4 || parts[0] !== 'pbkdf2_sha256' || parts[1] !== '600000' || !/^[0-9a-f]{32}$/.test(parts[2]) || !/^[0-9a-f]{64}$/.test(parts[3])) {
    throw error_(503,'網站帳密設定格式錯誤，請管理者檢查。');
  }
  const actual = LoginCrypto.pbkdf2(LoginCrypto.sha256,bytes_(password),LoginCrypto.hexToBytes(parts[2]),{c:600000,dkLen:32});
  return equal_(LoginCrypto.bytesToHex(actual),parts[3]);
}

function limitLogin_() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(3000)) throw error_(429,'登入服務忙碌，請稍後再試。');
  try {
    const properties = PropertiesService.getScriptProperties();
    const bucket = Math.floor(Date.now()/60000);
    let rate;
    try { rate = JSON.parse(properties.getProperty('LOGIN_RATE') || '{}'); } catch (_) { rate={}; }
    if (rate.bucket !== bucket) rate = {bucket:bucket,count:0};
    if (rate.count >= 20) throw error_(429,'登入次數過多，請一分鐘後再試。');
    rate.count++;
    properties.setProperty('LOGIN_RATE',JSON.stringify(rate));
  } finally { lock.releaseLock(); }
}

function apiLogin(input) {
  return result_(function() {
    const settings = credentials_();
    if (!input || typeof input.username !== 'string' || typeof input.password !== 'string' || !input.username || input.username.length > 100 || !input.password || input.password.length > 256) {
      throw error_(400,'請輸入帳號及密碼。');
    }
    limitLogin_();
    const passwordOk = verifyPassword_(input.password,settings.hash);
    if (!equal_(digest_(input.username),digest_(settings.username)) || !passwordOk) throw error_(401,'帳號或密碼錯誤。');
    const lock = LockService.getScriptLock();
    if (!lock.tryLock(3000)) throw error_(429,'登入服務忙碌，請稍後再試。');
    const token = Utilities.getUuid().replace(/-/g,'') + Utilities.getUuid().replace(/-/g,'');
    try {
      const properties = PropertiesService.getScriptProperties();
      const all = properties.getProperties();
      let active = 0;
      Object.keys(all).filter(function(key) {return key.indexOf('SESSION_') === 0;}).forEach(function(key) {
        let saved;
        try { saved = JSON.parse(all[key]); } catch (_) { saved={}; }
        if (!saved.expires || saved.expires <= Date.now() || saved.version !== settings.version) properties.deleteProperty(key);
        else active++;
      });
      if (active >= 200) throw error_(503,'目前登入人數已滿，請稍後再試。');
      properties.setProperty('SESSION_'+digest_(token),JSON.stringify({expires:Date.now()+DEFAULT_CONFIG_.sessionHours*3600000,version:settings.version}));
    } finally { lock.releaseLock(); }
    return {status:'success',token:token,config:clientConfig_()};
  });
}

function requireSession_(token) {
  if (typeof token !== 'string' || !/^[0-9a-f]{64}$/i.test(token)) throw error_(401,'請先登入後再查詢。');
  const settings = credentials_();
  const properties = PropertiesService.getScriptProperties();
  const key = 'SESSION_'+digest_(token);
  let session;
  try {session=JSON.parse(properties.getProperty(key) || '{}');} catch (_) {session={};}
  if (!session.expires || session.expires <= Date.now() || session.version !== settings.version) {
    properties.deleteProperty(key);
    throw error_(401,'登入已過期，請重新登入。');
  }
  return key;
}

function apiSession(input) {
  return result_(function() {
    requireSession_(input && input.token);
    return {status:'success',config:clientConfig_()};
  });
}

function apiLogout(input) {
  return result_(function() {
    const key = requireSession_(input && input.token);
    PropertiesService.getScriptProperties().deleteProperty(key);
    return {status:'success'};
  });
}

function validDate_(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(value+'T00:00:00Z');
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0,10) === value;
}

function nextDate_(value) {
  const parsed = new Date(value+'T00:00:00Z');
  parsed.setUTCDate(parsed.getUTCDate()+1);
  return parsed.toISOString().slice(0,10);
}

function minute_(value) { const pieces=value.split(':').map(Number);return pieces[0]*60+pieces[1]; }
function clock_(minute) {return String(Math.floor(minute/60)).padStart(2,'0')+':'+String(minute%60).padStart(2,'0');}

function criteria_(input) {
  const people = new Map(DEFAULT_CONFIG_.people.map(function(person){return [person.id,person];}));
  if (!input || !Array.isArray(input.selected) || input.selected.length < 1 || input.selected.length > people.size || new Set(input.selected).size !== input.selected.length || input.selected.some(function(id){return !people.has(id);})) throw error_(400,'請選擇有效的主管。');
  if (!validDate_(input.dateStart) || !validDate_(input.dateEnd) || input.dateStart > input.dateEnd || input.dateEnd >= '9999-12-31') throw error_(400,'請確認查詢日期。');
  const rangeDays = (Date.parse(input.dateEnd+'T00:00:00Z')-Date.parse(input.dateStart+'T00:00:00Z'))/86400000+1;
  if (rangeDays > DEFAULT_CONFIG_.maxRangeDays) throw error_(400,'單次查詢最多 '+DEFAULT_CONFIG_.maxRangeDays+' 天，請分段查詢。');
  const pattern=/^(?:[01]\d|2[0-3]):[0-5]\d$/;
  if (typeof input.dailyStart !== 'string' || typeof input.dailyEnd !== 'string' || !pattern.test(input.dailyStart) || !pattern.test(input.dailyEnd) || input.dailyStart >= input.dailyEnd || !Number.isInteger(input.minimumMinutes) || input.minimumMinutes < 30 || input.minimumMinutes > 1440 || typeof input.workdays !== 'boolean' || typeof input.holidays !== 'boolean' || (!input.workdays && !input.holidays)) throw error_(400,'請確認每日時段、空檔長度與日期類型。');
  return {input:input,accounts:input.selected.map(function(id){return people.get(id);})};
}

function queryBusy_(criteria) {
  let response;
  try {
    response = Calendar.Freebusy.query({timeMin:criteria.input.dateStart+'T00:00:00+08:00',timeMax:nextDate_(criteria.input.dateEnd)+'T00:00:00+08:00',timeZone:DEFAULT_CONFIG_.timeZone,items:criteria.accounts.map(function(person){return {id:person.calendarId};})});
  } catch (_) {throw error_(502,'Google Calendar 無法提供忙碌資料，請管理者檢查授權或使用額度。');}
  if (!response || !response.calendars) throw error_(502,'Google Calendar 沒有回傳有效資料。');
  const windows=[];
  criteria.accounts.forEach(function(person) {
    const calendar=response.calendars[person.calendarId];
    if (!calendar || (calendar.errors && calendar.errors.length) || !Array.isArray(calendar.busy)) throw error_(424,'無法讀取'+person.title+'的日曆，請確認分享權限；未將讀取失敗視為空檔。');
    calendar.busy.forEach(function(window) {
      const start=Date.parse(window.start),end=Date.parse(window.end);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || !/(?:Z|[+-]\d{2}:\d{2})$/.test(window.start) || !/(?:Z|[+-]\d{2}:\d{2})$/.test(window.end)) throw error_(502,'Google Calendar 回傳的時段格式無效。');
      windows.push([start,end]);
    });
  });
  return windows;
}

function rows_(criteria,windows) {
  const input=criteria.input, workStart=minute_(input.dailyStart), workEnd=minute_(input.dailyEnd);
  const holidays=new Set(DEFAULT_CONFIG_.holidayDates),labels=['日','一','二','三','四','五','六'];
  const accounts=criteria.accounts.map(function(person){return {title:person.title,email:person.email};});
  const rows=[];
  for(let date=input.dateStart;date<=input.dateEnd;date=nextDate_(date)) {
    const day=new Date(date+'T00:00:00Z').getUTCDay();
    const holiday=day===0 || day===6 || holidays.has(date);
    if (!(input.holidays && holiday) && !(input.workdays && !holiday)) continue;
    const midnight=Date.parse(date+'T00:00:00+08:00');
    const busy=windows.filter(function(window){return window[1]>midnight+workStart*60000 && window[0]<midnight+workEnd*60000;}).map(function(window){return [Math.max(workStart,Math.floor((window[0]-midnight)/60000)),Math.min(workEnd,Math.ceil((window[1]-midnight)/60000))];}).sort(function(a,b){return a[0]-b[0];});
    let cursor=workStart;
    const slots=[];
    busy.forEach(function(window) {
      if(window[0]-cursor>=input.minimumMinutes) slots.push(clock_(cursor)+'–'+clock_(window[0]));
      cursor=Math.max(cursor,window[1]);
    });
    if(workEnd-cursor>=input.minimumMinutes) slots.push(clock_(cursor)+'–'+clock_(workEnd));
    if(slots.length) rows.push({date:date,weekday:labels[day],slots:slots,accounts:accounts,note:'已即時比對 '+accounts.length+' 個共享行事曆；僅查忙碌／空閒'});
  }
  return rows;
}

function apiAvailability(input) {
  return result_(function() {
    requireSession_(input && input.token);
    const criteria=criteria_(input.criteria);
    const rows=rows_(criteria,queryBusy_(criteria));
    return {status:'success',rows:rows,count:rows.length};
  });
}

// Editor-only diagnostics: private helpers cannot be called through google.script.run.
function authorizeAndCheckCalendars_() {
  const today=Utilities.formatDate(new Date(),DEFAULT_CONFIG_.timeZone,'yyyy-MM-dd');
  const criteria=criteria_({selected:DEFAULT_CONFIG_.people.map(function(person){return person.id;}),dateStart:today,dateEnd:today,dailyStart:'08:00',dailyEnd:'17:00',minimumMinutes:240,workdays:true,holidays:true});
  queryBusy_(criteria);
  console.log('Calendar permissions checked: '+criteria.accounts.length+' calendars.');
}
