// ======================= DotCoin long video: the scene library (engine v2, 2026-11-17) =======================
// A shot = {type, p:{...}, si (its sentence), t0, d, cam, tr, bgk}. Each scene draws one full frame at its local
// time tl (0..d). Words of the shot's sentence come in when they are spoken (sw(k) = the k-th word's time, local).
const SCN={};
function swords(sh){const s=CHD.sent[sh.si];return s?s.words:[];}
function wloc(sh,k){const ws=swords(sh);const w=ws[Math.min(k,ws.length-1)];return w?w.s-sh.t0:0;}
// the time (local to the shot) a word containing `sub` is spoken (else frac of the shot)
function wsub(sh,sub,frac=0.3){if(sub==null)return sh.d*frac;const ws=swords(sh);const n=x=>String(x).replace(/‌/g,'').replace(/[؟?:،؛.!«»]/g,'');for(const w of ws){if(n(w.w).includes(n(sub)))return Math.max(0,w.s-sh.t0);}return sh.d*frac;}
// big kinetic words: each word slams in at its spoken time (or staggered), key words on a chip
function slamWords(sh,tl,text,key,cx,cy,size,maxw,col,chipBg,chipFg,opt={}){const f=opt.f||'YKE';const {lines,sp}=layoutWords(text,key,size,f,maxw);const lh=size*(opt.lh||1.22);const y0=cy-(lines.length-1)*lh/2;let k=0;
 const synced=opt.sync&&swords(sh).length>=text.split(' ').length;let wi=0;
 lines.forEach((ln,li)=>{const tot=ln.reduce((s,it)=>s+it.w,0)+sp*(ln.length-1);let xr=cx+tot/2;const yy=y0+li*lh;
  ln.forEach(it=>{const nW=it.s.split(' ').length;const at=synced?wloc(sh,wi)-0.08:(opt.t0||0)+k*(opt.stag||0.09);wi+=nW;const p=pr(tl,at,0.28);if(p<=0){xr-=it.w+sp;k++;return;}
   const sc=lerp(opt.from||1.8,1,eback(p,1.2));X.save();X.translate(xr-it.w/2,yy);X.scale(sc,sc);X.globalAlpha*=clamp(p*3);
   if(it.key){const h=size*1.32;rr(-it.w/2,-h/2,it.w,h,h*0.16);X.fillStyle=chipBg;X.fill();T(it.s,0,0,size,f,chipFg,'center');}else T(it.s,0,0,size,f,col,'center');
   X.restore();xr-=it.w+sp;k++;});});}
function chipIn(tl,at,s,x,y,size,fg,bg,align='center',dir='rtl',f='YKE'){const p=eback(pr(tl,at,0.35));if(p<=0)return;X.save();X.translate(x,y);X.scale(p,p);X.translate(-x,-y);chip(s,x,y,size,f,fg,bg,align,dir);X.restore();}
function kicker(tl,s,x,y,dark=true){const p=eo(pr(tl,0.05,0.4));if(p<=0)return;X.save();X.globalAlpha=p;X.fillStyle=MU;X.fillRect(x-6,y-22,6,44);T(s,x-22,y,30,'YKB',dark?'rgba(255,255,255,0.85)':'rgba(0,0,0,0.75)','right');X.restore();}

// 1. hook: the cold open: giant words on black, one key on mustard, a pulsing accent
SCN.hook=function(tl,d,sh){const p=sh.p;bgPulse(tl);slamWords(sh,tl,p.text,p.key,W/2,H/2-(p.sub?40:0),p.size||118,1500,WH,MU,BK,{sync:p.sync===true,t0:-0.25,stag:0.11});
 if(p.sub){const q=eo(pr(tl,p.subAt!=null?p.subAt:d*0.55,0.5));if(q>0){X.save();X.globalAlpha=q;T(p.sub,W/2,H/2+170,44,'YKB','rgba(255,255,255,0.8)','center');X.restore();}}};
function bgPulse(tl){const r=0.5+0.5*Math.sin(tl*2.2);for(let i=0;i<3;i++){circle(W/2,H/2,380+i*150+r*20,null,`rgba(243,194,66,${0.07-i*0.02})`,2);}}
// 2. kinetic: full-screen kinetic typography (any background), line by line, optional big ghost word
SCN.kinetic=function(tl,d,sh){const p=sh.p;const dark=(sh.bgk||'black')==='black'||sh.bgk==='content';
 if(p.ghost){X.save();X.font=font(360,'ANT');X.textAlign='center';X.textBaseline='middle';X.direction='ltr';X.fillStyle=dark?'rgba(255,255,255,0.05)':'rgba(0,0,0,0.07)';X.fillText(p.ghost,W/2+(tl*18)%40-20,H/2+20);X.restore();}
 if(p.kicker)kicker(tl,p.kicker,W-150,190,dark);
 slamWords(sh,tl,p.text,p.key,W/2,H/2,p.size||96,1560,dark?WH:BK,dark?MU:BK,dark?BK:MU,{sync:p.sync!==false});};
// 3. bignumber: a number that rolls in, its unit and a label; optional bar of scale
SCN.bignumber=function(tl,d,sh){const p=sh.p;const dark=(sh.bgk||'black')!=='mustard'&&sh.bgk!=='paper';const col=dark?WH:BK;
 const at=Math.min(wsub(sh,p.at,0.15),0.35);const u=eo(pr(tl,at,p.roll||1.1));const v=p.value*u;const txt=p.text?(u>0.98?p.text:fa(Math.round(v))):(p.decimals?fa(v.toFixed(p.decimals)).replace('.','٫'):sep(Math.round(v)));
 if(u<=0&&!p.pre)return;X.save();const sc=lerp(1.25,1,eback(pr(tl,at,0.5)));X.translate(W/2,H/2-30);X.scale(sc,sc);
 T(txt,0,0,p.size||260,'YKE',p.col||(dark?MU:BK),'center');X.restore();
 if(p.unit){const q=eo(pr(tl,at+0.4,0.4));X.save();X.globalAlpha=q;T(p.unit,W/2,H/2+140,58,'YKK',col,'center');X.restore();}
 if(p.label){const q=eo(pr(tl,at+0.7,0.4));X.save();X.globalAlpha=q;chip(p.label,W/2,H/2+250,36,'YKB',dark?BK:MU,dark?MU:BK,'center');X.restore();}};
// 4. digits: a flood of random digits (a huge random number), a window that freezes on part of it
SCN.digits=function(tl,d,sh){const p=sh.p;const r=rng(7);const cols=48,rows=14;const cw=W/cols,chh=H/rows;X.font=font(34,'YLB');X.textAlign='center';X.textBaseline='middle';X.direction='ltr';
 const fr=Math.floor(tl*12);for(let j=0;j<rows;j++)for(let i=0;i<cols;i++){const rr2=rng(i*131+j*977+fr*7);const dgt=Math.floor(rr2()*10);const hot=Math.abs(j-rows/2)<1.5;X.fillStyle=hot?`rgba(243,194,66,${0.5+0.5*rr2()})`:`rgba(255,255,255,${0.06+0.14*rr2()})`;X.fillText(String(dgt),i*cw+cw/2,j*chh+chh/2);}
 const q=eo(pr(tl,Math.min(wsub(sh,p.at,0.4),0.6),0.5));if(q>0){X.save();X.globalAlpha=q;rr(W/2-520,H/2-90,1040,180,20);X.fillStyle='rgba(0,0,0,0.85)';X.fill();X.lineWidth=4;X.strokeStyle=MU;X.stroke();T(p.label||'',W/2,H/2,64,'YKE',WH,'center');X.restore();}};
// 5. zoom: a card (a key, a block, a transaction) seen whole, then the camera dives into one field with a callout
SCN.zoom=function(tl,d,sh){const p=sh.p;const at=wsub(sh,p.at,0.45);const z=eio(pr(tl,at,0.9));const f=p.fields||[];const fi=p.focus||0;
 const cx=W/2,cy=H/2;const cw=1100,ch=140+f.length*92;const fy=cy-ch/2+130+fi*92;
 X.save();const s=lerp(1,p.zoom||1.6,z);const fx=cx-125;X.translate(cx,cy);X.scale(s,s);X.translate(-lerp(cx,fx,z),-lerp(cy,fy,z));
 tile(cx-cw/2,cy-ch/2,cw,ch,WH,BK,26,0.25);X.fillStyle=BK;X.fillRect(cx-cw/2,cy-ch/2,cw,70);T(p.title||'',cx+cw/2-30,cy-ch/2+36,32,'YKK',MU,'right');circle(cx-cw/2+40,cy-ch/2+36,10,MU);
 f.forEach((fl,i)=>{const y=cy-ch/2+130+i*92;const q=eo(pr(tl,0.15+i*0.12,0.4));X.save();X.globalAlpha*=q;T(fl.k,cx+cw/2-40,y,30,'YKB','rgba(0,0,0,0.55)','right');
  rr(cx-cw/2+40,y-28,cw-330,56,10);X.fillStyle=i===fi?'rgba(243,194,66,0.35)':'#F1F1F4';X.fill();TL(fl.v,cx-cw/2+60,y,fl.v.length>40?24:30,'YLB',BK);X.restore();});X.restore();
 if(z>0.6&&p.callout){const q=eback(pr(tl,at+0.7,0.45));X.save();X.translate(W/2,H-170);X.scale(q,q);chip(p.callout,0,0,44,'YKE',BK,MU,'center');X.restore();}};
// 6. words: the 12 (or 24) word tiles flipping in on a grid
SCN.words=function(tl,d,sh){const p=sh.p;const ws=p.words||[];const n=ws.length;const cols=p.cols||4;const rows=Math.ceil(n/cols);const tw2=360,th=110,gx=28,gy=28;
 const x0=W/2+(cols*tw2+(cols-1)*gx)/2,y0=H/2-(rows*th+(rows-1)*gy)/2+(p.title?50:0);if(p.title)kicker(tl,p.title,W-170,150);
 ws.forEach((w,i)=>{const c=i%cols,r2=Math.floor(i/cols);const x=x0-(c+1)*tw2-c*gx,y=y0+r2*(th+gy);const at=(p.t0!=null?p.t0:0.2)+i*(p.stag||0.12);const q=pr(tl,at,0.4);if(q<=0)return;
  const flip=Math.cos((1-eo(q))*Math.PI/2);X.save();X.translate(x+tw2/2,y+th/2);X.scale(1,Math.max(0.02,flip));tile(-tw2/2,-th/2,tw2,th,i%4===0?MU:WH,BK,14,0.22);
  T(fa(i+1),tw2/2-24,0,30,'YKE','rgba(0,0,0,0.45)','right');TL(w,-tw2/2+28,0,44,'YLK',BK,'left');X.restore();});};
// 7. grid: a big set of cells (a word list of 2048, a block's slots) with highlights picked one by one
SCN.grid=function(tl,d,sh){const p=sh.p;const n=p.n||2048;const cols=p.cols||64;const rows=Math.ceil(n/cols);const cs=Math.min((W-200)/cols,(H-300)/rows);const x0=W/2-cols*cs/2,y0=H/2-rows*cs/2+60;
 const fill=eo(pr(tl,0.1,1.0));const m=Math.floor(n*fill);X.fillStyle='rgba(255,255,255,0.16)';for(let i=0;i<m;i++){const c=i%cols,r2=Math.floor(i/cols);X.fillRect(x0+c*cs+1,y0+r2*cs+1,cs-2,cs-2);}
 const picks=p.picks||12;const r=rng(p.seed||11);for(let k=0;k<picks;k++){const i=Math.floor(r()*n);const at=wsub(sh,p.at,0.45)+k*0.12;const q=eback(pr(tl,at,0.35));if(q<=0)continue;const c=i%cols,r2=Math.floor(i/cols);const x=x0+c*cs+cs/2,y=y0+r2*cs+cs/2;
  X.fillStyle=MU;X.fillRect(x-cs/2*q*1.4,y-cs/2*q*1.4,cs*q*1.4,cs*q*1.4);if(k<4)circle(x,y,cs*2.2*q,null,'rgba(243,194,66,0.5)',2);}
 if(p.big){const q=eback(pr(tl,0.2,0.6));X.save();X.translate(W/2,170);X.scale(q,q);T(p.big,0,0,96,'YKE',MU,'center');X.restore();}
 if(p.label){const q=eo(pr(tl,0.6,0.4));X.save();X.globalAlpha=q;T(p.label,W/2,H-90,40,'YKB',WH,'center');X.restore();}};
// 8. split: two sides, slid in, each with an icon and lines; the middle sign («=», «≠», «vs»)
SCN.split=function(tl,d,sh){const p=sh.p;const L=p.right||{},R=p.left||{};// reading order: right first
 const a=eo(pr(tl,0.05,0.5)),b=eo(pr(tl,wsub(sh,p.at,0.35),0.5));
 const side=(o,x0,q,col,fg)=>{if(q<=0)return;X.save();X.globalAlpha=q;X.translate((1-q)*(x0>W/2?220:-220),0);tile(x0-400,170,800,740,col,BK,30,0.25);
  if(o.icon)ICON(o.icon,x0,380,150,fg);T(o.title||'',x0,560,60,'YKE',fg,'center');(o.lines||[]).forEach((l,i)=>T(l,x0,650+i*62,36,'YKB',fg,'center'));if(o.chip)chip(o.chip,x0,840,34,'YKE',col===MU?MU:BK,col===MU?BK:MU,'center');X.restore();};
 side(L,W*0.74,a,L.col||WH,BK);side(R,W*0.26,b,R.col||MU,BK);
 // the words travel from the right card to the left one (the same 12 words open the other wallet)
 if(p.flow&&b>0.5){const fl=p.flow;fl.forEach((w,i)=>{const f=((tl-wsub(sh,p.at,0.35))*0.45+i/fl.length)%1;if(f<0)return;const x=lerp(W*0.74-200,W*0.26+200,eio(f)),y=540-Math.sin(f*Math.PI)*260;
   X.save();X.globalAlpha=Math.sin(f*Math.PI);chip(w,x,y,26,'YLB',BK,MU,'center','ltr');X.restore();});}
 if(p.sign){const q=eback(pr(tl,wsub(sh,p.at,0.35)+0.3,0.4));X.save();X.translate(W/2,540);X.scale(q,q);circle(0,0,70,BK,MU,6);TL(p.sign,0,4,64,'ANT',MU,'center');X.restore();}};
// 9. ui: a phone with an app (a wallet, an exchange) that the hand uses: rows, a tap, a toast
SCN.ui=function(tl,d,sh){const p=sh.p;const cx=p.x||W/2,cy=540;const q=eback(pr(tl,0.05,0.6));X.save();X.translate(cx,cy+(1-q)*400);X.rotate(lerp(-0.08,0,q));
 rr(-250,-470,500,940,64);X.fillStyle='#0B0B0F';X.fill();rr(-226,-446,452,892,46);X.fillStyle=p.dark?'#15161C':WH;X.fill();const fg=p.dark?WH:BK;
 rr(-60,-430,120,26,13);X.fillStyle='#0B0B0F';X.fill();T(p.title||'',200,-360,40,'YKE',fg,'right');if(p.sub)T(p.sub,200,-310,26,'YKB',p.dark?'rgba(255,255,255,0.6)':'rgba(0,0,0,0.55)','right');
 if(p.balance!=null){const bal=p.drain?lerp(p.balance,0,eio(pr(tl,wsub(sh,p.drainAt,0.5),1.2))):p.balance;T(p.balancePre||'',190,-220,30,'YKB',fg,'right');TL((p.unit||'')+' '+bal.toFixed(p.dec||2),-190,-150,64,'YLK',p.drain&&bal<p.balance*0.5?RED:fg,'left');}
 (p.rows||[]).forEach((r,i)=>{const at=0.3+i*0.15;const qq=eo(pr(tl,at,0.35));X.save();X.globalAlpha=qq;const y=-40+i*110;rr(-196,y,392,90,18);X.fillStyle=p.dark?'#22232C':'#F2F2F5';X.fill();circle(150,y+45,24,r.col||MU);T(r.t,110,y+32,28,'YKK',fg,'right');if(r.s)T(r.s,110,y+64,22,'YKR',p.dark?'rgba(255,255,255,0.55)':'rgba(0,0,0,0.5)','right');if(r.v)TL(r.v,-176,y+45,28,'YLB',r.vcol||fg);X.restore();});
 if(p.tap!=null){const at=wsub(sh,p.tapAt,0.55);const y=-40+p.tap*110+45;const qq=pr(tl,at-0.6,0.6);if(qq>0&&qq<1.6){const hx=lerp(260,0,eio(qq)),hy=lerp(500,y,eio(qq));hand(hx,hy+40,1);}if(tl>at){const r=pr(tl,at,0.6);circle(0,y,30+r*120,null,`rgba(243,194,66,${1-r})`,6);}}
 if(p.toast){const at=wsub(sh,p.toastAt,0.75);const qq=eback(pr(tl,at,0.4));if(qq>0){X.save();X.translate(0,340);X.scale(qq,qq);rr(-200,-50,400,100,24);X.fillStyle=p.toastCol||RED;X.fill();T(p.toast,0,0,32,'YKE',WH,'center');X.restore();}}
 X.restore();
 if(p.side){const qq=eo(pr(tl,0.5,0.5));X.save();X.globalAlpha=qq;slamWords(sh,tl,p.side,p.sideKey,cx<W/2?W*0.72:W*0.28,540,72,700,(sh.bgk==='mustard'||sh.bgk==='paper')?BK:WH,MU,BK,{t0:0.5});X.restore();}};
function hand(x,y,s){X.save();X.translate(x,y);X.scale(s,s);X.fillStyle='#E7B98F';X.strokeStyle=BK;X.lineWidth=4;X.beginPath();X.moveTo(-10,-60);X.quadraticCurveTo(-12,-80,0,-82);X.quadraticCurveTo(12,-80,10,-60);X.lineTo(14,-10);X.quadraticCurveTo(40,-14,46,10);X.lineTo(50,70);X.quadraticCurveTo(30,110,-10,110);X.quadraticCurveTo(-46,100,-50,60);X.lineTo(-48,0);X.quadraticCurveTo(-30,-12,-14,-6);X.closePath();X.fill();X.stroke();X.restore();}
// 10. still: a full-bleed AI picture with parallax (the picture slow, a dark grade, the words over it)
SCN.still=function(tl,d,sh){const p=sh.p;const u=tl/Math.max(1,d);const k=p.img;
 if(p.frame&&IMG[k]){// a small source picture: framed at its own size (never blown up soft), the frame drifting
  const fw=1180,fh=Math.round(fw*IMG[k].height/IMG[k].width);const q=eback(pr(tl,0,0.5));X.save();X.translate(W/2+lerp(40,-40,u),H/2-60+lerp(10,-10,u));X.scale(q,q);X.rotate(lerp(-0.02,0.01,u));
  tile(-fw/2-14,-fh/2-14,fw+28,fh+28,BK,null,18,0.35);X.save();rr(-fw/2,-fh/2,fw,fh,10);X.clip();imgCover(k,0,0,fw,fh,lerp(1.0,1.08,u));X.restore();X.restore();
  if(p.text)slamWords(sh,tl,p.text,p.key,W/2,H-150,p.size||70,1500,(sh.bgk==='mustard'||sh.bgk==='paper')?BK:WH,(sh.bgk==='mustard')?BK:MU,(sh.bgk==='mustard')?MU:BK,{t0:p.t0||0.5,from:1.3});return;}
 if(!IMG[k]){bg('content',tl);}else{X.save();const s=lerp(1.08,1.18,u);imgCover(k,W/2+lerp(30,-30,u)*(p.dir||1),H/2+lerp(10,-10,u),W,H,s);X.restore();}
 const g=X.createLinearGradient(0,H*0.45,0,H);g.addColorStop(0,'rgba(0,0,0,0)');g.addColorStop(1,'rgba(0,0,0,0.78)');X.fillStyle=g;X.fillRect(0,0,W,H);
 if(p.text){slamWords(sh,tl,p.text,p.key,W/2,H-210,p.size||76,1500,WH,MU,BK,{t0:p.t0||0.4,from:1.3});}};
// 11. teaser: «coming up»: three or four tiles, a quick cut between them, a progress tick
SCN.teaser=function(tl,d,sh){const p=sh.p;const it=p.items||[];const n=it.length;kicker(tl,p.title||'توی این ویدیو',W-150,150);
 it.forEach((o,i)=>{const at=Math.min(wsub(sh,o.at,0.12+i*0.2),0.25+i*0.9);const q=eback(pr(tl,at,0.45));if(q<=0)return;const cw=(W-240-(n-1)*30)/n;const x=W-120-(i+1)*cw-i*30;
  X.save();X.translate(x+cw/2,560);X.scale(q,q);X.rotate((i%2?1:-1)*0.015);tile(-cw/2,-300,cw,600,i%2?WH:MU,BK,26,0.3);
  T(fa(String(i+1).padStart(2,'0')),cw/2-30,-240,64,'YKE','rgba(0,0,0,0.25)','right');if(o.icon)ICON(o.icon,0,-40,150,BK);
  const {lines}=layoutWords(o.t,'',40,'YKE',cw-60);lines.forEach((ln,li)=>T(ln.map(x2=>x2.s).join(' '),0,150+li*54,40,'YKE',BK,'center'));X.restore();});};
// 12. chapter: the chapter card as a re-hook (number, title, the question it answers)
SCN.chapter=function(tl,d,sh){const p=sh.p;const q=eo(pr(tl,0,0.5));X.save();X.font=font(300,'ANT');X.textAlign='center';X.textBaseline='middle';X.direction='ltr';X.lineWidth=4;X.strokeStyle='rgba(0,0,0,0.85)';X.strokeText(p.en||'',W/2+(1-q)*160-tl*30,760);X.restore();
 X.fillStyle=BK;X.fillRect(120,520,lerp(0,W-240,eo(pr(tl,0.1,0.7))),8);
 const g=eback(pr(tl,0,0.5));X.save();X.translate(W-150,330);X.scale(g,g);T(fa(String(p.n).padStart(2,'0')),0,0,300,'YKE',BK,'right');X.restore();
 X.save();X.globalAlpha=eo(pr(tl,0.25,0.4));T(p.title||'',W-590,300,100,'YKE',BK,'right');X.restore();
 if(p.hook){X.save();X.globalAlpha=eo(pr(tl,0.6,0.4));chip(p.hook,W-590,430,40,'YKK',MU,BK,'right');X.restore();}};
// 13. cliff: the chapter's end: a cliffhanger line, a heartbeat, a cut to black
SCN.cliff=function(tl,d,sh){const p=sh.p;const beat=Math.max(0,Math.sin(tl*7))**8;X.fillStyle=`rgba(243,194,66,${0.06+beat*0.06})`;X.fillRect(0,0,W,H);
 slamWords(sh,tl,p.text,p.key,W/2,H/2-30,p.size||84,1500,WH,MU,BK,{sync:true});
 if(p.tease){const q=eo(pr(tl,d-1.6,0.5));X.save();X.globalAlpha=q*(1-pr(tl,d-0.3,0.3));chip(p.tease,W/2,H/2+170,34,'YKB',BK,MU,'center');X.restore();}};
// 14. network: nodes in a field, packets flowing along the links, one route highlighted
SCN.network=function(tl,d,sh){const p=sh.p;const r=rng(p.seed||5);const n=p.n||26;const pts=[];for(let i=0;i<n;i++)pts.push([200+r()*(W-400),200+r()*(H-360)]);
 const q=eo(pr(tl,0.05,0.8));const edges=[];for(let i=0;i<n;i++){let best=[],ds=[];for(let j=0;j<n;j++)if(j!==i)ds.push([Math.hypot(pts[i][0]-pts[j][0],pts[i][1]-pts[j][1]),j]);ds.sort((a,b)=>a[0]-b[0]);ds.slice(0,2).forEach(([_,j])=>{if(i<j)edges.push([i,j]);});}
 X.save();X.globalAlpha=q;edges.forEach(([i,j])=>line(pts[i][0],pts[i][1],pts[j][0],pts[j][1],'rgba(255,255,255,0.18)',2));
 edges.forEach(([i,j],k)=>{const f=((tl*0.6+k*0.137)%1);circle(lerp(pts[i][0],pts[j][0],f),lerp(pts[i][1],pts[j][1],f),7,PAL.b);});
 // one route lit up, hop by hop: the words reach a wallet anywhere
 const route=[0];for(let h=0;h<6;h++){const last=route[route.length-1];const nx=edges.filter(e=>e.includes(last)).map(e=>e[0]===last?e[1]:e[0]).find(v=>!route.includes(v));if(nx==null)break;route.push(nx);}
 const lit=clamp((tl-0.3)/Math.max(0.5,d*0.7))*(route.length-1);for(let h=0;h<route.length-1;h++){const f=clamp(lit-h);if(f<=0)break;const a2=pts[route[h]],b2=pts[route[h+1]];line(a2[0],a2[1],lerp(a2[0],b2[0],f),lerp(a2[1],b2[1],f),MU,7);}
 pts.forEach((pt,i)=>{const on=route.indexOf(i)>=0&&route.indexOf(i)<=lit+0.01;circle(pt[0],pt[1],i===0?34:on?26:18,i===0||on?MU:PAL.a,on?BK:WH,4);if(on)ICON('wallet',pt[0],pt[1],30,BK);});X.restore();
 if(p.label){chipIn(tl,wsub(sh,p.at,0.4),p.label,W/2,H-110,42,BK,MU);}};
// 15. chart: bars that build (or a line), the meaning colours for up/down, a highlighted bar
SCN.chart=function(tl,d,sh){const p=sh.p;const it=p.items||[];const n=it.length;const x0=260,x1=W-260,y0=860,hmax=520;const mx=Math.max(...it.map(o=>o.v));
 X.fillStyle='rgba(255,255,255,0.4)';X.fillRect(x0,y0,x1-x0,4);if(p.title)kicker(tl,p.title,W-150,150);
 it.forEach((o,i)=>{const bw=(x1-x0)/n*0.6;const x=x1-(i+0.5)*(x1-x0)/n;const q=eo(pr(tl,0.2+i*0.15,0.7));const h=hmax*o.v/mx*q;
  rr(x-bw/2,y0-h,bw,h,8);X.fillStyle=o.col||(i===p.hi?MU:PAL.b);X.fill();if(q>0.5){T(o.s||fa(o.v),x,y0-h-40,40,'YKE',WH,'center');T(o.l,x,y0+44,30,'YKB','rgba(255,255,255,0.8)','center');}});};
// 16. timeline: a track with years, a playhead that scrubs from event to event
SCN.timeline=function(tl,d,sh){const p=sh.p;const ev=p.events||[];const x0=1720,x1=200,y=600;line(x0,y,x1,y,'rgba(255,255,255,0.5)',4);
 const head=lerp(x0,x1,eio(clamp(tl/(d*0.9))));ev.forEach((e,i)=>{const x=lerp(x0,x1,(i+0.5)/ev.length);const on=head<=x+4;circle(x,y,on?16:10,on?MU:'#444',WH,3);T(e.y,x,y+60,40,'YKE',on?MU:'rgba(255,255,255,0.5)','center');
  if(on){const q=eback(pr(head===x?tl:tl,0,0.01));X.save();X.translate(x,y-120);tile(-180,-70,360,140,i%2?WH:MU,BK,18,0.3);T(e.t,0,0,32,'YKE',BK,'center');X.restore();}});
 X.fillStyle=MU;X.fillRect(head-3,y-40,6,80);};
// 17. wipe: before / after, a vertical edge sweeping across
SCN.wipe=function(tl,d,sh){const p=sh.p;const u=eio(pr(tl,wsub(sh,p.at,0.35),1.0));const xe=lerp(W,0,u);
 const pane=(o,col,fg)=>{X.fillStyle=col;X.fillRect(0,0,W,H);if(o.icon)ICON(o.icon,W/2,420,220,fg);T(o.title||'',W/2,650,72,'YKE',fg,'center');if(o.line)T(o.line,W/2,740,38,'YKB',fg,'center');};
 pane(p.before||{},'#141418',WH);X.save();X.beginPath();X.rect(xe,0,W-xe,H);X.clip();pane(p.after||{},MU,BK);X.restore();X.fillStyle=WH;X.fillRect(xe-4,0,8,H);circle(xe,H/2,34,WH,BK,4);arrow(xe-6,H/2,xe-24,H/2,1,BK,4,10);arrow(xe+6,H/2,xe+24,H/2,1,BK,4,10);};
// 18. character: an anonymous figure with a feeling (a question, an idea, a worry), and a thought
SCN.character=function(tl,d,sh){const p=sh.p;const q=eback(pr(tl,0.05,0.5));X.save();X.translate(W*0.3,640);X.scale(q,q);circle(0,-60,230,PAL.a);person(0,60,330,BK);X.restore();
 const m=p.mood||'question';const bq=eback(pr(tl,0.45,0.4));X.save();X.translate(W*0.3+170,250);X.scale(bq,bq);
 if(m==='idea'){circle(0,0,70,MU,BK,5);line(-22,90,22,90,BK,8);}else if(m==='worry'){T('!',0,0,150,'YKE',RED,'center');}else{T('؟',0,0,160,'YKE',MU,'center');}X.restore();
 if(p.text)slamWords(sh,tl,p.text,p.key,W*0.7,540,80,800,(sh.bgk==='paper'||sh.bgk==='mustard')?BK:WH,MU,BK,{t0:0.4});};
// 19. list: numbered points, one at a time, the current one big
SCN.list=function(tl,d,sh){const p=sh.p;const it=p.items||[];const dark=sh.bgk!=='mustard'&&sh.bgk!=='paper';if(p.title)kicker(tl,p.title,W-150,150,dark);
 it.forEach((s,i)=>{const at=wsub(sh,s.at,0.1+i*0.22);const q=eo(pr(tl,at,0.4));if(q<=0)return;const y=300+i*130;X.save();X.globalAlpha=q;X.translate((1-q)*-60,0);
  X.fillStyle=MU;X.fillRect(W-260,y-48,96,96);T(fa(i+1),W-212,y,64,'YKE',BK,'center');T(s.t,W-300,y,58,'YKE',dark?WH:BK,'right');X.restore();});};
// 20. iso: an isometric object under a camera push (a chain of blocks, a vault, a stack of coins)
SCN.iso=function(tl,d,sh){const p=sh.p;const o={x:W/2,y:620,u:p.u||70};const what=p.obj||'chain';
 if(what==='chain'){for(let i=0;i<5;i++){const q=eback(pr(tl,0.1+i*0.12,0.5));if(q<=0)continue;const x=-7+i*3;X.save();const c=P(o,x+1,1,1);X.translate(c[0],c[1]);X.scale(q,q);X.translate(-c[0],-c[1]);cube(o,x,0,0,2,i===4?MU:PAL.b);X.restore();if(i>0)line(...P(o,x-1,1,1),...P(o,x,1,1),BK,6);}}
 else if(what==='vault'){box(o,-2.5,-2.5,0,5,5,4,['#2E3046','#43465E','#5C5F7A']);const c=P(o,0,2.5,2);circle(c[0]-40,c[1]+10,70,MU,BK,5);X.save();X.translate(c[0]-40,c[1]+10);X.rotate(tl*1.5);for(let i=0;i<3;i++){X.rotate(2.09);X.fillStyle=BK;X.fillRect(-5,-60,10,40);}X.restore();}
 else if(what==='coins'){for(let i=0;i<12;i++){const q=eo(pr(tl,0.1+i*0.08,0.3));if(q<=0)continue;const c=P(o,0,0,i*0.28+(1-q)*3);X.beginPath();X.ellipse(c[0],c[1],110,42,0,0,6.2832);X.fillStyle=i%2?MU:'#F7D46A';X.fill();X.lineWidth=3;X.strokeStyle=BK;X.stroke();}}
 if(p.label)chipIn(tl,wsub(sh,p.at,0.4),p.label,W/2,980,42,BK,MU);};
// 21. define: a term and its one-line meaning, typed out, the term on a chip
SCN.define=function(tl,d,sh){const p=sh.p;const dark=sh.bgk!=='mustard'&&sh.bgk!=='paper';chipIn(tl,0.1,p.term,W/2,330,84,dark?BK:MU,dark?MU:BK);
 if(p.en){const q=eo(pr(tl,0.4,0.4));X.save();X.globalAlpha=q;TL(p.en,W/2,450,46,'YLB',dark?'rgba(255,255,255,0.7)':'rgba(0,0,0,0.6)','center');X.restore();}
 const full=p.def||'';const n=Math.floor(full.length*eo(pr(tl,0.7,Math.max(1,d*0.6))));const {lines}=layoutWords(full.slice(0,n),'',54,'YKB',1400);lines.forEach((ln,i)=>T(ln.map(x=>x.s).join(' '),W/2,600+i*80,54,'YKB',dark?WH:BK,'center'));};
// icons drawn in the brand (no logos)
function ICON(k,x,y,s,col){X.save();X.translate(x,y);X.lineWidth=s*0.06;X.strokeStyle=col;X.fillStyle=col;
 if(k==='key'){circle(-s*0.25,0,s*0.22,null,col,s*0.07);X.fillRect(-s*0.05,-s*0.04,s*0.6,s*0.08);X.fillRect(s*0.35,0,s*0.07,s*0.18);X.fillRect(s*0.47,0,s*0.07,s*0.13);}
 else if(k==='lock'){X.beginPath();X.arc(0,-s*0.12,s*0.24,Math.PI,0);X.stroke();rr(-s*0.35,-s*0.12,s*0.7,s*0.5,s*0.08);X.fill();}
 else if(k==='phone'){rr(-s*0.24,-s*0.42,s*0.48,s*0.84,s*0.08);X.stroke();X.fillRect(-s*0.06,s*0.3,s*0.12,s*0.04);}
 else if(k==='paper'){rr(-s*0.3,-s*0.4,s*0.6,s*0.8,s*0.04);X.stroke();for(let i=0;i<4;i++)X.fillRect(-s*0.2,-s*0.22+i*s*0.14,s*0.4,s*0.05);}
 else if(k==='wallet'){rr(-s*0.42,-s*0.28,s*0.84,s*0.56,s*0.08);X.stroke();rr(s*0.1,-s*0.1,s*0.3,s*0.2,s*0.05);X.fill();}
 else if(k==='eye'){X.beginPath();X.ellipse(0,0,s*0.42,s*0.22,0,0,6.2832);X.stroke();circle(0,0,s*0.1,col);}
 else if(k==='warn'){X.beginPath();X.moveTo(0,-s*0.38);X.lineTo(s*0.4,s*0.32);X.lineTo(-s*0.4,s*0.32);X.closePath();X.stroke();X.fillRect(-s*0.03,-s*0.12,s*0.06,s*0.24);X.fillRect(-s*0.03,s*0.18,s*0.06,s*0.06);}
 else if(k==='globe'){circle(0,0,s*0.38,null,col,s*0.05);X.beginPath();X.ellipse(0,0,s*0.16,s*0.38,0,0,6.2832);X.stroke();line(-s*0.38,0,s*0.38,0,col,s*0.05);}
 else if(k==='dice'){rr(-s*0.32,-s*0.32,s*0.64,s*0.64,s*0.1);X.stroke();[[-1,-1],[1,1],[0,0],[1,-1],[-1,1]].forEach(([a,b])=>circle(a*s*0.15,b*s*0.15,s*0.05,col));}
 X.restore();}
