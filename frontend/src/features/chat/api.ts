const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

async function requestJSON(endpoint: string, options?: RequestInit) {
  const res = await fetch(`${API_URL}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchCustomQuestions() {
  return requestJSON('/api/chat/custom-questions');
}

export async function createCustomQuestion(label: string, query: string) {
  return requestJSON('/api/chat/custom-questions', {
    method: 'POST',
    body: JSON.stringify({ label, query }),
  });
}

export async function deleteCustomQuestion(id: string) {
  return requestJSON(`/api/chat/custom-questions/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export async function requestChat(payload: Record<string, unknown>) {
  return requestJSON('/api/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
