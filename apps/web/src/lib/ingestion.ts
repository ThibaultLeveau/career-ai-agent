export const sourceTypes = ["jobs", "projects", "skills", "documents"] as const;
export type SourceType = (typeof sourceTypes)[number];
export type IngestionSummary = {
  status: string;
  job_id: number | null;
  stage: string | null;
  error: string | null;
  completed_chunks: number;
  total_chunks: number;
};
export type IngestionJob = {
  id: number;
  source_type: SourceType;
  record_id: number;
  source_deleted: boolean;
  label: string;
  trigger: string;
  status: string;
  stage: string;
  settings: {
    embeddings: { model: string; dimensions: number };
    ingestion: {
      max_retries: number;
      chunk_size: number;
      chunk_overlap: number;
    };
  };
  total_chunks: number;
  completed_chunks: number;
  retries: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  available_at: string;
};
export const activeStatus = (status: string) =>
  ["queued", "running", "retrying"].includes(status);
export const statusLabels: Record<string, string> = {
  queued: "Queued",
  running: "Processing",
  retrying: "Retrying",
  succeeded: "Ingested",
  failed: "Failed",
  not_ingested: "Not ingested",
  outdated: "Out of date",
  cancelled: "Cancelled",
  superseded: "Superseded",
};
