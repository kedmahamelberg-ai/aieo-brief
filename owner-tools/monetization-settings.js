(function(root){'use strict';
 function create(v){const out={schema_version:'aieo_brief_monetization_v1'};
 if(v.update_ads){if(!/^ca-pub-\d{16}$/.test(v.publisher_id||''))throw Error('Enter your AdSense publisher ID.');
 const active=v.stage!=='verify';if(active&&(!v.approved||!v.cmp))throw Error('Confirm site approval and a published Google consent message first.');
 const slots={};for(const k of ['feed','rail','story']){slots[k]=(v[k]||'').trim();if(slots[k]&&!/^\d{1,20}$/.test(slots[k]))throw Error('Ad-unit IDs must contain only digits.');}
 if(!['verify','auto','placements'].includes(v.stage))throw Error('Choose an advertising stage.');
 if(v.stage==='placements'&&!Object.values(slots).some(Boolean))throw Error('Add at least one ad-unit ID.');
 out.adsense={publisher_id:v.publisher_id,enabled:active,cmp_enabled:active&&!!v.cmp,mode:v.stage==='placements'?'placements':'auto',slots};}
 if(v.update_support){const value=(v.support_url||'').trim();if(value){const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||/[\s<>]/.test(value))throw Error('Use a complete HTTPS support link.');}out.support_url=value;}
 if(v.update_sponsor){const enabled=!!v.sponsor_enabled;const sponsor={enabled,name:(v.sponsor_name||'').trim(),message:(v.sponsor_message||'').trim(),url:(v.sponsor_url||'').trim(),starts:v.sponsor_starts||'',ends:v.sponsor_ends||''};
 if(enabled){if(!sponsor.name||!sponsor.message||sponsor.name.length>100||sponsor.message.length>180)throw Error('Add a sponsor name and concise message.');const u=new URL(sponsor.url);if(u.protocol!=='https:'||u.username||u.password||/[\s<>]/.test(sponsor.url))throw Error('Use the sponsor’s HTTPS destination.');for(const day of [sponsor.starts,sponsor.ends])if(!/^\d{4}-\d{2}-\d{2}$/.test(day)||Number.isNaN(Date.parse(day))||new Date(day).toISOString().slice(0,10)!==day)throw Error('Add valid campaign dates.');if(sponsor.ends<sponsor.starts)throw Error('The end must follow the start.');}out.sponsor=sponsor;}
 if(Object.keys(out).length===1)throw Error('Select advertising, sponsorship or reader support to update.');return out;}
 if(typeof module==='object')module.exports={create};else root.BriefMonetization={create};
})(globalThis);
