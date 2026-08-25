import os
import json
import datetime

def generate_sitemap():
    today = datetime.date.today().isoformat()
    base_url = 'https://krec.kz'
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pages_path = os.path.join(base_dir, 'kvit_test', 'data', 'extracted_portal_pages.json')
    docs_path = os.path.join(base_dir, 'kvit_test', 'data', 'documents.json')
    out_path = os.path.join(base_dir, 'kvit_test', 'static', 'sitemap.xml')
    
    with open(pages_path, 'r', encoding='utf-8') as f:
        pages = json.load(f)
    
    with open(docs_path, 'r', encoding='utf-8') as f:
        docs = json.load(f)
    
    urls = []
    
    # Core high-priority pages
    core_pages = [
        ('/', 1.0, 'daily'),
        ('/kvit/', 0.9, 'weekly'),
        ('/reports.php', 0.8, 'monthly'),
        ('/tarif.php', 0.8, 'monthly'),
        ('/zakup.php', 0.8, 'monthly'),
        ('/tu.php', 0.8, 'monthly'),
        ('/load.php', 0.8, 'monthly'),
        ('/contacts.php', 0.8, 'monthly'),
        ('/vacancy.php', 0.7, 'monthly'),
        ('/price.php', 0.7, 'monthly'),
        ('/pd_byt_potr.php', 0.7, 'monthly'),
        ('/ktp.php', 0.7, 'monthly'),
        ('/lines10kv.php', 0.7, 'monthly'),
        ('/tbinst.php', 0.7, 'monthly'),
        ('/tbquest.php', 0.7, 'monthly'),
    ]
    
    for path, priority, freq in core_pages:
        urls.append((f"{base_url}{path}", priority, freq))
    
    # Portal section pages
    for k in pages.keys():
        if k in ('404', 'home'):
            continue
        full_url = f"{base_url}/{k}.php"
        if not any(u[0] == full_url for u in urls):
            urls.append((full_url, 0.7, 'monthly'))
    
    # Document pages
    for doc_key in docs.keys():
        full_url = f"{base_url}/{doc_key}"
        if not any(u[0] == full_url for u in urls):
            urls.append((full_url, 0.6, 'yearly'))
    
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    
    for url, priority, freq in urls:
        xml_lines.append('  <url>')
        xml_lines.append(f'    <loc>{url}</loc>')
        xml_lines.append(f'    <lastmod>{today}</lastmod>')
        xml_lines.append(f'    <changefreq>{freq}</changefreq>')
        xml_lines.append(f'    <priority>{priority:.1f}</priority>')
        xml_lines.append('  </url>')
    
    xml_lines.append('</urlset>')
    
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml_lines) + '\n')
    
    print(f"Sitemap successfully generated with {len(urls)} URLs at {out_path}")

if __name__ == '__main__':
    generate_sitemap()
