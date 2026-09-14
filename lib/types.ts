export const CAPABILITIES = ["text_to_image", "image_to_image", "text_to_video", "image_to_video", "keyframe_video", "reference_video"] as const;
export type Capability = (typeof CAPABILITIES)[number];
export type TaskStatus = "pending" | "running" | "succeeded" | "failed";
export type ProviderType = "agnes" | "modelscope";

export type FieldSchema = {
  key: string;
  label: string;
  type: "text" | "textarea" | "number" | "select";
  required?: boolean;
  default?: string | number;
  options?: string[];
  min?: number;
  max?: number;
};

export type ModelRecord = {
  id: string;
  providerId: string;
  externalModelId: string;
  name: string;
  version: string | null;
  description: string | null;
  capabilities: Capability[];
  parameterSchema: FieldSchema[];
  inputConstraints: Record<string, unknown>;
  enabled: boolean;
  sortOrder: number;
};

export type ProviderRecord = {
  id: string;
  providerType: ProviderType;
  name: string;
  baseUrl: string;
  enabled: boolean;
  maxConcurrency: number;
};

export type AssetRecord = {
  id: string;
  storageKey: string;
  originalFilename: string;
  mimeType: string;
  sizeBytes: number;
  metadata: Record<string, unknown>;
  createdAt: number;
};

export type TaskRecord = {
  id: string;
  providerId: string;
  modelId: string;
  capability: Capability;
  mode: string | null;
  parameters: Record<string, unknown>;
  status: TaskStatus;
  progress: number;
  externalTaskId: string | null;
  externalVideoId: string | null;
  error: string | null;
  createdAt: number;
  startedAt: number | null;
  completedAt: number | null;
  parentTaskId: string | null;
  resultAssetId: string | null;
  isFavorite: boolean;
  favoritedAt: number | null;
};

export type TaskSummary = {
  id: string;
  status: TaskStatus;
  capability: Capability;
  mode: string | null;
  prompt: string | null;
  modelName: string;
  createdAt: number;
  completedAt: number | null;
  progress: number;
  error: string | null;
  resultAssetId: string | null;
  resultMimeType: string | null;
  isFavorite: boolean;
  favoritedAt: number | null;
};

export type TaskAssetLink = {
  role: string;
  asset: AssetRecord;
};

export type TaskDetailRecord = TaskRecord & {
  modelName: string;
  assets: TaskAssetLink[];
};

export type TaskListOrderBy = "createdAt" | "favoritedAt";

export type TaskListQuery = {
  page?: number;
  pageSize?: number;
  favoriteOnly?: boolean;
  succeededOnly?: boolean;
  status?: TaskStatus;
  capability?: Capability;
  orderBy?: TaskListOrderBy;
};

export type TaskListResult = {
  items: TaskSummary[];
  page: number;
  pageSize: number;
  total: number;
};

export type ProviderTaskRef = { taskId: string; videoId?: string; resultUrls?: string[] };
export type ProviderStatus = { status: "running" | "succeeded" | "failed"; progress: number; resultUrls?: string[]; error?: string };
export type TaskInput = { prompt: string; parameters: Record<string, unknown>; assets: { role: string; asset: AssetRecord; publicUrl?: string }[] };
