import { seedCustodyBase, seedFiles, seedReport, seedScore } from '../mock/data';
import type {
  CustodyEntry,
  RecoveryMessage,
  RecoveredFile,
  ReportData,
  Score,
  UploadResult,
} from './types';
import { mapCustodyEntry, mapRecoveredFile, mapScore } from './mappers';
import type { ApiCustodyEntry, ApiRecoveredFile, ApiScore } from './mappers';

export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';

const encoder = new TextEncoder();
const ACTIVE_CASE_KEY = 'trace-active-case';
const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');
const API_PREFIX = API_BASE.endsWith('/api') ? API_BASE : `${API_BASE}/api`;
const API_KEY = import.meta.env.VITE_API_KEY;
const API_TOKEN = import.meta.env.VITE_API_TOKEN;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export interface RecoverySocket extends EventTarget {
  start(): void;
  close(): void;
}

class APIRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'APIRequestError';
    this.status = status;
  }
}

async function requestJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (API_KEY) headers.set('X-API-Key', API_KEY);
  if (API_TOKEN) headers.set('Authorization', `Bearer ${API_TOKEN}`);
  const response = await fetch(`${API_PREFIX}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `The request could not be completed (${response.status}).`;
    try {
      const body = await response.json() as { error?: { message?: string } };
      message = body.error?.message ?? message;
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
    }
    throw new APIRequestError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function resolveCaseId(): Promise<string | null> {
  const current = window.localStorage.getItem(ACTIVE_CASE_KEY);
  if (current) return current;
  const response = await requestJSON<{ cases: Array<{ id: string }> }>('/cases?limit=1');
  const id = response.cases[0]?.id ?? null;
  if (id) window.localStorage.setItem(ACTIVE_CASE_KEY, id);
  return id;
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(value));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

export async function uploadEvidence(file: File): Promise<UploadResult> {
  if (!USE_MOCK) {
    let caseId = await resolveCaseId();
    if (!caseId) {
      const created = await requestJSON<{ id: string }>('/cases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: file.name }),
      });
      caseId = created.id;
      window.localStorage.setItem(ACTIVE_CASE_KEY, caseId);
    }
    const body = new FormData();
    body.append('file', file, file.name);
    const uploaded = await requestJSON<{ image: { sha256: string; size_bytes: number; original_filename: string } }>(
      `/cases/${encodeURIComponent(caseId)}/upload`,
      { method: 'POST', body },
    );
    return {
      fileName: uploaded.image.original_filename,
      sizeBytes: uploaded.image.size_bytes,
      fingerprint: uploaded.image.sha256.slice(0, 24),
    };
  }
  await sleep(300);
  const fingerprint = await sha256(`${file.name}:${file.size}:${new Date().toISOString()}`);
  return {
    fileName: file.name,
    sizeBytes: file.size,
    fingerprint: fingerprint.slice(0, 24),
  };
}

const progressSteps: Array<Omit<RecoveryMessage, 'fileIds'>> = [
  { status: 'reading', found: 2, message: 'Looking at the drive and checking the write history.' },
  { status: 'scanning', found: 5, message: 'Finding deleted files in the unallocated space.' },
  { status: 'isolating', found: 8, message: 'Digging through raw data and isolating likely evidence.' },
  { status: 'reconstructing', found: 11, message: 'Piece fragments together where sectors were damaged.' },
  { status: 'verifying', found: 13, message: 'Checking and labelling the recovered files.' },
  { status: 'done', found: 13, message: 'Recovery complete. The evidence set is ready for review.' },
];

export class MockRecoverySocket extends EventTarget implements RecoverySocket {
  private timer?: number;
  private index = 0;

  start() {
    const emit = () => {
      const step = progressSteps[this.index] ?? progressSteps[progressSteps.length - 1];
      this.dispatchEvent(
        new CustomEvent('message', {
          detail: {
            ...step,
            fileIds: seedFiles.slice(0, step.found).map((file) => file.id),
          },
        }),
      );

      this.index += 1;
      if (this.index >= progressSteps.length) {
        window.clearInterval(this.timer);
        return;
      }
    };

    emit();
    this.timer = window.setInterval(emit, 2200);
  }

  close() {
    if (this.timer) {
      window.clearInterval(this.timer);
    }
  }
}

export function createRecoveryStream(): RecoverySocket {
  if (!USE_MOCK) return createAPIRecoverySocket();
  const socket = new MockRecoverySocket();
  socket.start();
  return socket;
}

export async function fetchResults(): Promise<RecoveredFile[]> {
  if (!USE_MOCK) {
    const caseId = await resolveCaseId();
    if (!caseId) return [];
    try {
      const response = await requestJSON<{ files: ApiRecoveredFile[] }>(
        `/cases/${encodeURIComponent(caseId)}/results?sort=confidence_desc`,
      );
      return response.files.map(mapRecoveredFile);
    } catch (error) {
      if (error instanceof APIRequestError && error.status === 404) return [];
      throw error;
    }
  }
  await sleep(250);
  return seedFiles;
}

export async function fetchScore(): Promise<Score> {
  if (!USE_MOCK) {
    const caseId = await resolveCaseId();
    if (!caseId) return { recovered: 0, expected: 0, precision: 0, completeness: 0, falsePositives: 0 };
    try {
      const score = await requestJSON<ApiScore>(`/cases/${encodeURIComponent(caseId)}/score`);
      return mapScore(score);
    } catch (error) {
      if (error instanceof APIRequestError && error.status === 404) {
        return { recovered: 0, expected: 0, precision: 0, completeness: 0, falsePositives: 0 };
      }
      throw error;
    }
  }
  await sleep(220);
  return seedScore;
}

export async function fetchReport(): Promise<ReportData> {
  if (!USE_MOCK) {
    const caseId = await resolveCaseId();
    if (!caseId) {
      return {
        caseId: 'No case',
        caseName: 'No recovery report is available yet',
        summary: 'Upload an evidence image and complete a recovery run to prepare a report.',
        notes: [],
        fileNames: [],
        limitations: ['Recovery results may be incomplete and are not a legal certification.'],
        collection: 'No evidence image attached',
      };
    }
    let caseInfo: { id: string; title: string; image: { original_filename: string } | null };
    let results: { files: ApiRecoveredFile[] };
    try {
      [caseInfo, results] = await Promise.all([
        requestJSON<{ id: string; title: string; image: { original_filename: string } | null }>(`/cases/${encodeURIComponent(caseId)}`),
        requestJSON<{ files: ApiRecoveredFile[] }>(`/cases/${encodeURIComponent(caseId)}/results`),
      ]);
    } catch (error) {
      if (error instanceof APIRequestError && error.status === 404) {
        return {
          caseId,
          caseName: 'No completed recovery report is available yet',
          summary: 'Complete a recovery run before preparing the report.',
          notes: [],
          fileNames: [],
          limitations: ['Recovery results may be incomplete and are not a legal certification.'],
          collection: 'No completed run',
        };
      }
      throw error;
    }
    return {
      caseId: caseInfo.id,
      caseName: caseInfo.title,
      summary: `${results.files.length} file(s) were recovered for review. Confidence describes the available recovery evidence; it does not guarantee completeness.`,
      notes: ['Review each recovered file and its technical details before relying on it.'],
      fileNames: results.files.slice(0, 8).map((file) => file.name ?? file.id),
      limitations: ['Some deleted sectors may be overwritten.', 'Reconstructed files can contain missing or altered content.'],
      collection: caseInfo.image?.original_filename ?? 'No evidence image attached',
    };
  }
  await sleep(180);
  return seedReport;
}

export async function verifyChain(entries: CustodyEntry[]): Promise<{ valid: boolean; brokenIndex: number | null }> {
  if (!USE_MOCK) {
    const caseId = await resolveCaseId();
    if (caseId) {
      const result = await requestJSON<{ ok: boolean; first_failing_index: number | null }>(
        `/cases/${encodeURIComponent(caseId)}/verify`,
      );
      return { valid: result.ok, brokenIndex: result.first_failing_index };
    }
  }
  let prevHash = 'root';
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const payload = `${prevHash}|${entry.time}|${entry.step}|${JSON.stringify(entry.details)}`;
    const computed = await sha256(payload);
    const valid = computed === entry.hash;
    if (!valid) {
      return { valid: false, brokenIndex: index + 1 };
    }
    prevHash = entry.hash;
  }
  return { valid: true, brokenIndex: null };
}

export async function buildCustodyChain(): Promise<CustodyEntry[]> {
  return fetchCustodyEntries();
}

export async function fetchCustodyEntries(): Promise<CustodyEntry[]> {
  if (!USE_MOCK) {
    const caseId = await resolveCaseId();
    if (!caseId) return [];
    const response = await requestJSON<{ entries: ApiCustodyEntry[] }>(`/cases/${encodeURIComponent(caseId)}/custody`);
    return response.entries.map(mapCustodyEntry);
  }
  await sleep(200);
  let previousHash = 'root';
  const chain: CustodyEntry[] = [];
  for (const entry of seedCustodyBase) {
    const payload = `${previousHash}|${entry.time}|${entry.step}|${JSON.stringify(entry.details)}`;
    const nextHash = await sha256(payload);
    chain.push({
      ...entry,
      prevHash: previousHash,
      hash: nextHash,
    });
    previousHash = nextHash;
  }
  return chain;
}

export async function tamperDemo(indexToBreak: number): Promise<{ valid: boolean; brokenIndex: number; message: string }> {
  if (!USE_MOCK) {
    const caseId = await resolveCaseId();
    if (!caseId) throw new Error('Upload an evidence image before running a tamper demonstration.');
    const response = await requestJSON<{
      verify: { ok: boolean; first_failing_index: number | null };
    }>(`/cases/${encodeURIComponent(caseId)}/tamper-demo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: indexToBreak }),
    });
    const brokenIndex = response.verify.first_failing_index ?? indexToBreak;
    return {
      valid: response.verify.ok,
      brokenIndex,
      message: response.verify.ok
        ? 'The chain still holds.'
        : `Entry ${brokenIndex} was changed. Everything after it can no longer be trusted.`,
    };
  }
  const chain = await fetchCustodyEntries();
  const target = Math.max(1, Math.min(indexToBreak, chain.length));
  const entry = chain[target - 1];
  const tampered = {
    ...entry,
    details: { ...entry.details, altered: true },
    hash: `${entry.hash.slice(0, 12)}deadbeef${entry.hash.slice(12)}`,
  };
  const entries = [...chain];
  entries[target - 1] = tampered;
  const result = await verifyChain(entries);
  return {
    valid: result.valid,
    brokenIndex: result.brokenIndex ?? target,
    message: result.valid
      ? 'The chain still holds.'
      : `Entry ${target} was changed. Everything after it can no longer be trusted.`,
  };
}

export async function fetchMockReport(): Promise<ReportData> {
  await sleep(150);
  return seedReport;
}

export async function getPrintableReport(): Promise<ReportData> {
  if (!USE_MOCK) return fetchReport();
  return seedReport;
}

export async function mockPdfDownload(): Promise<{ ok: true; placeholder: string }> {
  if (!USE_MOCK) {
    const caseId = await resolveCaseId();
    if (!caseId) throw new Error('Complete a recovery run before downloading a report.');
    await requestJSON(`/cases/${encodeURIComponent(caseId)}/report`, { method: 'POST' });
    const headers = new Headers();
    if (API_KEY) headers.set('X-API-Key', API_KEY);
    if (API_TOKEN) headers.set('Authorization', `Bearer ${API_TOKEN}`);
    const response = await fetch(`${API_PREFIX}/cases/${encodeURIComponent(caseId)}/report`, { headers });
    if (!response.ok) throw new APIRequestError('The report could not be downloaded.', response.status);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${caseId}-trace-report.pdf`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    return { ok: true, placeholder: 'The Trace PDF report was downloaded.' };
  }
  await sleep(400);
  return {
    ok: true,
    placeholder: 'PDF placeholder generated for the court summary.',
  };
}

function createAPIRecoverySocket(): RecoverySocket {
  class APIRecoverySocket extends EventTarget implements RecoverySocket {
    private connection?: WebSocket;
    private closed = false;
    private lastSequence = 0;
    private retryCount = 0;
    private retryTimer = 0;
    private caseId?: string;
    private runId?: string;
    private finished = false;

    start() {
      void this.startRun();
    }

    close() {
      this.closed = true;
      window.clearTimeout(this.retryTimer);
      this.connection?.close();
    }

    private async startRun() {
      try {
        this.caseId = await resolveCaseId() ?? undefined;
        if (!this.caseId) throw new Error('Upload an evidence image before starting recovery.');
        const started = await requestJSON<{ run: { id: string } }>(
          `/cases/${encodeURIComponent(this.caseId)}/runs`,
          { method: 'POST' },
        );
        this.runId = started.run.id;
        this.connect();
      } catch (error) {
        this.dispatchEvent(new CustomEvent('error', { detail: error }));
      }
    }

    private connect() {
      if (this.closed || !this.caseId || !this.runId) return;
      const base = API_BASE ? new URL(API_PREFIX, window.location.href) : new URL('/api', window.location.href);
      base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
      base.pathname = `${base.pathname.replace(/\/$/, '')}/ws/cases/${encodeURIComponent(this.caseId)}`;
      base.searchParams.set('after_seq', String(this.lastSequence));
      if (API_KEY) base.searchParams.set('api_key', API_KEY);
      if (API_TOKEN) base.searchParams.set('token', API_TOKEN);
      this.connection = new WebSocket(base);
      this.connection.onmessage = (event) => {
        const payload = JSON.parse(String(event.data)) as {
          seq?: number;
          type?: string;
          stage?: string;
          message?: string;
          found_so_far?: number;
          payload?: { public_id?: string };
        };
        if (typeof payload.seq === 'number') this.lastSequence = Math.max(this.lastSequence, payload.seq);
        if (payload.type === 'done' || payload.type === 'error') this.finished = true;
        const status = payload.type === 'done'
          ? 'done'
          : statusByStage[payload.stage ?? ''] ?? (payload.type === 'error' ? 'done' : 'reading');
        this.dispatchEvent(new CustomEvent('message', {
          detail: {
            status,
            found: payload.found_so_far ?? 0,
            message: payload.message ?? `Recovery run ${this.runId} is in progress.`,
            fileIds: payload.payload?.public_id ? [payload.payload.public_id] : [],
          } satisfies RecoveryMessage,
        }));
      };
      this.connection.onopen = () => { this.retryCount = 0; };
      this.connection.onclose = () => {
        if (this.closed || this.finished) return;
        this.retryCount += 1;
        if (this.retryCount <= 6) {
          this.retryTimer = window.setTimeout(
            () => this.connect(),
            Math.min(500 * 2 ** (this.retryCount - 1), 8000),
          );
        }
      };
      this.connection.onerror = () => this.connection?.close();
    }
  }

  const statusByStage: Record<string, RecoveryMessage['status']> = {
    reading: 'reading',
    scanning: 'scanning',
    isolating: 'isolating',
    reconstructing: 'reconstructing',
    verifying: 'verifying',
  };
  const socket = new APIRecoverySocket();
  socket.start();
  return socket;
}
