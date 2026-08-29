'use client';

import { FormEvent, Fragment, KeyboardEvent, useCallback, useEffect, useMemo, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_CODEATLAS_API_URL ?? 'http://localhost:8000/api';

type Project = {
  id: string;
  name: string;
  source: string;
  source_type: 'local' | 'github' | 'demo';
  branch: string;
  status: string;
  indexed_at: string | null;
  created_at: string;
  file_count: number;
  symbol_count: number;
  chunk_count: number;
  embedding_provider: string;
};

type FileItem = { path: string; language: string; lines: number };

type Citation = {
  number: number;
  chunk_id: string;
  file_path: string;
  language: string;
  symbol: string | null;
  kind: string;
  start_line: number;
  end_line: number;
  excerpt: string;
  score: number;
};

type Answer = {
  question: string;
  answer: string;
  citations: Citation[];
  confidence: 'high' | 'medium' | 'low';
  answer_mode: 'openai' | 'local-extractive';
  elapsed_ms: number;
};

type ConversationItem = { id: string; question: string; result?: Answer; error?: string };

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? 'Request failed');
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

function relativeTime(value: string | null): string {
  if (!value) return 'Not indexed';
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return 'Indexed just now';
  if (seconds < 3600) return `Indexed ${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `Indexed ${Math.floor(seconds / 3600)}h ago`;
  return `Indexed ${Math.floor(seconds / 86400)}d ago`;
}

function fileLabel(language: string): string {
  const labels: Record<string, string> = {
    python: 'PY', javascript: 'JS', typescript: 'TS', markdown: 'MD',
    java: 'JV', go: 'GO', rust: 'RS', config: '{}', sql: 'DB',
  };
  return labels[language] ?? '·';
}

function InlineAnswer({ text, onCitation }: { text: string; onCitation: (number: number) => void }) {
  const parts = text.split(/(`[^`]+`|\[\d+\])/g);
  return parts.map((part, index) => {
    const citation = part.match(/^\[(\d+)\]$/);
    if (citation) {
      return <button className="cite" key={`${part}-${index}`} onClick={() => onCitation(Number(citation[1]))} type="button">{citation[1]}</button>;
    }
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function AnswerBody({ text, onCitation }: { text: string; onCitation: (number: number) => void }) {
  return (
    <div className="answer-copy answer-text">
      {text.split('\n').map((line, index) => {
        if (!line.trim()) return <div className="answer-space" key={index} />;
        if (line.startsWith('- ')) return <p className="answer-bullet" key={index}><span>—</span><InlineAnswer text={line.slice(2)} onCitation={onCitation} /></p>;
        const numbered = line.match(/^(\d+)\.\s+(.+)/);
        if (numbered) return <p className="answer-bullet" key={index}><span>{numbered[1]}.</span><InlineAnswer text={numbered[2]} onCitation={onCitation} /></p>;
        return <p key={index}><InlineAnswer text={line} onCitation={onCitation} /></p>;
      })}
    </div>
  );
}

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [files, setFiles] = useState<FileItem[]>([]);
  const [fileFilter, setFileFilter] = useState('');
  const [question, setQuestion] = useState('');
  const [conversation, setConversation] = useState<ConversationItem[]>([]);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [source, setSource] = useState('');
  const [projectName, setProjectName] = useState('');
  const [busy, setBusy] = useState<string | null>('Connecting to the CodeAtlas API…');
  const [backendError, setBackendError] = useState('');
  const [formError, setFormError] = useState('');

  const selected = projects.find((project) => project.id === selectedId) ?? projects[0] ?? null;
  const latestAnswer = [...conversation].reverse().find((item) => item.result)?.result;

  const refreshProjects = useCallback(async (preferredId?: string) => {
    const result = await api<Project[]>('/projects');
    setProjects(result);
    setSelectedId((current) => preferredId ?? (current || result[0]?.id || ''));
    setBackendError('');
  }, []);

  useEffect(() => {
    refreshProjects()
      .catch((error: Error) => setBackendError(error.message))
      .finally(() => setBusy(null));
  }, [refreshProjects]);

  useEffect(() => {
    if (!selected?.id) {
      setFiles([]);
      return;
    }
    api<FileItem[]>(`/projects/${selected.id}/files`)
      .then(setFiles)
      .catch((error: Error) => setBackendError(error.message));
  }, [selected?.id]);

  const visibleFiles = useMemo(() => {
    const needle = fileFilter.toLowerCase();
    return files.filter((file) => file.path.toLowerCase().includes(needle)).slice(0, 180);
  }, [files, fileFilter]);

  function chooseCitation(number: number, result = latestAnswer) {
    const citation = result?.citations.find((item) => item.number === number);
    if (citation) setActiveCitation(citation);
  }

  async function addRepository(event: FormEvent) {
    event.preventDefault();
    setFormError('');
    setBusy('Indexing repository…');
    try {
      const created = await api<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify({ source, name: projectName || null }),
      });
      await refreshProjects(created.id);
      setConversation([]);
      setActiveCitation(null);
      setShowAdd(false);
      setSource('');
      setProjectName('');
    } catch (error) {
      setFormError((error as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function loadDemo() {
    setBusy('Indexing the TinyShop demo…');
    try {
      const created = await api<Project>('/projects/demo', { method: 'POST', body: '{}' });
      await refreshProjects(created.id);
      setConversation([]);
      setActiveCitation(null);
    } catch (error) {
      setBackendError((error as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function reindex() {
    if (!selected) return;
    setBusy(`Re-indexing ${selected.name}…`);
    try {
      const updated = await api<Project>(`/projects/${selected.id}/index`, { method: 'POST', body: '{}' });
      await refreshProjects(updated.id);
    } catch (error) {
      setBackendError((error as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function ask(event?: FormEvent, suggestedQuestion?: string) {
    event?.preventDefault();
    const prompt = (suggestedQuestion ?? question).trim();
    if (!prompt || !selected || busy) return;
    const itemId = crypto.randomUUID();
    setConversation((items) => [...items, { id: itemId, question: prompt }]);
    setQuestion('');
    setBusy('Retrieving code evidence…');
    try {
      const result = await api<Answer>(`/projects/${selected.id}/ask`, {
        method: 'POST',
        body: JSON.stringify({ question: prompt, top_k: 8 }),
      });
      setConversation((items) => items.map((item) => item.id === itemId ? { ...item, result } : item));
      setActiveCitation(result.citations[0] ?? null);
    } catch (error) {
      setConversation((items) => items.map((item) => item.id === itemId ? { ...item, error: (error as Error).message } : item));
    } finally {
      setBusy(null);
    }
  }

  function handleComposerKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void ask();
    }
  }

  return (
    <main className="atlas-shell">
      <header className="topbar">
        <div className="brand" aria-label="CodeAtlas home">
          <span className="brand-mark">CA</span><span>CodeAtlas</span><span className="beta">LOCAL</span>
        </div>
        {selected ? (
          <label className="project-switcher">
            <span className="repo-dot" aria-hidden="true" />
            <select value={selected.id} onChange={(event) => { setSelectedId(event.target.value); setConversation([]); setActiveCitation(null); }}>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
            <span className="branch">{selected.branch}</span>
          </label>
        ) : <div />}
        <div className="top-actions">
          {selected && <span className="index-state"><i /> {relativeTime(selected.indexed_at)}</span>}
          {selected && <button className="ghost-button" disabled={!!busy} onClick={reindex} type="button">Re-index</button>}
          <button className="primary-button" onClick={() => setShowAdd(true)} type="button">Add repository</button>
        </div>
      </header>

      {backendError && (
        <div className="backend-banner" role="alert">
          <strong>Backend unavailable.</strong> {backendError}. Start the API on port 8000, then refresh this page.
        </div>
      )}

      {!selected && !busy ? (
        <section className="welcome-state">
          <span className="welcome-mark">CA</span>
          <span className="eyebrow">Your repository, mapped</span>
          <h1>Ask the codebase.<br />Follow the evidence.</h1>
          <p>Index a local folder or public GitHub repository. CodeAtlas answers with exact files, symbols, and line ranges.</p>
          <div className="welcome-actions">
            <button className="primary-button large" onClick={() => setShowAdd(true)} type="button">Add your repository</button>
            <button className="ghost-button large" onClick={loadDemo} type="button">Explore the TinyShop demo</button>
          </div>
          <div className="feature-strip"><span>Structure-aware chunks</span><span>Hybrid retrieval</span><span>Grounded citations</span><span>Runs without an API key</span></div>
        </section>
      ) : selected ? (
        <section className="workspace">
          <aside className="repository-panel" aria-label="Repository explorer">
            <div className="panel-heading">
              <div><span className="eyebrow">Repository</span><h2>{selected.name}</h2></div>
              <span className={`status-chip ${selected.status}`}>{selected.status}</span>
            </div>
            <label className="file-search"><span aria-hidden="true">⌕</span><input aria-label="Filter files" onChange={(event) => setFileFilter(event.target.value)} placeholder="Filter files…" value={fileFilter} /><kbd>/</kbd></label>
            <nav className="file-tree" aria-label="Repository files">
              {visibleFiles.map((file) => (
                <button className={`file-row ${activeCitation?.file_path === file.path ? 'active' : ''}`} key={file.path} onClick={() => {
                  const known = latestAnswer?.citations.find((citation) => citation.file_path === file.path);
                  if (known) setActiveCitation(known);
                }} style={{ paddingLeft: `${11 + Math.min(2, file.path.split('/').length - 1) * 10}px` }} type="button" title={file.path}>
                  <span className={`file-icon ${file.language}`}>{fileLabel(file.language)}</span><span>{file.path}</span>
                </button>
              ))}
            </nav>
            <div className="repo-stats">
              <div><strong>{selected.file_count.toLocaleString()}</strong><span>Files</span></div>
              <div><strong>{selected.symbol_count.toLocaleString()}</strong><span>Symbols</span></div>
              <div><strong>{selected.chunk_count.toLocaleString()}</strong><span>Chunks</span></div>
            </div>
          </aside>

          <section className="conversation" aria-label="Codebase conversation">
            <div className="conversation-heading">
              <div><span className="eyebrow">Ask the codebase</span><h1>Trace ideas to implementation.</h1></div>
              <button className="new-chat" onClick={() => { setConversation([]); setActiveCitation(null); }} type="button">＋ New thread</button>
            </div>

            <div className="messages">
              {conversation.length === 0 && (
                <section className="prompt-start">
                  <span className="prompt-orbit">CA</span>
                  <h2>What do you want to understand?</h2>
                  <p>Ask about architecture, request flows, behavior, tests, or the impact of a change.</p>
                  <div className="suggestions">
                    {['Explain the architecture of this repository.', 'How does authentication work?', 'Where is error handling implemented?', 'Which tests cover the main request flow?'].map((prompt) => (
                      <button key={prompt} onClick={() => void ask(undefined, prompt)} type="button">{prompt}<span>↗</span></button>
                    ))}
                  </div>
                </section>
              )}
              {conversation.map((item) => (
                <div className="exchange" key={item.id}>
                  <article className="question"><span className="avatar user-avatar">YO</span><div><span className="message-label">You</span><p>{item.question}</p></div></article>
                  {item.result ? (
                    <article className="answer">
                      <div className="assistant-meta"><span className="avatar atlas-avatar">CA</span><div><span className="message-label">CodeAtlas</span><span className="grounded">Grounded in {item.result.citations.length} sources</span></div></div>
                      <AnswerBody text={item.result.answer} onCitation={(number) => chooseCitation(number, item.result)} />
                      <div className="answer-footer"><span>Retrieved {item.result.citations.length} sources · {(item.result.elapsed_ms / 1000).toFixed(2)}s · {item.result.answer_mode}</span><span className={`confidence-text ${item.result.confidence}`}>{item.result.confidence} confidence</span></div>
                    </article>
                  ) : item.error ? <div className="message-error" role="alert">{item.error}</div> : <div className="answer-loading"><span /><span /><span /> Reading the repository evidence…</div>}
                </div>
              ))}
            </div>

            <form className="composer" onSubmit={ask}>
              <textarea aria-label="Ask about this repository" disabled={!!busy} onChange={(event) => setQuestion(event.target.value)} onKeyDown={handleComposerKey} placeholder="Ask how something works, where it lives, or what a change could affect…" rows={2} value={question} />
              <div className="composer-row"><div className="scope"><span>⌘</span> {selected.name}</div><div className="composer-actions"><span>{busy ?? 'Enter to send'}</span><button disabled={!question.trim() || !!busy} type="submit" aria-label="Send question">↗</button></div></div>
            </form>
          </section>

          <aside className="evidence-panel" aria-label="Retrieved evidence">
            <div className="evidence-heading"><div><span className="eyebrow">Evidence</span><h2>{latestAnswer ? `${latestAnswer.citations.length} sources` : 'Waiting for a question'}</h2></div>{latestAnswer && <span className={`confidence ${latestAnswer.confidence}`}>{latestAnswer.confidence} confidence</span>}</div>
            {!latestAnswer && <div className="evidence-empty"><span>◎</span><p>Retrieved code will appear here with file paths, symbols, line ranges, and relevance scores.</p></div>}
            {latestAnswer?.citations.map((citation) => (
              <article className={`source-card ${activeCitation?.chunk_id === citation.chunk_id ? 'selected' : ''}`} key={citation.chunk_id} onClick={() => setActiveCitation(citation)}>
                <div className="source-top"><span className="source-number">{citation.number}</span><span className="score">{Math.round(citation.score * 100)}%</span></div>
                <strong>{citation.file_path}</strong>
                <span className="line-ref">Lines {citation.start_line}–{citation.end_line}{citation.symbol ? ` · ${citation.symbol}` : ''}</span>
                {activeCitation?.chunk_id === citation.chunk_id && <pre><code>{citation.excerpt}</code></pre>}
              </article>
            ))}
          </aside>
        </section>
      ) : (
        <section className="loading-screen"><span className="loader" /><h1>{busy}</h1><p>Large repositories can take a moment on their first index.</p></section>
      )}

      {showAdd && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setShowAdd(false); }}>
          <section aria-labelledby="add-title" aria-modal="true" className="modal" role="dialog">
            <button aria-label="Close" className="modal-close" disabled={!!busy} onClick={() => setShowAdd(false)} type="button">×</button>
            <span className="eyebrow">New knowledge source</span><h2 id="add-title">Add a repository</h2>
            <p>Use an absolute local directory or a public GitHub HTTPS URL. CodeAtlas reads text source files and skips secrets, binaries, generated folders, and lockfiles by default.</p>
            <form onSubmit={addRepository}>
              <label>Repository source<input autoFocus onChange={(event) => setSource(event.target.value)} placeholder="C:\\work\\my-api or https://github.com/org/repo" required value={source} /></label>
              <label>Display name <span>optional</span><input onChange={(event) => setProjectName(event.target.value)} placeholder="My API" value={projectName} /></label>
              {formError && <div className="form-error" role="alert">{formError}</div>}
              <div className="modal-actions"><button className="ghost-button" disabled={!!busy} onClick={() => setShowAdd(false)} type="button">Cancel</button><button className="primary-button" disabled={!source.trim() || !!busy} type="submit">{busy ?? 'Index repository'}</button></div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
