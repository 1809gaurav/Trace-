import type {
  CustodyEntry,
  FileType,
  RecoveredFile,
  Score,
} from './types';

export interface ApiRecoveredFile {
  id: string;
  name: string | null;
  type: string;
  stage: string;
  classification: RecoveredFile['classification'];
  confidence: number;
  reason: string;
  offsets: Array<{ start: number; end: number }>;
  size_bytes: number;
  sha256: string;
}

export interface ApiCustodyEntry {
  index: number;
  time: string;
  step: string;
  details: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface ApiScore {
  recovered: number;
  expected: number;
  precision: number;
  completeness: number;
  false_positives: number;
}

const fileTypes = new Set<FileType>(['jpeg', 'png', 'pdf', 'mp4', 'dvr']);

export function mapRecoveredFile(file: ApiRecoveredFile): RecoveredFile {
  const type = fileTypes.has(file.type as FileType) ? file.type as FileType : 'dvr';
  return {
    id: file.id,
    name: file.name ?? file.id,
    type,
    stage: file.stage,
    classification: file.classification,
    confidence: file.confidence,
    reason: file.reason,
    offsets: file.offsets,
    sizeBytes: file.size_bytes,
    sha256: file.sha256,
  };
}

export function mapCustodyEntry(entry: ApiCustodyEntry): CustodyEntry {
  return {
    index: entry.index,
    time: entry.time,
    step: entry.step,
    details: entry.details,
    prevHash: entry.prev_hash,
    hash: entry.hash,
  };
}

export function mapScore(score: ApiScore): Score {
  return {
    recovered: score.recovered,
    expected: score.expected,
    precision: score.precision,
    completeness: score.completeness,
    falsePositives: score.false_positives,
  };
}
