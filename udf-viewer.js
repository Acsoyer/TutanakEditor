(() => {
  'use strict';

  const MAX_FILES = 3;
  const MAX_ARCHIVE_BYTES = 30 * 1024 * 1024;
  const MAX_XML_BYTES = 20 * 1024 * 1024;
  const DEFAULT_TAB_STOP_PT = 69;
  const MANUAL_ZOOM_LEVELS = [0.5, 0.6, 0.7, 0.8, 0.9, 1, 1.1, 1.2, 1.4];
  const A4_WIDTH_PX = 210 * 96 / 25.4;
  const ALIGNMENTS = { '0': 'left', '1': 'center', '2': 'right', '3': 'justify' };

  const state = {
    documents: [],
    activeId: null,
    zoom: 1,
    fitZoom: 1,
    zoomMode: 'fit',
    currentPage: 1,
    statusTimer: null,
    toastTimer: null
  };

  const el = {
    app: document.getElementById('app'),
    welcome: document.getElementById('welcome'),
    viewer: document.getElementById('viewer'),
    dropZone: document.getElementById('dropZone'),
    fileInput: document.getElementById('fileInput'),
    addFileInput: document.getElementById('addFileInput'),
    tabs: document.getElementById('documentTabs'),
    canvas: document.getElementById('canvas'),
    pages: document.getElementById('pages'),
    prevPage: document.getElementById('prevPage'),
    nextPage: document.getElementById('nextPage'),
    pageIndicator: document.getElementById('pageIndicator'),
    zoomOut: document.getElementById('zoomOut'),
    zoomIn: document.getElementById('zoomIn'),
    zoomSelect: document.getElementById('zoomSelect'),
    statusBar: document.getElementById('statusBar'),
    toast: document.getElementById('toast'),
    measureHost: document.getElementById('measureHost')
  };

  function uid() {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function showStatus(message) {
    clearTimeout(state.statusTimer);
    el.statusBar.textContent = message;
    el.statusBar.classList.add('is-visible');
    state.statusTimer = setTimeout(() => el.statusBar.classList.remove('is-visible'), 2200);
  }

  function showError(message) {
    clearTimeout(state.toastTimer);
    el.toast.textContent = message;
    el.toast.classList.add('is-visible');
    state.toastTimer = setTimeout(() => el.toast.classList.remove('is-visible'), 5200);
  }

  function setBusy(isBusy) {
    document.body.style.cursor = isBusy ? 'progress' : '';
    el.dropZone.style.pointerEvents = isBusy ? 'none' : '';
  }

  function codePoints(value) {
    return Array.from(value || '');
  }

  function slicePool(pool, node) {
    const start = Number.parseInt(node.getAttribute('startOffset') || '0', 10);
    const length = Number.parseInt(node.getAttribute('length') || '0', 10);
    if (!Number.isFinite(start) || !Number.isFinite(length) || start < 0 || length < 0) return '';
    return pool.slice(start, start + length).join('').replace(/[\r\n]+/g, '');
  }

  function directChild(parent, tagName) {
    return Array.from(parent?.children || []).find(child => child.tagName === tagName) || null;
  }

  function signedArgbToCss(value, fallback = null) {
    if (value === null || value === undefined || value === '') return fallback;
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    const unsigned = parsed >>> 0;
    const alpha = ((unsigned >>> 24) & 255) / 255;
    const red = (unsigned >>> 16) & 255;
    const green = (unsigned >>> 8) & 255;
    const blue = unsigned & 255;
    if (alpha === 0 && unsigned <= 0xFFFFFF) return `rgb(${red} ${green} ${blue})`;
    return `rgba(${red}, ${green}, ${blue}, ${alpha.toFixed(3)})`;
  }

  function parseStyles(root) {
    const map = new Map();
    root.querySelectorAll('styles > style').forEach(style => {
      const attrs = {};
      for (const attr of style.attributes) attrs[attr.name] = attr.value;
      if (attrs.name) map.set(attrs.name, attrs);
    });
    return map;
  }

  function resolvedAttributes(node, styleMap, seen = new Set()) {
    const own = {};
    for (const attr of node?.attributes || []) own[attr.name] = attr.value;
    const resolver = own.resolver;
    if (!resolver || seen.has(resolver) || !styleMap.has(resolver)) return own;
    seen.add(resolver);
    const style = styleMap.get(resolver);
    const inherited = resolvedStyle(style, styleMap, seen);
    return { ...inherited, ...own };
  }

  function resolvedStyle(style, styleMap, seen = new Set()) {
    if (!style) return {};
    const resolver = style.resolver;
    if (!resolver || seen.has(resolver) || !styleMap.has(resolver)) return { ...style };
    seen.add(resolver);
    return { ...resolvedStyle(styleMap.get(resolver), styleMap, seen), ...style };
  }

  function pt(value, fallback = 0) {
    const number = Number.parseFloat(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function webFontFamily(family) {
    const value = String(family || '').trim();
    return /bookman/i.test(value) ? 'Libre Baskerville' : value;
  }

  function applyTextStyle(target, attrs) {
    if (attrs.family) target.style.fontFamily = `"${webFontFamily(attrs.family)}", "Times New Roman", serif`;
    if (attrs.size) target.style.fontSize = `${pt(attrs.size, 12)}pt`;
    if (attrs.bold === 'true') target.style.fontWeight = '700';
    if (attrs.italic === 'true') target.style.fontStyle = 'italic';
    if (attrs.underline === 'true') target.style.textDecoration = 'underline';
    const color = signedArgbToCss(attrs.foreground);
    if (color) target.style.color = color;
    const background = signedArgbToCss(attrs.background);
    if (background && attrs.background !== '-1') target.style.backgroundColor = background;
  }

  function applyParagraphStyle(target, attrs) {
    target.style.setProperty('--text-align', ALIGNMENTS[attrs.Alignment] || 'left');
    target.style.setProperty('--left-indent', `${pt(attrs.LeftIndent)}pt`);
    target.style.setProperty('--right-indent', `${pt(attrs.RightIndent)}pt`);
    target.style.setProperty('--first-indent', `${pt(attrs.FirstLineIndent)}pt`);
    target.style.setProperty('--space-above', `${pt(attrs.SpaceAbove)}pt`);
    target.style.setProperty('--space-below', `${pt(attrs.SpaceBelow)}pt`);
    const spacing = pt(attrs.LineSpacing, 0);
    target.style.setProperty('--line-height', spacing > 0 ? String(1 + spacing) : 'normal');
    const tabStops = String(attrs.TabSet || '')
      .split(',')
      .map(item => pt(item.split(':')[0], NaN))
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    target.dataset.tabStops = tabStops.join(',');
    if (attrs.family) target.style.setProperty('--font-family', `"${webFontFamily(attrs.family)}"`);
    if (attrs.size) target.style.setProperty('--font-size', `${pt(attrs.size, 12)}pt`);
    if (attrs.bold === 'true') target.style.setProperty('--font-weight', '700');
    if (attrs.italic === 'true') target.style.setProperty('--font-style', 'italic');
    if (attrs.underline === 'true') target.style.setProperty('--text-decoration', 'underline');
  }

  function renderInline(node, context) {
    const tag = node.tagName;
    if (!['content', 'field', 'space', 'tab', 'image'].includes(tag)) return null;

    if (tag === 'image') {
      if (context.inFooter && !context.arbsysGenerated) return null;
      const raw = node.getAttribute('imageData') || '';
      if (!raw || raw.length > 12 * 1024 * 1024) return null;
      const img = document.createElement('img');
      img.className = 'udf-image';
      img.alt = '';
      img.src = raw.startsWith('data:') ? raw : `data:image/png;base64,${raw}`;
      img.style.width = `${pt(node.getAttribute('width'), 80)}pt`;
      img.style.height = `${pt(node.getAttribute('height'), 60)}pt`;
      return img;
    }

    const attrs = resolvedAttributes(node, context.styleMap);
    const text = tag === 'tab' ? '\t' : slicePool(context.pool, node);
    const fragment = document.createDocumentFragment();
    text.split('\t').forEach((part, index) => {
      if (index > 0) {
        const tab = document.createElement('span');
        tab.className = 'udf-tab';
        tab.setAttribute('aria-hidden', 'true');
        fragment.appendChild(tab);
      }
      if (part) {
        const span = document.createElement('span');
        span.className = 'udf-run';
        applyTextStyle(span, attrs);
        span.textContent = part;
        fragment.appendChild(span);
      }
    });
    return fragment;
  }

  function renderParagraph(node, context) {
    const paragraph = document.createElement('p');
    paragraph.className = 'udf-paragraph';
    const attrs = resolvedAttributes(node, context.styleMap);
    applyParagraphStyle(paragraph, attrs);
    Array.from(node.children).forEach(child => {
      const inline = renderInline(child, context);
      if (inline) paragraph.appendChild(inline);
    });
    const fontUsage = new Map();
    paragraph.querySelectorAll('.udf-run').forEach(run => {
      const family = run.style.fontFamily || attrs.family || '';
      const size = run.style.fontSize || (attrs.size ? `${pt(attrs.size, 12)}pt` : '');
      if (!family && !size) return;
      const key = `${family}\u0000${size}`;
      fontUsage.set(key, (fontUsage.get(key) || 0) + Math.max(1, run.textContent.length));
    });
    const dominantFont = Array.from(fontUsage.entries()).sort((a, b) => b[1] - a[1])[0]?.[0];
    if (dominantFont) {
      const [family, size] = dominantFont.split('\u0000');
      if (family) paragraph.style.setProperty('--font-family', family);
      if (size) paragraph.style.setProperty('--font-size', size);
    }
    if (!paragraph.textContent && !paragraph.querySelector('img')) paragraph.appendChild(document.createTextNode('\u200B'));
    return paragraph;
  }

  function borderCss(attrs) {
    const width = `${Math.max(.3, pt(attrs.borderWidth, .75))}pt`;
    const styleMap = {
      'borderStyle-dotted': 'dotted',
      'borderStyle-dashed': 'dashed',
      'borderStyle-double': 'double',
      'borderStyle-solid': 'solid'
    };
    const style = styleMap[attrs.borderStyle] || 'solid';
    const color = signedArgbToCss(attrs.borderColor, '#000');
    return `${width} ${style} ${color}`;
  }

  function renderTable(node, context) {
    const table = document.createElement('table');
    table.className = 'udf-table';
    const tableAttrs = resolvedAttributes(node, context.styleMap);
    if (tableAttrs.border && tableAttrs.border !== 'borderNone') table.classList.add('has-border');

    const rowNodes = Array.from(node.children).filter(child => child.tagName === 'row');
    const columnCount = Math.max(1, ...rowNodes.map(rowNode => (
      Array.from(rowNode.children)
        .filter(child => child.tagName === 'cell')
        .reduce((total, cellNode) => {
          const attrs = resolvedAttributes(cellNode, context.styleMap);
          return total + Math.max(1, Number.parseInt(attrs.colspan, 10) || 1);
        }, 0)
    )));
    table.dataset.columns = String(columnCount);

    const spans = (tableAttrs.columnSpans || '').split(',').map(Number).filter(Number.isFinite);
    const colgroup = document.createElement('colgroup');
    if (spans.length === columnCount) {
      spans.forEach(width => {
        const col = document.createElement('col');
        col.style.width = `${width}pt`;
        colgroup.appendChild(col);
      });
    } else {
      for (let index = 0; index < columnCount; index += 1) {
        const col = document.createElement('col');
        col.style.width = `${100 / columnCount}%`;
        colgroup.appendChild(col);
      }
    }
    table.appendChild(colgroup);

    const tbody = document.createElement('tbody');
    rowNodes.forEach(rowNode => {
      const row = document.createElement('tr');
      const rowAttrs = resolvedAttributes(rowNode, context.styleMap);
      if (rowAttrs.height) row.style.height = `${pt(rowAttrs.height)}pt`;
      Array.from(rowNode.children).filter(child => child.tagName === 'cell').forEach(cellNode => {
        const cell = document.createElement('td');
        const attrs = resolvedAttributes(cellNode, context.styleMap);
        if (attrs.colspan) cell.colSpan = Math.max(1, Number.parseInt(attrs.colspan, 10) || 1);
        if (attrs.rowspan) cell.rowSpan = Math.max(1, Number.parseInt(attrs.rowspan, 10) || 1);
        cell.style.verticalAlign = attrs.align === 'vcenter' ? 'middle' : (attrs.align || 'top');
        const fill = signedArgbToCss(attrs.fillColor);
        if (fill) cell.style.backgroundColor = fill;
        if (attrs.border === 'borderNone' || tableAttrs.border === 'borderNone') {
          cell.classList.add('border-none');
        } else if (attrs.borderSpec) {
          const spec = Number.parseInt(attrs.borderSpec, 10) || 0;
          const border = borderCss(attrs);
          cell.style.borderTop = spec & 1 ? border : '0';
          cell.style.borderRight = spec & 2 ? border : '0';
          cell.style.borderBottom = spec & 4 ? border : '0';
          cell.style.borderLeft = spec & 8 ? border : '0';
        }
        Array.from(cellNode.children).forEach(child => {
          if (child.tagName === 'paragraph') cell.appendChild(renderParagraph(child, context));
          if (child.tagName === 'table') cell.appendChild(renderTable(child, context));
        });
        row.appendChild(cell);
      });
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    return table;
  }

  function renderBlock(node, context) {
    if (node.tagName === 'paragraph') return renderParagraph(node, context);
    if (node.tagName === 'table') return renderTable(node, context);
    if (node.tagName === 'page-break') {
      const marker = document.createElement('div');
      marker.dataset.pageBreak = 'true';
      return marker;
    }
    return null;
  }

  function parsePageFormat(root) {
    const format = root.querySelector('properties > pageFormat');
    const landscape = format?.getAttribute('paperOrientation') === '0';
    return {
      widthPt: landscape ? 841.89 : 595.28,
      heightPt: landscape ? 595.28 : 841.89,
      leftPt: pt(format?.getAttribute('leftMargin'), 42.52),
      rightPt: pt(format?.getAttribute('rightMargin'), 28.35),
      topPt: pt(format?.getAttribute('topMargin'), 42.52),
      bottomPt: pt(format?.getAttribute('bottomMargin'), 42.52),
      headerOffsetPt: pt(format?.getAttribute('headerFOffset'), 14.17),
      footerOffsetPt: pt(format?.getAttribute('footerFOffset'), 8.5)
    };
  }

  function isArbsysGeneratedUdf(root, elements) {
    const tabLength = directChild(root, 'tabLength');
    const tables = Array.from(elements.children).filter(node => node.tagName === 'table');
    return root.getAttribute('format_id') === '1.8'
      && tabLength?.getAttribute('length') === '1.25'
      && elements.getAttribute('resolver') === 'hvl-default'
      && tables.some(table => /^Sabit\d+$/.test(table.getAttribute('tableName') || ''));
  }

  function getWebId(root) {
    const raw = root.querySelector('webID')?.getAttribute('id') || '';
    return raw.replace(/\s+/g, ' ').trim();
  }

  async function parseDocumentProperties(zip) {
    const entry = zip.file('documentproperties.xml');
    if (!entry) return {};
    const declaredSize = Number(entry?._data?.uncompressedSize || 0);
    if (declaredSize > 256 * 1024) return {};
    const source = await entry.async('string');
    if (source.length > 256 * 1024) return {};
    const safeSource = source.replace(/<!DOCTYPE[\s\S]*?>/i, '');
    const xml = new DOMParser().parseFromString(safeSource, 'application/xml');
    if (xml.querySelector('parsererror')) return {};
    const properties = {};
    xml.querySelectorAll('entry[key]').forEach(item => {
      properties[item.getAttribute('key')] = (item.textContent || '').trim();
    });
    return properties;
  }

  function parsePageNumberSettings(footerNode) {
    if (!footerNode?.hasAttribute('pageNumber-spec')) return null;
    return {
      separator: footerNode.getAttribute('pageNumber-seperator') || '/',
      prefix: footerNode.getAttribute('pageNumber-foreStr') || '',
      start: Number.parseInt(footerNode.getAttribute('pageNumber-pageStartNumStr') || '1', 10) || 1,
      family: footerNode.getAttribute('pageNumber-fontFace') || 'Arial',
      size: pt(footerNode.getAttribute('pageNumber-fontSize'), 9),
      bold: footerNode.getAttribute('pageNumber-fontBold') === 'true',
      italic: footerNode.getAttribute('pageNumber-fontItalic') === 'true',
      color: signedArgbToCss(footerNode.getAttribute('pageNumber-color'), '#000')
    };
  }

  async function parseUdf(file) {
    if (!file.name.toLocaleLowerCase('tr-TR').endsWith('.udf')) throw new Error('Yalnızca .udf dosyaları destekleniyor.');
    if (file.size > MAX_ARCHIVE_BYTES) throw new Error('Dosya 30 MB sınırını aşıyor.');

    const zip = await JSZip.loadAsync(file, { checkCRC32: true, createFolders: false });
    const archiveEntries = Object.values(zip.files);
    if (archiveEntries.length > 50) throw new Error('UDF arşivi beklenenden fazla dosya içeriyor.');
    const xmlEntry = zip.file('content.xml');
    if (!xmlEntry) throw new Error('UDF içinde content.xml bulunamadı.');
    const declaredXmlSize = Number(xmlEntry?._data?.uncompressedSize || 0);
    if (declaredXmlSize > MAX_XML_BYTES) throw new Error('Belge içeriği güvenli boyut sınırını aşıyor.');
    const xmlText = await xmlEntry.async('string');
    if (new Blob([xmlText]).size > MAX_XML_BYTES) throw new Error('Belge içeriği güvenli boyut sınırını aşıyor.');
    if (/<!DOCTYPE|<!ENTITY/i.test(xmlText)) throw new Error('Güvenli olmayan XML bildirimi nedeniyle belge açılmadı.');

    const xml = new DOMParser().parseFromString(xmlText, 'application/xml');
    const parserError = xml.querySelector('parsererror');
    if (parserError || xml.documentElement.tagName !== 'template') throw new Error('Belge XML yapısı okunamadı.');

    const root = xml.documentElement;
    const contentNode = directChild(root, 'content');
    const elements = directChild(root, 'elements');
    if (!contentNode || !elements) throw new Error('Belgenin metin veya eleman bölümü eksik.');

    const pool = codePoints(contentNode.textContent || '');
    const styleMap = parseStyles(root);
    const documentProperties = await parseDocumentProperties(zip);
    const arbsysGenerated = isArbsysGeneratedUdf(root, elements);
    const context = { pool, styleMap, inFooter: false, arbsysGenerated };
    const blocks = [];
    let footerNode = null;
    let headerNode = null;

    Array.from(elements.children).forEach(node => {
      if (node.tagName === 'footer') { footerNode = node; return; }
      if (node.tagName === 'header') { headerNode = node; return; }
      const block = renderBlock(node, context);
      if (block) blocks.push(block);
    });

    const footerBlocks = [];
    if (footerNode) {
      const footerContext = { ...context, inFooter: true };
      Array.from(footerNode.children).forEach(node => {
        const block = renderBlock(node, footerContext);
        if (block) footerBlocks.push(block);
      });
    }

    const headerBlocks = [];
    if (headerNode) {
      Array.from(headerNode.children).forEach(node => {
        const block = renderBlock(node, context);
        if (block) headerBlocks.push(block);
      });
    }

    return {
      id: uid(),
      name: file.name,
      size: file.size,
      blocks,
      footerBlocks,
      headerBlocks,
      pageFormat: parsePageFormat(root),
      arbsysGenerated,
      webId: getWebId(root),
      watermark: documentProperties.uyapsicil || '',
      pageNumber: parsePageNumberSettings(footerNode),
      pageNodes: [],
      scrollTop: 0
    };
  }

  function mmFromPt(value) {
    return value * 25.4 / 72;
  }

  function configurePage(page, documentModel) {
    const format = documentModel.pageFormat;
    page.style.setProperty('--margin-left', `${mmFromPt(format.leftPt)}mm`);
    page.style.setProperty('--margin-right', `${mmFromPt(format.rightPt)}mm`);
    page.style.setProperty('--margin-top', `${mmFromPt(format.topPt)}mm`);
    const reservedBottomMm = documentModel.arbsysGenerated
      ? mmFromPt(format.bottomPt)
      : (documentModel.webId ? Math.max(25, mmFromPt(format.bottomPt)) : Math.max(16, mmFromPt(format.bottomPt)));
    page.style.setProperty('--body-bottom', `${reservedBottomMm}mm`);
    page.style.setProperty('--header-offset', `${mmFromPt(format.headerOffsetPt)}mm`);
    page.style.setProperty('--footer-offset', `${mmFromPt(format.footerOffsetPt)}mm`);
    page.style.setProperty('--footer-max-height', `${Math.max(0, mmFromPt(format.bottomPt - format.footerOffsetPt))}mm`);
  }

  function createPageShell(documentModel) {
    const page = document.createElement('article');
    page.className = 'udf-page';
    page.classList.toggle('is-arbsys-generated', documentModel.arbsysGenerated);
    configurePage(page, documentModel);

    if (documentModel.watermark) {
      const watermark = document.createElement('div');
      watermark.className = 'watermark-layer';
      const grid = document.createElement('div');
      grid.className = 'watermark-grid';
      for (let columnIndex = 0; columnIndex < 7; columnIndex += 1) {
        const column = document.createElement('div');
        column.className = 'watermark-column';
        column.style.setProperty('--column-index', String(columnIndex));
        for (let rowIndex = 0; rowIndex < 15; rowIndex += 1) {
          const item = document.createElement('span');
          item.textContent = documentModel.watermark;
          column.appendChild(item);
        }
        grid.appendChild(column);
      }
      watermark.appendChild(grid);
      page.appendChild(watermark);
    }

    if (documentModel.arbsysGenerated && documentModel.headerBlocks.length) {
      const header = document.createElement('header');
      header.className = 'udf-header';
      documentModel.headerBlocks.forEach(block => header.appendChild(block.cloneNode(true)));
      page.appendChild(header);
    }

    const body = document.createElement('div');
    body.className = 'udf-body';
    if (!documentModel.arbsysGenerated) {
      documentModel.headerBlocks.forEach(block => body.appendChild(block.cloneNode(true)));
    }
    page.appendChild(body);

    if (documentModel.footerBlocks.length) {
      const footer = document.createElement('footer');
      footer.className = 'udf-footer';
      documentModel.footerBlocks.forEach(block => footer.appendChild(block.cloneNode(true)));
      page.appendChild(footer);
    }

    let number = null;
    if (documentModel.pageNumber) {
      number = document.createElement('div');
      number.className = 'page-number';
      number.style.fontFamily = `"${webFontFamily(documentModel.pageNumber.family)}", Arial, sans-serif`;
      number.style.fontSize = `${documentModel.pageNumber.size}pt`;
      number.style.fontWeight = documentModel.pageNumber.bold ? '700' : '400';
      number.style.fontStyle = documentModel.pageNumber.italic ? 'italic' : 'normal';
      number.style.color = documentModel.pageNumber.color;
      page.appendChild(number);
    }

    if (documentModel.webId) {
      const verify = document.createElement('div');
      verify.className = 'verification-footer';
      verify.textContent = `UYAP Bilişim Sistemindeki bu dokümana http://vatandas.uyap.gov.tr adresinden ${documentModel.webId} ile erişebilirsiniz.`;
      page.appendChild(verify);
    }

    return {
      page,
      body,
      number,
      bodyHeaderCount: documentModel.arbsysGenerated ? 0 : documentModel.headerBlocks.length
    };
  }

  function bodyOverflows(body) {
    return body.scrollHeight > body.clientHeight + 1;
  }

  function tabStopsFor(paragraph) {
    const explicit = String(paragraph.dataset.tabStops || '')
      .split(',')
      .map(value => Number.parseFloat(value))
      .filter(Number.isFinite)
      .sort((a, b) => a - b);
    return explicit;
  }

  function nextTabStop(currentPt, explicitStops) {
    const explicit = explicitStops.find(stop => stop > currentPt + .35);
    if (explicit !== undefined) return explicit;
    if (explicitStops.length > 1) {
      const last = explicitStops[explicitStops.length - 1];
      const previous = explicitStops[explicitStops.length - 2];
      const interval = Math.max(1, last - previous);
      return last + Math.max(1, Math.floor((currentPt - last) / interval) + 1) * interval;
    }
    if (explicitStops.length === 1) {
      const interval = Math.max(1, explicitStops[0]);
      return Math.max(1, Math.floor(currentPt / interval) + 1) * interval;
    }
    return Math.max(1, Math.floor(currentPt / DEFAULT_TAB_STOP_PT) + 1) * DEFAULT_TAB_STOP_PT;
  }

  function layoutParagraphTabs(paragraph) {
    const markers = paragraph.querySelectorAll(':scope > .udf-tab');
    if (!markers.length || !paragraph.isConnected) return;
    const explicitStops = tabStopsFor(paragraph);
    const page = paragraph.closest('.udf-page');
    const scale = page ? page.getBoundingClientRect().width / page.offsetWidth : 1;
    const paragraphLeft = paragraph.getBoundingClientRect().left;
    markers.forEach(marker => {
      marker.style.width = '0pt';
      for (let pass = 0; pass < 3; pass += 1) {
        const before = marker.getBoundingClientRect();
        const currentPt = ((before.left - paragraphLeft) / Math.max(scale, .01)) * 72 / 96;
        const targetPt = nextTabStop(Math.max(0, currentPt), explicitStops);
        marker.style.width = `${Math.max(1, targetPt - currentPt)}pt`;
        const after = marker.getBoundingClientRect();
        if (Math.abs(after.left - before.left) < .5) break;
      }
    });
  }

  function layoutBlockTabs(root) {
    if (root.matches?.('.udf-paragraph')) layoutParagraphTabs(root);
    root.querySelectorAll?.('.udf-paragraph').forEach(layoutParagraphTabs);
  }

  function isShortMeaningfulParagraph(block) {
    if (!block?.classList?.contains('udf-paragraph')) return false;
    const text = (block.textContent || '').replace(/\u200B/g, '').trim();
    return text.length > 0 && text.length <= 320;
  }

  function shouldMoveWithNext(block, nextBlock, body) {
    if (!isShortMeaningfulParagraph(block) || !isShortMeaningfulParagraph(nextBlock)) return false;
    const probe = nextBlock.cloneNode(true);
    body.appendChild(probe);
    layoutBlockTabs(probe);
    const pairOverflows = bodyOverflows(body);
    probe.remove();
    return pairOverflows;
  }

  function splitParagraphToFit(paragraph, body) {
    const runs = Array.from(paragraph.childNodes).map(node => ({
      template: node.nodeType === Node.ELEMENT_NODE ? node.cloneNode(false) : null,
      text: node.classList?.contains('udf-tab') ? '\t' : (node.textContent || ''),
      isTab: node.classList?.contains('udf-tab') || false
    }));
    const tokens = [];
    runs.forEach((run, runIndex) => {
      const parts = run.isTab ? ['\t'] : (run.text.match(/\S+\s*|\s+/g) || []);
      parts.forEach(text => tokens.push({ runIndex, text, isTab: run.isTab }));
    });
    if (tokens.length < 2) return null;

    const make = tokenList => {
      const p = paragraph.cloneNode(false);
      let lastRun = -1;
      let holder = null;
      tokenList.forEach(token => {
        if (token.runIndex !== lastRun) {
          holder = runs[token.runIndex].template ? runs[token.runIndex].template.cloneNode(false) : document.createTextNode('');
          p.appendChild(holder);
          lastRun = token.runIndex;
        }
        if (!token.isTab) {
          if (holder.nodeType === Node.TEXT_NODE) holder.textContent += token.text;
          else holder.appendChild(document.createTextNode(token.text));
        }
      });
      return p;
    };

    let low = 1;
    let high = tokens.length - 1;
    let best = 0;
    while (low <= high) {
      const middle = Math.floor((low + high) / 2);
      const candidate = make(tokens.slice(0, middle));
      body.appendChild(candidate);
      layoutBlockTabs(candidate);
      const fits = !bodyOverflows(body);
      candidate.remove();
      if (fits) { best = middle; low = middle + 1; }
      else high = middle - 1;
    }
    if (best <= 0 || best >= tokens.length) return null;
    const first = make(tokens.slice(0, best));
    const continuation = make(tokens.slice(best));
    continuation.classList.add('is-continuation');
    continuation.style.setProperty('--space-above', '0pt');
    continuation.style.setProperty('--first-indent', '0pt');
    return [first, continuation];
  }

  async function waitForDocumentFonts(documentModel) {
    const requests = new Set();
    const roots = [...documentModel.headerBlocks, ...documentModel.blocks, ...documentModel.footerBlocks];
    roots.forEach(root => {
      root.querySelectorAll('.udf-run').forEach(run => {
        const family = run.style.fontFamily;
        if (!family) return;
        const style = run.style.fontStyle || 'normal';
        const weight = run.style.fontWeight || '400';
        const size = run.style.fontSize || '12pt';
        requests.add(`${style} ${weight} ${size} ${family}`);
      });
    });
    await Promise.all(Array.from(requests, request => document.fonts.load(request)));
    await document.fonts.ready;
  }

  async function paginate(documentModel) {
    await waitForDocumentFonts(documentModel);
    el.measureHost.replaceChildren();
    const measurement = createPageShell(documentModel);
    el.measureHost.appendChild(measurement.page);
    layoutBlockTabs(measurement.page);

    const pages = [];
    let shell = measurement;
    let pending = documentModel.blocks.map(block => block.cloneNode(true));

    const commit = () => {
      pages.push(shell.page);
      shell = createPageShell(documentModel);
      el.measureHost.appendChild(shell.page);
      layoutBlockTabs(shell.page);
    };

    while (pending.length) {
      const block = pending.shift();
      if (block.dataset.pageBreak === 'true') {
        block.remove();
        if (shell.body.childElementCount > shell.bodyHeaderCount) commit();
        continue;
      }

      shell.body.appendChild(block);
      layoutBlockTabs(block);
      if (!bodyOverflows(shell.body)) {
        const nextBlock = pending[0];
        const bodyHasEarlierContent = shell.body.childElementCount > shell.bodyHeaderCount + 1;
        if (bodyHasEarlierContent && shouldMoveWithNext(block, nextBlock, shell.body)) {
          block.remove();
          commit();
          pending.unshift(block);
        }
        continue;
      }

      block.remove();
      const bodyHasContent = shell.body.childElementCount > shell.bodyHeaderCount;
      if (block.classList.contains('udf-paragraph')) {
        const split = splitParagraphToFit(block, shell.body);
        if (split) {
          shell.body.appendChild(split[0]);
          layoutBlockTabs(split[0]);
          commit();
          pending.unshift(split[1]);
          continue;
        }
      }

      if (bodyHasContent) {
        commit();
        pending.unshift(block);
      } else {
        shell.body.appendChild(block);
        commit();
      }
    }

    if (shell.body.childElementCount > shell.bodyHeaderCount || pages.length === 0) pages.push(shell.page);
    else shell.page.remove();

    pages.forEach((page, index) => {
      const number = page.querySelector('.page-number');
      if (number && documentModel.pageNumber) {
        const current = documentModel.pageNumber.start + index;
        const total = documentModel.pageNumber.start + pages.length - 1;
        number.textContent = `${documentModel.pageNumber.prefix}${current}${documentModel.pageNumber.separator}${total}`;
      }
      page.dataset.page = String(index + 1);
    });
    documentModel.pageNodes = pages.map(page => page.cloneNode(true));
    el.measureHost.replaceChildren();
  }

  function renderTabs() {
    el.tabs.replaceChildren();
    state.documents.forEach(documentModel => {
      const tab = document.createElement('div');
      tab.className = `document-tab${documentModel.id === state.activeId ? ' is-active' : ''}`;

      const select = document.createElement('button');
      select.type = 'button';
      select.className = 'document-tab-select';
      select.textContent = documentModel.name;
      select.title = documentModel.name;
      select.setAttribute('aria-pressed', documentModel.id === state.activeId ? 'true' : 'false');
      select.addEventListener('click', () => activateDocument(documentModel.id));

      const close = document.createElement('button');
      close.type = 'button';
      close.className = 'document-tab-close';
      close.textContent = '×';
      close.title = `${documentModel.name} belgesini kapat`;
      close.setAttribute('aria-label', `${documentModel.name} belgesini kapat`);
      close.addEventListener('click', () => closeDocument(documentModel.id));

      tab.append(select, close);
      el.tabs.appendChild(tab);
    });
  }

  function renderActiveDocument() {
    const documentModel = state.documents.find(item => item.id === state.activeId);
    el.pages.replaceChildren();
    if (!documentModel) return;

    documentModel.pageNodes.forEach(pageNode => {
      const frame = document.createElement('div');
      frame.className = 'page-frame';
      frame.dataset.page = pageNode.dataset.page;
      frame.appendChild(pageNode.cloneNode(true));
      el.pages.appendChild(frame);
    });
    requestAnimationFrame(() => {
      el.canvas.scrollTop = Math.min(documentModel.scrollTop || 0, el.canvas.scrollHeight);
      if (state.zoomMode === 'fit') applyFitZoom();
      else updateCurrentPage();
    });
  }

  function showWelcome() {
    state.activeId = null;
    state.currentPage = 0;
    state.zoomMode = 'fit';
    state.zoom = 1;
    state.fitZoom = 1;
    document.documentElement.style.setProperty('--zoom', '1');
    updateZoomControl();
    el.pages.replaceChildren();
    el.tabs.replaceChildren();
    el.viewer.hidden = true;
    el.welcome.hidden = false;
    el.app.classList.add('is-empty');
  }

  function closeDocument(id) {
    const index = state.documents.findIndex(item => item.id === id);
    if (index < 0) return;
    const wasActive = state.activeId === id;
    state.documents.splice(index, 1);
    if (!state.documents.length) {
      showWelcome();
      return;
    }
    if (wasActive) {
      const next = state.documents[Math.min(index, state.documents.length - 1)];
      activateDocument(next.id);
    } else {
      renderTabs();
    }
  }

  function activateDocument(id) {
    const current = state.documents.find(item => item.id === state.activeId);
    if (current) current.scrollTop = el.canvas.scrollTop;
    state.activeId = id;
    state.currentPage = 1;
    renderTabs();
    renderActiveDocument();
    const active = state.documents.find(item => item.id === id);
    if (active) showStatus(`${active.name} · ${active.pageNodes.length} sayfa`);
  }

  function updateCurrentPage() {
    const frames = Array.from(el.pages.querySelectorAll('.page-frame'));
    if (!frames.length) {
      state.currentPage = 0;
      el.pageIndicator.textContent = '0 / 0';
      return;
    }
    const canvasTop = el.canvas.getBoundingClientRect().top;
    let closest = frames[0];
    let distance = Infinity;
    frames.forEach(frame => {
      const currentDistance = Math.abs(frame.getBoundingClientRect().top - canvasTop - 16);
      if (currentDistance < distance) { distance = currentDistance; closest = frame; }
    });
    state.currentPage = Number.parseInt(closest.dataset.page, 10) || 1;
    el.pageIndicator.textContent = `${state.currentPage} / ${frames.length}`;
    el.prevPage.disabled = state.currentPage <= 1;
    el.nextPage.disabled = state.currentPage >= frames.length;
  }

  function goToPage(pageNumber) {
    const frames = Array.from(el.pages.querySelectorAll('.page-frame'));
    if (!frames.length) return;
    const targetNumber = Math.max(1, Math.min(pageNumber, frames.length));
    scrollPageToTop(targetNumber, 'smooth');
  }

  function scrollPageToTop(pageNumber, behavior = 'auto') {
    const frame = el.pages.querySelector(`.page-frame[data-page="${pageNumber}"]`);
    if (!frame) return;
    const canvasStyle = getComputedStyle(el.canvas);
    const pagesStyle = getComputedStyle(el.pages);
    const firstGap = Number.parseFloat(canvasStyle.paddingTop) || 28;
    const betweenGap = Number.parseFloat(pagesStyle.rowGap || pagesStyle.gap) || 28;
    const visibleGap = pageNumber === 1 ? firstGap : betweenGap;
    el.canvas.scrollTo({ top: Math.max(0, frame.offsetTop - visibleGap), behavior });
  }

  function updateZoomControl() {
    const choices = zoomChoices();
    el.zoomSelect.replaceChildren();
    choices.forEach(choice => {
      const option = document.createElement('option');
      option.value = choice.key;
      option.textContent = choice.label;
      el.zoomSelect.appendChild(option);
    });
    const wanted = state.zoomMode === 'fit' ? 'fit' : `fixed-${state.zoom}`;
    el.zoomSelect.value = choices.some(choice => choice.key === wanted) ? wanted : 'fit';
  }

  function zoomChoices() {
    const fitPercent = Math.round(state.fitZoom * 100);
    const choices = MANUAL_ZOOM_LEVELS
      .filter(level => Math.abs(level - state.fitZoom) > .004)
      .map(level => ({
        key: `fixed-${level}`,
        zoom: level,
        label: `${Math.round(level * 100)}%`,
        mode: 'manual'
      }));
    choices.push({
      key: 'fit',
      zoom: state.fitZoom,
      label: `${fitPercent}%`,
      mode: 'fit'
    });
    return choices.sort((a, b) => b.zoom - a.zoom || (a.mode === 'fit' ? -1 : 1));
  }

  function setZoom(value, mode = 'manual') {
    const minimum = mode === 'fit' ? .05 : .5;
    state.zoom = Math.max(minimum, Math.min(1.4, value));
    state.zoomMode = mode;
    document.documentElement.style.setProperty('--zoom', String(state.zoom));
    updateZoomControl();
    const pageNumber = Math.max(1, state.currentPage || 1);
    requestAnimationFrame(() => {
      scrollPageToTop(pageNumber, 'auto');
      updateCurrentPage();
    });
  }

  function calculateFitZoom() {
    const canvasStyle = getComputedStyle(el.canvas);
    const padding = Number.parseFloat(canvasStyle.paddingLeft) + Number.parseFloat(canvasStyle.paddingRight);
    const availableWidth = Math.max(1, el.canvas.clientWidth - padding - 8);
    return Math.min(1, availableWidth / A4_WIDTH_PX);
  }

  function applyFitZoom() {
    if (el.viewer.hidden) return;
    state.fitZoom = calculateFitZoom();
    setZoom(state.fitZoom, 'fit');
  }

  function changeZoom(direction) {
    const choices = zoomChoices().slice().sort((a, b) => a.zoom - b.zoom);
    const currentKey = state.zoomMode === 'fit' ? 'fit' : `fixed-${state.zoom}`;
    let index = choices.findIndex(choice => choice.key === currentKey);
    if (index < 0) {
      index = direction > 0
        ? choices.findIndex(choice => choice.zoom > state.zoom + .001) - 1
        : choices.findIndex(choice => choice.zoom >= state.zoom - .001);
    }
    const targetIndex = Math.max(0, Math.min(choices.length - 1, index + direction));
    const target = choices[targetIndex];
    setZoom(target.zoom, target.mode);
  }

  async function handleFiles(fileList) {
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;
    if (state.documents.length + incoming.length > MAX_FILES) {
      showError(`Aynı anda en fazla ${MAX_FILES} belge açabilirsiniz.`);
      return;
    }

    setBusy(true);
    let firstNewId = null;
    let succeeded = 0;
    for (const file of incoming) {
      try {
        showStatus(`${file.name} okunuyor…`);
        const model = await parseUdf(file);
        await paginate(model);
        state.documents.push(model);
        firstNewId ||= model.id;
        succeeded += 1;
      } catch (error) {
        showError(`${file.name}: ${error.message || 'Dosya açılamadı.'}`);
      }
    }
    setBusy(false);
    el.fileInput.value = '';
    el.addFileInput.value = '';

    if (succeeded) {
      el.app.classList.remove('is-empty');
      el.welcome.hidden = true;
      el.viewer.hidden = false;
      activateDocument(firstNewId || state.documents[0].id);
    }
  }

  function prevent(event) { event.preventDefault(); }
  ['dragenter', 'dragover'].forEach(type => {
    el.dropZone.addEventListener(type, event => { prevent(event); el.dropZone.classList.add('is-over'); });
  });
  ['dragleave', 'drop'].forEach(type => {
    el.dropZone.addEventListener(type, event => { prevent(event); el.dropZone.classList.remove('is-over'); });
  });
  el.dropZone.addEventListener('drop', event => handleFiles(event.dataTransfer.files));
  ['dragenter', 'dragover'].forEach(type => {
    el.canvas.addEventListener(type, event => { prevent(event); el.canvas.classList.add('is-over'); });
  });
  ['dragleave', 'drop'].forEach(type => {
    el.canvas.addEventListener(type, event => { prevent(event); el.canvas.classList.remove('is-over'); });
  });
  el.canvas.addEventListener('drop', event => handleFiles(event.dataTransfer.files));
  window.addEventListener('dragover', prevent);
  window.addEventListener('drop', prevent);
  el.fileInput.addEventListener('change', event => handleFiles(event.target.files));
  el.addFileInput.addEventListener('change', event => handleFiles(event.target.files));
  el.prevPage.addEventListener('click', () => goToPage(state.currentPage - 1));
  el.nextPage.addEventListener('click', () => goToPage(state.currentPage + 1));
  el.pageIndicator.addEventListener('click', () => goToPage(state.currentPage));
  el.zoomSelect.addEventListener('change', event => {
    if (event.target.value === 'fit') applyFitZoom();
    else setZoom(Number.parseFloat(event.target.value.replace('fixed-', '')), 'manual');
  });
  el.zoomOut.addEventListener('click', () => changeZoom(-1));
  el.zoomIn.addEventListener('click', () => changeZoom(1));
  el.canvas.addEventListener('scroll', () => requestAnimationFrame(updateCurrentPage), { passive: true });

  let resizeFrame = 0;
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(applyFitZoom);
  });

  document.addEventListener('keydown', event => {
    if (el.viewer.hidden) return;
    if ((event.ctrlKey || event.metaKey) && ['+', '=', '-','0'].includes(event.key)) {
      event.preventDefault();
      if (event.key === '-' ) changeZoom(-1);
      else if (event.key === '0') setZoom(1, 'manual');
      else changeZoom(1);
    }
    if (event.key === 'PageDown') { event.preventDefault(); goToPage(state.currentPage + 1); }
    if (event.key === 'PageUp') { event.preventDefault(); goToPage(state.currentPage - 1); }
  });
})();
