import re

message_text = """
Premium Referrals, [24-12-2025 09:09]
Company - ideaForge
Role - GET
Location - India

Apply Link - https://example.com/1

Company - AppsForBharat
Role - Designer Intern
Batch - 2024/2025/2026/2027
Stipend - Competitive
Location - Bengaluru

Apply Link - https://careers.kula.ai/appsforbharat/19758
"""

# Simulate LLM Result
jobs = [
    {"company_name": "ideaForge"},
    {"company_name": "AppsForBharat"}
]

print("--- RAW MESSAGE ---")
print(message_text)
print("-------------------")

# Logic from llm_processor.py
job_indices = []
current_search_pos = 0

for i, job in enumerate(jobs):
    cname = job.get('company_name', '')
    if not cname: continue
    
    idx = message_text.find(cname, current_search_pos)
    if idx == -1:
        idx = message_text.lower().find(cname.lower(), current_search_pos)
    
    if idx != -1:
        job_indices.append((i, idx))
        current_search_pos = idx + len(cname)

print(f"\nFound Indices: {job_indices}")

if job_indices:
    for k in range(len(job_indices)):
        job_idx, start_pos = job_indices[k]
        
        if k < len(job_indices) - 1:
            _, next_start = job_indices[k+1]
            end_pos = next_start
        else:
            end_pos = len(message_text)
        
        # Lookback Logic
        lookback_limit = max(0, start_pos - 50)
        prefix_text = message_text[lookback_limit:start_pos]
        last_newline_idx = prefix_text.rfind('\n')
        
        if last_newline_idx != -1:
            real_start = lookback_limit + last_newline_idx + 1
        else:
            real_start = lookback_limit
            
        raw_slice = message_text[real_start:end_pos].strip()
        
        print(f"\n--- Job {job_idx} Extracted Text ---")
        print(f"'{raw_slice}'")
