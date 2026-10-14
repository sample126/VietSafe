const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
let JSDOM;
try { ({JSDOM}=require('jsdom')); } catch {} // optional smoke test dependency
const root=path.resolve(__dirname,'../..');
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');

test('shell provides map, login and community-report dialogs',{skip: !JSDOM && 'Install jsdom with npm install'},()=>{
  const dom=new JSDOM(html,{url:'http://localhost:8765/'});
  const doc=dom.window.document;
  for(const id of ['map','login-dialog','register-dialog','report-dialog','toast']){
    assert.ok(doc.getElementById(id),`missing #${id}`);
  }
  assert.ok(doc.querySelector('script[type="module"][src="/js/main.js"]'));
  assert.ok(doc.querySelector('link[href="/css/style.css"]'));
  assert.ok(doc.querySelector('script[src="/vendor/leaflet.js"]'));
  assert.ok(!html.includes('vietsafe2026'),'do not advertise nonexistent demo credentials');
});

test('all local stylesheet/script URLs in HTML resolve to files',{skip: !JSDOM && 'Install jsdom with npm install'},()=>{
  const doc=new JSDOM(html).window.document;
  for(const element of doc.querySelectorAll('script[src],link[href]')){
    const link=element.getAttribute('src')||element.getAttribute('href');
    if(link.startsWith('/')){
      assert.ok(fs.existsSync(path.join(root,'frontend',link)),`missing asset ${link}`);
    }
  }
});
