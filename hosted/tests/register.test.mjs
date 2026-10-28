import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { randomUUID } from 'node:crypto';
import initSqlJs from 'sql.js';
import { createEntry,updateRemark,updateHelplines,entryHistory,listEntries,exportData,validateEntry,handleApi,buildQuery } from '../lib/register-core.mjs';

const migrations=fs.readdirSync(new URL('../drizzle/',import.meta.url)).filter(name=>name.endsWith('.sql')).sort();
function database(){
  const connection=new DatabaseSync(':memory:');
  connection.exec('PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON;');
  for(const file of migrations)connection.exec(fs.readFileSync(new URL('../drizzle/'+file,import.meta.url),'utf8'));
  const db={
    connection,
    prepare(sql){return this.statement(sql,[]);},
    statement(sql,args){return {
      bind(...values){return db.statement(sql,values);},
      async first(){return connection.prepare(sql).get(...args)??null;},
      async all(){return {results:connection.prepare(sql).all(...args)};},
      sql,args,
    };},
    async batch(statements){connection.exec('BEGIN');try{const results=statements.map(s=>({results:connection.prepare(s.sql).all(...s.args)}));connection.exec('COMMIT');return results;}catch(error){connection.exec('ROLLBACK');throw error;}},
    close(){connection.close();},
  };
  return db;
}
const body=(overrides={})=>({request_id:randomUUID(),calling_helpline:'H3',victim_name:'Fictional Test Person',dob:'1990-05-24',pin:'A A 382210',mo:'100% test_only',mobile:'9000000000',notice_helpline:'SM',remarks:'Initial note',...overrides});
const actor='test-operator@example.test';

test('All saved entry details are locked by the migrated SQLite triggers',async()=>{
  const db=database();try{
    await createEntry(db,body(),actor);
    for(const [field,value] of Object.entries({id:9,request_id:randomUUID(),victim_name:'Changed',dob:'1991-01-01',pin:'123',recorded_at:'1990',mo:'Changed',mobile:'9111111111',created_by:'other'})){
      assert.throws(()=>db.connection.prepare(`UPDATE entries SET ${field}=?, remarks_version=1,remarks_updated_at='today',remarks_updated_by='other' WHERE id=1`).run(value),/cannot be changed/);
    }
    assert.throws(()=>db.connection.exec('DELETE FROM entries'),/cannot be deleted/);
  }finally{db.close();}
});

test('Retries create one permanent record and detect changed details',async()=>{
  const db=database();try{const draft=body(),first=await createEntry(db,draft,actor);assert.deepEqual(await createEntry(db,draft,actor),first);assert.equal((await listEntries(db,new URLSearchParams())).total,1);await assert.rejects(createEntry(db,{...draft,victim_name:'Another person'},actor),{status:409});}finally{db.close();}
});

test('Remarks updates preserve original values, Unicode, operator and version',async()=>{
  const db=database();try{
    await createEntry(db,body(),actor);
    const updated=await updateRemark(db,1,{remarks:'ગુજરાતી નોંધ ✓',version:0},actor);
    assert.equal(updated.remarks_version,1);assert.equal(updated.victim_name,'Fictional Test Person');
    const history=await entryHistory(db,1);assert.equal(history.history[0].old_remarks,'Initial note');assert.equal(history.history[0].new_remarks,'ગુજરાતી નોંધ ✓');assert.equal(history.history[0].changed_by,actor);assert.match(history.history[0].changed_at,/\+05:30$/);
    assert.throws(()=>db.connection.exec('DELETE FROM remark_history'),/cannot be deleted/);
    assert.throws(()=>db.connection.exec("UPDATE remark_history SET new_remarks='Tampered'"),/cannot be changed/);
  }finally{db.close();}
});

test('Concurrent remark drafts conflict and safe retries do not duplicate history',async()=>{
  const db=database();try{
    await createEntry(db,body(),actor);const draft={remarks:'First editor',version:0};
    const first=await updateRemark(db,1,draft,actor);assert.deepEqual(await updateRemark(db,1,draft,actor),first);
    await assert.rejects(updateRemark(db,1,{remarks:'Second editor',version:0},'other@example.test'),{status:409});
    await updateRemark(db,1,{remarks:'First editor',version:1},actor);
    assert.equal((await entryHistory(db,1)).history.length,1);
  }finally{db.close();}
});

test('Malformed dates, mobile numbers, helplines and extra fields are rejected',()=>{
  for(const change of [{dob:'1990-02-30'},{dob:'2099-01-01'},{mobile:'123'},{mobile:'abcdefghij'},{calling_helpline:'H99'},{victim_name:'x'},{mo:''},{created_by:'forged'}])assert.throws(()=>validateEntry(body(change)),{status:400});
});

test('PATCH rejects locked fields, invalid versions and long remarks',async()=>{
  const db=database();try{
    await createEntry(db,body(),actor);
    for(const change of [{remarks:'x',version:0,victim_name:'Changed'},{remarks:'x',version:true},{remarks:'x',version:-1},{remarks:'x'.repeat(5001),version:0}])await assert.rejects(updateRemark(db,1,change,actor),{status:400});
  }finally{db.close();}
});

test('Search treats percent/underscore as literals and filters both helpline columns',async()=>{
  const db=database();try{
    await createEntry(db,body(),actor);await createEntry(db,body({mo:'Unrelated incident',calling_helpline:'H4',notice_helpline:'H5'}),actor);
    assert.equal((await listEntries(db,new URLSearchParams({q:'100%'}))).total,1);
    assert.equal((await listEntries(db,new URLSearchParams({q:'test_only'}))).total,1);
    assert.equal((await listEntries(db,new URLSearchParams({helpline:'SM'}))).total,1);
    assert.equal((await listEntries(db,new URLSearchParams({to:'2000-01-01'}))).total,0);
    assert.throws(()=>buildQuery(new URLSearchParams({from:'2026-01-03',to:'2026-01-01'})),{status:400});
  }finally{db.close();}
});

test('CSV/JSON exports include all pages, optional filters, formula protection and Unicode',async()=>{
  const db=database();try{
    for(let i=0;i<65;i++)await createEntry(db,body({victim_name:'Export Test '+i,remarks:i===0?'=1+1':'ગુજરાતી'}),actor);
    const first=await listEntries(db,new URLSearchParams());assert.equal(first.entries.length,50);assert.equal(first.total,65);
    assert.equal((await listEntries(db,new URLSearchParams({page:'2'}))).entries.length,15);
    const json=JSON.parse((await exportData(db,new URLSearchParams({format:'json'}))).body);assert.equal(json.entries.length,65);
    const csv=await exportData(db,new URLSearchParams({format:'csv'}));assert.ok(csv.body.startsWith('\ufeff'));assert.ok(csv.body.includes("'=1+1"));assert.ok(csv.body.includes('ગુજરાતી'));
    const filtered=JSON.parse((await exportData(db,new URLSearchParams({format:'json',q:'Export Test 64'}))).body);assert.equal(filtered.entries.length,1);
  }finally{db.close();}
});

test('Full SQLite download can be reconstructed with all locks and remarks history',async()=>{
  const db=database();let copy;try{
    await createEntry(db,body(),actor);await updateRemark(db,1,{remarks:'Updated Unicode નોંધ',version:0},actor);await updateHelplines(db,1,{calling_helpline:'H14',notice_helpline:'H2',version:0},actor);
    const snapshot=JSON.parse((await exportData(db,new URLSearchParams({format:'sqlite',q:'Should be ignored'}))).body);
    assert.equal(snapshot.entries.length,1);
    const SQL=await initSqlJs();copy=new SQL.Database();copy.run(snapshot.schema);copy.run('BEGIN');
    for(const [table,fields,rows] of [['entries',snapshot.entry_fields,snapshot.entries],['remark_history',snapshot.history_fields,snapshot.remark_history],['helpline_history',snapshot.helpline_history_fields,snapshot.helpline_history]]){
      const insert=copy.prepare(`INSERT INTO ${table} (${fields.join(',')}) VALUES (${fields.map(()=>'?').join(',')})`);for(const row of rows)insert.run(fields.map(field=>row[field]??null));insert.free();
    }
    copy.run('COMMIT');const bytes=copy.export();assert.equal(Buffer.from(bytes).subarray(0,16).toString(),'SQLite format 3\0');assert.equal(copy.exec('SELECT count(*) FROM remark_history')[0].values[0][0],1);assert.equal(copy.exec('SELECT count(*) FROM helpline_history')[0].values[0][0],1);assert.throws(()=>copy.run('DELETE FROM entries'),/cannot be deleted/);
  }finally{copy?.close();db.close();}
});

test('API uses authenticated identity and rejects edits, deletes and cross-origin writes',async()=>{
  const db=database();try{
    const req=(path,method='GET',data,origin)=>new Request('https://register.example'+path,{method,headers:{...(data?{'Content-Type':'application/json'}:{}),...(origin?{Origin:origin}:{})},body:data?JSON.stringify(data):undefined});
    assert.equal((await handleApi(req('/api/entries'),db,null)).status,401);
    assert.equal((await handleApi(req('/api/export?format=json'),db,null)).status,401);
    assert.equal((await handleApi(req('/api/entries','POST',body(),'https://evil.example'),db,actor)).status,403);
    assert.equal((await handleApi(req('/api/entries','POST',body({calling_helpline:'',notice_helpline:''})),db,actor)).status,201);
    for(const method of ['DELETE','PUT','PATCH'])assert.equal((await handleApi(req('/api/entries/1',method),db,actor)).status,405);
    const history=await handleApi(req('/api/entries/1/history'),db,actor);assert.equal(history.status,200);
    assert.equal((await handleApi(req('/api/health'),db,null)).status,200);
  }finally{db.close();}
});

test('Only admins can assign or change helplines and only dropdown values are accepted',async()=>{
  const db=database();try{
    const req=(path,method,data)=>new Request('https://register.example'+path,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    assert.equal((await handleApi(req('/api/entries','POST',body()),db,actor,'Operator',false)).status,403);
    assert.equal((await handleApi(req('/api/entries','POST',body()),db,actor,'Admin',true)).status,201);
    const change={calling_helpline:'H14',notice_helpline:'H2',version:0};
    assert.equal((await handleApi(req('/api/entries/1/helplines','PATCH',change),db,actor,'Operator',false)).status,403);
    assert.equal((await handleApi(req('/api/entries/1/helplines','PATCH',change),db,actor,'Admin',true)).status,200);
    assert.equal((await handleApi(req('/api/entries/1/helplines','PATCH',{...change,calling_helpline:'Custom text',version:1}),db,actor,'Admin',true)).status,400);
    assert.equal((await handleApi(req('/api/entries/1/helplines','PATCH',{...change,version:1,victim_name:'Changed'}),db,actor,'Admin',true)).status,400);
    const current=await db.prepare('SELECT * FROM entries WHERE id=1').first();assert.equal(current.calling_helpline,'H14');assert.equal(current.notice_helpline,'H2');assert.equal(current.victim_name,'Fictional Test Person');
  }finally{db.close();}
});

test('Helpline changes have their own immutable audit history and conflict version',async()=>{
  const db=database();try{
    await createEntry(db,body(),actor);const change={calling_helpline:'H14',notice_helpline:'H2',version:0};
    const result=await updateHelplines(db,1,change,actor);assert.equal(result.helpline_version,1);assert.equal(result.remarks_version,0);
    assert.deepEqual(await updateHelplines(db,1,change,actor),result);
    await assert.rejects(updateHelplines(db,1,{...change,calling_helpline:'H5'},'another-admin@example.test'),{status:409});
    const history=await db.prepare('SELECT * FROM helpline_history WHERE entry_id=1').first();assert.equal(history.old_calling_helpline,'H3');assert.equal(history.new_calling_helpline,'H14');assert.equal(history.old_notice_helpline,'SM');assert.equal(history.new_notice_helpline,'H2');assert.equal(history.changed_by,actor);
    assert.equal((await entryHistory(db,1)).history.length,0);
    await updateRemark(db,1,{remarks:'Follow-up',version:0},actor);
    assert.equal((await db.prepare('SELECT count(*) AS total FROM helpline_history').first()).total,1);
    assert.throws(()=>db.connection.exec('DELETE FROM helpline_history'),/cannot be deleted/);
    assert.throws(()=>db.connection.exec("UPDATE helpline_history SET new_calling_helpline='H5'"),/cannot be changed/);
    assert.throws(()=>db.connection.exec("UPDATE entries SET calling_helpline='H4' WHERE id=1"),/versioned/);
  }finally{db.close();}
});

test('Operator page has no API URL, password form or browser record storage',()=>{
  const html=fs.readFileSync(new URL('../ui/register.html',import.meta.url),'utf8');
  for(const banned of ['connectDialog','connectForm','apiUrl','localStorage','DEFAULT_API_URL','GITHUB_TOKEN'])assert.ok(!html.includes(banned),banned);
  new Function(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
  assert.ok(html.includes('bootstrap();'));assert.ok(html.includes("credentials:'same-origin'"));
});
