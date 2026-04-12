from backend.rag.generator import detect_query_type, generate_structured_response

# ---- 测试1：检测 query type 是否识别正确 ----
test_queries = [
    "What did Flex say about tariffs two quarters ago?",
    "How has Flex's stance on tariffs shifted over time?",
    "What was Flex's position on tariffs last quarter?",
    "Compare Flex and Jabil CapEx",   # 这条应该识别为 comparison，不是 historical
    "What is Flex's revenue?",         # 这条应该识别为 numeric
]

print("=== Query Type Detection ===")
for q in test_queries:
    qtype = detect_query_type(q)
    print(f"[{qtype}] {q}")


fake_context = """
[Q3 FY2025 - Flex Earnings Call]
CEO: "The tariff situation remains fluid and uncertain. We are seeing customers delay
purchasing decisions as they wait for more clarity on policy direction."

[Q2 FY2025 - Flex Earnings Call]
CFO: "We are working closely with our customers on a case-by-case basis to navigate
the tariff impacts. It requires more effort but we are managing through it."

[Q1 FY2025 - Flex Earnings Call]
CEO: "Tariffs are largely a pass-through cost for us. We do not expect any material
impact on our margins as a result of current tariff policies."
"""

query = "What did Flex say about tariffs over the past few quarters?"

result = generate_structured_response(query, fake_context)

print(f"Query Type: {result['query_type']}")
print(f"Confidence: {result['confidence']}")
print(f"\nTone Shift: {result.get('tone_shift', 'N/A')}")
print(f"\nFinal Answer:\n{result['answer']}")
print(f"\nQuarters Detail:")
for q in result.get('quarters', []):
    print(f"  {q['quarter']} [{q['tone']}]: {q['stance']}")
