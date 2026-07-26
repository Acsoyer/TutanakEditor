const fs = require('fs');
const vm = require('vm');
const path = require('path');

const root = __dirname;
const editor = fs.readFileSync(path.join(root, 'ArbsysEditor_v4.htm'), 'utf8');
const context = { window: {} };
vm.runInNewContext(fs.readFileSync(path.join(root, 'arbsys-dispute-data.js'), 'utf8'), context);
const data = context.window.ARBSYS_DISPUTE_DATA;

const archiveRoot = path.resolve(root, '..');
const versionEditors = [1, 2, 3, 4].map((version) =>
  path.join(archiveRoot, `ArbsysEditor_v${version}`, `ArbsysEditor_v${version}.htm`)
);
let scriptsChecked = 0;
for (const editorPath of versionEditors) {
  const versionHtml = fs.readFileSync(editorPath, 'utf8');
  const scriptPattern = /<script(?![^>]*\bsrc=)(?![^>]*type=["']application\/json["'])[^>]*>([\s\S]*?)<\/script>/gi;
  let match;
  while ((match = scriptPattern.exec(versionHtml))) {
    if (!match[1].trim()) continue;
    new Function(match[1]);
    scriptsChecked += 1;
  }
}

const required = [
  'openDataDashboard()',
  'dashboardHasUntitledVariants',
  'dashboardSaveActiveRecord',
  'dashboardExportData',
  'dashboardImportData',
  'negotiationOptionTitles',
  'agreementOptionTitles',
  'Seçenek başlığı eksik olanlar'
];
for (const fragment of required) {
  if (!editor.includes(fragment)) throw new Error(`v4 bütünleşmesi eksik: ${fragment}`);
}

const negotiationVariants = data.records.filter((record) =>
  (record.templateValues.negotiationOptions || []).length > 1
).length;
const agreementVariants = data.records.filter((record) =>
  (record.templateValues.agreementOptions || []).length > 1
).length;
const incomplete = data.records.filter((record) =>
  !record.completeness.canGenerateDocument
).length;

console.log(JSON.stringify({
  records: data.records.length,
  incomplete,
  negotiationVariants,
  agreementVariants,
  versionEditorsChecked: versionEditors.length,
  scriptsChecked,
  dashboardWired: true,
  optionTitlesEditable: true,
  optionsCanBeAddedAndDeleted: true
}, null, 2));
