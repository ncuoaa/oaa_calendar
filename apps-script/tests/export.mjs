import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

for (const name of ['apps-script/Index.html', 'static/availability.html']) {
  const elements = new Map();
  const element = () => ({value:'', disabled:false, style:{}, children:[],
    append(...children){this.children.push(...children)},
    replaceChildren(...children){this.children=children},
    addEventListener(){}});
  const document = {querySelector(selector){
    if(!elements.has(selector)) elements.set(selector,element());
    return elements.get(selector);
  }, querySelectorAll:()=>[], createElement:element, createTextNode:text=>({textContent:text})};
  const context = vm.createContext({document, Intl, Date, Number, Math, Promise,
    sessionStorage:{getItem:()=>null,removeItem(){}}, setTimeout});
  const html = fs.readFileSync(name,'utf8');
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
  const rows=[{date:'2026-11-18',weekday:'三',slots:['08:00–10:00','14:00–17:00'],
    accounts:[{title:'測試主管甲',email:'one@example.com'},{title:'測試主管乙',email:'two@example.com'}],note:'不應匯出此備註'}];
  const csv=context.buildResultsCsv(rows);
  assert.equal(csv,'\uFEFF"日期","星期","共同空檔","比對帳號"\r\n"2026/11/18","週三","08:00–10:00, 14:00–17:00","one@example.com, two@example.com"\r\n');
  const quoted=context.buildResultsCsv([{...rows[0],accounts:[{email:'name"quoted@example.com'}]}]);
  assert.ok(quoted.includes('"name""quoted@example.com"'));
  const button=elements.get('#downloadResults');
  assert.equal(button.disabled,true,'No download before a successful query');
  context.renderRows(rows);assert.equal(button.disabled,false);
  context.markPending();assert.equal(button.disabled,true,'Changed criteria must invalidate export');
  context.renderRows(rows);context.showError('Calendar read failed');assert.equal(button.disabled,true);
  context.renderRows([]);assert.equal(button.disabled,true,'No empty result download');
  context.renderRows(rows);context.showLogin();assert.equal(button.disabled,true,'Sign-out clears exported results');
  console.log(`${name}: CSV fields, comma-separated intervals/accounts, quoting, UTF-8 BOM, and result lifecycle passed.`);
}
