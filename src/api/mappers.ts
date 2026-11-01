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
  recall: number;
  completeness: number;
  false_positives: number;
  false_positive_rate: number;
  metadata_accuracy: number;
  classification_accuracy: number;
  overconfident_errors: number;
  image_integrity_ok: boolean;
  per_file: Array<{
    ground_truth_id: string;
    name: string;
    status: string;
    completeness: number;
    classification_expected: string;
    classification_got: string | null;
    confidence: number | null;
    matched_result_id: string | null;
  }>;
  calibration: Array<{
    lower: number;
    upper: number;
    count: number;
    correct_rate: number | null;
  }>;
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
    recall: score.recall,
    completeness: score.completeness,
    falsePositives: score.false_positives,
    falsePositiveRate: score.false_positive_rate,
    metadataAccuracy: score.metadata_accuracy,
    classificationAccuracy: score.classification_accuracy,
    overconfidentErrors: score.overconfident_errors,
    imageIntegrityOk: score.image_integrity_ok,
    perFile: score.per_file.map((item) => ({
      groundTruthId: item.ground_truth_id,
      name: item.name,
      status: item.status,
      completeness: item.completeness,
      classificationExpected: item.classification_expected,
      classificationGot: item.classification_got,
      confidence: item.confidence,
      matchedResultId: item.matched_result_id,
    })),
    calibration: score.calibration.map((bucket) => ({
      lower: bucket.lower,
      upper: bucket.upper,
      count: bucket.count,
      correctRate: bucket.correct_rate,
    })),
  };
}
