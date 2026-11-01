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
  completeness: number;
  falsePositives: number;
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
  fileIds?: string[];
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
