// Markdown -> .docx for the documents in outputs/access/.
//
//   node scripts/md_to_docx.js <in.md> <out.docx> "<subtitle>" [toc] [map.png]
//
// A map passed as the fifth argument is dropped in on its own LANDSCAPE page
// between the front matter and the body, sized to fill the page. The rest of
// the document stays portrait: Word takes a page size per section, so the
// landscape page is simply its own section.
//
// Needs the `docx` npm package (preinstalled in this environment; otherwise
// `npm install docx`). Pandoc is not available here, which is why this exists.
//
// It handles only what our own Markdown uses: ATX headings, pipe tables,
// bullet and numbered lists with 2-space nesting and continuation lines,
// `---` rules, and inline **bold** / `code` / *italic*. It is deliberately
// not a general Markdown implementation - anything it does not recognise
// comes through as plain text rather than silently vanishing.

const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, AlignmentType, LevelFormat,
  TableOfContents, PageBreak, ImageRun, PageOrientation,
} = require('docx');

const CONTENT_DXA = 9026;          // A4 minus 1" margins each side
const MONO = 'Consolas';

// A4 landscape, half-inch margins, in pixels at 96dpi - what ImageRun wants.
const LAND_W_PX = Math.round((11.69 - 1.0) * 96);
const LAND_H_PX = Math.round((8.27 - 1.0) * 96);

function mapPage(mapPath) {
  const png = fs.readFileSync(mapPath);
  // PNG header: width and height are big-endian 32-bit ints at byte 16 and 20.
  const w = png.readUInt32BE(16), h = png.readUInt32BE(20);
  let dw = LAND_W_PX, dh = Math.round(LAND_W_PX * h / w);
  if (dh > LAND_H_PX) { dh = LAND_H_PX; dw = Math.round(LAND_H_PX * w / h); }
  return {
    properties: {
      page: {
        size: { orientation: PageOrientation.LANDSCAPE },
        margin: { top: 720, bottom: 720, left: 720, right: 720 },
      },
    },
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 0 },
      children: [new ImageRun({
        type: 'png',
        data: png,
        transformation: { width: dw, height: dh },
      })],
    })],
  };
}

// ---------- inline ----------

function inline(text, base = {}) {
  const runs = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0, m;
  const push = (t, opts) => { if (t) runs.push(new TextRun({ text: t, ...base, ...opts })); };
  while ((m = re.exec(text)) !== null) {
    push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith('**')) push(tok.slice(2, -2), { bold: true });
    else if (tok.startsWith('`')) push(tok.slice(1, -1), { font: MONO, size: 19 });
    else push(tok.slice(1, -1), { italics: true });
    last = re.lastIndex;
  }
  push(text.slice(last));
  return runs.length ? runs : [new TextRun({ text: '', ...base })];
}

// ---------- block parsing ----------

function parse(md) {
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let i = 0;

  const isTableRow = (l) => /^\s*\|/.test(l);
  const isRule = (l) => /^---+$/.test(l.trim());
  const heading = (l) => /^(#{1,6})\s+(.*)$/.exec(l);
  const bullet = (l) => /^(\s*)-\s+(.*)$/.exec(l);
  const numbered = (l) => /^(\s*)(\d+)\.\s+(.*)$/.exec(l);

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    const h = heading(line);
    if (h) { blocks.push({ t: 'h', level: h[1].length, text: h[2].trim() }); i++; continue; }

    if (isRule(line)) { blocks.push({ t: 'rule' }); i++; continue; }

    if (isTableRow(line)) {
      const rows = [];
      while (i < lines.length && isTableRow(lines[i])) {
        rows.push(lines[i].trim().replace(/^\|/, '').replace(/\|$/, '')
          .split('|').map((c) => c.trim()));
        i++;
      }
      blocks.push({ t: 'table', rows: rows.filter((r) => !r.every((c) => /^:?-+:?$/.test(c))) });
      continue;
    }

    const b = bullet(line) || numbered(line);
    if (b) {
      const items = [];
      while (i < lines.length) {
        const bl = bullet(lines[i]), nl = numbered(lines[i]);
        if (bl || nl) {
          const indent = (bl ? bl[1] : nl[1]).length;
          items.push({
            level: Math.min(Math.floor(indent / 2), 2),
            ordered: !!nl,
            marker: nl ? nl[2] : null,
            text: bl ? bl[2] : nl[3],
          });
          i++;
        } else if (/^\s+\S/.test(lines[i]) && items.length) {
          // An indented line that is not itself an item continues the one above.
          items[items.length - 1].text += ' ' + lines[i].trim();
          i++;
        } else break;
      }
      blocks.push({ t: 'list', items });
      continue;
    }

    const buf = [];
    while (i < lines.length && lines[i].trim()
           && !heading(lines[i]) && !isRule(lines[i]) && !isTableRow(lines[i])
           && !bullet(lines[i]) && !numbered(lines[i])) {
      buf.push(lines[i].trim());
      i++;
    }
    blocks.push({ t: 'p', text: buf.join(' ') });
  }
  return blocks;
}

// ---------- rendering ----------

const HEAD = {
  1: HeadingLevel.HEADING_1, 2: HeadingLevel.HEADING_2, 3: HeadingLevel.HEADING_3,
  4: HeadingLevel.HEADING_4, 5: HeadingLevel.HEADING_5, 6: HeadingLevel.HEADING_6,
};

// `[x]` / `[~]` / `[ ]` / `[?]` are kept literal rather than swapped for
// ballot-box glyphs: the checklist defines those markers in its own legend,
// and an unticked box is also how the team marks one off by hand on paper.
const TASK = /^\[([x~? ])\]\s*(.*)$/;

function renderList(items) {
  const out = [];
  for (const it of items) {
    const task = TASK.exec(it.text);
    const indent = { left: 360 + it.level * 540, hanging: 360 };
    if (task) {
      out.push(new Paragraph({
        spacing: { before: 20, after: 40 }, indent,
        children: [
          new TextRun({ text: `[${task[1]}]  `, bold: true, font: MONO, size: 19 }),
          ...inline(task[2]),
        ],
      }));
    } else if (it.ordered) {
      out.push(new Paragraph({
        spacing: { before: 20, after: 40 }, indent,
        children: [new TextRun({ text: `${it.marker}.  `, bold: true }), ...inline(it.text)],
      }));
    } else {
      out.push(new Paragraph({
        spacing: { before: 20, after: 40 },
        numbering: { reference: 'bullets', level: it.level },
        children: inline(it.text),
      }));
    }
  }
  return out;
}

function renderTable(rows) {
  const cols = Math.max(...rows.map((r) => r.length));
  const firstMax = Math.max(...rows.map((r) => (r[0] || '').length));
  let widths;
  if (cols === 2) {
    const w0 = Math.min(Math.max(firstMax * 110, 1400), 3600);
    widths = [w0, CONTENT_DXA - w0];
  } else if (cols === 3 && firstMax <= 6) {
    widths = [900, 2600, CONTENT_DXA - 3500];
  } else {
    const even = Math.floor(CONTENT_DXA / cols);
    widths = Array(cols).fill(even);
    widths[cols - 1] = CONTENT_DXA - even * (cols - 1);
  }

  const cell = (text, isHeader, idx) => new TableCell({
    width: { size: widths[idx], type: WidthType.DXA },
    // CLEAR, never SOLID: SOLID renders as a black block.
    shading: isHeader ? { type: ShadingType.CLEAR, fill: 'EDF1F6', color: 'auto' } : undefined,
    margins: { top: 60, bottom: 60, left: 110, right: 110 },
    children: [new Paragraph({
      spacing: { before: 0, after: 0 },
      children: inline(text, isHeader ? { bold: true } : {}),
    })],
  });

  return new Table({
    columnWidths: widths,
    width: { size: CONTENT_DXA, type: WidthType.DXA },
    rows: rows.map((r, ri) => new TableRow({
      tableHeader: ri === 0,
      children: Array.from({ length: cols }, (_, ci) => cell(r[ci] || '', ri === 0, ci)),
    })),
  });
}

function render(blocks) {
  const out = [];
  for (const b of blocks) {
    if (b.t === 'h') {
      out.push(new Paragraph({
        heading: HEAD[b.level],
        spacing: { before: b.level === 1 ? 0 : 260, after: 120 },
        children: inline(b.text),
      }));
    } else if (b.t === 'p') {
      out.push(new Paragraph({ spacing: { before: 0, after: 140 }, children: inline(b.text) }));
    } else if (b.t === 'list') {
      out.push(...renderList(b.items));
      out.push(new Paragraph({ spacing: { before: 0, after: 100 }, text: '' }));
    } else if (b.t === 'table') {
      out.push(renderTable(b.rows));
      out.push(new Paragraph({ spacing: { before: 0, after: 160 }, text: '' }));
    } else if (b.t === 'rule') {
      out.push(new Paragraph({
        spacing: { before: 120, after: 180 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'C8CDD4', space: 1 } },
        children: [new TextRun('')],
      }));
    }
  }
  return out;
}

// ---------- document ----------

function build(mdPath, outPath, { subtitle, toc, mapPath }) {
  const blocks = parse(fs.readFileSync(mdPath, 'utf8'));

  let title = '';
  if (blocks.length && blocks[0].t === 'h' && blocks[0].level === 1) {
    title = blocks.shift().text;          // the H1 becomes the title block
  }

  const front = [
    new Paragraph({
      spacing: { before: 0, after: 60 },
      children: inline(title, { bold: true, size: 40 }),
    }),
    new Paragraph({
      spacing: { before: 0, after: 320 },
      children: [new TextRun({ text: subtitle || '', color: '5A6673', size: 20 })],
    }),
  ];
  if (toc) {
    front.push(new Paragraph({
      spacing: { before: 0, after: 100 },
      children: [new TextRun({ text: 'Contents', bold: true, size: 24 })],
    }));
    // dirty:true, so Word fills in the page numbers when the file is opened.
    front.push(new TableOfContents('Contents', { hyperlink: true, headingStyleRange: '1-3' }));
    // No manual break when a map follows: the landscape section starts its
    // own page, and a break as well would leave a blank one behind.
    if (!mapPath) front.push(new Paragraph({ children: [new PageBreak()] }));
  }

  const portrait = {
    page: { margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } },
  };
  const sections = mapPath
    ? [{ properties: portrait, children: front },
       mapPage(mapPath),
       { properties: portrait, children: render(blocks) }]
    : [{ properties: portrait, children: [...front, ...render(blocks)] }];

  const doc = new Document({
    creator: 'Managalas Conservation Area track mapping',
    title,
    description: subtitle || '',
    styles: {
      default: {
        document: { run: { font: 'Calibri', size: 21 }, paragraph: { spacing: { line: 276 } } },
        heading1: { run: { font: 'Calibri', size: 32, bold: true, color: '1F4E79' } },
        heading2: { run: { font: 'Calibri', size: 26, bold: true, color: '1F4E79' } },
        heading3: { run: { font: 'Calibri', size: 23, bold: true, color: '2E4A63' } },
        heading4: { run: { font: 'Calibri', size: 21, bold: true, color: '2E4A63' } },
      },
    },
    numbering: {
      config: [{
        reference: 'bullets',
        levels: [0, 1, 2].map((l) => ({
          level: l,
          format: LevelFormat.BULLET,
          text: ['•', '◦', '▪'][l],
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 360 + l * 540, hanging: 260 } } },
        })),
      }],
    },
    sections,
  });

  return Packer.toBuffer(doc).then((buf) => {
    fs.writeFileSync(outPath, buf);
    console.log(`${outPath}  ${buf.length} bytes`);
  });
}

const [, , mdPath, outPath, subtitle, tocFlag, mapPath] = process.argv;
if (!mdPath || !outPath) {
  console.error('usage: node scripts/md_to_docx.js <in.md> <out.docx> "<subtitle>" [toc] [map.png]');
  process.exit(2);
}
build(mdPath, outPath, { subtitle, toc: tocFlag === 'toc', mapPath })
  .catch((e) => { console.error(e); process.exit(1); });
