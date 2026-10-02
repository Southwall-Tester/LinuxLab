"""Render the Markdown subset used by notes.md in a plain Unicode terminal."""
import re
import shutil
import unicodedata


def display_width(text):
    return sum(0 if unicodedata.combining(ch) else
               2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
               for ch in text)


def inline_text(text):
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
    return text.replace('**', '').replace('`', '').replace('\\|', '|')


def wrap(text, width):
    """Wrap by terminal cells, preserving short English words where possible."""
    lines, line = [], ''
    for token in re.findall(r'[A-Za-z0-9_./:+~=@%#*<>-]+|\s+|.', text.expandtabs(4)):
        if token.isspace():
            if line and not line.endswith(' '):
                line += ' '
            continue
        if display_width(line + token) <= width:
            line += token
            continue
        if line.strip():
            lines.append(line.rstrip())
            line = ''
        for ch in token:
            if display_width(line + ch) > width:
                lines.append(line.rstrip())
                line = ''
            line += ch
    if line.strip() or not lines:
        lines.append(line.rstrip())
    return lines


def cells(line):
    # Notes tables do not contain literal pipe characters inside inline code.
    return [inline_text(cell.strip()) for cell in line.strip().strip('|').split('|')]


def table_lines(rows, width):
    headers, *body = rows
    count = len(headers)
    if width < (76 if count >= 4 else 48):
        result = []
        for row in body:
            for header, value in zip(headers, row):
                result.extend('  ' + part for part in wrap(header + '：' + value, width - 2))
            result.append('')
        return result
    available = width - 3 * count - 1
    weights = [0.18, 0.22, 0.36, 0.24] if count == 4 else [1 / count] * count
    widths = [max(display_width(h), int(available * w)) for h, w in zip(headers, weights)]
    while sum(widths) > available:
        col = max(range(count), key=lambda i: widths[i] - display_width(headers[i]))
        widths[col] -= 1
    widths[-1] += available - sum(widths)

    def border(left, middle, right):
        return left + middle.join('─' * (size + 2) for size in widths) + right

    result = [border('┌', '┬', '┐')]
    for index, row in enumerate(rows):
        wrapped = [wrap(value, size) for value, size in zip(row, widths)]
        for n in range(max(map(len, wrapped))):
            parts = []
            for lines, size in zip(wrapped, widths):
                value = lines[n] if n < len(lines) else ''
                parts.append(' ' + value + ' ' * (size - display_width(value) + 1))
            result.append('│' + '│'.join(parts) + '│')
        if index < len(rows) - 1:
            result.append(border('├', '┼', '┤'))
    result.append(border('└', '┴', '┘'))
    return result


def render_markdown(text, width=None):
    """Keep Markdown in the file; output readable headings, tables and text."""
    width = max(20, min(width or shutil.get_terminal_size((100, 24)).columns, 120))
    lines = text.splitlines()
    result, index, in_code = [], 0, False
    while index < len(lines):
        line = lines[index]
        if line.startswith('```'):
            in_code = not in_code
            index += 1
            continue
        if in_code:
            result.extend('  ' + part for part in wrap(line, width - 2))
        elif (line.startswith('|') and index + 1 < len(lines)
              and all(re.fullmatch(r':?-{3,}:?', cell) for cell in cells(lines[index + 1]))):
            rows = [cells(line)]
            index += 2
            while index < len(lines) and lines[index].startswith('|'):
                row = cells(lines[index])
                if len(row) != len(rows[0]):
                    raise ValueError('笔记表格的列数不一致。')
                rows.append(row)
                index += 1
            result.extend(table_lines(rows, width))
            continue
        elif re.match(r'^#{1,6} ', line):
            title = inline_text(line.lstrip('#').strip())
            result.extend(wrap(title, width))
            result.append('─' * min(width, display_width(title)))
        elif line.startswith('- '):
            parts = wrap(inline_text(line[2:]), width - 2)
            result.extend(('- ' if n == 0 else '  ') + part for n, part in enumerate(parts))
        else:
            result.extend(wrap(inline_text(line), width))
        index += 1
    return '\n'.join(result).rstrip()
