/* LeakTrace QA harness: stand-in for supabase-js v2.
   Implements only what the LeakTrace pages call. Every request goes to the local
   harness server (same origin), never to supabase.co. */
(function(){
  const API = '/mock';
  const STORE_KEY = 'sb-mock-auth-token';
  const listeners = new Set();
  let session = null;

  function loadSession(){
    try{ const s = JSON.parse(localStorage.getItem(STORE_KEY) || 'null'); return s; }catch(e){ return null; }
  }
  function saveSession(s){
    session = s;
    try{ s ? localStorage.setItem(STORE_KEY, JSON.stringify(s)) : localStorage.removeItem(STORE_KEY); }catch(e){}
  }
  function emit(event, s){
    listeners.forEach(cb=>{ try{ cb(event, s); }catch(e){ console.error(e); } });
  }
  async function call(path, body, method){
    const headers = { 'Content-Type':'application/json' };
    if(session) headers.Authorization = 'Bearer ' + session.access_token;
    const res = await fetch(API + path, { method: method || 'POST', headers, body: JSON.stringify(body || {}) });
    let j = {};
    try{ j = await res.json(); }catch(e){}
    if(j.error){
      const e = new Error(j.error.message); e.code = j.error.code; e.status = res.status;
      return { data: null, error: e };
    }
    return { data: j.data === undefined ? null : j.data, error: null };
  }

  /* --- auth initialisation: read tokens from a link (#access_token=...) like detectSessionInUrl --- */
  const ready = (async ()=>{
    session = loadSession();
    const hash = window.location.hash || '';
    if(hash.indexOf('access_token=') >= 0){
      const p = new URLSearchParams(hash.slice(1));
      const r = await call('/auth/session', { access_token: p.get('access_token'), refresh_token: p.get('refresh_token'), type: p.get('type') });
      if(r.data && r.data.session){
        saveSession(r.data.session);
        const ev = p.get('type') === 'recovery' ? 'PASSWORD_RECOVERY' : 'SIGNED_IN';
        try{ history.replaceState(null, '', window.location.pathname + window.location.search); }catch(e){}
        setTimeout(()=>emit(ev, session), 0);
      }
    }
  })();

  class Query {
    constructor(table){ this.q = { table, op:'select', filters:[], order:[] }; this._mode = null; }
    select(cols){
      if(this.q.op === 'select') this.q.columns = cols || '*';
      else this.q.select = cols || '*';
      return this;
    }
    insert(values){ this.q.op = 'insert'; this.q.values = values; return this; }
    upsert(values, opts){ this.q.op = 'upsert'; this.q.values = values; this.q.onConflict = opts && opts.onConflict; return this; }
    update(values){ this.q.op = 'update'; this.q.values = values; return this; }
    delete(){ this.q.op = 'delete'; return this; }
    eq(col, val){ this.q.filters.push({ op:'eq', col, val }); return this; }
    order(col, opts){ this.q.order.push([col, !(opts && opts.ascending === false)]); return this; }
    limit(n){ this.q.limit = n; return this; }
    single(){ this._mode = 'single'; return this; }
    maybeSingle(){ this._mode = 'maybe'; return this; }
    async _run(){
      await ready;
      const r = await call('/rest', this.q);
      if(r.error || !this._mode) return r;
      const rows = Array.isArray(r.data) ? r.data : [];
      if(rows.length > 1){
        const e = new Error('JSON object requested, multiple (or no) rows returned'); e.code = 'PGRST116';
        return { data:null, error:e };
      }
      if(rows.length === 0 && this._mode === 'single'){
        const e = new Error('JSON object requested, multiple (or no) rows returned'); e.code = 'PGRST116';
        return { data:null, error:e };
      }
      return { data: rows[0] || null, error:null };
    }
    then(res, rej){ return this._run().then(res, rej); }
    catch(rej){ return this._run().catch(rej); }
  }

  function createClient(){
    const auth = {
      async getSession(){ await ready; return { data:{ session }, error:null }; },
      async getUser(){ await ready; return { data:{ user: session ? session.user : null }, error:null }; },
      onAuthStateChange(cb){
        listeners.add(cb);
        ready.then(()=>setTimeout(()=>{ try{ cb('INITIAL_SESSION', session); }catch(e){} }, 0));
        return { data:{ subscription:{ unsubscribe(){ listeners.delete(cb); } } } };
      },
      async signUp(args){
        await ready;
        const r = await call('/auth/signup', args);
        if(r.data && r.data.session){ saveSession(r.data.session); emit('SIGNED_IN', session); }
        return r.error ? { data:{ user:null, session:null }, error:r.error } : r;
      },
      async signInWithPassword(args){
        await ready;
        const r = await call('/auth/password', args);
        if(r.data && r.data.session){ saveSession(r.data.session); emit('SIGNED_IN', session); }
        return r.error ? { data:{ user:null, session:null }, error:r.error } : r;
      },
      async signInWithOtp(args){ await ready; return call('/auth/otp', args); },
      async resetPasswordForEmail(email, opts){ await ready; return call('/auth/recover', { email, options: opts || {} }); },
      async updateUser(attrs){
        await ready;
        const r = await call('/auth/user', attrs);
        if(r.data && r.data.user && session){ session.user = r.data.user; saveSession(session); emit('USER_UPDATED', session); }
        return r;
      },
      async signOut(){
        await ready;
        await call('/auth/logout', {});
        saveSession(null);
        emit('SIGNED_OUT', null);
        return { error:null };
      }
    };

    const storage = {
      from(bucket){
        return {
          async upload(path, file, opts){
            await ready;
            const headers = { 'Content-Type': (opts && opts.contentType) || file.type || 'application/octet-stream' };
            if(session) headers.Authorization = 'Bearer ' + session.access_token;
            const url = API + '/storage/upload/' + encodeURIComponent(bucket) + '/' + path.split('/').map(encodeURIComponent).join('/') + '?upsert=' + !!(opts && opts.upsert);
            const res = await fetch(url, { method:'PUT', headers, body:file });
            const j = await res.json().catch(()=>({}));
            if(j.error){ const e = new Error(j.error.message); e.statusCode = j.error.statusCode; return { data:null, error:e }; }
            return { data:j.data, error:null };
          },
          async remove(paths){ await ready; return call('/storage/remove', { bucket, paths }); },
          async createSignedUrl(path, expires){ await ready; return call('/storage/sign', { bucket, path, expires }); }
        };
      }
    };

    return {
      auth,
      storage,
      from(table){ return new Query(table); },
      async rpc(name, args){ await ready; return call('/rpc/' + name, args || {}); }
    };
  }

  window.supabase = { createClient };
  window.__LEAKTRACE_MOCK__ = true;
})();
