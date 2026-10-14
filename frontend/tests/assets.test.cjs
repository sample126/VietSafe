/** Static smoke test with no external dependencies; validates ES module import graph. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const frontend=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(frontend,'index.html'),'utf8');

test('local HTML CSS, JS and favicon assets exist',()=>{
  for(const match of html.matchAll(/(?:src|href)=["'](\/[^"']+)["']/g)){
    const url=match[1];
    if(url.startsWith('/api/'))continue;
    assert.ok(fs.existsSync(path.join(frontend,url)),`Missing referenced asset ${url}`);
  }
});

test('all relative ES module import files resolve',()=>{
  const jsRoot=path.join(frontend,'js');
  let count=0;
  const walk=dir=>{
    for(const item of fs.readdirSync(dir,{withFileTypes:true})){
      const file=path.join(dir,item.name);
      if(item.isDirectory())walk(file);
      else if(file.endsWith('.js')){
        count++;
        const content=fs.readFileSync(file,'utf8');
        for(const match of content.matchAll(/\bimport\s+(?:[\s\S]*?\s+from\s+)?["'](\.[^"']+)["']/g)){
          assert.ok(fs.existsSync(path.resolve(path.dirname(file),match[1])),`Missing import ${match[1]} in ${item.name}`);
        }
      }
    }
  };
  walk(jsRoot);
  assert.ok(count>=5,'ES module tree unexpectedly small');
});

test('HTML references only the new ES module entrypoint',()=>{
  assert.match(html,/<script\s+type="module"\s+src="\/js\/main\.js"/);
  assert.ok(!html.includes('src="/app.js"'));
});
