import puppeteer from 'puppeteer-core';
import {readFileSync, readdirSync} from 'node:fs';
const D=process.argv[2];
const b=await puppeteer.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
const p=await b.newPage();
for(const f of readdirSync(D).filter(x=>x.endsWith('.svg'))){
  const svg=readFileSync(D+'/'+f,'utf8'); const m=/width="(\d+)" height="(\d+)"/.exec(svg);
  await p.setViewport({width:+m[1],height:+m[2],deviceScaleFactor:1.5});
  await p.setContent('<html><body style="margin:0;background:#fff">'+svg+'</body></html>');
  await p.screenshot({path:D+'/'+f.replace('.svg','.png'),clip:{x:0,y:0,width:+m[1],height:+m[2]}});
}
await b.close();
