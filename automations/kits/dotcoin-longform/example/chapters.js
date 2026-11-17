// ================= shared scene pieces
function base(t,dark=false){paperBg(0,PX,dark);}
function stageO(u=56,x=600,y=560){return {x,y,u};}
function ledgerRows(o,x,y,z,w,d,p,rows){// lines written on a top face
 for(let i=0;i<rows;i++){const q=clamp(p*rows-i);if(q<=0)break;const yy=y+0.35+i*(d-0.7)/(rows-1||1);face(o,[[x+0.3,yy,z],[x+0.3+(w-0.6)*q,yy,z]],null,3,i%3===0?MU:'rgba(59,64,196,0.55)');}}
function chainBlock(o,x,y,z,s,cols,lw=3){box(o,x,y,z,s,s,s,cols,lw);}
function link(o,x0,y0,z0,x1,y1,z1,p=1,col=IND){if(p<=0)return;const a=P(o,x0,y0,z0),b=P(o,x1,y1,z1);line(a[0],a[1],lerp(a[0],b[0],p),lerp(a[1],b[1],p),col,6);}
function globe(cx,cy,r,t,p=1){X.save();X.globalAlpha*=p;circle(cx,cy,r,PALE,IND,3);X.save();X.beginPath();X.arc(cx,cy,r,0,6.2832);X.clip();
 X.strokeStyle='rgba(59,64,196,0.35)';X.lineWidth=2;for(let i=-2;i<=2;i++){X.beginPath();X.ellipse(cx,cy+i*r*0.36,r*Math.sqrt(1-(i*0.36)**2),r*0.1*Math.sqrt(1-(i*0.36)**2)+1,0,0,6.2832);X.stroke();}
 const rot=t*0.15;for(let k=0;k<6;k++){const a=(k/6*Math.PI+rot)%Math.PI;X.beginPath();X.ellipse(cx,cy,Math.abs(Math.cos(a))*r,r,0,0,6.2832);X.stroke();}
 X.restore();X.restore();}
function globeNodes(cx,cy,r,t,n,seed,p,col=MU){const pts=[];for(let i=0;i<n;i++){const b=Math.acos(1-2*(i+0.5)/n),a=i*2.39996+seed;let lon=a+t*0.15;const x=Math.sin(b)*Math.cos(lon),z=Math.sin(b)*Math.sin(lon),y=Math.cos(b);if(z<-0.1)continue;pts.push([cx+x*r,cy+y*r*0.98,z]);}
 const q=eo(p);X.save();X.globalAlpha*=q;for(let i=0;i<pts.length;i++)for(let j=i+1;j<pts.length;j++){const d=Math.hypot(pts[i][0]-pts[j][0],pts[i][1]-pts[j][1]);if(d<r*0.55)line(pts[i][0],pts[i][1],pts[j][0],pts[j][1],'rgba(59,64,196,0.4)',1.5);}
 pts.forEach((pt,i)=>{const s=clamp(p*n*0.6-i*0.4);circle(pt[0],pt[1],(7+pt[2]*4)*s,col,BK,2);});X.restore();return pts;}
function docIso(o,x,y,z,w,d,title,p=1){X.save();X.globalAlpha*=p;box(o,x,y,z,w,d,0.12,[WH,PALE,PALE],2.5);onFace(o,'T',x,y,z+0.12,()=>{X.save();X.transform(1,0,0,1,0,0);X.fillStyle='rgba(59,64,196,0.5)';for(let i=0;i<7;i++)X.fillRect(0.35,0.9+i*0.42,(w-0.7)*(i%3===2?0.6:1),0.12);X.restore();});X.restore();}
function cursor(x,y,s=1,col=WH){X.save();X.translate(x,y);X.scale(s,s);X.beginPath();X.moveTo(0,0);X.lineTo(0,42);X.lineTo(11,32);X.lineTo(19,50);X.lineTo(26,47);X.lineTo(18,29);X.lineTo(33,29);X.closePath();X.fillStyle=col;X.fill();X.lineWidth=3;X.strokeStyle=BK;X.stroke();X.restore();}
function power(cx,cy,r,col,ring,lw=10){circle(cx,cy,r,null,ring,lw);X.beginPath();X.arc(cx,cy,r*0.5,-Math.PI/2+0.7,-Math.PI/2-0.7+6.2832);X.strokeStyle=col;X.lineWidth=lw;X.lineCap='round';X.stroke();line(cx,cy-r*0.62,cx,cy-r*0.12,col,lw);}
function codeCard(x,y,w,h,t,p,hl=-1,hlcol=RED,dark=false){if(p<=0)return;X.save();X.globalAlpha*=p;rr(x+10,y+12,w,h,18);X.fillStyle='rgba(22,23,58,0.16)';X.fill();rr(x,y,w,h,18);X.fillStyle=dark?'#14152B':WH;X.fill();X.lineWidth=3;X.strokeStyle=IND;X.stroke();
 X.fillStyle=IND;X.fillRect(x,y,w,46);[0,1,2].forEach(i=>circle(x+28+i*26,y+23,7,i===0?MU:'rgba(255,255,255,0.7)'));
 const r=rng(5),rows=Math.floor((h-80)/34),cols=[PERI,LIL,MU,AQUA,PEACH];for(let i=0;i<rows;i++){const ind=(i%4===1||i%4===2)?40:0;let xx=x+30+ind;const yy=y+70+i*34;if(i===hl){X.fillStyle='rgba(234,57,67,0.16)';X.fillRect(x+6,yy-14,w-12,30);}
  const segs=1+Math.floor(r()*3);for(let k=0;k<segs;k++){const sw=40+r()*120;const q=clamp(p*1.4-i*0.04);X.fillStyle=i===hl?hlcol:cols[(i+k)%5];if(xx+sw>x+w-30)break;rr(xx,yy-8,sw*q,16,8);X.fill();xx+=sw+14;}}
 X.restore();}
function vending(o,x,y,z,t,coinT,btnT,canT){// tall iso machine
 shadow(o,x,y,2.4,1.6,0.14);box(o,x,y,z,2.4,1.6,4.2,[LIL,PERI,'#6E86E0'],3);
 onFace(o,'L',x,y+1.6,z+4.2,()=>{X.fillStyle=WH;X.fillRect(0.18,0.25,1.45,2.55);X.lineWidth=0.05;X.strokeStyle=IND;X.strokeRect(0.18,0.25,1.45,2.55);
  const cc=[MU,AQUA,PEACH,'#6E86E0',LIL,GRN];for(let r=0;r<4;r++)for(let c=0;c<3;c++){X.fillStyle=cc[(r*3+c)%6];rr(0.28+c*0.45,0.38+r*0.62,0.32,0.5,0.06);X.fill();X.strokeStyle=IND;X.lineWidth=0.03;X.stroke();}
  X.fillStyle='#22245A';X.fillRect(1.78,0.4,0.45,0.7);// coin panel
  X.fillStyle=MU;X.fillRect(1.9,0.55,0.2,0.05);// slot
  const pb=clamp((t-btnT)/0.25);const press=pb>0&&pb<1?0.04:0;X.fillStyle=t>btnT?MU:WH;rr(1.82,1.3+press,0.37,0.3,0.06);X.fill();X.strokeStyle=IND;X.stroke();
  X.fillStyle='#22245A';X.fillRect(0.25,3.2,1.4,0.55);// tray
  if(t>canT){const q=eo(pr(t,canT,0.4));X.fillStyle=MU;rr(0.75,3.2+0.5*q-0.45,0.36,0.42,0.06);X.fill();X.strokeStyle=BK;X.lineWidth=0.03;X.stroke();}
 });
 // the flying coin
 if(t>coinT-0.6&&t<coinT+0.1){const q=eio(pr(t,coinT-0.6,0.6));const a=P(o,x-2.5,y+5,z+5.5),b=P(o,x+0.15,y+1.6,z+4.2-0.58);const cx=lerp(a[0],b[0]+1.95*IC*o.u,q),cy=lerp(a[1],b[1]+1.95*IS*o.u,q)-Math.sin(q*Math.PI)*80;coin(cx,cy,26,'mu',t*8);}}
function bank(cx,cy,s,col=WH){X.save();X.translate(cx,cy);X.fillStyle=col;X.strokeStyle=IND;X.lineWidth=4;X.beginPath();X.moveTo(-s,-s*0.45);X.lineTo(0,-s*0.95);X.lineTo(s,-s*0.45);X.closePath();X.fill();X.stroke();X.fillRect(-s,s*0.6,s*2,s*0.18);X.strokeRect(-s,s*0.6,s*2,s*0.18);for(let i=0;i<4;i++){const xx=-s*0.75+i*s*0.5;X.fillRect(xx-s*0.09,-s*0.35,s*0.18,s*0.92);X.strokeRect(xx-s*0.09,-s*0.35,s*0.18,s*0.92);}X.restore();}
function lockIcon(cx,cy,s,col=MU,p=1){if(p<=0)return;X.save();X.globalAlpha*=p;X.lineWidth=s*0.14;X.strokeStyle=BK;X.beginPath();X.arc(cx,cy-s*0.25,s*0.32,Math.PI,0);X.stroke();rr(cx-s*0.5,cy-s*0.25,s,s*0.8,s*0.12);X.fillStyle=col;X.fill();X.lineWidth=4;X.stroke();circle(cx,cy+s*0.1,s*0.09,BK);X.restore();}
function shield(cx,cy,s,col,p=1){if(p<=0)return;X.save();X.globalAlpha*=p;X.beginPath();X.moveTo(cx,cy-s*0.6);X.quadraticCurveTo(cx+s*0.5,cy-s*0.45,cx+s*0.55,cy-s*0.42);X.quadraticCurveTo(cx+s*0.55,cy+s*0.35,cx,cy+s*0.65);X.quadraticCurveTo(cx-s*0.55,cy+s*0.35,cx-s*0.55,cy-s*0.42);X.quadraticCurveTo(cx-s*0.5,cy-s*0.45,cx,cy-s*0.6);X.closePath();X.fillStyle=col;X.fill();X.lineWidth=5;X.strokeStyle=BK;X.stroke();X.restore();}
function magnifier(cx,cy,s,p=1){if(p<=0)return;X.save();X.globalAlpha*=p;circle(cx,cy,s*0.42,'rgba(255,255,255,0.35)',BK,s*0.08);line(cx+s*0.3,cy+s*0.3,cx+s*0.7,cy+s*0.7,BK,s*0.14);X.restore();}
function flame(cx,cy,s,t,p=1){if(p<=0)return;X.save();X.globalAlpha*=p;const k=Math.sin(t*14)*0.06,k2=Math.cos(t*11)*0.05;
 const fl=(sc,col)=>{X.beginPath();X.moveTo(cx,cy+s*0.5*sc);X.bezierCurveTo(cx-s*0.55*sc,cy+s*0.45*sc,cx-s*(0.45+k)*sc,cy-s*0.2*sc,cx+s*k2*sc,cy-s*(0.75+k)*sc);X.bezierCurveTo(cx+s*0.12*sc,cy-s*0.3*sc,cx+s*(0.5+k2)*sc,cy-s*0.15*sc,cx+s*0.42*sc,cy+s*0.2*sc);X.quadraticCurveTo(cx+s*0.35*sc,cy+s*0.5*sc,cx,cy+s*0.5*sc);X.closePath();X.fillStyle=col;X.fill();};
 fl(1,FIRE);fl(0.62,MU);X.lineWidth=3;X.restore();}
function clockRing(cx,cy,r,f,col=MU){circle(cx,cy,r,WH,BK,5);X.beginPath();X.arc(cx,cy,r-14,-Math.PI/2,-Math.PI/2+6.2832*f);X.strokeStyle=col;X.lineWidth=18;X.lineCap='butt';X.stroke();for(let i=0;i<12;i++){const a=i/12*6.2832;line(cx+Math.sin(a)*(r-34),cy-Math.cos(a)*(r-34),cx+Math.sin(a)*(r-26),cy-Math.cos(a)*(r-26),BK,3);}}
function rig(o,x,y,z,s,t,boltP){box(o,x,y,z,s,s*0.8,s*0.9,['#5C5F7A','#43465E','#2E3046'],2.5,BK);onFace(o,'L',x,y+s*0.8,z+s*0.9,()=>{for(let i=0;i<2;i++){X.save();X.translate(0.3+i*0.45,0.42);X.rotate(t*12+i);X.strokeStyle='#9A9DBA';X.lineWidth=0.04;for(let k=0;k<4;k++){X.rotate(1.57);X.beginPath();X.moveTo(0,0);X.lineTo(0.15,0);X.stroke();}X.restore();}});
 if(boltP>0){const [bx,by]=P(o,x+s/2,y+s*0.4,z+s*0.9+0.6);X.save();X.globalAlpha=boltP;X.beginPath();X.moveTo(bx+8,by-34);X.lineTo(bx-12,by+4);X.lineTo(bx+2,by+4);X.lineTo(bx-8,by+34);X.lineTo(bx+16,by-6);X.lineTo(bx+2,by-6);X.closePath();X.fillStyle=MU;X.fill();X.lineWidth=3;X.strokeStyle=BK;X.stroke();X.restore();}}
function bolt(cx,cy,s,col=MU){X.beginPath();X.moveTo(cx+s*0.2,cy-s*0.9);X.lineTo(cx-s*0.35,cy+s*0.1);X.lineTo(cx+s*0.02,cy+s*0.1);X.lineTo(cx-s*0.2,cy+s*0.9);X.lineTo(cx+s*0.42,cy-s*0.15);X.lineTo(cx+s*0.05,cy-s*0.15);X.closePath();X.fillStyle=col;X.fill();X.lineWidth=4;X.strokeStyle=BK;X.stroke();}
function envelope(cx,cy,w,col=WH){const h=w*0.66;X.fillStyle=col;X.fillRect(cx-w/2,cy-h/2,w,h);X.strokeStyle=IND;X.lineWidth=2.5;X.strokeRect(cx-w/2,cy-h/2,w,h);X.beginPath();X.moveTo(cx-w/2,cy-h/2);X.lineTo(cx,cy+h*0.08);X.lineTo(cx+w/2,cy-h/2);X.stroke();}
function walletIcon(cx,cy,s,col=MU){rr(cx-s*0.6,cy-s*0.42,s*1.2,s*0.84,s*0.12);X.fillStyle=col;X.fill();X.lineWidth=4;X.strokeStyle=BK;X.stroke();rr(cx+s*0.18,cy-s*0.14,s*0.48,s*0.28,s*0.08);X.fillStyle=BK;X.fill();circle(cx+s*0.34,cy,s*0.05,MU);}
function tile(x,y,w,h,col,stroke=BK,r=16){rr(x+8,y+10,w,h,r);X.fillStyle='rgba(22,23,58,0.14)';X.fill();rr(x,y,w,h,r);X.fillStyle=col;X.fill();if(stroke){X.lineWidth=3.5;X.strokeStyle=stroke;X.stroke();}}
// a big number that counts up
function counter(v,t,t0,d=0.9){return Math.round(v*eo(pr(t,t0,d)));}

// ================= ch0: the hook and the title
function ch0(t){
 const s4=S(4);
 // black hook field (sentences 0..1), the ETH reveal (2), the agenda (3), the title card (4)
 if(t<S(2)+0.4){X.fillStyle='#08080B';X.fillRect(0,0,W,H);
  const p0=1;
  // power button with a cursor that clicks it; the program keeps running
  const bx=560,by=520;const click=WT(0,'خاموش',0,0.35);
  X.save();X.globalAlpha=p0*(1-eo(pr(t,S(1)-0.1,0.4)));
  for(let r=0;r<4;r++)circle(bx,by,300+r*70,null,`rgba(243,194,66,${0.08-r*0.015})`,2);circle(bx,by,250,'#121320');power(bx,by,170,t>click&&t<click+0.25?WH:MU,'rgba(243,194,66,0.35)',16);
  const cp=eio(pr(t,0.15,click-0.15));cursor(lerp(bx+330,bx+40,cp),lerp(by+260,by+60,cp),1.3);
  if(t>click){const q=pr(t,click,0.6);circle(bx,by,150+q*120,null,`rgba(243,194,66,${0.6*(1-q)})`,6);}
  // status: running
  const sp=eo(pr(t,click+0.25,0.35));if(sp>0){X.globalAlpha=p0*sp*(1-eo(pr(t,S(1)-0.1,0.4)));rr(bx-170,by+250,340,84,42);X.fillStyle='#1B1C2E';X.fill();circle(bx-112,by+292,14,MU);TL('RUNNING',bx-82,by+292,48,'BEB',WH);}
  X.restore();
  headline(CHD.sent[0].h,CHD.sent[0].k,t,-0.7,S(1),W-120,430,92,760,WH,MU,BK);
  // sentence 1: code card and coins that follow it exactly
  const a1=vis(t,S(1),S(2)+0.4,0.5,0.4);if(a1>0){X.save();X.globalAlpha=a1;codeCard(220,250,560,420,t,eo(pr(t,S(1),0.8)),-1,RED,true);
   for(let i=0;i<6;i++){const q=pr(t,S(1)+0.8+i*0.32,1.1);if(q<=0||q>=1)continue;const e=eio(q);const x=lerp(800,1180,e),y=lerp(460,640,e)-Math.sin(e*Math.PI)*90;coin(x,y,30,'mu',0);}
   tile(1150,560,200,150,'#1B1C2E',MU);T('۱۰۰',1250,620,64,'YKE',MU,'center');T('دقیقاً',1250,680,26,'YKB',WH,'center');X.restore();}
  headline(CHD.sent[1].h,CHD.sent[1].k,t,S(1)+0.1,S(2),W-120,430,92,760,WH,MU,BK);
 }
 // sentence 2: ETHEREUM
 const a2=vis(t,S(2),S(3)+0.3,0.6,0.4);
 if(a2>0){X.save();X.globalAlpha=a2;X.fillStyle=MU;X.fillRect(0,0,W,H);dither(0,0,W,H,2);
  const p=eo(pr(t,S(2),1.0));X.font=font(300,'ANT');X.textAlign='center';X.textBaseline='middle';X.direction='ltr';X.fillStyle=BK;X.fillText('ETHEREUM',W/2+(1-p)*200,230);
  X.save();const g=eback(pr(t,S(2)+0.15,0.7));X.translate(W/2,610);X.scale(g,g);circle(0,0,215,BK);ethGlyph(0,0,300);X.restore();
  chip('رتبه‌ی ۲ ارز دیجیتال از نظر ارزش بازار',W/2,920,42,'YKK',MU,BK,'center');X.restore();}
 // sentence 3: the agenda on paper
 const a3=vis(t,S(3),S(4)+0.2,0.5,0.4);
 if(a3>0&&t<S(4)+0.3){X.save();X.globalAlpha=a3;paperBg(0,W);mark();
  T('توی این ویدیو',W-160,200,44,'YKB',BK,'right');X.fillStyle=BK;X.fillRect(160,250,W-320,6);
  const items=[['اتریوم چیست','اتریوم'],['قرارداد هوشمند','قرارداد'],['گس و کارمزد','گس'],['فرق با بیت‌کوین','فرق']];
  items.forEach((it,i)=>{const tt=WT(3,it[1],0,0.2+i*0.18)-0.15;const q=eo(pr(t,tt,0.5));if(q<=0)return;const y=360+i*165;X.save();X.globalAlpha=q;X.translate((1-q)*-60,0);
   X.fillStyle=MU;X.fillRect(W-300,y-60,140,120);T(fa(String(i+1).padStart(2,'0')),W-230,y,74,'YKE',BK,'center');T(it[0],W-340,y,84,'YKE',BK,'right');
   X.fillStyle='rgba(0,0,0,0.12)';X.fillRect(160,y+75,W-320,2);X.restore();});
  // a small ETH glyph block on the left
  const o=stageO(48,420,640);const q=eo(pr(t,S(3),0.8));X.save();X.globalAlpha=q;box(o,-2,-2,0,4,4,1.2,[PALE,PERI,LIL]);ethGlyph(P(o,0,0,1.2)[0],P(o,0,0,1.2)[1]-150,260);X.restore();
  X.restore();}
 // sentence 4: the title card
 const a4=eo(pr(t,s4,0.5));if(a4>0){X.save();X.globalAlpha=a4;X.fillStyle=MU;X.fillRect(0,0,W,H);dither(0,0,W,H,9);
  X.font=font(250,'ANT');X.textAlign='center';X.textBaseline='middle';X.direction='ltr';X.lineWidth=4;X.strokeStyle=BK;X.strokeText('ETHEREUM',W/2,890);
  const p=eo(pr(t,s4+0.1,0.7));X.save();X.translate(0,(1-p)*30);T('اتریوم چیست؟',W-150,380,170,'YKE',BK,'right');X.restore();
  X.save();X.globalAlpha=eo(pr(t,WT(4,'آموزش',0,0.3),0.5));chip('آموزش ارز دیجیتال به زبان ساده',W-150,560,42,'YKK',MU,BK,'right');X.restore();
  X.save();const g=eback(pr(t,s4+0.25,0.6));X.translate(400,380);X.scale(g,g);circle(0,0,190,BK);if(IMG.logo)X.drawImage(IMG.logo,-170,-170,340,340);X.restore();
  TL('dotcoin.me',400,630,52,'YLK',BK,'center');X.restore();}
}

// ================= ch1: the world computer
function ch1(t){base(t);mark();const o=stageO(54,600,560);const k=drift(t,0.03);X.save();X.translate(600,560);X.scale(k,k);X.translate(-600,-560);
 // s0: a definition: the glyph on its slab
 const a0=vis(t,CHD.card_end-0.3,S(1)+0.2);if(a0>0){X.save();X.globalAlpha=a0;const oo=stageO(70,620,640);const g=eback(pr(t,CHD.card_end-0.2,0.7));X.save();X.translate(620,640);X.scale(g,g);X.translate(-620,-640);shadow(oo,-2.5,-2.5,5,5);box(oo,-2.5,-2.5,0,5,5,0.9,[PALE,PERI,LIL]);X.restore();ethGlyph(620,380+Math.sin(t*2)*10,300*g);X.restore();}
 // s1: the shared ledger with a ring of nodes
 const a1=vis(t,S(1),S(2)+0.5);if(a1>0){X.save();X.globalAlpha=a1;const ringN=8;
  for(let i=0;i<ringN;i++){const ang=i/ringN*6.2832-1.2;const nx=Math.cos(ang)*5.2,ny=Math.sin(ang)*5.2;const q=eo(pr(t,S(1)+0.6+i*0.12,0.5));if(q<=0)continue;const c=P(o,0,0,0.6),n=P(o,nx,ny,0.5);X.save();X.globalAlpha*=q;line(c[0],c[1],n[0],n[1],'rgba(59,64,196,0.35)',2,[6,8]);node(o,nx-0.6,ny-0.6,0,1.2,Math.max(0,Math.sin(t*3+i))*0.6*(t>WT(1,'هزاران')?1:0));X.restore();}
  const bp=eback(pr(t,S(1),0.7));X.save();X.translate(o.x,o.y);X.scale(bp,bp);X.translate(-o.x,-o.y);box(o,-1.8,-1.4,0,3.6,2.8,0.45,[WH,PERI,LIL]);ledgerRows(o,-1.8,-1.4,0.45,3.6,2.8,pr(t,WT(1,'ثبت'),1.6),5);X.restore();
  // a ledger line as text
  const lp=eo(pr(t,WT(1,'ثبت'),0.6));if(lp>0){X.save();X.globalAlpha=lp;tile(140,850,520,96,WH,BK);rich([{s:'علی',size:38,f:'YKK',col:BK},{s:'←',size:38,f:'YKK',col:BK},{s:'سارا',size:38,f:'YKK',col:BK},{s:'۰٫۵',size:38,f:'YKE',col:BK,bg:MU}],620,898);X.restore();}
  X.restore();}
 // s2-s3: the chain of blocks; s3 opens them: money + program
 const a2=vis(t,S(2),S(4)+0.3);if(a2>0){X.save();X.globalAlpha=a2;const n=4;
  for(let i=0;i<n;i++){const q=eback(pr(t,S(2)+0.2+i*0.18,0.5));if(q<=0)continue;const x=-4.8+i*2.6;X.save();const c=P(o,x+0.9,0.9,0.9);X.translate(c[0],c[1]);X.scale(q,q);X.translate(-c[0],-c[1]);
   if(i>0)link(o,x-0.8,0.9,0.9,x,0.9,0.9,1,IND);shadow(o,x,0,1.8,1.8);chainBlock(o,x,0,0,1.8,[i===n-1?MU:PALE,WH,PERI]);
   // s3: icons pop on top: a coin and an app window
   const q3=eo(pr(t,WT(3,'پول')-0.1+i*0.08,0.45));if(q3>0){const top=P(o,x+0.9,0.9,1.8);coin(top[0]-34,top[1]-60-q3*30,26*q3,'mu',0);}
   const q4=eo(pr(t,WT(3,'برنامه')-0.1+i*0.08,0.45));if(q4>0){const top=P(o,x+0.9,0.9,1.8);X.save();X.globalAlpha*=q4;rr(top[0]+6,top[1]-118-q4*30,64,52,8);X.fillStyle=WH;X.fill();X.lineWidth=3;X.strokeStyle=IND;X.stroke();X.fillStyle=IND;X.fillRect(top[0]+6,top[1]-118-q4*30,64,12);X.fillStyle=LIL;X.fillRect(top[0]+16,top[1]-96-q4*30,30,6);X.fillStyle=MU;X.fillRect(top[0]+16,top[1]-84-q4*30,44,6);X.restore();}
   X.restore();}
    X.restore();}
 // s4-s5: the globe, a world computer; people around; no permission stamp
 const a4=vis(t,S(4),S(6)+0.3);if(a4>0){X.save();X.globalAlpha=a4;X.font=font(210,'ANT');X.textAlign='center';X.direction='ltr';X.fillStyle='rgba(59,64,196,0.10)';X.fillText('WORLD',620,300);X.fillText('COMPUTER',620,520+300);
  const gp=eback(pr(t,S(4),0.8));X.save();X.translate(620,540);X.scale(gp,gp);X.translate(-620,-540);
  // monitor frame around the globe
  rr(300,250,640,470,26);X.fillStyle=WH;X.fill();X.lineWidth=5;X.strokeStyle=BK;X.stroke();X.fillStyle=BK;X.fillRect(560,720,120,60);X.fillRect(480,775,280,18);
  globe(620,485,190,t);globeNodes(620,485,190,t,46,7,pr(t,WT(4,'هزاران'),1.2));X.restore();
  // people around (s5)
  const pp=pr(t,S(5),1.2);if(pp>0){const ps=[[150,330],[1090,330],[130,700],[1110,700],[620,950]];ps.forEach((q,i)=>{const e=eo(clamp(pp*2-i*0.25));if(e<=0)return;X.save();X.globalAlpha*=e;line(q[0],q[1],620,485,'rgba(0,0,0,0.3)',2,[5,8]);circle(q[0],q[1],46,MU,BK,3);person(q[0],q[1]+16,48,BK);X.restore();});}
  const st=eo(pr(t,WT(5,'اجازه'),0.5));if(st>0){X.save();X.globalAlpha=st;X.translate(1010,880);X.rotate(-0.12);X.scale(1+0.3*(1-st),1+0.3*(1-st));rr(-150,-52,300,104,10);X.lineWidth=6;X.strokeStyle=RED;X.stroke();T('مجوز',0,0,52,'YKE',RED,'center');line(-160,50,160,-50,BK,8);X.restore();}
  X.restore();}
 // s6: ether, the fuel
 const a6=vis(t,S(6),S(7)+0.2);if(a6>0){X.save();X.globalAlpha=a6;const g=eback(pr(t,S(6),0.7));X.save();X.translate(620,500);X.scale(g,g);coin(0,0,210,'eth',Math.sin(t*1.4)*0.25);X.restore();
  // fuel drop
  const d=eo(pr(t,WT(6,'اتر'),0.5));X.save();X.globalAlpha*=d;X.translate(900,330);X.beginPath();X.moveTo(0,-70);X.bezierCurveTo(30,-30,55,0,55,30);X.arc(0,30,55,0,Math.PI);X.bezierCurveTo(-55,0,-30,-30,0,-70);X.fillStyle=MU;X.fill();X.lineWidth=4;X.strokeStyle=BK;X.stroke();X.restore();
  chip('ETH',620,830,56,'ANT',MU,BK,'center','ltr');X.restore();}
 // s7: network vs coin
 const a7=vis(t,S(7),CHD.end);if(a7>0){X.save();X.globalAlpha=a7;const cards=[[880,'اتریوم','شبکه',0],[360,'اتر','ارز',1]];
  cards.forEach(([cx,a,b,i])=>{const q=eback(pr(t,(i?WT(7,'اتر',0,0.6):WT(7,'اتریوم',0,0.1))-0.05,0.55));if(q<=0)return;X.save();X.translate(cx,520);X.scale(q,q);tile(-210,-260,420,520,i?MU:WH,BK,22);
   if(i)coin(0,-90,100,'eth',0);else{const oo={x:0,y:-70,u:30};for(let k=0;k<5;k++){const ang=k/5*6.2832;node(oo,Math.cos(ang)*2.6-0.5,Math.sin(ang)*2.6-0.5,0,1,0);}circle(0,-90,16,MU,BK,3);}
   T(a,0,90,64,'YKE',BK,'center');T('=',0,150,40,'YKE',BK,'center');chip(b,0,215,46,'YKE',i?MU:BK,i?BK:MU,'center');X.restore();});X.restore();}
 X.restore();panel(t);panelHead(t);}

// ================= ch2: the birth
function ch2(t){base(t);mark();const k=drift(t,0.02);X.save();X.translate(620,540);X.scale(k,k);X.translate(-620,-540);
 // timeline axis (right to left: older at the right)
 const ax=pr(t,S(0)-0.3,1.2);const y0=900;line(1140,y0,lerp(1140,100,eo(ax)),y0,BK,5);
 const marks=[[1040,'۲۰۱۳',S(1)],[760,'۲۰۱۵',S(4)],[520,'۲۰۲۱',WT(5,'ارتقای',0,0.3)],[380,'۲۰۲۲',WT(5,'ارتقای',0,0.3)+0.25],[240,'۲۰۲۴',WT(5,'ارتقای',0,0.3)+0.5],[110,'۲۰۲۵',WT(5,'ارتقای',0,0.3)+0.75]];
 const labels=['','','لندن','ادغام','دنکان','پکترا'];
 marks.forEach(([x,yv,tt],i)=>{const q=eback(pr(t,tt,0.5));if(q<=0)return;circle(x,y0,14*q,i===1?MU:WH,BK,4);T(yv,x,y0+50,i<2?44:34,'YKE',BK,'center');if(labels[i]){X.save();X.globalAlpha=q;chip(labels[i],x,y0-56,26,'YKK',BK,i===3?MU:WH,'center');X.restore();}});
 // s0: an idea
 const a0=vis(t,CHD.card_end-0.3,S(1)+0.1);if(a0>0){X.save();X.globalAlpha=a0;const g=eback(pr(t,CHD.card_end-0.2,0.7));X.save();X.translate(620,470);X.scale(g,g);for(let i=0;i<8;i++){const a=i/8*6.2832+0.2;const q=0.5+0.5*Math.sin(t*3+i);line(Math.cos(a)*190,Math.sin(a)*190-40,Math.cos(a)*(230+q*20),Math.sin(a)*(230+q*20)-40,BK,8);}circle(0,-40,140,MU,BK,6);X.fillStyle=WH;X.fillRect(-60,110,120,40);X.strokeStyle=BK;X.lineWidth=6;X.strokeRect(-60,110,120,40);X.fillStyle=BK;X.fillRect(-45,150,90,26);line(-40,30,-10,-50,BK,6);line(40,30,10,-50,BK,6);X.restore();X.restore();}
 // s1: the whitepaper (2013) and a silhouette
 const a1=vis(t,S(1),S(2)+0.2);if(a1>0){X.save();X.globalAlpha=a1;const o=stageO(60,720,420);const q=eback(pr(t,WT(1,'سندی',0,0.7),0.6));
  if(q>0){X.save();const c=P(o,0,0,0);X.translate(c[0],c[1]);X.scale(q,q);X.translate(-c[0],-c[1]);shadow(o,-2.2,-3,4.4,6);docIso(o,-2.2,-3,0,4.4,6,'',1);
   onFace(o,'T',-2.2,-3,0.12,()=>{X.fillStyle=IND;X.fillRect(0.4,0.35,3.2,0.35);});X.restore();
   X.save();X.globalAlpha*=q;chip('Ethereum White Paper',720,760,32,'YLB',WH,IND,'center','ltr');X.restore();}
  const sp=eo(pr(t,WT(1,'برنامه‌نویس'),0.6));if(sp>0){X.save();X.globalAlpha*=sp;circle(300,420,120,MU,BK,4);person(300,450,130,BK);const ag=eo(pr(t,WT(1,'نوزده'),0.5));if(ag>0){X.globalAlpha=a1*ag;chip('۱۹ ساله',300,600,40,'YKE',MU,BK,'center');}X.restore();}
  X.restore();}
 // s2: bitcoin's deliberately limited language
 const a2=vis(t,S(2),S(3)+0.2);if(a2>0){X.save();X.globalAlpha=a2;const g=eback(pr(t,S(2),0.6));X.save();X.translate(420,450);X.scale(g,g);coin(0,0,150,'btc',0);X.restore();
  const tools=['ارسال','دریافت','قفل زمانی'];tools.forEach((s,i)=>{const q=eo(pr(t,S(2)+0.5+i*0.2,0.4));if(q<=0)return;X.save();X.globalAlpha*=q;tile(700,280+i*130,330,96,WH,BK,14);T(s,1000,328+i*130,40,'YKK',BK,'right');X.restore();});
  const lk=eo(pr(t,WT(2,'محدوده'),0.5));lockIcon(870,720,110,MU,lk);X.restore();}
 // s3: a chain built for any program
 const a3=vis(t,S(3),S(4)+0.2);if(a3>0){X.save();X.globalAlpha=a3;const o=stageO(64,620,520);const g=eback(pr(t,S(3),0.7));X.save();X.translate(620,520);X.scale(g,g);X.translate(-620,-520);shadow(o,-1.5,-1.5,3,3);box(o,-1.5,-1.5,0,3,3,2.4,[MU,PALE,PERI]);X.restore();
  const icons=[[AQUA,'۱'],[LIL,'۲'],[PEACH,'۳'],[PERI,'۴'],[MU,'۵'],[WH,'۶'],[AQUA,'۷'],[LIL,'۸']];icons.forEach((ic,i)=>{const q=eo(pr(t,S(3)+0.6+i*0.13,0.45));if(q<=0)return;const ang=i/8*6.2832+t*0.25;const x=620+Math.cos(ang)*360,y=440+Math.sin(ang)*230;X.save();X.globalAlpha*=q;rr(x-44,y-36,88,72,12);X.fillStyle=ic[0];X.fill();X.lineWidth=3;X.strokeStyle=IND;X.stroke();X.fillStyle=IND;X.fillRect(x-44,y-36,88,14);X.fillStyle='rgba(59,64,196,0.5)';X.fillRect(x-30,y-6,40,6);X.fillRect(x-30,y+8,56,6);X.restore();});
  X.restore();}
 // s4: launch (30 July 2015): the first block drops
 const a4=vis(t,S(4),S(5)+0.3);if(a4>0){X.save();X.globalAlpha=a4;const o=stageO(60,760,600);const q=eo(pr(t,WT(4,'سی‌ام')-0.2,0.6));const z=lerp(6,0,eio(q));
  if(q>0){shadow(o,-1,-1,2,2,0.18*q);box(o,-1,-1,z,2,2,2,[MU,PALE,PERI]);const top=P(o,0,0,z+2);ethGlyph(top[0],top[1]-70,120);}
  if(q>=1){const r=pr(t,WT(4,'سی‌ام')+0.4,0.8);circle(760,600,40+r*260,null,`rgba(243,194,66,${1-r})`,8);}
  const dc=eo(pr(t,WT(4,'سی‌ام'),0.5));if(dc>0){X.save();X.globalAlpha=dc;chip('۳۰ ژوئیه‌ی ۲۰۱۵',1100,220,44,'YKE',MU,BK,'right');X.restore();}
  const pp=pr(t,WT(4,'چند'),1.2);if(pp>0){[[300,380],[420,260],[220,560]].forEach((q2,i)=>{const e=eo(clamp(pp*2-i*0.3));if(e<=0)return;X.save();X.globalAlpha*=e;circle(q2[0],q2[1],44,WH,BK,3);person(q2[0],q2[1]+16,46,BK);X.restore();});}
  X.restore();}
 // s5: upgrades on the line (marks above), plus a teaser chip
 const a5=vis(t,S(5),CHD.end);if(a5>0){X.save();X.globalAlpha=a5;const o=stageO(40,620,520);for(let i=0;i<5;i++){const q=eback(pr(t,S(5)+0.1+i*0.12,0.5));if(q<=0)continue;const x=-5+i*2.3;box(o,x,-0.8,0,1.6,1.6,1.6,[i===2?MU:PALE,WH,PERI],2.5);if(i>0)link(o,x-0.7,0,0.8,x,0,0.8,1);}
  const q=eo(pr(t,WT(5,'مهم‌ترینش'),0.5));if(q>0){X.globalAlpha=a5*q;chip('مهم‌ترین: ادغام ۲۰۲۲',380,700,36,'YKE',BK,MU,'center');}X.restore();}
 X.restore();panel(t);panelHead(t);}

// ================= ch3: the smart contract
function ch3(t){base(t);mark();const k=drift(t,0.02);X.save();X.translate(620,540);X.scale(k,k);X.translate(-620,-540);
 // s0: a contract seal
 const a0=vis(t,S(0)-0.2,S(1)+0.1);if(a0>0){X.save();X.globalAlpha=a0;const o=stageO(64,620,560);const g=eback(pr(t,S(0)-0.1,0.7));X.save();X.translate(620,540);X.scale(g,g);X.translate(-620,-540);shadow(o,-2,-2.6,4,5.2);docIso(o,-2,-2.6,0,4,5.2,'',1);const c=P(o,1.2,1.8,0.2);circle(c[0],c[1],62,MU,BK,4);X.save();X.translate(c[0],c[1]);X.rotate(t*0.8);for(let i=0;i<8;i++){X.rotate(0.785);X.fillStyle=BK;X.fillRect(-6,-58,12,18);}X.restore();circle(c[0],c[1],30,BK);X.restore();X.restore();}
 // s1-s2: the vending machine
 const a1=vis(t,S(1),S(3)+0.25);if(a1>0){X.save();X.globalAlpha=a1;const o=stageO(64,600,560);const g=eback(pr(t,S(1),0.7));X.save();X.translate(560,560);X.scale(g,g);X.translate(-560,-560);
  vending(o,-1.2,-0.8,-2.1,t,WT(2,'پول',0,0.05),WT(2,'دکمه',0,0.25),WT(2,'نوشیدنی',0,0.45));X.restore();
  const rp=eo(pr(t,WT(2,'قانون',0,0.7),0.5));if(rp>0){X.save();X.globalAlpha=rp;tile(140,800,380,110,BK,null,14);T('قانون از قبل نوشته شده',490,855,34,'YKK',MU,'right');X.restore();}
  X.restore();}
 // s3: IF -> THEN
 const a3=vis(t,S(3),S(4)+0.1);if(a3>0){X.save();X.globalAlpha=a3;const p1=eback(pr(t,S(3)+0.3,0.5)),p2=eback(pr(t,S(3)+(E(3)-S(3))*0.5,0.5));
  if(p1>0){X.save();X.translate(880,520);X.scale(p1,p1);tile(-210,-140,420,280,WH,BK,22);chip('اگر',190,-90,40,'YKE',BK,MU,'right');T('شرط برقرار شد',190,10,48,'YKE',BK,'right');T('مثلاً: کار تحویل شد',190,80,32,'YKB','rgba(0,0,0,0.6)','right');X.restore();}
  arrow(650,520,560,520,eo(pr(t,S(3)+(E(3)-S(3))*0.42,0.4)),BK,8,26);
  if(p2>0){X.save();X.translate(330,520);X.scale(p2,p2);tile(-210,-140,420,280,MU,BK,22);chip('آنگاه',190,-90,40,'YKE',MU,BK,'right');T('خودکار اجرا شو',190,10,48,'YKE',BK,'right');T('بدون دخالت هیچ‌کس',190,80,32,'YKB','rgba(0,0,0,0.6)','right');X.restore();}
  X.restore();}
 // s4-s6: designer, customer, escrow contract; no middleman
 const a4=vis(t,S(4),S(7)+0.2);if(a4>0){X.save();X.globalAlpha=a4;const L=[230,560],R=[1010,560],M=[620,600];
  // dotted world arc
  X.beginPath();X.moveTo(L[0],L[1]-80);X.quadraticCurveTo(620,120,R[0],R[1]-80);X.setLineDash([4,12]);X.strokeStyle='rgba(0,0,0,0.35)';X.lineWidth=4;X.stroke();X.setLineDash([]);
  [[L,'طراح',MU,WT(4,'طراح')],[R,'مشتری',WH,WT(4,'مشتری')]].forEach(([p,s,c,tt])=>{const q=eback(pr(t,tt-0.1,0.5));if(q<=0)return;X.save();X.translate(p[0],p[1]);X.scale(q*0.82,q*0.82);circle(0,-30,110,c,BK,4);person(0,-10,120,BK);chip(s,0,120,40,'YKE',c===MU?BK:MU,c===MU?MU:BK,'center');X.restore();});
  // the contract box in the middle (s5)
  const cb=eback(pr(t,WT(5,'قرارداد',0,0.1),0.6));if(cb>0){const o={x:M[0],y:M[1]-30,u:56*cb};box(o,-1.3,-1.3,0,2.6,2.6,2.2,[PALE,WH,PERI]);const top=P(o,0,0,2.2);lockIcon(top[0],top[1]-70*cb,90*cb,MU,1);T('قرارداد هوشمند',M[0],M[1]+200,36,'YKK',BK,'center');}
  // coins in from the customer, then out to the designer
  const tin=WT(5,'می‌ذاره',0,0.12),tout=WT(5,'فرستاده',0,0.85);
  for(let i=0;i<5;i++){const q=pr(t,tin+i*0.12,0.8);if(q>0&&q<1){const e=eio(q);coin(lerp(R[0]-60,M[0]+30,e),lerp(R[1]-120,M[1]-150,e)-Math.sin(e*Math.PI)*120,24,'mu',0);}
   const r=pr(t,tout+i*0.12,0.8);if(r>0&&r<1){const e=eio(r);coin(lerp(M[0]-30,L[0]+60,e),lerp(M[1]-150,L[1]-120,e)-Math.sin(e*Math.PI)*120,24,'mu',0);}}
  [[WT(5,'تأیید',0,0.6),L],[WT(5,'تأیید',0,0.6)+0.2,R]].forEach(([tt,p])=>{const q=eo(pr(t,tt,0.4));if(q>0){circle(p[0]+90,p[1]-130,34*q,GRN,BK,3);check(p[0]+90,p[1]-130,32,WH,q,6);}});
  // s6: no middleman
  const nb=eo(pr(t,S(6),0.5));if(nb>0){X.save();X.globalAlpha*=nb;tile(470,140,300,220,WH,BK,18);bank(620,250,80,PALE);cross(620,250,170,RED,eo(pr(t,WT(6,'واسطه'),0.5)),14);X.restore();}
  X.restore();}
 // s7-s8: the EVM: the same code on every node, the same result
 const a7=vis(t,S(7),S(9)+0.15);if(a7>0){X.save();X.globalAlpha=a7;codeCard(470,120,300,200,t,eo(pr(t,S(7),0.6)));T('EVM',620,350,40,'ANT',BK,'center','ltr');
  const o=stageO(40,620,690);const xs=[-9,-5.4,-1.8,1.8,5.4];xs.forEach((x,i)=>{const q=eback(pr(t,WT(7,'همه‌ی')+i*0.1,0.5));if(q<=0)return;const n=P(o,x+1.2,-x*0+1.2-1.2,0);
   const c=P(o,x,0,1.6);X.save();X.globalAlpha*=q;line(620,330,c[0]+20,c[1]-60,'rgba(59,64,196,0.4)',2,[5,7]);node(o,x-0.6+0,-0.6+x*0,0,2.4,0.0);X.restore();
   const bad=i===3&&t>S(8)&&t<S(9);const rq=eo(pr(t,WT(7,'نتیجه',0,0.8)+i*0.1,0.4));if(rq>0){const rx=c[0]+30,ry=c[1]-130;circle(rx,ry,32*rq,bad?RED:GRN,BK,3);if(bad)cross(rx,ry,30,WH,1,6);else check(rx,ry,30,WH,rq,6);}});
  const rej=eo(pr(t,WT(8,'یواشکی'),0.5));if(rej>0&&t<S(9)){X.save();X.globalAlpha=a7*rej;chip('رد شد',P(o,1.8,0,1.6)[0]+30,P(o,1.8,0,1.6)[1]-210,32,'YKE',WH,RED,'center');X.restore();}
  X.restore();}
 // s9-s10: a bug runs exactly as written; the audit
 const a9=vis(t,S(9),CHD.end);if(a9>0){X.save();X.globalAlpha=a9;codeCard(160,180,640,520,t,eo(pr(t,S(9),0.6)),t>WT(9,'اشتباه')?6:-1);
  const op=eo(pr(t,WT(9,'اشتباهش'),0.5));if(op>0){arrow(820,440,960,440,op,BK,7,22);circle(1060,440,70*op,RED,BK,4);cross(1060,440,60,WH,op,10);}
  const mp=eo(pr(t,S(10),0.5));if(mp>0){const sx=lerp(250,700,0.5+0.5*Math.sin((t-S(10))*1.6));magnifier(sx,420,200,mp);}
  const sh=eback(pr(t,WT(10,'بازرسی',0,0.6),0.6));if(sh>0){X.save();X.translate(1060,440);X.scale(sh,sh);X.translate(-1060,-440);X.fillStyle=PAPER;X.fillRect(980,360,170,170);shield(1060,440,170,MU,1);check(1060,440,70,BK,eo(pr(t,WT(10,'بازرسی',0,0.6)+0.3,0.5)),12);X.restore();}
  X.restore();}
 X.restore();panel(t);panelHead(t);}

// ================= ch4: ether and gas
function gasPump(cx,cy,s,t,val){X.save();X.translate(cx,cy);tile(-s*0.5,-s*0.8,s,s*1.5,WH,BK,18);rr(-s*0.38,-s*0.68,s*0.76,s*0.42,10);X.fillStyle=BK;X.fill();T(sep(val),s*0.32,-s*0.47,s*0.16,'YKE',MU,'right');TL('GAS',-s*0.32,-s*0.47,s*0.13,'ANT',WH);
 X.fillStyle=MU;X.fillRect(-s*0.5,s*0.42,s,s*0.28);X.strokeStyle=BK;X.lineWidth=3.5;X.strokeRect(-s*0.5,s*0.42,s,s*0.28);
 X.beginPath();X.moveTo(s*0.5,-s*0.2);X.bezierCurveTo(s*0.85,-s*0.2,s*0.85,s*0.5,s*0.7,s*0.55);X.lineWidth=10;X.strokeStyle=BK;X.stroke();X.restore();}
function ch4(t){base(t);mark();const k=drift(t,0.02);X.save();X.translate(620,540);X.scale(k,k);X.translate(-620,-540);
 // s0: the node working on two kinds of work
 const a0=vis(t,S(0),S(1)+0.1);if(a0>0){X.save();X.globalAlpha=a0;const o=stageO(80,620,520);const g=eback(pr(t,S(0),0.6));X.save();X.translate(620,520);X.scale(g,g);X.translate(-620,-520);shadow(o,-1.5,-1.5,3,3);node(o,-1.5,-1.5,0,3,0.4+0.4*Math.sin(t*6));X.restore();
  [['انتقال ساده',WT(0,'انتقال'),300],['اجرای قرارداد',WT(0,'قرارداد'),940]].forEach(([s,tt,x])=>{const q=eo(pr(t,tt,0.5));if(q>0){X.save();X.globalAlpha*=q;chip(s,x,820,38,'YKE',BK,x<600?WH:MU,'center');X.restore();}});
  const w=pr(t,WT(0,'محاسباتی'),1.4);if(w>0){X.fillStyle=BK;X.fillRect(370,900,500,14);X.fillStyle=MU;X.fillRect(370+500*(1-eo(w)),900,500*eo(w),14);}
  X.restore();}
 // s1: the pump: gas is the unit of work
 const a1=vis(t,S(1),S(2)+0.1);if(a1>0){X.save();X.globalAlpha=a1;const g=eback(pr(t,S(1),0.6));X.save();X.translate(620,520);X.scale(g,g);gasPump(0,0,420,t,counter(21000,t,WT(1,'گس')));X.restore();X.restore();}
 // s2: 21,000 vs a complex contract
 const a2=vis(t,S(2),S(3)+0.1);if(a2>0){X.save();X.globalAlpha=a2;const base0=820;const h1=eo(pr(t,WT(2,'بیست‌ویک'),0.8))*160,h2=eo(pr(t,WT(2,'پیچیده'),1.0))*560;
  tile(760,base0-h1,220,h1,PERI,BK,8);T(sep(counter(21000,t,WT(2,'بیست‌ویک'))),870,base0-h1-50,56,'YKE',BK,'center');T('انتقال ساده‌ی اتر',870,base0+50,36,'YKK',BK,'center');
  tile(280,base0-h2,220,h2,MU,BK,8);if(h2>10){T('خیلی بیشتر',390,base0-h2-50,46,'YKE',BK,'center');}T('قرارداد پیچیده',390,base0+50,36,'YKK',BK,'center');X.fillStyle=BK;X.fillRect(200,base0,860,5);X.restore();}
 // s3-s5: the formula, gwei, the worked example
 const a3=vis(t,S(3),S(6)+0.15);if(a3>0){X.save();X.globalAlpha=a3;
  const f1=eback(pr(t,WT(3,'مقدار'),0.5)),f2=eback(pr(t,WT(3,'قیمت'),0.5)),f0=eback(pr(t,WT(3,'کارمزدی'),0.5));
  const ex=t>WT(5,'بیست‌ویک',0,0.3);const res=t>WT(5,'چهارصد',0,0.55);const eth=t>WT(5,'چهل',0,0.8);
  const box3=(cx,cy,q,top,val,bg)=>{if(q<=0)return;X.save();X.translate(cx,cy);X.scale(q,q);tile(-170,-110,340,220,bg,BK,18);T(top,0,-50,30,'YKB',BK,'center');T(val,0,30,56,'YKE',BK,'center');X.restore();};
  box3(1000,330,f0,'کارمزد',res?sep(420000):'؟',MU);T('=',800,330,80,'YKE',BK,'center');box3(600,330,f2,'قیمت هر گس',ex?'۲۰ گوئی':'گوئی',WH);T('×',400,330,80,'YKE',BK,'center');box3(200,330,f1,'گس مصرفی',ex?sep(21000):'گس',WH);
  if(res){const q=eo(pr(t,WT(5,'چهارصد',0,0.55),0.5));X.save();X.globalAlpha*=q;T('گوئی',1000,420,26,'YKB',BK,'center');X.restore();}
  // gwei: 1 ETH = 1,000,000,000 gwei
  const gp=eo(pr(t,WT(4,'گوئی'),0.6));if(gp>0){X.save();X.globalAlpha*=gp;tile(150,560,940,190,BK,null,22);coin(1000,655,62,'eth',0);rich([{s:'۱ اتر',size:52,f:'YKE',col:WH},{s:'=',size:52,f:'YKE',col:WH,dir:'ltr'},{s:sep(counter(1000000000,t,WT(4,'میلیارد'),1.2)),size:58,f:'YKE',col:BK,bg:MU},{s:'گوئی',size:52,f:'YKE',col:WH}],910,655);X.restore();}
  if(eth){const q=eback(pr(t,WT(5,'چهل',0,0.8),0.5));X.save();X.translate(620,880);X.scale(q,q);chip('= ۰٫۰۰۰۴۲ اتر',0,0,50,'YKE',MU,BK,'center');X.restore();}
  X.restore();}
 // s6: a block has limited room; s7: busy network, the base fee follows
 const a6=vis(t,S(6),S(8)+0.1);if(a6>0){X.save();X.globalAlpha=a6;const o=stageO(30,420,300);const cols=6,rows=5;const fill=pr(t,S(6)+0.3,2.0);
  tile(140,200,560,470,WH,BK,20);T('یک بلوک',680,240,32,'YKE',BK,'right');for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){const i=r*cols+c;const q=clamp(fill*cols*rows-i);const x=180+c*84,y=280+r*74;rr(x,y,70,58,8);X.fillStyle=q>0.5?(i%7===0?MU:PERI):'rgba(0,0,0,0.06)';X.fill();X.lineWidth=2;X.strokeStyle=q>0.5?IND:'rgba(0,0,0,0.15)';X.stroke();}
  // the queue outside
  for(let i=0;i<7;i++){const q=eo(pr(t,WT(6,'محدوده')+i*0.08,0.4));if(q<=0)continue;rr(760+i*62,430-(i%2)*30,50,46,8);X.fillStyle=LIL;X.globalAlpha=a6*q;X.fill();X.strokeStyle=IND;X.stroke();X.globalAlpha=a6;}
  // s7: chart: traffic bars and the base fee line
  const cp=pr(t,S(7),2.2);if(cp>0){const x0=140,y0=960,w=960,h=220;X.fillStyle=BK;X.fillRect(x0,y0,w,4);const n=24;let pts=[];for(let i=0;i<n;i++){const v=0.25+0.65*Math.max(0,Math.sin(i/n*Math.PI*1.4))+0.08*Math.sin(i*1.7);const q=clamp(cp*n*1.2-i);const bh=v*h*0.8*q;X.fillStyle='rgba(136,170,241,0.6)';X.fillRect(x0+w-(i+1)*w/n+4,y0-bh,w/n-8,bh);pts.push([x0+w-(i+0.5)*w/n,y0-v*h*0.95,q]);}
   X.beginPath();pts.forEach((p,i)=>{if(p[2]<=0)return;i?X.lineTo(p[0],p[1]):X.moveTo(p[0],p[1]);});X.strokeStyle=BK;X.lineWidth=5;X.stroke();
   T('شلوغی شبکه',x0+w,y0+36,28,'YKB',IND,'right');const lp=eo(pr(t,WT(7,'قیمت'),0.4));X.save();X.globalAlpha*=lp;chip('قیمت پایه‌ی گس',x0+w-40,y0-h-40,30,'YKE',MU,BK,'right');X.restore();}
  X.restore();}
 // s8: the base fee is burned (since 2021); s9: the tip
 const a8=vis(t,S(8),S(10)+0.1);if(a8>0){X.save();X.globalAlpha=a8;const fb=eo(pr(t,S(8),0.5));
  tile(200,190,840,130,WH,BK,18);T('کارمزد تو',1000,255,44,'YKE',BK,'right');coin(300,255,46,'eth',0);
  const sp=eo(pr(t,S(9)-0.4,0.6));// the split
  arrow(780,330,780,470,eo(pr(t,S(8)+0.3,0.5)),BK,6,20);tile(560,480,440,150,MU,BK,18);T('قیمت پایه',970,530,42,'YKE',BK,'right');T('سوزانده می‌شود',970,590,32,'YKB',BK,'right');
  const bt=WT(8,'سوزونده',0,0.5);flame(660,560,120,t,eo(pr(t,bt,0.5)));const bc=pr(t,bt,1.2);if(bc>0&&bc<1){coin(660,560-bc*20,40*(1-bc),'eth',0);}
  const yc=eo(pr(t,WT(8,'دو',0,0.2),0.4));if(yc>0){X.save();X.globalAlpha*=yc;chip('از ۲۰۲۱',560,450,30,'YKE',MU,BK,'left');X.restore();}
  if(sp>0){X.save();X.globalAlpha*=sp;arrow(420,330,420,470,sp,BK,6,20);tile(200,480,330,150,WH,BK,18);T('انعام',500,530,42,'YKE',BK,'right');T('برای اعتبارسنج',500,590,32,'YKB',BK,'right');X.restore();}
  X.restore();}
 // s10: ether, the fuel of the whole network
 const a10=vis(t,S(10),CHD.end);if(a10>0){X.save();X.globalAlpha=a10;globe(760,500,200,t);globeNodes(760,500,200,t,40,4,pr(t,S(10)+0.3,1.2));
  const q=eback(pr(t,S(10),0.6));X.save();X.translate(330,560);X.scale(q,q);tile(-130,-190,260,380,MU,BK,30);coin(0,-30,90,'eth',Math.sin(t*1.5)*0.3);T('سوخت',0,130,44,'YKE',BK,'center');X.restore();
  for(let i=0;i<5;i++){const r=((t-S(10))*0.8+i/5)%1;if(t<S(10)+0.5)break;circle(lerp(460,560,r),lerp(560,500,r),8,MU,BK,2);}X.restore();}
 X.restore();panel(t);panelHead(t);}

// ================= ch5: proof of stake
function ch5(t){base(t);mark();const k=drift(t,0.02);X.save();X.translate(620,540);X.scale(k,k);X.translate(-620,-540);
 // s0: the next block, empty
 const a0=vis(t,S(0),S(1)+0.1);if(a0>0){X.save();X.globalAlpha=a0;const o=stageO(64,620,560);for(let i=0;i<3;i++){const x=-6+i*2.6;box(o,x,0,0,1.8,1.8,1.8,[PALE,WH,PERI]);if(i>0)link(o,x-0.8,0.9,0.9,x,0.9,0.9);}
  const q=eback(pr(t,S(0)+0.3,0.6));X.save();X.translate(...P(o,2.6,0.9,0.9));X.scale(q,q);X.setLineDash([10,10]);const oo={x:0,y:0,u:64};box(oo,-0.9,-0.9,-0.9,1.8,1.8,1.8,['rgba(243,194,66,0.25)',null,null],3,BK);X.setLineDash([]);T('؟',0,-40,110,'YKE',BK,'center');X.restore();X.restore();}
 // s1: proof of work: power-hungry rigs
 const a1=vis(t,S(1),S(2)+0.4);if(a1>0){X.save();X.globalAlpha=a1;const o=stageO(54,620,540);
  for(let i=0;i<3;i++)for(let j=0;j<2;j++){const q=eback(pr(t,S(1)+0.2+(i+j*3)*0.1,0.5));if(q<=0)continue;rig(o,-4+i*2.6,-2.5+j*2.8,0,2,t,(Math.sin(t*5+i*2+j)>0.2?1:0)*eo(pr(t,WT(1,'پرمصرف'),0.4)));}
  const pp=eo(pr(t,WT(1,'معما'),0.5));if(pp>0){X.save();X.globalAlpha*=pp;tile(860,150,240,160,WH,BK,16);T('#?',980,230,70,'ANT',BK,'center','ltr');X.restore();}
  X.restore();}
 // s2: the merge: two chains become one (15 September 2022)
 const a2=vis(t,S(2),S(4)+0.2);if(a2>0){X.save();X.globalAlpha=a2;const m=eio(pr(t,WT(2,'مِرج',0,0.7)-0.4,1.2));
  const yA=lerp(330,540,m),yB=lerp(750,540,m);for(let i=0;i<7;i++){const x=1080-i*150;const q=eo(pr(t,S(2)+i*0.06,0.4));if(q<=0)continue;
   // upper chain: proof of work (bolts), lower: the beacon chain (coins)
   const fu=i<4?1:1-m,fl=i<4?1-m:1;
   if(fl>0){X.save();X.globalAlpha*=fl;tile(x-55,yB-55,110,110,PALE,BK,10);coin(x,yB,30,'eth',0);X.restore();}
   if(fu>0){X.save();X.globalAlpha*=fu;tile(x-55,yA-55,110,110,'#5C5F7A',BK,10);bolt(x,yA,40,MU);X.restore();}}
  if(m<0.3){X.save();X.globalAlpha*=1-m/0.3;T('اثبات کار',1140,yA-100,30,'YKE',BK,'right');T('زنجیره‌ی اثبات سهام',1140,yB+100,30,'YKE',BK,'right');X.restore();}
  const lab=eo(pr(t,WT(2,'پونزدهم'),0.5));if(lab>0){X.save();X.globalAlpha*=lab;chip('۱۵ سپتامبر ۲۰۲۲',1100,140,42,'YKE',MU,BK,'right');X.restore();}
  if(m>0.5){X.save();X.globalAlpha*=eo(pr(t,WT(2,'مِرج',0,0.7)+0.4,0.5));T('THE MERGE',620,860,90,'ANT',BK,'center','ltr');X.restore();}
  X.restore();}
 // s4: validators lock 32 ETH
 const a4=vis(t,S(4),S(5)+0.1);if(a4>0){X.save();X.globalAlpha=a4;const o=stageO(60,520,640);shadow(o,-2,-2,4,4);box(o,-2,-2,0,4,4,2.6,['#2E3046','#43465E','#5C5F7A'],3,BK);
  onFace(o,'L',-2,2,2.6,()=>{X.beginPath();X.arc(2,1.3,0.75,0,6.2832);X.fillStyle=MU;X.fill();X.lineWidth=0.06;X.strokeStyle=BK;X.stroke();X.save();X.translate(2,1.3);X.rotate(t);for(let i=0;i<3;i++){X.rotate(2.09);X.fillStyle=BK;X.fillRect(-0.05,-0.6,0.1,0.45);}X.restore();});
  const n=counter(32,t,WT(4,'سی‌ودو',0,0.8)-0.6,1.1);for(let i=0;i<Math.min(n,32);i++){const c=P(o,1.1,-1.4,2.6+i*0.13);X.save();X.beginPath();X.ellipse(c[0],c[1],48,18,0,0,6.2832);X.fillStyle=i===n-1?MU:'#ECEFFE';X.fill();X.lineWidth=2.5;X.strokeStyle=IND;X.stroke();X.restore();}
  tile(820,330,300,230,MU,BK,22);T(fa(n),970,420,110,'YKE',BK,'center');T('اتر',970,510,40,'YKE',BK,'center');
  T('اعتبارسنج',520,960,40,'YKE',BK,'center');X.restore();}
 // s5: every 12 seconds a block is proposed and attested
 const a5=vis(t,S(5),S(6)+0.1);if(a5>0){X.save();X.globalAlpha=a5;const f=((t-S(5))/(E(5)-S(5)+0.6))%1;clockRing(330,470,170,eo(pr(t,S(5),1.4)));T('۱۲',330,450,90,'YKE',BK,'center');T('ثانیه',330,530,32,'YKB',BK,'center');
  const ns=7;for(let i=0;i<ns;i++){const ang=-1.2+i*(2.4/(ns-1));const x=880+Math.cos(ang+Math.PI)*-240,y=470+Math.sin(ang)*300;const pro=i===3;circle(x,y,46,pro?MU:WH,BK,4);person(x,y+12,44,BK);
   const q=eo(pr(t,WT(5,'تأیید',0,0.7)+Math.abs(i-3)*0.12,0.4));if(!pro&&q>0){circle(x+38,y-38,20*q,GRN,BK,2);check(x+38,y-38,20,WH,q,4);}}
  const bq=eback(pr(t,WT(5,'پیشنهاد'),0.5));if(bq>0){X.save();X.translate(880,470);X.scale(bq,bq);tile(-60,-60,120,120,MU,BK,12);ethGlyph(0,0,70);X.restore();}
  X.restore();}
 // s6: honest -> reward (green), cheating -> loses part of the stake (red)
 const a6=vis(t,S(6),S(7)+0.1);if(a6>0){X.save();X.globalAlpha=a6;const L=[880,480],R=[360,480];
  const q1=eback(pr(t,S(6),0.5)),q2=eback(pr(t,WT(6,'تقلب'),0.5));
  if(q1>0){X.save();X.translate(...L);X.scale(q1,q1);tile(-200,-220,400,440,WH,BK,22);circle(0,-80,70,MU,BK,4);person(0,-60,76,BK);chip('+ پاداش',0,110,44,'YKE',WH,GRN,'center');X.restore();}
  if(q2>0){X.save();X.translate(...R);X.scale(q2,q2);tile(-200,-220,400,440,WH,BK,22);circle(0,-80,70,PALE,BK,4);person(0,-60,76,BK);chip('− بخشی از سهم',0,110,40,'YKE',WH,RED,'center');
   for(let i=0;i<3;i++){const f=pr(t,WT(6,'دست')+i*0.15,0.9);if(f>0&&f<1)coin(-60+i*60,160+f*160,22,'eth',f*4);}X.restore();}
  X.restore();}
 // s7: energy use fell about 99.95% (Ethereum Foundation estimate)
 const a7=vis(t,S(7),S(8)+0.1);if(a7>0){X.save();X.globalAlpha=a7;const sh=eio(pr(t,WT(7,'کم',0,0.85)-0.3,1.0));
  T('مصرف برق شبکه',1100,250,44,'YKE',BK,'right');bolt(1150,420,60,MU);
  tile(160,370,880,110,BK,null,8);T('قبل از ادغام',1110,425,30,'YKK',BK,'right');T('بعد از ادغام',1110,575,30,'YKK',BK,'right');
  const aw=lerp(880,6,sh);tile(160,520,aw,110,MU,BK,8);
  const v=(99.98*eo(pr(t,WT(7,'نود'),1.2))).toFixed(2);const q=eo(pr(t,WT(7,'نود'),0.4));if(q>0){X.save();X.globalAlpha*=q;T('٪'+fa(v).replace('.','٫'),620,800,170,'YKE',BK,'center','rtl');chip('بیش از این · برآورد منتشرشده در سایت رسمی اتریوم',620,950,30,'YKK',MU,BK,'center');X.restore();}
  X.restore();}
 // s8: security from capital, not electricity: a balance
 const a8=vis(t,S(8),CHD.end);if(a8>0){X.save();X.globalAlpha=a8;const sw=eio(pr(t,WT(8,'سرمایه',0,0.6)-0.3,0.9));const ang=lerp(-0.16,0.16,sw);
  X.fillStyle=BK;X.beginPath();X.moveTo(620,460);X.lineTo(540,860);X.lineTo(700,860);X.closePath();X.fill();X.fillRect(470,850,300,22);
  X.save();X.translate(620,460);X.rotate(ang);rr(-400,-10,800,20,10);X.fillStyle=BK;X.fill();
  const pan=(px,draw)=>{X.save();X.translate(px,0);X.rotate(-ang);line(-90,0,0,-1,BK,0);line(0,0,-80,150,BK,4);line(0,0,80,150,BK,4);X.beginPath();X.ellipse(0,160,110,26,0,0,6.2832);X.fillStyle=MU;X.fill();X.lineWidth=4;X.strokeStyle=BK;X.stroke();draw();X.restore();};
  pan(380,()=>{X.save();X.globalAlpha*=1-sw;bolt(0,90,70,MU);X.restore();});
  pan(-380,()=>{X.save();X.globalAlpha*=clamp(sw*1.5);for(let i=0;i<5;i++){X.beginPath();X.ellipse(0,140-i*20,62,20,0,0,6.2832);X.fillStyle='#ECEFFE';X.fill();X.lineWidth=3;X.strokeStyle=IND;X.stroke();}ethGlyph(0,40,70);X.restore();});
  X.restore();
  const lb=eo(pr(t,WT(8,'امنیت'),0.5));if(lb>0){X.save();X.globalAlpha*=lb;chip('امنیت شبکه',620,300,48,'YKE',MU,BK,'center');X.restore();}
  T('برق',1000,780,36,'YKE',BK,'center');T('سرمایه',240,780,36,'YKE',BK,'center');
  X.restore();}
 X.restore();panel(t);panelHead(t);}

// ================= ch6: the world on Ethereum
function lego(x,y,w,h,col,label){X.save();for(let i=0;i<Math.round(w/70);i++){rr(x+14+i*70,y-16,44,20,6);X.fillStyle=col;X.fill();X.lineWidth=3;X.strokeStyle=BK;X.stroke();}tile(x,y,w,h,col,BK,10);T(label,x+w/2,y+h/2,40,'YKE',BK,'center');X.restore();}
function ch6(t){base(t);mark();const k=drift(t,0.02);X.save();X.translate(620,540);X.scale(k,k);X.translate(-620,-540);const o=stageO(54,620,640);
 // the platform slab (all chapter long)
 const sp=eback(pr(t,S(0),0.7));X.save();X.translate(620,640);X.scale(sp,sp);X.translate(-620,-640);shadow(o,-4,-4,8,8,0.12);box(o,-4,-4,0,8,8,0.7,[PALE,PERI,LIL]);const top=P(o,0,0,0.7);X.save();X.translate(top[0],top[1]);X.scale(1,0.58);X.globalAlpha=0.9;ethGlyph(0,0,180);X.restore();X.restore();
 // s1: tokens pop out of a contract
 const a1=vis(t,S(1),S(4)+0.1);if(a1>0){X.save();X.globalAlpha=a1;const kinds=['mu','lil','aqua','peach','peri'];for(let i=0;i<5;i++){const q=eback(pr(t,WT(1,'توکن')+i*0.14,0.6));if(q<=0)continue;const x=260+i*175,y=300-Math.sin(i*1.3)*30;X.save();X.translate(x,y);X.scale(q,q);coin(0,0,62,kinds[i],Math.sin(t*1.5+i)*0.4);X.fillStyle=BK;if(i%3===0){X.fillRect(-18,-18,36,36);}else if(i%3===1){X.beginPath();X.moveTo(0,-22);X.lineTo(22,16);X.lineTo(-22,16);X.closePath();X.fill();}else circle(0,0,20,BK);X.restore();}
  // s2: the common standard: every token fits the same socket
  const s2=eo(pr(t,S(2),0.5));if(s2>0){X.save();X.globalAlpha*=s2;tile(370,430,500,120,BK,null,16);TL('ERC-20',620,490,74,'ANT',MU,'center');X.restore();for(let i=0;i<5;i++){const q=eo(pr(t,WT(2,'بشناسن')+i*0.08,0.4));if(q>0)line(260+i*175,360,620,430,'rgba(0,0,0,0.35)',2.5,[6,6]);}}
  // s3: tether on ERC-20
  const s3=eback(pr(t,S(3),0.6));if(s3>0){X.save();X.translate(940,780);X.scale(s3,s3);coin(0,0,80,'usdt',0);X.restore();X.save();X.globalAlpha*=eo(pr(t,WT(3,'تتری'),0.5));rich([{s:'تتر روی',size:38,f:'YKE',col:BK},{s:'ERC-20',size:38,f:'YLK',col:MU,bg:BK,dir:'ltr'}],830,780);X.restore();}
  X.restore();}
 // s4: DeFi: loan, saving, swap
 const a4=vis(t,S(4),S(5)+0.1);if(a4>0){X.save();X.globalAlpha=a4;const items=[['وام',Math.min(WT(4,'وام'),S(4)+0.5)],['پس‌انداز',WT(4,'پس‌انداز')],['تبادل ارز',WT(4,'تبادل')]];
  items.forEach(([s,tt],i)=>{const q=eback(pr(t,tt-0.15,0.5));if(q<=0)return;const x=960-i*340;X.save();X.translate(x,330);X.scale(q,q);tile(-150,-150,300,300,i===1?MU:WH,BK,22);
   if(i===0){X.beginPath();X.ellipse(0,10,80,34,0,0,6.2832);X.fillStyle=PEACH;X.fill();X.lineWidth=4;X.strokeStyle=BK;X.stroke();coin(0,-40,40,'mu',0);}
   if(i===1){const oo={x:0,y:-10,u:34};box(oo,-1.2,-1.2,-1,2.4,2.4,1.8,['#2E3046','#43465E','#5C5F7A'],3,BK);circle(0,0,18,MU,BK,3);}
   if(i===2){coin(-40,-10,40,'lil',0);coin(40,-10,40,'aqua',0);arrow(-30,-70,30,-70,1,BK,4,12);arrow(30,50,-30,50,1,BK,4,12);}
   T(s,0,105,42,'YKE',BK,'center');X.restore();});X.restore();}
 // s5: NFT: a unique artwork or a ticket, with a certificate
 const a5=vis(t,S(5),S(6)+0.1);if(a5>0){X.save();X.globalAlpha=a5;const q=eback(pr(t,S(5)+0.3,0.6));if(q>0){X.save();X.translate(780,340);X.scale(q,q);X.rotate(-0.04);tile(-190,-200,380,400,WH,BK,8);X.fillStyle=AQUA;X.fillRect(-160,-170,320,340);circle(-40,-40,80,MU,BK,4);X.fillStyle=LIL;X.beginPath();X.moveTo(-160,170);X.lineTo(20,-10);X.lineTo(160,170);X.closePath();X.fill();X.strokeStyle=BK;X.stroke();circle(70,-100,30,PEACH,BK,3);X.restore();}
  const q2=eback(pr(t,WT(5,'بلیت')-0.1,0.6));if(q2>0){X.save();X.translate(360,360);X.scale(q2,q2);X.rotate(0.08);tile(-170,-90,340,180,MU,BK,14);X.setLineDash([8,8]);line(70,-90,70,90,BK,3);X.setLineDash([]);T('بلیت',-50,-20,50,'YKE',BK,'center');T('شماره‌ی ۰۰۷',-50,40,26,'YKB',BK,'center');X.restore();}
  const sq=eo(pr(t,WT(5,'گواهی'),0.5));if(sq>0){circle(940,510,56*sq,GRN,BK,4);check(940,510,50,WH,sq,8);}X.restore();}
 // s6: more uses: voting and games
 const a6=vis(t,S(6),S(7)+0.1);if(a6>0){X.save();X.globalAlpha=a6;[['رأی‌گیری',WT(6,'رأی‌گیری'),860],['بازی',WT(6,'بازی'),380]].forEach(([s,tt,x],i)=>{const q=eback(pr(t,tt-0.15,0.5));if(q<=0)return;X.save();X.translate(x,340);X.scale(q,q);tile(-160,-150,320,300,i?WH:MU,BK,22);
   if(i===0){tile(-70,-60,140,110,WH,BK,8);X.fillStyle=BK;X.fillRect(-40,-62,80,10);rr(-30,-110,60,70,6);X.fillStyle=PEACH;X.fill();X.stroke();}
   else{rr(-90,-60,180,100,40);X.fillStyle=LIL;X.fill();X.lineWidth=4;X.strokeStyle=BK;X.stroke();X.fillStyle=BK;X.fillRect(-60,-16,40,10);X.fillRect(-45,-31,10,40);circle(45,-20,10,MU,BK,2);circle(60,0,10,AQUA,BK,2);}
   T(s,0,95,42,'YKE',BK,'center');X.restore();});X.restore();}
 // s7: an Ethereum wallet; its address starts with 0x
 const a7=vis(t,S(7),S(8)+0.1);if(a7>0){X.save();X.globalAlpha=a7;const q=eback(pr(t,S(7)+0.2,0.6));X.save();X.translate(620,330);X.scale(q,q);tile(-330,-150,660,300,WH,BK,26);walletIcon(220,-30,150,MU);T('کیف‌پول اتریوم',110,-60,40,'YKE',BK,'right');
  const ap=pr(t,WT(7,'صفر'),1.0);const addr='0x71C4…9A3F';const n=Math.round(addr.length*eo(ap));rr(-300,30,560,84,12);X.fillStyle=BK;X.fill();TL(addr.slice(0,n),-270,72,44,'YLB',WH);if(ap>0){X.fillStyle=MU;X.fillRect(-270,96,tw('0x',44,'YLB','ltr')*eo(pr(t,WT(7,'صفر'),0.4)),6);}X.restore();X.restore();}
 // s8: all of it snaps together like lego
 const a8=vis(t,S(8),CHD.end);if(a8>0){X.save();X.globalAlpha=a8;const bricks=[['توکن',MU,0],['دیفای',LIL,1],['ان‌اف‌تی',AQUA,2],['کیف‌پول',PEACH,3]];
  bricks.forEach(([s,c,i])=>{const tt=S(8)+0.3+i*0.55;const q=eio(pr(t,tt,0.5));if(q<=0)return;const yT=[470,370,270,170][i],xT=[300,560,380,640][i];X.save();X.globalAlpha*=clamp(q*2);lego(xT,lerp(yT-160,yT,q),300,90,c,s);X.restore();});X.restore();}
 X.restore();panel(t);panelHead(t);}

// ================= ch7: layer 2
function ch7(t){base(t);mark();const k=drift(t,0.02);X.save();X.translate(620,540);X.scale(k,k);X.translate(-620,-540);const o=stageO(50,620,700);
 // the main network slab (L1)
 const l1=eback(pr(t,S(0)-0.2,0.6));X.save();X.translate(620,700);X.scale(l1,l1);X.translate(-620,-700);shadow(o,-5,-3,10,6);box(o,-5,-3,0,10,6,0.8,[PALE,PERI,LIL]);const lt=P(o,4.2,-2.2,0.8);X.restore();
 T('لایه‌ی یک · اتریوم',1120,1000,32,'YKE',BK,'right');
 // s0: a traffic jam of transactions on L1, the fee meter rises
 const a0=vis(t,S(0),S(1)+0.4);if(a0>0){X.save();X.globalAlpha=a0;for(let i=0;i<22;i++){const r=rng(i+3);const x=-4.6+r()*9,y=-2.6+r()*5.2;const jam=0.3*Math.sin(t*2+i);const c=P(o,x+jam*0.1,y,0.8);const q=eo(pr(t,S(0)+i*0.04,0.4));rr(c[0]-20,c[1]-30*q,40,26*q,6);X.fillStyle=i%5===0?MU:WH;X.fill();X.lineWidth=2;X.strokeStyle=IND;X.stroke();}
  const fm=eio(pr(t,S(0)+0.8,Math.max(1,E(0)-S(0)-0.8)));tile(890,150,260,200,WH,BK,18);T('کارمزد',1120,190,30,'YKE',BK,'right');X.fillStyle=BK;X.fillRect(930,330-140*fm,180,140*fm);X.restore();}
 // s1-s6: the L2 slab above
 const a1=vis(t,S(1),CHD.end);const z2=lerp(6,4.2,eo(pr(t,S(1),0.8)));if(a1>0&&t<S(7)){X.save();X.globalAlpha=a1;box(o,-3.5,-2,z2,7,4,0.6,[MU,'#E0AE35','#C99A2B'],3,BK);const tp=P(o,3.4,-1.6,z2+0.6);T('لایه‌ی دو',tp[0]+60,tp[1]-40,34,'YKE',BK,'right');
  // pillars
  [[-3.3,-1.8],[3.3,-1.8],[-3.3,1.8],[3.3,1.8]].forEach(([x,y])=>{const a=P(o,x,y,0.8),b=P(o,x,y,z2);line(a[0],a[1],b[0],b[1],'rgba(0,0,0,0.35)',3,[6,6]);});
  // s2: transactions gather into a bundle that drops to L1
  const g0=WT(2,'جمع',0,0.5),d0=WT(2,'ثبت',0,0.85);for(let i=0;i<14;i++){const r=rng(i+40);const x0=-3+r()*6,y0=-1.6+r()*3.2;const gp=eio(pr(t,g0-0.6+i*0.03,0.7));const c=P(o,lerp(x0,0,gp),lerp(y0,0,gp),z2+0.6);const q=eo(pr(t,S(2)+i*0.05,0.4));if(t>d0)break;circle(c[0],c[1]-10,12*q*(1-gp*0.6),WH,IND,2);}
  const dp=eio(pr(t,d0-0.1,0.7));if(t>g0){const c=P(o,0,0,lerp(z2+0.6,0.8,dp));X.save();X.translate(c[0],c[1]-34);const bq=eback(pr(t,g0,0.4));X.scale(bq,bq);const oo={x:0,y:0,u:40};box(oo,-0.8,-0.8,0,1.6,1.6,1.1,[PEACH,WH,PERI],3);X.restore();if(dp>=1){const r=pr(t,d0+0.6,0.7);circle(c[0],c[1],30+r*200,null,`rgba(0,0,0,${0.5*(1-r)})`,4);}}
  // s3: 100 letters vs one parcel
  const lp=vis(t,S(3),S(4)+0.1);if(lp>0){X.save();X.globalAlpha*=lp;tile(120,90,470,240,WH,BK,18);for(let i=0;i<12;i++){const sq=eio(pr(t,WT(3,'بسته‌ی',0,0.5)+i*0.02,0.5));envelope(lerp(170+(i%6)*70,250,sq),lerp(160+Math.floor(i/6)*70,200,sq),50*(1-sq*0.7));}
   const pq=eback(pr(t,WT(3,'بسته‌ی',0,0.5)+0.4,0.5));if(pq>0){X.save();X.translate(450,210);X.scale(pq,pq);const oo={x:0,y:0,u:30};box(oo,-1.2,-1.2,-1,2.4,2.4,1.6,[PEACH,WH,PERI],3);X.restore();}
   const cq=eo(pr(t,WT(3,'تقسیم'),0.5));if(cq>0){X.globalAlpha=lp*cq;chip('هزینه ÷ ۱۰۰',355,370,34,'YKE',MU,BK,'center');}X.restore();}
  // s4: rollup names (text only)
  const nm=vis(t,S(4),S(5)+0.1);if(nm>0){X.save();X.globalAlpha*=nm;['Arbitrum','Optimism','Base'].forEach((s,i)=>{const q=eback(pr(t,WT(4,['آربیتروم','آپتیمیزم','بیس'][i])-0.1,0.4));if(q<=0)return;X.save();X.translate(240+i*0,170+i*90);X.scale(q,q);chip(s,0,0,42,'YLB',WH,BK,'center','ltr');X.restore();});X.restore();}
  // s5: security from L1, fees much lower
  const sc=vis(t,S(5),S(6)+0.1);if(sc>0){X.save();X.globalAlpha*=sc;shield(1000,250,150,MU,eo(pr(t,S(5),0.5)));const fq=eo(pr(t,WT(5,'کارمزدشون'),0.6));tile(120,120,330,260,WH,BK,18);T('کارمزد',420,160,30,'YKE',BK,'right');X.fillStyle=BK;X.fillRect(170,340-180,90,180);X.fillStyle=MU;X.fillRect(310,340-180*lerp(1,0.12,fq),90,180*lerp(1,0.12,fq));X.strokeStyle=BK;X.lineWidth=3;X.strokeRect(310,340-180*lerp(1,0.12,fq),90,180*lerp(1,0.12,fq));T('لایه‌ی ۱',215,365,24,'YKB',BK,'center');T('لایه‌ی ۲',355,365,24,'YKB',BK,'center');X.restore();}
  // s6: L2 fees paid in ETH
  const ep=vis(t,S(6),S(7)+0.1);if(ep>0){X.save();X.globalAlpha*=ep;const c=P(o,0,0,z2+0.6);const q=eback(pr(t,WT(6,'اتر'),0.5));X.save();X.translate(c[0],c[1]-120);X.scale(q,q);coin(0,0,80,'eth',Math.sin(t*2)*0.3);X.restore();X.restore();}
  X.restore();}
 // s7: the withdrawal: the chosen network must match the wallet's
 const a7=vis(t,S(7),CHD.end);if(a7>0){X.save();X.globalAlpha=a7;X.save();X.setTransform(1,0,0,1,0,0);paperBg(0,PX);mark();X.restore();
  const q=eback(pr(t,S(7),0.6));X.save();X.translate(860,540);X.scale(q,q);rr(-200,-380,400,760,44);X.fillStyle=BK;X.fill();rr(-180,-350,360,700,30);X.fillStyle=WH;X.fill();T('برداشت',150,-290,38,'YKE',BK,'right');T('شبکه را انتخاب کن',150,-230,26,'YKB','rgba(0,0,0,0.6)','right');
   const nets=['Ethereum (ERC-20)','Arbitrum One','Optimism','Base'];const pick=t>WT(7,'انتخاب')?1:-1;nets.forEach((s,i)=>{const y=-160+i*95;rr(-150,y-36,300,72,14);X.fillStyle=i===pick?MU:'#F1F1F4';X.fill();X.lineWidth=i===pick?4:1.5;X.strokeStyle=i===pick?BK:'rgba(0,0,0,0.2)';X.stroke();TL(s,-125,y,26,'YLB',BK);});X.restore();
  const wq=eback(pr(t,WT(7,'کیف‌پول'),0.6));if(wq>0){X.save();X.translate(330,540);X.scale(wq,wq);tile(-190,-170,380,340,WH,BK,26);walletIcon(0,-60,140,MU);T('کیف‌پول مقصد',0,50,32,'YKE',BK,'center');chip('Arbitrum One',0,115,30,'YLB',WH,BK,'center','ltr');X.restore();}
  const mq=eo(pr(t,WT(7,'یکی'),0.5));if(mq>0){arrow(650,540,540,540,mq,BK,7,22);circle(595,440,40*mq,GRN,BK,3);check(595,440,36,WH,mq,7);}X.restore();}
 X.restore();panel(t);panelHead(t);}

// ================= ch8: bitcoin vs ethereum (full-width table)
function ch8(t){const pOut=eio(pr(t,CHD.card_end-0.1,0.7))*(1-eio(pr(t,S(6)-0.2,0.6)));const px=lerp(PX,W,pOut);base(t);paperBg(0,W);mark();
 const L=120,Rr=lerp(px-80,W-120,pOut);const tblW=Rr-L;const cLab=Rr-260,cBtc=L+tblW*0.62,cEth=L+tblW*0.22;
 X.fillStyle=MU;X.fillRect(0,128,W,124);dither(0,128,W,124,8);const hp=eo(pr(t,S(0),0.6));if(hp>0){X.save();X.globalAlpha=hp;
  coin(cBtc+220,190,46,'btc',0);T('بیت‌کوین',cBtc+160,190,56,'YKE',BK,'right');coin(cEth+220,190,46,'eth',0);T('اتریوم',cEth+160,190,56,'YKE',BK,'right');X.fillStyle=BK;X.fillRect(L,250,tblW,6);X.restore();}
 const rows=[['هدف','پول دیجیتال و ذخیره‌ی ارزش','بستر برنامه‌پذیر',1],['عرضه','سقف ۲۱ میلیون','بدون سقف ثابت + سوزاندن',2],['اجماع','اثبات کار','اثبات سهام',3],['زمان بلوک','حدود ۱۰ دقیقه','۱۲ ثانیه',4],['برنامه‌پذیری','ساده و محدود','تقریباً هر برنامه‌ای',5]];
 rows.forEach(([lab,b,e,si],i)=>{const tt=S(si);const q=eo(pr(t,tt,0.5));if(q<=0)return;const y=320+i*140;X.save();X.globalAlpha=q;X.translate(0,(1-q)*24);
  const on=t>=S(si)&&t<N(si);if(on){X.fillStyle='rgba(243,194,66,0.35)';X.fillRect(L,y-10,tblW,120);}
  chip(lab,Rr,y+50,40,'YKE',MU,BK,'right');const qb=eo(pr(t,tt+0.4,0.4)),qe=eo(pr(t,WT(si,'اتریوم',0,0.5)-0.1,0.4));X.globalAlpha=q*qb;T(b,cBtc+220,y+50,46,'YKK',BK,'right');X.globalAlpha=q*qe;T(e,cEth+220,y+50,46,'YKK',BK,'right');X.globalAlpha=q;X.fillStyle='rgba(0,0,0,0.15)';X.fillRect(L,y+118,tblW,2);X.restore();});
 if(px<W)panel(t,px);
 // s6: the statement on black
 const a6=eo(pr(t,S(6)-0.2,0.6));if(a6>0){X.save();X.globalAlpha=a6;X.fillStyle='#08080B';X.fillRect(0,0,W,H);coin(W/2+260,330,90,'btc',0);coin(W/2-260,330,90,'eth',0);T('VS',W/2,330,90,'ANT',MU,'center','ltr');
  headline('دو ابزار برای دو کار متفاوت','متفاوت',t,S(6),CHD.end+5,W/2,620,110,1600,WH,MU,BK,'center');mark(true);X.restore();}}

// ================= ch9: recap and the end card
function ch9(t){X.fillStyle=MU;X.fillRect(0,0,W,H);dither(0,0,W,H,99);mark();
 const items=[1,2,3,4,5];T('خلاصه',W-120,150,64,'YKE',BK,'right');X.fillStyle=BK;X.fillRect(120,205,W-240,6);
 items.forEach(i=>{const s=CHD.sent[i];const q=eo(pr(t,S(i),0.5));if(q<=0)return;const y=280+(i-1)*140;X.save();X.globalAlpha=q*(i===items.length||t<S(i+1)?1:0.55);X.translate((1-q)*-40,0);
  X.fillStyle=BK;X.fillRect(W-230,y-50,110,110);T(fa(i),W-175,y+5,80,'YKE',MU,'center');T(s.h,W-270,y+5,64,'YKE',BK,'right');X.restore();});
 // s6: the article on the site
 const a6=vis(t,S(6),S(7)+0.2,0.6,0.4);if(a6>0){X.save();X.globalAlpha=a6;X.fillStyle=MU;X.fillRect(0,0,W,H);mark();const q=eback(pr(t,S(6),0.7));X.save();X.translate(W/2,520);X.scale(q,q);
  rr(-620,-330,1240,660,26);X.fillStyle=WH;X.fill();X.lineWidth=6;X.strokeStyle=BK;X.stroke();X.fillStyle=BK;X.fillRect(-620,-330,1240,74);[0,1,2].forEach(i=>circle(-580+i*36,-293,10,i===0?MU:'rgba(255,255,255,0.6)'));
  rr(-420,-318,840,50,25);X.fillStyle='#2A2A2E';X.fill();TL('dotcoin.me/learn/ethereum',0,-293,30,'YKB',WH,'center');
  T('اتریوم چیست؟',560,-170,80,'YKE',BK,'right');T('از قرارداد هوشمند تا گس و اثبات سهام',560,-80,40,'YKK','rgba(0,0,0,0.65)','right');
  const parts=['پاسخ کوتاه','جدول مقایسه','پرسش‌های پرتکرار','منابع'];parts.forEach((s,i)=>{chip(s,560-i*285,30,32,'YKE',i===0?BK:BK,i===0?MU:'#EEE','right');});
  [0,1,2,3].forEach(i=>{X.fillStyle='rgba(0,0,0,0.12)';X.fillRect(-560,110+i*48,1120*(i===3?0.6:1),18);});X.restore();X.restore();}
 // s7: the end card
 const a7=eo(pr(t,S(7),0.6));if(a7>0){X.save();X.globalAlpha=a7;X.fillStyle=BK;X.fillRect(0,0,W,H);
  const g=eback(pr(t,S(7)+0.1,0.7));X.save();X.translate(W/2,400);X.scale(g,g);circle(0,0,170,MU);if(IMG.logo)X.drawImage(IMG.logo,-155,-155,310,310);X.restore();
  TL('dotcoin.me',W/2,650,84,'YKK',WH,'center');const sp=eback(pr(t,WT(7,'سابسکرایب',0,0.5),0.6));if(sp>0){X.save();X.translate(W/2,800);X.scale(sp,sp);chip('دات‌کوین رو سابسکرایب کن',0,0,52,'YKE',BK,MU,'center');X.restore();}
  X.restore();}}
