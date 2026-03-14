import re
import json

def parse_sun_tzu(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    book_data = {
        "title": "The Art of War",
        "author": "Sun Tzu",
        "translator": "Lionel Giles",
        "chapters": []
    }

    current_chapter = None
    chapter_pattern = re.compile(r'^([IVX]+)\.\s+(.+)$')
    quote_pattern = re.compile(r'^(\d+(?:,\d+)?)\.\s+(.+)$')

    roman_to_int = {
        'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
        'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
        'XI': 11, 'XII': 12, 'XIII': 13
    }

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for Chapter Title
        chapter_match = chapter_pattern.match(line)
        if chapter_match:
            roman_num = chapter_match.group(1)
            title = chapter_match.group(2)
            current_chapter = {
                "chapter_number": roman_to_int.get(roman_num, 0),
                "chapter_title": title,
                "quotes": []
            }
            book_data["chapters"].append(current_chapter)
            continue

        # Check for Quote
        quote_match = quote_pattern.match(line)
        if quote_match and current_chapter is not None:
            quote_num = quote_match.group(1)
            text = quote_match.group(2)
            current_chapter["quotes"].append({
                "id": f"{current_chapter['chapter_number']}.{quote_num}",
                "text": text
            })
        elif current_chapter is not None and current_chapter["quotes"]:
            # Append continuation of previous quote if it doesn't start with a number
            # but only if it's not a new chapter title (already handled)
            # and looks like text.
            # However, looking at the file, most quotes are single lines or start with a number.
            # There might be some multi-line quotes.
            # Let's assume for now that if it doesn't match the quote pattern and we are in a chapter,
            # it might be a continuation. But the file format seems to have one quote per paragraph/line usually.
            # Let's check if the previous line was a quote.
            last_quote = current_chapter["quotes"][-1]
            last_quote["text"] += " " + line

    return book_data

if __name__ == "__main__":
    file_path = "references/sun-tzu-art-of-war.md"
    data = parse_sun_tzu(file_path)
    
    output_path = "references/sun-tzu-quotes.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"Successfully created {output_path}")
