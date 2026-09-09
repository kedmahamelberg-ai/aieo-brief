(function(){'use strict';
 const config=JSON.parse(document.getElementById('brief-config').textContent),authKey='aieo-brief-auth-v1';
 let session=null,refreshing=null;
 const enabled=!!(config.community_enabled&&config.supabase_url&&config.supabase_publishable_key&&!config.is_preview);
 function stored(){try{return JSON.parse(localStorage.getItem(authKey));}catch{return null;}}
 function persist(next){session=next;try{if(next)localStorage.setItem(authKey,JSON.stringify(next));else localStorage.removeItem(authKey);}catch{};window.dispatchEvent(new CustomEvent('brief-auth',{detail:{signedIn:!!next}}));}
 function headers(token){const h={'Content-Type':'application/json','apikey':config.supabase_publishable_key};if(token)h.Authorization='Bearer '+token;else if(config.supabase_publishable_key?.startsWith('eyJ'))h.Authorization='Bearer '+config.supabase_publishable_key;return h;}
 async function request(path,body,token,method='POST'){const response=await fetch(config.supabase_url.replace(/\/$/,'')+path,{method,headers:headers(token),body:method==='GET'?undefined:JSON.stringify(body),credentials:'omit',referrerPolicy:'no-referrer'});let result;try{result=await response.json();}catch{result={};}if(!response.ok){const message=result.msg||result.message||result.error_description||'The service is unavailable. Please try again.';throw new Error(message);}return result;}
 async function access(){if(!session)return null;if((session.expires_at||0)*1000>Date.now()+60000)return session.access_token;
 if(!refreshing)refreshing=request('/auth/v1/token?grant_type=refresh_token',{refresh_token:session.refresh_token},null).then(s=>{persist({...s,expires_at:s.expires_at||Math.floor(Date.now()/1000)+s.expires_in});return s.access_token;}).catch(e=>{persist(null);throw e;}).finally(()=>{refreshing=null;});return refreshing;}
 async function rpc(name,body={}){if(!enabled)throw new Error('Community is not connected on this version. You can still read, save on this device and share.');return request('/rest/v1/rpc/'+name,body,await access());}
 async function init(){if(!enabled)return;session=stored();const hash=new URLSearchParams(location.hash.slice(1));
 if(hash.has('access_token')){const token=hash.get('access_token'),refresh=hash.get('refresh_token');history.replaceState(null,'',location.pathname+location.search);try{const user=await request('/auth/v1/user',undefined,token,'GET');persist({access_token:token,refresh_token:refresh,expires_at:Math.floor(Date.now()/1000)+Number(hash.get('expires_in')||3600),user});}catch(e){persist(null);throw e;}}
 else if(hash.has('error_description')){const err=hash.get('error_description');history.replaceState(null,'',location.pathname+location.search);throw new Error(err);}
 else if(session){try{await access();const user=await request('/auth/v1/user',undefined,session.access_token,'GET');session.user=user;persist(session);}catch{persist(null);}}
 }
 async function signIn(email){if(!enabled)throw new Error('Sign-in is temporarily unavailable. Please try again shortly.');const redirect=config.site_url.replace(/\/$/,'')+'/account/';if(!redirect.startsWith('https://'))throw new Error('The live Brief URL is needed for email sign-in.');return request('/auth/v1/otp?redirect_to='+encodeURIComponent(redirect),{email,create_user:true},null);}
 async function signOut(){try{if(session)await request('/auth/v1/logout',{},await access());}finally{persist(null);}}
 async function metrics(keys){let all={};for(let n=0;n<keys.length;n+=200)Object.assign(all,await rpc('brief_community_metrics',{p_keys:keys.slice(n,n+200)}));return all;}
 window.BriefCommunity={enabled,init,rpc,metrics,signIn,signOut,signedIn:()=>!!session,user:()=>session?.user||null};
})();
