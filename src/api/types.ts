export type Classification = 'intact' | 'carved' | 'reconstructed' | 'partial';
export type FileType = 'jpeg' | 'png' | 'pdf' | 'mp4' | 'dvr';

export interface RecoveredFile {
  id: string;
  name: string;
  type: FileType;
  stage: string;
  classification: Classification;
  confidence: number;
  reason: string;
  offsets: Array<{ start: number; end: number }>;
  sizeBytes: number;
  sha256: string;
  previewUrl?: string;
}

export interface CustodyEntry {
  index: number;
  time: string;
  step: string;
  details: Record<string, unknown>;
  prevHash: string;
  hash: string;
}

export interface Score {
  recovered: number;
  expected: number;
  precision: number;
  recall: number;
  completeness: number;
  falsePositives: number;
  falsePositiveRate: number;
  metadataAccuracy: number;
  classificationAccuracy: number;
  overconfidentErrors: number;
  imageIntegrityOk: boolean;
  perFile: Array<{
    groundTruthId: string;
    name: string;
    status: string;
    completeness: number;
    classificationExpected: string;
    classificationGot: string | null;
    confidence: number | null;
    matchedResultId: string | null;
  }>;
  calibration: Array<{
    lower: number;
    upper: number;
    count: number;
    correctRate: number | null;
  }>;
  benchmarkUnavailable?: boolean;
}

export interface UploadResult {
  fileName: string;
  sizeBytes: number;
  fingerprint: string;
}

export interface RecoveryMessage {
  status: 'reading' | 'scanning' | 'isolating' | 'reconstructing' | 'verifying' | 'done';
  found: number;
  message: string;
  percent?: number;
  fileIds?: string[];
  file?: {
    id: string;
    name: string | null;
    type: string;
    classification: Classification;
    confidence: number;
  };
}

export interface ReportData {
  caseId: string;
  caseName: string;
  summary: string;
  notes: string[];
  fileNames: string[];
  limitations: string[];
  collection: string;
}
