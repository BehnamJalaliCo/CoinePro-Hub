/* ======================= TOON — animation layer (owner's rule 2026-11-13: animation + motion graphics together in every scene) =======================
   «پرو», a flat two-colour trader with a headset, acts out every sentence on top of the motion graphics: he lands on the replay bar,
   pulls the playhead back, walks candle by candle, hides his eyes from the future, meets a blind-folded script robot, presses the keys,
   referees the strict SL/TP call, slips on the past (soft landing), types the comment, catches the link and walks the risk rope.
   Only #000 and #D4A64A (+ alpha shades). Lip-sync from the approved voice envelope (DATA.vol, 60 per second). */
const VOL=DATA.vol||[];
function vol(t){const i=Math.max(0,t*60),a=Math.floor(i),f=i-a;return (VOL[a]||0)*(1-f)+(VOL[a+1]||0)*f;}
const W8=(n,i)=>L[n][i].s;
// hand targets from the shoulder: [out, down] (out>0 = away from the body)
const HP={idle:[16,108],wave:[50,-98],pu:[80,-78],pr:[112,-4],pd:[84,72],think:[-36,-24],cover:[-32,-60],shrug:[60,14],up:[34,-106],
  present:[96,-50],self:[-46,34],shh:[-42,-38],top:[8,-112],fist:[30,-102],thumb:[52,-24],hold:[-24,66],mouth:[-40,-32],side:[112,2],
  wag:[40,-96],reach:[106,36],cross:[-58,56],you:[18,46]};
const POSES={
  idle:{}, wave:{R:'wave',rh:'open',wv:1,smile:1}, bye:{R:'wave',rh:'open',wv:1,smile:1},
  pru:{R:'pu',rh:'point'}, pr:{R:'pr',rh:'point'}, prd:{R:'pd',rh:'point'},
  plu:{L:'pu',lh:'point'}, pl:{L:'pr',lh:'point'},
  idea:{R:'top',rh:'point',brow:.8}, think:{R:'think',brow:.6,smile:.1,ly:-.6,lx:.5},
  cover:{L:'cover',R:'cover',lh:'open',rh:'open',smile:-.1}, shrug:{L:'shrug',R:'shrug',lh:'open',rh:'open',brow:1,smile:-.3,sh:-10},
  cheer:{L:'up',R:'up',lh:'open',rh:'open',smile:1}, stretch:{L:'up',R:'up',eye:.06,yawn:1,talk:0},
  present:{R:'present',rh:'open',smile:.8}, self:{R:'self',rh:'open',smile:.7}, shh:{R:'shh',rh:'point',brow:.7,smile:0,talk:0},
  you:{R:'you',rh:'point',rbig:1.45,smile:.7}, two:{R:'up',rh:'v',smile:.8}, press:{R:'top',rh:'fist',brow:-.3},
  buy:{R:'top',rh:'fist',brow:-.4,smile:.6}, sell:{L:'pd',lh:'point',brow:-.4}, sl:{L:'pd',lh:'open'}, tp:{L:'pd',lh:'open',R:'pu',rh:'open'},
  fist:{R:'fist',rh:'fist',smile:1}, thumbs:{R:'thumb',rh:'thumb',smile:1},
  pull:{L:'reach',R:'cross',lean:.24,brow:-.6,smile:-.2}, hold:{L:'hold',R:'hold',ly:.8,prop:'phone',tap:1},
  whistle:{R:'mouth',brow:-.9,talk:0,prop:'whistle'}, card:{L:'top',lh:'card',R:'mouth',brow:-.9,talk:0,prop:'whistle'},
  balance:{L:'side',R:'side',lh:'open',rh:'open'}, wag:{R:'wag',rh:'point',wg:1,shake:1,smile:.3}, crouch:{L:'shrug',R:'shrug',sq:.2},
};
const PDEF={L:'idle',R:'idle',lh:'fist',rh:'fist',lean:0,brow:0,smile:.65,eye:1,lx:0,ly:0,wv:0,wg:0,talk:1,yawn:0,sh:0,prop:'',rbig:1,tap:0,shake:0,wob:0,sq:0};
function pz(name,ex){const o=Object.assign({},PDEF,POSES[name]||{},ex||{});const l=HP[o.L]||HP.idle,r=HP[o.R]||HP.idle;
  o.Lx=o.Lx??l[0];o.Ly=o.Ly??l[1];o.Rx=o.Rx??r[0];o.Ry=o.Ry??r[1];return o;}
function mix(a,b,p){const o={};for(const k in b){const va=a[k],vb=b[k];o[k]=(typeof vb==='number'&&typeof va==='number')?va+(vb-va)*p:(p<0.5&&va!==undefined?va:vb);}return o;}
function trackEval(keys,t){ // keys: [time, obj, tr]; continuous even when windows overlap
  let cur=keys[0][1];
  for(let i=1;i<keys.length;i++){
    const k=keys[i],tr=k[2]??0.26,ws=k[0]-tr/2;if(t<ws)break;
    const nxt=Object.assign({},cur,k[1]);const k2=keys[i+1];const ws2=k2?k2[0]-(k2[2]??0.26)/2:1e9;
    if(t<ws2)return mix(cur,nxt,eio(clamp((t-ws)/tr)));
    cur=mix(cur,nxt,eio(clamp((ws2-ws)/tr)));
  }
  return cur;
}
const blinkAt=t=>{const q=(t/2.9+0.31)%1;return q<0.045?Math.abs(q/0.0225-1):1;};

/* ---------- drawing primitives for the toon ---------- */
function seg(pts,w){X.save();X.lineCap='round';X.lineJoin='round';X.beginPath();X.moveTo(pts[0][0],pts[0][1]);for(let i=1;i<pts.length;i++)X.lineTo(pts[i][0],pts[i][1]);
  X.strokeStyle=K;X.lineWidth=w+12;X.stroke();X.strokeStyle=M;X.lineWidth=w;X.stroke();X.restore();}
function fillM(lw=6){X.fillStyle=M;X.fill();X.lineWidth=lw;X.strokeStyle=K;X.stroke();}
function ik(sx,sy,tx,ty,l1,l2,sd){
  let dx=tx-sx,dy=ty-sy,d=Math.hypot(dx,dy);const mx=l1+l2-0.5,mn=Math.abs(l1-l2)+8;
  if(d>mx){dx*=mx/d;dy*=mx/d;d=mx;}if(d<mn){const k=mn/Math.max(d,1e-3);dx*=k;dy*=k;d=mn;}
  const a=Math.atan2(dy,dx),c=Math.acos(clamp((l1*l1+d*d-l2*l2)/(2*l1*d),-1,1));
  const e1=[sx+Math.cos(a+c)*l1,sy+Math.sin(a+c)*l1],e2=[sx+Math.cos(a-c)*l1,sy+Math.sin(a-c)*l1];
  return [(e1[0]*sd>e2[0]*sd)?e1:e2,[sx+dx,sy+dy]];
}
function handDraw(x,y,ang,kind,sd,big){
  X.save();X.translate(x,y);X.scale(big,big);
  const finger=(a,len)=>{X.save();X.rotate(a);X.lineCap='round';X.strokeStyle=K;X.lineWidth=19;X.beginPath();X.moveTo(4,0);X.lineTo(len,0);X.stroke();X.strokeStyle=M;X.lineWidth=10;X.stroke();X.restore();};
  if(kind==='point')finger(ang,32);
  if(kind==='v'){finger(ang-0.32,30);finger(ang+0.32,30);}
  if(kind==='thumb')finger(-Math.PI/2,30);
  if(kind==='card'){X.save();X.rotate(ang+Math.PI/2);rr(-27,-92,54,74,7);fillM(5);X.restore();}
  X.beginPath();X.arc(0,0,kind==='open'?17:15,0,6.283);fillM(5);
  if(kind==='open'){X.save();X.rotate(ang);X.beginPath();X.arc(9,-sd*12,7.5,0,6.283);fillM(4);X.restore();}
  X.restore();
}
function guy(o,t){
  const sc=o.s;if(!(sc>0.005))return;
  X.save();X.translate(o.x,o.y-(o.air||0));X.rotate(o.rot||0);const sq=o.sq||0;X.scale(sc*(1+sq*0.55),sc*(1-sq));
  const wa=clamp(o.walk||0),ph=o.ph||0,swing=Math.sin(ph)*0.45*wa,bob=Math.abs(Math.cos(ph))*8*wa;
  X.translate(0,-bob);
  const hipY=-128,kn=(o.air||0)>8?0.5:0;
  for(const [sd,th] of [[-1,-0.07+swing],[1,0.07-swing]]){
    const hx=sd*21,kx=hx+Math.sin(th)*64,ky=hipY+Math.cos(th)*64,th2=th+sd*kn,fx=kx+Math.sin(th2)*60,fy=ky+Math.cos(th2)*60;
    seg([[hx,hipY],[kx,ky],[fx,fy]],27);
    X.save();X.translate(fx+sd*9,fy+1);X.beginPath();X.ellipse(0,0,25,13,0,0,6.283);fillM(5);X.restore();
  }
  X.save();X.translate(0,hipY);X.rotate((o.lean||0)+Math.sin(t*4.2)*0.14*(o.wob||0));X.translate(0,-hipY);
  const br=Math.sin(t*2.7)*2.2;
  // torso
  rr(-49,-252-br,98,132+br,34);fillM(6);
  line(-46,-138,46,-138,6,K);
  X.save();X.strokeStyle=K;X.lineWidth=6;X.lineJoin='round';X.beginPath();X.moveTo(-19,-250-br);X.lineTo(0,-228-br);X.lineTo(19,-250-br);X.stroke();X.restore();
  X.beginPath();X.arc(-21,-196,17,0,6.283);X.fillStyle=K;X.fill();logo(-21,-196,22);
  // head
  const shk=Math.sin(t*15)*0.9*(o.shake||0);
  const lx=clamp((o.lx||0)+shk,-1.2,1.2),ly=o.ly||0,hy=-306+(o.sh||0)*0.3;
  rr(-11,-266,22,22,4);fillM(5);
  X.save();X.translate(lx*4,0);
  for(const sd of [-1,1]){X.beginPath();X.arc(sd*52,hy+4,11,0,6.283);fillM(5);}
  X.beginPath();X.arc(0,hy,53,0,6.283);fillM(6);
  // hair (black, inside a mustard rim)
  X.save();X.beginPath();X.arc(0,hy,47,0,6.283);X.clip();X.beginPath();X.moveTo(-70,hy-80);X.lineTo(70,hy-80);X.lineTo(70,hy-24);
  X.quadraticCurveTo(14+lx*6,hy-4,-14+lx*6,hy-24);X.quadraticCurveTo(-36,hy-12,-70,hy-14);X.closePath();X.fillStyle=K;X.fill();X.restore();
  // headset
  X.save();X.lineCap='round';X.strokeStyle=K;X.lineWidth=17;X.beginPath();X.arc(0,hy,60,Math.PI*1.07,Math.PI*1.93);X.stroke();X.strokeStyle=M;X.lineWidth=9;X.stroke();X.restore();
  for(const sd of [-1,1]){rr(sd*60-9,hy-17,18,34,7);fillM(4);}
  seg([[60,hy+12],[48,hy+34],[26,hy+38]],5);X.beginPath();X.arc(24,hy+38,6.5,0,6.283);fillM(3);
  // face
  const fx=lx*9,fy=ly*5,eo2=clamp((o.eye??1)*blinkAt(t));
  for(const sd of [-1,1]){
    if(eo2>0.18){X.beginPath();X.ellipse(sd*19+fx,hy+7+fy,7.5,11*eo2,0,0,6.283);X.fillStyle=K;X.fill();}
    else line(sd*19+fx-8,hy+8+fy,sd*19+fx+8,hy+8+fy,5,K);
    const bw=o.brow||0,by=hy-12-bw*6+fy*0.6;
    X.save();X.translate(sd*19+fx*0.8,by);X.rotate(-sd*bw*0.2);line(-10,0,10,0,5.5,K);X.restore();
  }
  const op=Math.max(clamp(vol(t)*1.7)*(o.talk??1),(o.yawn||0)*0.95);
  if(op>0.1){X.beginPath();X.ellipse(fx*0.7,hy+31,9+op*3,2+op*12,0,0,6.283);X.fillStyle=K;X.fill();}
  else{const sm=o.smile??0.6;X.save();X.strokeStyle=K;X.lineWidth=5;X.lineCap='round';X.beginPath();X.moveTo(-13+fx*0.7,hy+29);X.quadraticCurveTo(fx*0.7,hy+29+sm*13,13+fx*0.7,hy+29);X.stroke();X.restore();}
  X.restore();
  // arms
  const tp=(o.tap||0)*Math.sin(t*24)*4;
  const arms=[[-1,o.Lx,o.Ly+tp,o.lh,1],[1,o.Rx+Math.sin(t*13)*17*(o.wv||0)+Math.sin(t*17)*13*(o.wg||0),o.Ry-tp,o.rh,o.rbig||1]];
  const hands=[];
  for(const [sd,ax,ay,kind,big] of arms){
    const sx=sd*47,sy=-238+(o.sh||0),[e,h]=ik(sx,sy,sx+sd*ax,sy+ay+Math.sin(t*2.2+sd)*2,60,56,sd);
    seg([[sx,sy],e,h],22);hands.push([h,Math.atan2(h[1]-e[1],h[0]-e[0]),kind,sd,big]);
  }
  if(o.prop==='phone'){const mx=(hands[0][0][0]+hands[1][0][0])/2,my=(hands[0][0][1]+hands[1][0][1])/2;
    X.save();X.translate(mx,my-10);rr(-34,-54,68,104,13);X.fillStyle=K;X.fill();X.lineWidth=6;X.strokeStyle=M;X.stroke();
    for(let i=0;i<3;i++){const on=((t*3+i)%3)<1.6;rr(-20+i*15,-26,9,on?30:18,2);X.fillStyle=on?M:mA(0.4);X.fill();}X.restore();}
  if(o.prop==='whistle'){const h=hands[1][0];X.save();X.translate(h[0]-14,h[1]-6);rr(-20,-9,30,18,8);fillM(4);X.restore();
    for(let i=0;i<3;i++){const q=((t*3.2+i/3)%1);X.save();X.globalAlpha*=(1-q);X.strokeStyle=M;X.lineWidth=5;X.beginPath();X.arc(h[0]-40,h[1]-10,26+q*44,-0.5-Math.PI,0.5-Math.PI);X.stroke();X.restore();}}
  for(const [h,a,kind,sd,big] of hands)handDraw(h[0],h[1],a,kind,sd,big);
  X.restore();
  X.restore();
}
function robot(x,y,sc,t,blind){
  if(!(sc>0.005))return;X.save();X.translate(x,y);X.scale(sc,sc);
  line(-17,-28,-17,-4,11,M);line(17,-28,17,-4,11,M);
  rr(-42,-96,84,70,15);X.fillStyle=K;X.fill();X.lineWidth=6;X.strokeStyle=M;X.stroke();
  T('</>',0,-61,30,'8',M,'center','ltr');
  const sw=Math.sin(t*6)*8;line(-42,-74,-62,-50+sw,9,M);line(42,-74,62,-50-sw,9,M);
  X.save();X.translate(0,Math.sin(t*5)*3);
  line(0,-176,0,-154,6,M);X.save();X.shadowColor=mA(0.9);X.shadowBlur=14+10*Math.sin(t*8);X.beginPath();X.arc(0,-182,9,0,6.283);X.fillStyle=M;X.fill();X.restore();
  rr(-50,-156,100,64,19);X.fillStyle=K;X.fill();X.lineWidth=6;X.strokeStyle=M;X.stroke();
  const bl=blinkAt(t+1.3);for(const ex of [-21,21]){X.beginPath();X.ellipse(ex,-124,9.5,12*bl,0,0,6.283);X.fillStyle=M;X.fill();}
  if(blind>0){const by=lerp(-215,-124,eback(clamp(blind)));rr(-60,by-15,120,30,9);fillM(4);line(58,by,82,by-14,7,M);line(58,by,84,by+10,7,M);T('؟',0,by-1,30,'9',K);}
  X.restore();X.restore();
}
function pop(t,t0,x,y,r=60){const q=P(t,t0,0.42);if(q<=0||q>=1)return;X.save();X.globalAlpha*=1-q;X.strokeStyle=M;X.lineWidth=6*(1-q)+1;X.beginPath();X.arc(x,y,r*eo(q),0,6.283);X.stroke();
  for(let i=0;i<8;i++){const a=i*0.785+0.3,r1=r*(0.9+0.5*eo(q)),r2=r1+24*(1-q);line(x+Math.cos(a)*r1,y+Math.sin(a)*r1,x+Math.cos(a)*r2,y+Math.sin(a)*r2,5,M);}X.restore();}
function arrowUD(x,y,dir,sz,al){if(al<=0)return;X.save();X.globalAlpha*=al;X.translate(x,y);X.scale(1,dir);X.beginPath();X.moveTo(0,-sz);X.lineTo(sz*0.75,0);X.lineTo(sz*0.27,0);
  X.lineTo(sz*0.27,sz*0.85);X.lineTo(-sz*0.27,sz*0.85);X.lineTo(-sz*0.27,0);X.lineTo(-sz*0.75,0);X.closePath();
  if(dir>0){X.fillStyle=M;X.fill();}else{X.fillStyle=K;X.fill();X.lineWidth=6;X.strokeStyle=M;X.stroke();}X.restore();}
function plane(x,y,a,sz){X.save();X.translate(x,y);X.rotate(a);X.beginPath();X.moveTo(sz,0);X.lineTo(-sz*0.8,-sz*0.62);X.lineTo(-sz*0.38,0);X.lineTo(-sz*0.8,sz*0.62);X.closePath();fillM(4);line(-sz*0.38,0,sz*0.95,0,3,K);X.restore();}
function cushion(x,y,al){if(al<=0)return;X.save();X.globalAlpha*=al;X.translate(x,y);X.scale(1,0.6+0.4*al);rr(-140,-40,280,62,31);X.fillStyle=mA(0.25);X.fill();X.lineWidth=5;X.strokeStyle=M;X.stroke();T('تمرین',0,-9,36,'8',M);X.restore();}
function ropeDraw(t,t0,x0,x1,y){const p=eo(P(t,t0,0.55));if(p<=0)return;const xm=lerp(x0,x1,p);X.save();X.strokeStyle=M;X.lineWidth=5;X.beginPath();X.moveTo(x0,y);X.quadraticCurveTo((x0+xm)/2,y+16*p,xm,y);X.stroke();X.restore();
  line(x0,y-8,x0,y+44,8,M);if(p>0.98)line(x1,y-8,x1,y+44,8,M);}
const ropeY=(x,x0,x1,y)=>{const u=clamp((x-x0)/(x1-x0));return y+16*4*u*(1-u)*0.5;};

/* ---------- choreography: one track per shot, every key on a spoken word ---------- */
const hd34=t=>lerp(610,130,clamp(story(t).n/34));
const TOON=[
 {t0:0,t1:S1,cam:'hud',
  pos:[[0,{x:262,y:1500,s:1.0,air:0}],[W8(1,6),{air:60},0.3],[W8(1,6)+0.3,{air:0},0.3]],
  pose:[[0,pz('idle',{lx:.6,ly:-.5})],[W8(1,0),pz('wave',{})],[W8(1,4),pz('pru',{lx:.7,ly:-.7})],[W8(1,6),pz('cheer',{})],[W8(1,8),pz('think',{})]],
  appear:0.02,
  fx:(t,o)=>{const q=eo(P(t,W8(1,8),0.3));if(q>0)qmark(o.x+70,o.y-o.s*470-20*q,96,q,24);}},
 {t0:S1,t1:S2,cam:'none',
  pos:[[S1,{x:-110,y:1360,s:.88,air:0,rot:0}],[S1+0.32,{x:170},0.62],[S2-0.6,{x:170,y:1360,s:.88,rot:0},0.1],[S2-0.28,{x:545,y:1020,s:.08,rot:6.283},0.56]],
  pose:[[S1,pz('idle',{lx:.5})],[W8(2,0),pz('pru',{lx:.6,ly:-.6})],[W8(2,5),pz('thumbs',{})],[W8(2,7),pz('pr',{lx:.8,ly:.2})],[S2-0.62,pz('crouch',{})],[S2-0.45,pz('cheer',{})]],
  fx:(t,o)=>{pop(t,W8(2,5),o.x+o.s*70,o.y-o.s*280,50);}},
 {t0:S2,t1:S3,cam:'hud',
  pos:[[S2,{dx:0,y:1135,s:.68,air:640,sq:0}],[S2+0.42,{air:0},0.5],[S2+0.72,{sq:.24},0.1],[S2+0.86,{sq:0},0.2],
       [W8(3,2),{dx:34},0.3],[W8(3,9),{dx:-6},0.3],[W8(4,17),{dx:-40},0.5]],
  pose:[[S2,pz('cheer',{})],[W8(3,0),pz('idle',{ly:-.8,lx:.3})],[W8(3,2),pz('pull',{})],[W8(3,7),pz('idle',{smile:.9,lx:-.4})],
        [W8(3,10),pz('pl',{lx:-.7})],[W8(4,0),pz('idea',{})],[W8(4,3),pz('pru',{lx:.8,ly:-.5})],[W8(4,5),pz('shh',{lx:.5})],
        [W8(4,8),pz('you',{})],[W8(4,10),pz('idle',{smile:.8})],[W8(4,14),pz('cover',{})],[W8(4,17),pz('pr',{lx:.8})],[W8(4,20),pz('shrug',{lx:.5})]],
  xf:(t,o)=>hd34(t)+o.dx,
  fx:(t,o)=>{const ra=eback(P(t,W8(4,17)-0.12,0.42));if(ra>0){robot(o.x+160,1135,0.68*ra,t,P(t,W8(4,20)-0.15,0.4));pop(t,W8(4,17)-0.12,o.x+160,1050,60);}
    const q=eo(P(t,W8(4,0),0.25))*(1-P(t,W8(4,3),0.2));if(q>0)pop(t,W8(4,0),o.x+20,o.y-o.s*520,40);}},
 {t0:S3,t1:S5,cam:'hud',
  pos:[[S3,{x:0,y:1155,s:.68,air:0,sq:0}],[S3+0.35,{x:330},0.7],[W8(5,7)-0.05,{air:70},0.24],[W8(5,7)+0.22,{air:0},0.24],
       [W8(5,21),{sq:.22},0.2],[W8(5,23),{x:300,air:90,sq:0},0.3],[W8(5,23)+0.3,{x:270,air:0},0.3],[W8(5,23)+0.55,{sq:.15},0.1],[W8(5,23)+0.7,{sq:0},0.2]],
  pose:[[S3,pz('shrug',{lx:.5})],[W8(5,0),pz('self',{})],[W8(5,3),pz('you',{})],[W8(5,5),pz('two',{})],[W8(5,7),pz('press',{})],
        [W8(5,9),pz('buy',{})],[W8(5,11),pz('sell',{})],[W8(5,14),pz('sl',{ly:.6})],[W8(5,17),pz('tp',{ly:-.6})],[W8(5,21),pz('crouch',{lx:-.6})],
        [W8(5,23),pz('cheer',{lx:-.6})],[W8(5,23)+0.6,pz('idle',{smile:1})]],
  start:t=>hd34(S3-0.001)+(-40),
  fx:(t,o)=>{
    arrowUD(o.x+o.s*60,o.y-o.s*560-30*eo(P(t,W8(5,9),0.4)),1,46,eo(P(t,W8(5,9)-0.05,0.2))*(1-P(t,W8(5,11)-0.1,0.2)));
    arrowUD(o.x-o.s*150,o.y-o.s*40+30*eo(P(t,W8(5,11),0.4)),-1,46,eo(P(t,W8(5,11)-0.05,0.2))*(1-P(t,W8(5,14)-0.1,0.2)));
    pop(t,W8(5,7)+0.05,o.x+o.s*20,o.y-o.s*470,46);}},
 {t0:S5,t1:S6,cam:'hud',
  pos:[[S5,{x:-110,y:1375,s:.72,air:0}],[S5+0.35,{x:200},0.62],[W8(6,6)-0.05,{air:50},0.22],[W8(6,6)+0.2,{air:0},0.22]],
  pose:[[S5,pz('idle',{})],[W8(6,0),pz('stretch',{})],[W8(6,2),pz('present',{lx:.6,ly:-.7})],[W8(6,6),pz('fist',{})],[W8(6,8),pz('thumbs',{})],
        [W8(6,11),pz('prd',{lx:.6,ly:.3})],[W8(6,12)+0.12,pz('pru',{lx:.7,ly:-.7}),0.55],[36.15,pz('cheer',{})]],
  fx:(t,o)=>{pop(t,W8(6,6),o.x+o.s*40,o.y-o.s*500,50);}},
 {t0:S6,t1:S7,cam:'scene',
  pos:[[S6,{x:250,y:1152,s:.82,air:560,sq:0}],[S6+0.3,{air:0},0.5],[S6+0.58,{sq:.22},0.1],[S6+0.72,{sq:0},0.2]],
  pose:[[S6,pz('cheer',{})],[W8(7,0),pz('think',{lx:.9})],[W8(7,6),pz('pr',{lx:.9,ly:.2})],[W8(7,12),pz('pru',{lx:.8,ly:-.9})],
        [W8(7,14),pz('whistle',{lx:.6})],[W8(7,17),pz('card',{lx:.6})],[42.75,pz('idle',{brow:-.3,smile:.3})]],
  fx:(t,o)=>{pop(t,W8(7,17),o.x-o.s*60,o.y-o.s*560,60);}},
 {t0:S7,t1:S8,cam:'hud',
  pos:[[S7,{x:540,y:1382,s:.62,rot:0}],[W8(8,1)+0.12,{rot:-1.32},0.36],[W8(8,5),{rot:0},0.42]],
  pose:[[S7,pz('idle',{})],[W8(8,1),pz('cheer',{smile:-.5,brow:1})],[W8(8,4),pz('idle',{smile:1,eye:.1,brow:.6})],[W8(8,5),pz('thumbs',{})],
        [W8(8,7),pz('wag',{})],[47.05,pz('idle',{})]],
  appear:S7+0.05,
  under:(t,o)=>{cushion(430,1376,eo(P(t,W8(8,1),0.25))*(1-P(t,W8(8,5)+0.3,0.3)));}},
 {t0:S8,t1:S9,cam:'hud',
  pos:[[S8,{x:850,y:1380,s:.8,air:0}],[W8(9,9)+0.1,{air:40},0.2],[W8(9,9)+0.32,{air:0},0.22]],
  pose:[[S8,pz('idle',{lx:-.5})],[W8(9,1),pz('plu',{lx:-.8,ly:-.6})],[W8(9,3),pz('hold',{})],[W8(9,6),pz('idle',{lx:-.8,ly:-.4})],[W8(9,9)+0.12,pz('cheer',{})]],
  appear:S8+0.05,
  fx:(t,o)=>{const q=P(t,W8(9,6)-0.1,W8(9,9)-W8(9,6)+0.25);if(q>0&&q<1){const u=eio(q);const x0=700,y0=1025,x1=o.x-10,y1=o.y-o.s*330;
      const cx=lerp(x0,x1,u)+Math.sin(u*Math.PI)*-60,cy=lerp(y0,y1,u)-Math.sin(u*Math.PI)*260;const u2=Math.min(1,u+0.02);
      const nx=lerp(x0,x1,u2)+Math.sin(u2*Math.PI)*-60,ny=lerp(y0,y1,u2)-Math.sin(u2*Math.PI)*260;plane(cx,cy,Math.atan2(ny-cy,nx-cx),44);}
    pop(t,W8(9,9)+0.12,o.x,o.y-o.s*330,60);}},
 {t0:S9,t1:S10,cam:'hud',
  pos:[[S9,{x:170,y:1330,s:.76}],[W8(10,2),{x:260},0.7],[W8(10,6),{x:430},1.3],[W8(10,9),{x:580},1.3]],
  pose:[[S9,pz('balance',{})],[W8(10,0),pz('idea',{L:'side',lh:'open'})],[W8(10,2),pz('balance',{wob:1})],[W8(10,6),pz('balance',{lx:-1,wob:.7})],
        [W8(10,8),pz('balance',{lx:1,wob:1,brow:.8,smile:.1})],[55.2,pz('balance',{wob:.3,smile:.8})]],
  appear:S9+0.08,
  under:(t,o)=>{ropeDraw(t,S9+0.02,110,930,1330);},
  yf:(t,o)=>ropeY(o.x,110,930,1330),
  fx:(t,o)=>{const q=eo(P(t,W8(10,8),0.3))*(1-P(t,55.3,0.3));if(q>0)qmark(o.x+80,o.y-o.s*470,84,q,20);}},
 {t0:S10,t1:99,cam:'hud',
  pos:[[S10,{x:165,y:1222,s:.68}]],
  pose:[[S10,pz('idle',{lx:.5})],[W8(11,0),pz('pru',{lx:.6,ly:-.8})],[W8(11,2),pz('fist',{brow:-.3})],[W8(11,4),pz('present',{lx:.7})],
        [B('11c')+0.1,pz('prd',{lx:.6,ly:.6})],[59.9,pz('bye',{})]],
  appear:S10+0.06},
];
function toonLayer(t){
  const k=TOON.findIndex(c=>t>=c.t0&&t<c.t1);if(k<0)return;const c=TOON[k];
  const sh=SHOTS.find(z=>t>=z[0]&&t<z[1])||SHOTS[0];
  const evalPos=tt=>{const keys=c.start&&c.pos[0][1].x===0?[[c.pos[0][0],Object.assign({},c.pos[0][1],{x:c.start(tt)})],...c.pos.slice(1)]:c.pos;const p=trackEval(keys,tt);
    if(c.xf)p.x=c.xf(tt,p);if(c.yf)p.y=c.yf(tt,p);return p;};
  const p=evalPos(t),p0=evalPos(Math.max(c.t0,t-1/60));
  const v=Math.abs(p.x-p0.x)*60;const o=Object.assign({},trackEval(c.pose,t),p);
  o.walk=clamp(v/160);o.ph=(p.x/26);
  if(c.appear!=null)o.s*=eback(P(t,c.appear,0.4));
  X.save();
  if(c.cam!=='none'){const cam=sh[2](t,'cam');if(c.cam==='scene')applyCam(cam);else applyCam({x:cam.x*0.45,y:cam.y*0.45,z:1+(cam.z-1)*0.35,r:cam.r*0.5});}
  if(c.under)c.under(t,o);
  // soft floor shadow
  if(!(o.air>2)&&o.s>0.05&&!o.rot){X.save();X.globalAlpha*=0.35;X.beginPath();X.ellipse(o.x,o.y+2,58*o.s,9*o.s,0,0,6.283);X.fillStyle=mA(0.5);X.fill();X.restore();}
  guy(o,t);
  if(c.fx)c.fx(t,o);
  X.restore();
}
