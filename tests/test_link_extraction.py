import re

text = """
Premium Referrals, [24-12-2025 09:09]
Company - ideaForge
Role - Graduate Engineer Trainee
Batch - 2024/2025/2026
CTC - Competitive
Location - India

Apply Link - https://app.webbtree.com/company/ideaforge/jobs/graduate-engineer-trainees-get-82799cd3-923e-400f-832a-96655175b87d

Premium Referrals, [24-12-2025 09:09]
Company - AppsForBharat
Role - Designer Intern
Batch - 2024/2025/2026/2027
Stipend - Competitive
Location - Bengaluru

Apply Link - https://careers.kula.ai/appsforbharat/19758
"""

def extract_link(text):
    pattern = r'https?://[^\s]+'
    match = re.search(pattern, text)
    return match.group(0) if match else None

sections = re.split(r'\n\s*\n|---+', text)
for i, section in enumerate(sections):
    if len(section.strip()) < 10: continue
    print(f"--- Section {i} ---")
    link = extract_link(section)
    print(f"Link found: {link}")

