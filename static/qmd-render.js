// 共通の QMD → HTML 変換ロジック

function stripYaml(text) {
  const lines = (text || '').split(/\r?\n/);
  if (!lines.length || lines[0].trim() !== '---') return text || '';

  let i = 1;
  while (i < lines.length && lines[i].trim() !== '---') i++;
  if (i >= lines.length) return text || '';

  return lines.slice(i + 1).join('\n');
}

function sanitizeTeX(text) {
  if (!text) return '';
  let t = text;
  // MathJax が未対応の \hspace{...zw} を安全なスペースに変換
  t = t.replace(/\\hspace\{[^}]*zw\}/g, '\\quad ');

  // OCR 由来の pmatrix で、行ごとが空行で区切られている場合に行末に \\\\ を補う
  // 例: \begin{pmatrix} 1 & a & 0 \n\n 0 & 1 & 0 ...
  t = t.replace(/\\begin{pmatrix}([\s\S]*?)\\end{pmatrix}/g, (match, inner) => {
    const fixedInner = inner.replace(/\n\s*\n/g, '\\\\\n');
    return '\\begin{pmatrix}' + fixedInner + '\\end{pmatrix}';
  });

  return t;
}

function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function qmdToHtml(text) {
  const withoutYaml = stripYaml(text || '');
  const sanitized = sanitizeTeX(withoutYaml);
  const rawLines = sanitized.split(/\r?\n/);

  // フッターの区切り線とセットになった「元問題 PDF / 元問題スキャン」ブロックを事前に取り除く
  // 例:
  // ---
  // 元問題 PDF: [こちらを開く](...)
  const lines = [];
  for (let i = 0; i < rawLines.length; i++) {
    const trimmed = rawLines[i].trim();
    const next = (i + 1 < rawLines.length) ? rawLines[i + 1].trim() : '';

    if (
      trimmed === '---' &&
      (next.startsWith('元問題 PDF:') || next.startsWith('元問題スキャン:'))
    ) {
      // 区切り線とその直後の PDF/スキャン行を両方スキップ
      i++; // 次の行も飛ばす
      continue;
    }

    // 念のため、単独で現れた場合の PDF/スキャン行もスキップ
    if (trimmed.startsWith('元問題 PDF:') || trimmed.startsWith('元問題スキャン:')) {
      continue;
    }

    lines.push(rawLines[i]);
  }

  const htmlLines = lines.map(line => {
    const trimmed = line.trim();
    if (!trimmed) return '';

    // LaTeX の description 環境は MathJax が解釈できないので、簡易HTMLに変換
    if (/^\\begin{description}/.test(trimmed) || /^\\end{description}/.test(trimmed)) {
      return '';
    }
    const itemMatch = trimmed.match(/^\\item\[(.*?)\](.*)$/);
    if (itemMatch) {
      const label = escapeHtml(itemMatch[1].trim());
      const body = escapeHtml(itemMatch[2].trim());
      if (label) {
        return `<p><strong>${label}</strong> ${body}</p>`;
      }
      // ラベルなしの \item[] は普通の段落として表示
      return `<p>${body}</p>`;
    }

    // Markdown 見出し行 (### など) を HTML 見出しに変換
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const level = Math.min(headingMatch[1].length, 6);
      const content = escapeHtml(headingMatch[2].trim());
      return `<h${level}>${content}</h${level}>`;
    }

    // 画像行: ![](url)
    const imgOnly = trimmed.match(/^!\[[^\]]*\]\(([^)]+)\)/);
    if (imgOnly) {
      const src = imgOnly[1];
      return `<div><img src="${src}" style="max-width:100%;height:auto;"></div>`;
    }

    // 単純なリンク行: [text](url)
    const linkOnly = trimmed.match(/^\[([^\]]+)\]\(([^)]+)\)/);
    if (linkOnly) {
      const textLabel = escapeHtml(linkOnly[1]);
      const href = linkOnly[2];
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${textLabel}</a>`;
    }

    // 上記のどれにも当てはまらない行は、HTML をエスケープして返す
    // これにより 0<t<5/2 のような不等号を含む TeX も安全に埋め込める
    return escapeHtml(trimmed);
  });
  return htmlLines.join('\n');
}

function stripSolutionHeading(text) {
  const lines = (text || '').split(/\r?\n/);
  let i = 0;
  // 先頭の空行をスキップ
  while (i < lines.length && !lines[i].trim()) i++;

  if (i < lines.length && /^##\s*解答\s*$/.test(lines[i].trim())) {
    i++;
    // 見出し直後の空行も飛ばす
    while (i < lines.length && !lines[i].trim()) i++;
  } else {
    i = 0;
  }
  return lines.slice(i).join('\n');
}

function qmdSolutionToHtml(text) {
  const stripped = stripSolutionHeading(text || '');
  return qmdToHtml(stripped);
}

function appendCitation(html, citation) {
  if (!citation) return html;
  const escaped = escapeHtml(citation);
  return html + '\n\n<div class="citation">' + escaped + '</div>';
}
