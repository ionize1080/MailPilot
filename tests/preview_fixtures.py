"""Small editable Office documents and a two-page PDF for the real preview engines."""
import base64
import shutil
import zipfile
from pathlib import Path

def create(folder):
    folder.mkdir(parents=True, exist_ok=True)
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    def relations(targets):
        return '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
            f'<Relationship Id="rId{i}" Type="{rel}{kind}" Target="{target}"/>' for i,(kind,target) in enumerate(targets, 1)) + '</Relationships>'
    def office(name, main, parts):
        with zipfile.ZipFile(folder/name, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("_rels/.rels", relations([("officeDocument", main)]))
            manifest = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            for part, kind, data in parts:
                if kind:
                    manifest += f'<Override PartName="/{part}" ContentType="application/vnd.openxmlformats-officedocument.{kind}+xml"/>'
                z.writestr(part, data)
            z.writestr("[Content_Types].xml", manifest + '</Types>')
    sheets = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="' + rel[:-1] + '"><sheets><sheet name="采购清单" sheetId="1" r:id="rId1"/><sheet name="复核" sheetId="2" r:id="rId2"/></sheets></workbook>'
    parts = [('xl/workbook.xml','spreadsheetml.sheet.main',sheets),
             ('xl/_rels/workbook.xml.rels',None,relations([('worksheet','worksheets/sheet1.xml'),('worksheet','worksheets/sheet2.xml'),('styles','styles.xml')])),
             ('xl/styles.xml','spreadsheetml.styles','<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="1"><xf xfId="0"/></cellXfs></styleSheet>')]
    for i in (1,2):
        parts.append((f'xl/worksheets/sheet{i}.xml', 'spreadsheetml.worksheet',
            f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>采购数量</t></is></c><c r="B1"><v>{i*27}</v></c></row></sheetData></worksheet>'))
    office('报价单.xlsx','xl/workbook.xml',parts)
    office('交付说明.docx','word/document.xml',[('word/document.xml','wordprocessingml.document.main',
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Delivery receipt · 交付说明</w:t></w:r></w:p><w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>')])
    ns = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="'+rel[:-1]+'"'
    tree = '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
    parts = [('ppt/presentation.xml','presentationml.presentation.main',f'<p:presentation {ns}><p:sldIdLst><p:sldId id="256" r:id="rId1"/><p:sldId id="257" r:id="rId2"/></p:sldIdLst><p:sldSz cx="9144000" cy="5143500"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'),
             ('ppt/_rels/presentation.xml.rels', None,relations([('slide',f'slides/slide{i}.xml') for i in (1,2)]))]
    for i in (1,2):
        shape = f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="360000" y="360000"/><a:ext cx="8000000" cy="2000000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="4400"/><a:t>Delivery · 交付 {i}</a:t></a:r></a:p></p:txBody></p:sp>'
        parts.append((f'ppt/slides/slide{i}.xml','presentationml.slide',f'<p:sld {ns}><p:cSld><p:spTree>{tree}{shape}</p:spTree></p:cSld></p:sld>'))
    office('进度汇报.pptx','ppt/presentation.xml',parts)
    objects = ['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Count 2 /Kids [3 0 R 4 0 R] >>']
    for i in (5,6):
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 240] /Resources << /Font << /F1 7 0 R >> >> /Contents {i} 0 R >>')
    for i in (1,2):
        content = f'BT /F1 24 Tf 35 140 Td (MailPilot delivery {i}) Tj ET\n'
        objects.append(f'<< /Length {len(content)} >>\nstream\n{content}endstream')
    objects.append('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    data = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{i} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(data)
    data += b'xref\n0 8\n0000000000 65535 f \n' + b''.join(f"{v:010} 00000 n \n".encode() for v in offsets[1:])
    (folder/'确认书.pdf').write_bytes(data+f'trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
    (folder/'记录.md').write_text('# 采购记录\n\n| 物料 | 数量 |\n| --- | --- |\n| 纸张 | 24 |',encoding='utf-8')
    (folder/'说明.txt').write_text('收货时间为周三下午。',encoding='gb18030')
    shutil.copyfile(Path(__file__).resolve().parents[1]/'docs/icon-80.png',folder/'签名.png')
    # Two solid-color 12 x 7 images; the JPEG exercises an attachment with only a MIME type.
    (folder/'收货照片').write_bytes(base64.b64decode(
        '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwg'
        'JC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIy'
        'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAHAAwDASIAAhEBAxEB/8QA'
        'FQABAQAAAAAAAAAAAAAAAAAAAAT/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAA'
        'AAAABf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AJACIR//2Q=='))
    (folder/'缩略图.webp').write_bytes(base64.b64decode('UklGRh4AAABXRUJQVlA4TBEAAAAvC4ABAAdQwirVsv+BiOh/AAA='))
    (folder/'数据.csv').write_text('物料,数量\n纸张,24\n',encoding='utf-8')

if __name__ == "__main__":
    import sys
    create(Path(sys.argv[1]))
