import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceRoot = path.join(projectRoot, 'src');
const allowedHex = new Set([
  '#F5F0DC',
  '#EDE6C9',
  '#94875F',
  '#173A2B',
  '#1B4332',
  '#1F5A40',
  '#2C513F',
  '#4B5F54',
  '#9BD3AE',
]);
const hexColorPattern = /#[\da-f]{3,8}\b/gi;
const colorFunctionPattern = /\b(?:rgba?|hsla?)\s*\(/gi;
const defaultColorClassPattern =
  /\b(?:bg|text|border|ring|outline|divide|from|via|to|fill|stroke|decoration|shadow|accent|caret|placeholder)-(?:white|black|(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)(?:-(?:50|100|200|300|400|500|600|700|800|900|950))?)(?:\/\d{1,3})?\b/gi;
const legacyPaletteClassPattern = /\b(?:bg|text|border)-(?:moss|gold|clay|forest-soft)(?:\/\d{1,3})?\b/gi;
const darkVariantPattern = /(?:^|[\s"'`])dark:[^\s"'`]*/g;
const violations = [];

async function scanDirectory(directory) {
  const entries = await readdir(directory, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    const relativePath = path.relative(sourceRoot, fullPath).replaceAll(path.sep, '/');

    if (entry.isDirectory()) {
      if (relativePath === 'components/archive') continue;
      await scanDirectory(fullPath);
      continue;
    }

    if (!entry.isFile() || relativePath === 'index.css' || relativePath === 'components/Radar.jsx') continue;

    const contents = await readFile(fullPath, 'utf8');
    const lines = contents.split(/\r?\n/);
    const reportMatches = (pattern, message, valueFor) => {
      pattern.lastIndex = 0;
      lines.forEach((line, index) => {
        for (const match of line.matchAll(pattern)) {
          violations.push(`${relativePath}:${index + 1}: ${message}: ${valueFor(match)}`);
        }
      });
    };

    reportMatches(colorFunctionPattern, 'disallowed color function', (match) => match[0]);
    reportMatches(defaultColorClassPattern, 'default Tailwind color class', (match) => match[0]);
    reportMatches(legacyPaletteClassPattern, 'legacy palette class', (match) => match[0]);
    reportMatches(darkVariantPattern, 'dark mode variant', (match) => match[0]);

    for (const match of contents.matchAll(hexColorPattern)) {
      if (!allowedHex.has(match[0].toUpperCase())) {
        const line = contents.slice(0, match.index).split(/\r?\n/).length;
        if (!violations.includes(`${relativePath}:${line}: disallowed hard-coded color: ${match[0].toUpperCase()}`)) {
          violations.push(`${relativePath}:${line}: disallowed hard-coded color: ${match[0].toUpperCase()}`);
        }
      }
    }
  }
}

await scanDirectory(sourceRoot);

if (violations.length > 0) {
  console.error(`Color policy violations (${violations.length}):`);
  for (const violation of violations) console.error(`  ${violation}`);
  process.exitCode = 1;
} else {
  console.log('Color policy check passed.');
}
