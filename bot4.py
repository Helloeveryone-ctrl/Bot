import pywikibot
import mwparserfromhell

site = pywikibot.Site('simple', 'wikipedia')

popcat_template = pywikibot.Page(site, 'Template:popcat')

for page in popcat_template.getReferences(namespaces=[14], only_template_inclusion=True):
    category = pywikibot.Category(page)
    member_count = len(list(category.members()))
    
    if member_count < 3:
        continue
        
    old_text = page.text
    wikicode = mwparserfromhell.parse(old_text)
    
    for template in wikicode.filter_templates():
        if template.name.matches('popcat'):
            wikicode.remove(template)
        
    new_text = str(wikicode)
    
    if old_text != new_text:
        pywikibot.showDiff(old_text, new_text) # showdiffs
        page.text = new_text
        page.save(f'Remove {{popcat}} template as category now has three or more members')
