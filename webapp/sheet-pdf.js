// SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
// SPDX-License-Identifier: GPL-3.0-only
// Draw the shared worksheet plan with the browser's Unicode font shaping.
// PDF ActualText preserves searchable text alongside the print-resolution page image.
const width=595.276, height=841.89, margin=36, bottom=height-53, content=width-2*margin;
const lineHeight=13, scale=3, ascii=new TextEncoder();
const hexText = text => 'FEFF'+Array.from({length:text.length},(_,i)=>text.charCodeAt(i).toString(16).padStart(4,'0')).join('');

class Worksheet {
  constructor(plan,language) {
    this.plan=plan;
    this.canvas=document.createElement('canvas');
    this.canvas.width=Math.round(width*scale); this.canvas.height=Math.round(height*scale);
    this.draw=this.canvas.getContext('2d',{alpha:false});
    this.fontFamily='"RatioLab Noto Tamil","RatioLab Noto CJK",Arial,sans-serif';
    this.graphemes=new Intl.Segmenter(language,{granularity:'grapheme'});
    this.pages=[]; this.text=[];
    this.newPage();
  }
  font(size,bold) {
    this.draw.font=(bold ? '600 ' : '')+size+'px '+this.fontFamily;
    this.draw.textBaseline='top';
  }
  write(text,x,y,size=9,bold=false) {
    if (!text) return;
    this.font(size,bold);
    this.draw.fillStyle='#17272d'; this.draw.fillText(text,x,y);
    this.text.push({text,x,y,size});
  }
  lines(value,available,size=9,bold=false) {
    this.font(size,bold);
    const rows=[];
    const measure=text=>this.draw.measureText(text).width;
    for (const paragraph of String(value ?? '').split('\n')) {
      let line='';
      for (const word of paragraph.match(/\s+|\S+/gu) ?? []) {
        if (measure(line+word)<=available) { line+=word; continue; }
        if (line.trim()) { rows.push(line.trimEnd()); line=''; }
        if (!word.trim()) continue;
        if (measure(word)<=available) { line=word; continue; }
        for (const {segment} of this.graphemes.segment(word)) {
          if (line && measure(line+segment)>available) { rows.push(line); line=''; }
          line+=segment;
        }
      }
      rows.push(line.trimEnd());
    }
    return rows;
  }
  finishPage() {
    const number=String(this.pages.length+1), pageY=height-32;
    this.lines(this.plan.footer,content-34,7.5).forEach((line,i)=>this.write(line,margin,pageY+i*9,7.5));
    this.write(number,width-margin-14,pageY,7.5);
    const text=this.text;
    const image=new Promise((resolve,reject)=>this.canvas.toBlob(
      blob=>blob ? resolve(blob.arrayBuffer()) : reject(Error('Could not encode the component sheet.')),
      'image/jpeg',.93));
    this.pages.push({text,image});
  }
  newPage() {
    if (this.y !== undefined) this.finishPage();
    this.text=[];
    const draw=this.draw;
    draw.setTransform(scale,0,0,scale,0,0);
    draw.fillStyle='#fff'; draw.fillRect(0,0,width+1,height+1);
    this.y=30;
    for (const line of this.lines(this.plan.title,content,17,true)) {
      this.write(line,margin,this.y,17,true); this.y+=24;
    }
    draw.fillStyle='#839b9d'; draw.fillRect(margin,this.y,content,.8); this.y+=10;
  }
  space(needed) {
    if (this.y+needed>bottom) this.newPage();
  }
  heading(text) {
    const rows=this.lines(text,content,11,true);
    this.space(rows.length*16+18);
    this.y+=6;
    for (const row of rows) {
      this.space(16); this.write(row,margin,this.y,11,true); this.y+=16;
    }
  }
  paragraph(text,size=9) {
    for (const row of this.lines(text,content,size)) {
      this.space(lineHeight); this.write(row,margin,this.y,size); this.y+=lineHeight;
    }
    this.y+=5;
  }
  table(headers,rows,ratios) {
    const total=ratios.reduce((a,b)=>a+b,0), columnWidths=ratios.map(ratio=>content*ratio/total);
    const header=headers.map((text,i)=>this.lines(text,columnWidths[i]-12,8.5,true));
    const headerCount=Math.max(...header.map(lines=>lines.length));
    const headerHeight=8+lineHeight*headerCount;
    const drawCells=(columns,count,offset,bold)=>{
      let x=margin;
      const h=8+count*lineHeight, draw=this.draw;
      for (const [i,lines] of columns.entries()) {
        const w=columnWidths[i];
        if (bold) { draw.fillStyle='#e6eff0'; draw.fillRect(x,this.y,w,h); }
        draw.strokeStyle='#aab9bd'; draw.lineWidth=.55; draw.strokeRect(x,this.y,w,h);
        lines.slice(offset,offset+count).forEach((line,j)=>this.write(line,x+6,this.y+4+j*lineHeight,8.5,bold));
        x+=w;
      }
      this.y+=h;
    };
    this.space(headerHeight+8+lineHeight);
    drawCells(header,headerCount,0,true);
    for (const cells of rows) {
      const columns=cells.map((text,i)=>this.lines(text,columnWidths[i]-12,8.5));
      const lineCount=Math.max(...columns.map(lines=>lines.length));
      let offset=0;
      while (offset<lineCount) {
        let available=Math.floor((bottom-this.y-8)/lineHeight);
        if (available<1 || offset===0 && available<lineCount && lineCount<12) {
          this.newPage(); drawCells(header,headerCount,0,true);
          available=Math.floor((bottom-this.y-8)/lineHeight);
        }
        const count=Math.min(available,lineCount-offset);
        drawCells(columns,count,offset,false); offset+=count;
      }
    }
    this.y+=3;
  }
  profile(caption,loops) {
    this.space(104+lineHeight*this.lines(caption,content,8).length);
    this.paragraph(caption,8);
    const bounds=[Infinity,Infinity,-Infinity,-Infinity];
    for (const loop of loops) for (const [x,y] of loop) {
      bounds[0]=Math.min(bounds[0],x);bounds[1]=Math.min(bounds[1],y);
      bounds[2]=Math.max(bounds[2],x);bounds[3]=Math.max(bounds[3],y);
    }
    const ratio=Math.min((content-20)/Math.max(bounds[2]-bounds[0],1e-9),88/Math.max(bounds[3]-bounds[1],1e-9));
    const cx=(bounds[0]+bounds[2])/2, cy=(bounds[1]+bounds[3])/2;
    for (const loop of loops) {
      this.draw.beginPath();
      loop.forEach(([x,y],i)=>this.draw[i ? 'lineTo' : 'moveTo'](width/2+(x-cx)*ratio,this.y+48-(y-cy)*ratio));
      this.draw.closePath(); this.draw.strokeStyle='#214f5b'; this.draw.lineWidth=.65; this.draw.stroke();
    }
    this.y+=100;
  }
  keep_text(heading,blocks) {
    this.space(14+16*this.lines(heading,content,11,true).length+
      blocks.reduce((total,[text,size])=>total+5+lineHeight*this.lines(text,content,size).length,0));
  }
  async pdf() {
    for (const [method,...args] of this.plan.operations) this[method](...args);
    this.finishPage();
    const pages=await Promise.all(this.pages.map(async page=>({...page,image:new Uint8Array(await page.image)})));
    return writePdf(this.plan.title,pages,this.canvas.width,this.canvas.height);
  }
}

function writePdf(title,pages,imageWidth,imageHeight) {
  const chunks=[], positions=[0];
  let length=0;
  const add=value=>{
    const data=typeof value==='string' ? ascii.encode(value) : value;
    length+=data.byteLength; chunks.push(data);
  };
  const object=(id,...data)=>{positions[id]=length;add(id+' 0 obj\n');data.forEach(add);add('\nendobj\n');};
  add('%PDF-1.4\n'); add(Uint8Array.of(37,226,227,207,211,10));
  object(1,'<< /Type /Catalog /Pages 2 0 R >>');
  object(2,'<< /Type /Pages /Kids ['+pages.map((_,i)=>(4+i*3)+' 0 R').join(' ')+'] /Count '+pages.length+' >>');
  object(3,'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
  for (const [index,{image,text}] of pages.entries()) {
    const id=4+index*3;
    object(id,'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 '+width+' '+height+'] /Resources << /XObject << /PageImage '+(id+1)+
      ' 0 R >> /Font << /F1 3 0 R >> >> /Contents '+(id+2)+' 0 R >>');
    object(id+1,'<< /Type /XObject /Subtype /Image /Width '+imageWidth+' /Height '+imageHeight+
      ' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length '+image.length+' >>\nstream\n',image,'\nendstream');
    const commands=['q '+width+' 0 0 '+height+' 0 0 cm /PageImage Do Q'];
    for (const line of text) commands.push('/Span << /ActualText <'+hexText(line.text)+'> >> BDC\nBT /F1 '+line.size+
      ' Tf 3 Tr 1 0 0 1 '+line.x.toFixed(3)+' '+(height-line.y-line.size).toFixed(3)+' Tm (x) Tj ET\nEMC');
    const drawing=ascii.encode(commands.join('\n')+'\n');
    object(id+2,'<< /Length '+drawing.length+' >>\nstream\n',drawing,'endstream');
  }
  const info=4+pages.length*3;
  object(info,'<< /Title <'+hexText(title)+'> /Creator (RatioLab) >>');
  const xref=length;
  add('xref\n0 '+positions.length+'\n0000000000 65535 f \n');
  positions.slice(1).forEach(position=>add(String(position).padStart(10,'0')+' 00000 n \n'));
  add('trailer\n<< /Size '+positions.length+' /Root 1 0 R /Info '+info+' 0 R >>\nstartxref\n'+xref+'\n%%EOF\n');
  return new Blob(chunks,{type:'application/pdf'});
}

const crcTable=Uint32Array.from({length:256},(_,i)=>{
  for(let bit=0;bit<8;++bit) i=i & 1 ? 0xedb88320 ^ (i>>>1) : i>>>1;
  return i;
});
function crc32(bytes) {
  let value=0xffffffff;
  for(const byte of bytes) value=crcTable[(value^byte)&255]^(value>>>8);
  return (value^0xffffffff)>>>0;
}
function archive(files) {
  const data=[], directory=[];
  let offset=0, directorySize=0;
  for(const [name,bytes] of files) {
    const filename=ascii.encode(name), size=bytes.length, checksum=crc32(bytes);
    const local=new DataView(new ArrayBuffer(30)), central=new DataView(new ArrayBuffer(46));
    local.setUint32(0,0x04034b50,true); local.setUint16(4,20,true); local.setUint16(12,33,true);
    local.setUint32(14,checksum,true); local.setUint32(18,size,true); local.setUint32(22,size,true);
    local.setUint16(26,filename.length,true);
    central.setUint32(0,0x02014b50,true); central.setUint16(4,20,true); central.setUint16(6,20,true);
    central.setUint16(14,33,true); central.setUint32(16,checksum,true);
    central.setUint32(20,size,true); central.setUint32(24,size,true); central.setUint16(28,filename.length,true);
    central.setUint32(42,offset,true);
    data.push(local.buffer,filename,bytes); offset+=30+filename.length+size;
    directory.push(central.buffer,filename); directorySize+=46+filename.length;
  }
  const end=new DataView(new ArrayBuffer(22));
  end.setUint32(0,0x06054b50,true); end.setUint16(8,files.length,true); end.setUint16(10,files.length,true);
  end.setUint32(12,directorySize,true); end.setUint32(16,offset,true);
  return new Blob([...data,...directory,end.buffer],{type:'application/zip'});
}

export async function exportSheetArchive(pages,report) {
  await Promise.all([
    document.fonts.load('9px "RatioLab Noto Tamil"','தமிழ்'),
    document.fonts.load('9px "RatioLab Noto CJK"','零件生产检查')
  ]);
  const files=[];
  for(const kind of ['production','inspection']) {
    const document=new Worksheet(pages[kind],report.language);
    files.push([kind+'.pdf',new Uint8Array(await (await document.pdf()).arrayBuffer())]);
  }
  files.push(['sheet-data.json',ascii.encode(JSON.stringify(report,null,2)+'\n')]);
  return archive(files);
}
