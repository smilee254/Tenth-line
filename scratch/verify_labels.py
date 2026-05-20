import fitz

doc = fitz.open('wide_output.pdf')
page = doc[0]
for b in page.get_text('dict')['blocks']:
    if b['type'] == 0:  # text
        for l in b['lines']:
            for s in l['spans']:
                if '-' in s['text'] and s['text'].strip('-').isdigit():
                    print(f"Label: {s['text']}, Origin: {s['origin']}, Font: {s['font']}, Size: {s['size']}")
