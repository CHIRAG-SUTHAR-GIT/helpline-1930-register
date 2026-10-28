// Shared record operations. Production uses a D1 binding; tests use real SQLite.
export class APIError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export const ENTRY_FIELDS = ['request_id','calling_helpline','victim_name','dob','pin','mo','mobile','notice_helpline','remarks'];
export const DATABASE_FIELDS = ['id','request_id','calling_helpline','victim_name','dob','pin','recorded_at','mo','mobile','notice_helpline','remarks','created_by','remarks_version','remarks_updated_at','remarks_updated_by','helpline_version','helpline_updated_at','helpline_updated_by'];
export const HISTORY_FIELDS = ['id','entry_id','old_remarks','new_remarks','changed_at','changed_by','version'];
export const HELPLINE_HISTORY_FIELDS = ['id','entry_id','old_calling_helpline','new_calling_helpline','old_notice_helpline','new_notice_helpline','changed_at','changed_by','version'];
const HELPLINES = new Set(['','SM',...Array.from({length:20},(_,i)=>`H${i+1}`)]);
const CSV_FIELDS = [['id','Entry ID'],['calling_helpline','Calling helpline'],['victim_name','Victim name'],['dob','DOB'],['pin','PIN'],['recorded_at','Date (IST)'],['mo','MO'],['mobile','Mobile no'],['notice_helpline','Notice helpline'],['created_by','Created by'],['remarks_version','Remarks version'],['remarks_updated_at','Remarks updated at'],['remarks_updated_by','Remarks updated by'],['helpline_version','Helpline version'],['helpline_updated_at','Helpline updated at'],['helpline_updated_by','Helpline updated by'],['remarks','Remarks']];

export const nowIST = () => new Date(Date.now()+19800000).toISOString().slice(0,19)+'+05:30';
const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;

export function validateEntry(body) {
  if (!body || Array.isArray(body) || typeof body !== 'object' || Object.keys(body).some(key=>!ENTRY_FIELDS.includes(key))) throw new APIError(400,'Only the entry fields may be submitted.');
  const limits={request_id:36,calling_helpline:3,victim_name:120,dob:10,pin:80,mo:3000,mobile:25,notice_helpline:3,remarks:5000}, entry={};
  for(const [key,max] of Object.entries(limits)) {
    const value=body[key] ?? '';
    if(typeof value!=='string' || value.trim().length>max || value.includes('\0')) throw new APIError(400,`Invalid ${key.replaceAll('_',' ')}.`);
    entry[key]=value.trim();
  }
  if(!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(entry.request_id)) throw new APIError(400,'A valid submission ID is required.');
  if(entry.victim_name.length<2 || !entry.mo) throw new APIError(400,'Victim name and MO are required.');
  if(!/^\+?[0-9 ()-]+$/.test(entry.mobile) || !/^\d{10,15}$/.test(entry.mobile.replace(/\D/g,''))) throw new APIError(400,'Enter a mobile number containing 10 to 15 digits.');
  if(entry.dob && (!validDate(entry.dob) || entry.dob<'1900-01-01' || entry.dob>nowIST().slice(0,10))) throw new APIError(400,'DOB must be a valid date from 1900 through today.');
  if(!HELPLINES.has(entry.calling_helpline) || !HELPLINES.has(entry.notice_helpline)) throw new APIError(400,'Select a valid helpline.');
  return entry;
}

function checkRetry(row,entry,actor) {
  if(row.created_by!==actor || Object.keys(entry).some(key=>key!=='remarks' && entry[key]!==row[key])) throw new APIError(409,'This submission was already saved with different details. Close the form and refresh the register to verify it before adding anything else.');
  return row;
}

export async function createEntry(db,body,actor) {
  const entry=validateEntry(body);
  const columns=[...Object.keys(entry),'recorded_at','created_by'];
  const values=[...Object.values(entry),nowIST(),actor];
  const inserted=await db.prepare(`INSERT INTO entries (${columns.join(',')}) VALUES (${columns.map(()=>'?').join(',')}) ON CONFLICT(request_id) DO NOTHING RETURNING *`).bind(...values).first();
  if(inserted) return inserted;
  const existing=await db.prepare('SELECT * FROM entries WHERE request_id=?').bind(entry.request_id).first();
  if(!existing) throw new APIError(503,'Could not confirm the entry. Please retry the same submission.');
  return checkRetry(existing,entry,actor);
}

export async function updateRemark(db,id,body,actor) {
  if(!body || Array.isArray(body) || typeof body!=='object' || Object.keys(body).sort().join(',')!=='remarks,version') throw new APIError(400,'Only remarks and its version may be submitted.');
  const {remarks,version}=body;
  if(typeof remarks!=='string' || remarks.length>5000 || remarks.includes('\0') || !Number.isInteger(version) || version<0) throw new APIError(400,'Remarks must contain at most 5,000 characters and a valid version.');
  const row=await db.prepare('SELECT * FROM entries WHERE id=?').bind(id).first();
  if(!row) throw new APIError(404,'Entry not found.');
  if(row.remarks_version===version && row.remarks===remarks) return row;
  const updated=await db.prepare('UPDATE entries SET remarks=?, remarks_version=remarks_version+1, remarks_updated_at=?, remarks_updated_by=? WHERE id=? AND remarks_version=? RETURNING *').bind(remarks,nowIST(),actor,id,version).first();
  if(updated) return updated;
  const current=await db.prepare('SELECT * FROM entries WHERE id=?').bind(id).first();
  if(current.remarks_version===version+1 && current.remarks===remarks && current.remarks_updated_by===actor) return current;
  throw new APIError(409,'Someone has updated these remarks. Copy your draft, then close and reopen the editor to load the latest version.');
}

export async function updateHelplines(db,id,body,actor) {
  if(!body || Array.isArray(body) || typeof body!=='object' || Object.keys(body).sort().join(',')!=='calling_helpline,notice_helpline,version') throw new APIError(400,'Only calling helpline, notice helpline and their version may be submitted.');
  const {calling_helpline,notice_helpline,version}=body;
  if(typeof calling_helpline!=='string' || typeof notice_helpline!=='string' || !HELPLINES.has(calling_helpline) || !HELPLINES.has(notice_helpline) || !Number.isInteger(version) || version<0) throw new APIError(400,'Select a helpline from the dropdown and submit a valid version.');
  const row=await db.prepare('SELECT * FROM entries WHERE id=?').bind(id).first();
  if(!row) throw new APIError(404,'Entry not found.');
  if(row.helpline_version===version && row.calling_helpline===calling_helpline && row.notice_helpline===notice_helpline) return row;
  const updated=await db.prepare('UPDATE entries SET calling_helpline=?,notice_helpline=?,helpline_version=helpline_version+1,helpline_updated_at=?,helpline_updated_by=? WHERE id=? AND helpline_version=? RETURNING *').bind(calling_helpline,notice_helpline,nowIST(),actor,id,version).first();
  if(updated) return updated;
  const current=await db.prepare('SELECT * FROM entries WHERE id=?').bind(id).first();
  if(current.helpline_version===version+1 && current.calling_helpline===calling_helpline && current.notice_helpline===notice_helpline && current.helpline_updated_by===actor) return current;
  throw new APIError(409,'Another admin updated the helpline assignment. Refresh the register before trying again.');
}

export function buildQuery(params,paginate=true) {
  const conditions=[],values=[],search=(params.get('q')||'').trim();
  if(search.length>200) throw new APIError(400,'Search is too long.');
  if(search) {
    conditions.push('('+['victim_name','mobile','pin','mo','remarks','created_by','CAST(id AS TEXT)'].map(field=>`${field} LIKE ? ESCAPE '\\'`).join(' OR ')+')');
    const literal=search.replace(/[\\%_]/g,char=>'\\'+char);
    values.push(...Array(7).fill('%'+literal+'%'));
  }
  for(const [key,operator] of [['from','>='],['to','<=']]) {
    const value=params.get(key);
    if(value) { if(!validDate(value)) throw new APIError(400,'Invalid date filter.'); conditions.push(`substr(recorded_at,1,10) ${operator} ?`); values.push(value); }
  }
  if(params.get('from') && params.get('to') && params.get('from')>params.get('to')) throw new APIError(400,'The From date must be on or before the To date.');
  const helpline=params.get('helpline');
  if(helpline) { if(!HELPLINES.has(helpline)) throw new APIError(400,'Invalid helpline filter.'); conditions.push('(calling_helpline=? OR notice_helpline=?)'); values.push(helpline,helpline); }
  const where=conditions.length?' WHERE '+conditions.join(' AND '):'';
  const countSql='SELECT count(*) AS total FROM entries'+where;
  const countValues=[...values];
  let sql='SELECT * FROM entries'+where+' ORDER BY id DESC';
  let page=1;
  if(paginate) { page=Number(params.get('page')||1); if(!Number.isSafeInteger(page) || page<1) throw new APIError(400,'Invalid page.'); sql+=' LIMIT 50 OFFSET ?'; values.push((page-1)*50); }
  return {sql,values,countSql,countValues,page,where};
}

function statement(db,sql,values=[]) { return values.length?db.prepare(sql).bind(...values):db.prepare(sql); }

export async function listEntries(db,params) {
  const q=buildQuery(params),today=nowIST().slice(0,10);
  const [rows,count,stats]=await db.batch([
    statement(db,q.sql,q.values),statement(db,q.countSql,q.countValues),
    db.prepare('SELECT count(*) AS total_entries,coalesce(sum(substr(recorded_at,1,10)=?),0) AS today_entries FROM entries').bind(today)
  ]);
  return {entries:rows.results,total:count.results[0].total,...stats.results[0],page_size:50,storage:'hosted'};
}

export async function entryHistory(db,id) {
  const [entries,history]=await db.batch([db.prepare('SELECT * FROM entries WHERE id=?').bind(id),db.prepare('SELECT * FROM remark_history WHERE entry_id=? ORDER BY version DESC').bind(id)]);
  if(!entries.results.length) throw new APIError(404,'Entry not found.');
  return {entry:entries.results[0],history:history.results};
}

function csvCell(value) {
  let text=value==null?'':String(value);
  if(/^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text="'"+text;
  return /[",\r\n]/.test(text)?'"'+text.replaceAll('"','""')+'"':text;
}

export async function exportData(db,params) {
  const format=params.get('format')||'csv';
  if(!['csv','json','sqlite'].includes(format)) throw new APIError(400,'Select CSV, JSON, or SQLite export.');
  // SQLite is built in the browser from this full snapshot using self-hosted sql.js.
  const q=buildQuery(format==='sqlite'?new URLSearchParams():params,false);
  const historySql='SELECT * FROM remark_history WHERE entry_id IN (SELECT id FROM entries'+q.where+') ORDER BY id';
  const [rows,history,helplineHistory,schema]=await db.batch([
    statement(db,q.sql,q.values),statement(db,historySql,q.countValues),
    statement(db,'SELECT * FROM helpline_history WHERE entry_id IN (SELECT id FROM entries'+q.where+') ORDER BY id',q.countValues),
    db.prepare("SELECT type,name,sql FROM sqlite_master WHERE tbl_name IN ('entries','remark_history','helpline_history') AND sql IS NOT NULL ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END,name")
  ]);
  if(format==='csv') {
    return {body:'\ufeff'+[CSV_FIELDS.map(([,label])=>csvCell(label)).join(','),...rows.results.map(row=>CSV_FIELDS.map(([key])=>csvCell(row[key])).join(','))].join('\r\n')+'\r\n',type:'text/csv; charset=utf-8',extension:'csv'};
  }
  return {body:JSON.stringify({exported_at:nowIST(),entries:rows.results,remark_history:history.results,helpline_history:helplineHistory.results,
    ...(format==='sqlite'?{schema:schema.results.map(row=>row.sql+';').join('\n'),entry_fields:DATABASE_FIELDS,history_fields:HISTORY_FIELDS,helpline_history_fields:HELPLINE_HISTORY_FIELDS}:{})}),type:'application/json; charset=utf-8',extension:'json'};
}

async function readBody(request) {
  if(!request.headers.get('Content-Type')?.startsWith('application/json')) throw new APIError(415,'Send application/json.');
  if(Number(request.headers.get('Content-Length'))>65536) throw new APIError(413,'Request is too large.');
  const body=await request.text();
  if(new TextEncoder().encode(body).length>65536) throw new APIError(413,'Request is too large.');
  try { return JSON.parse(body); } catch { throw new APIError(400,'Invalid JSON request.'); }
}

const HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'};
const json=(data,status=200)=>Response.json(data,{status,headers:HEADERS});

export async function handleApi(request,db,actor,displayName=actor,isAdmin=false) {
  try {
    if(!db) throw new APIError(503,'The register database is temporarily unavailable. Please retry shortly.');
    const url=new URL(request.url),path=url.pathname,method=request.method;
    if(path==='/api/health' && method==='GET') {
      // No records or identity information; safe for the owner-private service check.
      const row=await db.prepare("SELECT count(*) AS locks FROM sqlite_master WHERE type='trigger' AND name IN ('entries_no_delete','entries_locked_fields','entries_audit_remark','history_no_update','history_no_delete','entries_remark_version','entries_audit_helpline','helpline_history_no_update','helpline_history_no_delete')").first();
      return json({status:row.locks===9?'ready':'not_ready',storage:'hosted-sqlite',locks:row.locks},row.locks===9?200:503);
    }
    if(!actor) throw new APIError(401,'Sign in to open your private register.');
    const origin=request.headers.get('Origin');
    if(origin && origin!==url.origin) throw new APIError(403,'This request must come from your register.');
    if(path==='/api/me' && method==='GET') return json({username:displayName,storage:'hosted',is_admin:isAdmin});
    if(path==='/api/entries' && method==='GET') return json(await listEntries(db,url.searchParams));
    if(path==='/api/entries' && method==='POST') {
      const body=await readBody(request);
      if(!isAdmin && (body?.calling_helpline || body?.notice_helpline)) throw new APIError(403,'Only an admin can assign helplines.');
      return json(await createEntry(db,body,actor),201);
    }
    let match=path.match(/^\/api\/entries\/(\d+)\/remarks$/);
    if(match && method==='PATCH') return json(await updateRemark(db,Number(match[1]),await readBody(request),actor));
    match=path.match(/^\/api\/entries\/(\d+)\/helplines$/);
    if(match && method==='PATCH') {
      if(!isAdmin) throw new APIError(403,'Only an admin can change helplines.');
      return json(await updateHelplines(db,Number(match[1]),await readBody(request),actor));
    }
    match=path.match(/^\/api\/entries\/(\d+)\/history$/);
    if(match && method==='GET') return json(await entryHistory(db,Number(match[1])));
    if(path==='/api/export' && method==='GET') {
      const file=await exportData(db,url.searchParams);
      return new Response(file.body,{headers:{...HEADERS,'Content-Type':file.type,'Content-Disposition':`attachment; filename="helpline-1930-${nowIST().slice(0,10)}.${file.extension}"`}});
    }
    if(!['GET','POST','PATCH'].includes(method) || /^\/api\/entries\/\d+$/.test(path)) throw new APIError(405,'Saved details cannot be deleted or changed. Remarks and admin helpline assignments use their dedicated actions.');
    throw new APIError(404,'Endpoint not found.');
  } catch(error) {
    if(error instanceof APIError) return json({error:error.message},error.status);
    console.error('Register database operation failed',error instanceof Error?error.message:'Unknown error');
    return json({error:'The register could not complete the request. No save was confirmed; retry the same submission safely.'},503);
  }
}
