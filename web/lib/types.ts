export type Team = {
  id: string;
  key: string;
  name: string;
  lens: string;
  slack_enabled: boolean;
  slack_webhook_masked: string | null;
  immediate_threshold: number;
  digest_threshold: number;
  digest_hour_utc: number;
  last_digest_at: string | null;
  topics: Topic[];
};

export type Topic = {
  id: string;
  team_id: string | null;
  team_key: string | null;
  name: string;
  description: string | null;
};

export type SourceSummary = {
  id: string;
  kind: string;
  url: string;
  label: string | null;
  enabled: boolean;
  health: string;
  last_success_at: string | null;
  next_run_at: string | null;
  interval_minutes: number;
};

export type Competitor = {
  id: string;
  name: string;
  homepage_url: string;
  notes: string | null;
  muted: boolean;
  created_at: string;
  sources: SourceSummary[];
  item_count: number;
  last_item_at: string | null;
  health: "healthy" | "attention" | "checking";
};

export type Assessment = {
  team_key: string;
  team_name: string;
  relevance: number;
  category: string;
  category_label: string;
  why: string;
  evidence_quote: string | null;
  topics_matched: string[];
  route: string;
  created_at: string;
};

export type Feedback = {
  team_key: string;
  verdict: string;
  reason: string | null;
  created_at: string;
};

export type ItemCard = {
  id: string;
  kind: string;
  competitor_id: string;
  competitor_name: string;
  title: string;
  headline: string | null;
  summary: string | null;
  canonical_url: string;
  published_at: string | null;
  first_seen_at: string;
  status: string;
  primary_category: string | null;
  max_relevance: number | null;
  assessment: Assessment | null;
  feedback: Feedback | null;
};

export type ItemDetail = ItemCard & {
  content_excerpt: string;
  page_diff: {
    added: string[];
    removed: string[];
    changed_chars: number;
    before_excerpt?: string;
    after_excerpt?: string;
    page_label?: string;
  } | null;
  assessments: Assessment[];
  feedback: Feedback[];
  sources: string[];
  deliveries: { team_id: string; channel: string; status: string; sent_at: string | null; error: string | null }[];
};

export type InboxPage = {
  team: Team;
  items: ItemCard[];
  total: number;
  counts: Record<string, number>;
};

export type Overview = {
  teams: { team: Team; surfaced_7d: number; items: ItemCard[] }[];
  competitor_count: number;
  items_7d: number;
  attention: string[];
  monitoring: { running: boolean; last_check: string | null };
  recent_changes: ItemCard[];
};

export type SourceCandidate = {
  kind: string;
  url: string;
  label: string;
  confidence: number;
  sample_titles: string[];
  item_count: number;
  recommended: boolean;
  note: string | null;
};

export type Discovery = {
  homepage_url: string;
  site_name: string;
  candidates: SourceCandidate[];
  warnings: string[];
  elapsed_ms?: number;
};

export type OpsSource = SourceSummary & {
  competitor_id: string;
  competitor: string;
  requires_js: boolean;
  last_error: string | null;
  consecutive_failures: number;
  baseline_items_per_run: number | null;
  last_run_at: string | null;
  claimed_at: string | null;
  etag: string | null;
  config: Record<string, unknown>;
  yield_trend: { at: string; found: number; new: number; status: string }[];
};

export type OpsRun = {
  id: string;
  source_id: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  status: string;
  http_status: number | null;
  items_found: number;
  items_new: number;
  items_assessed: number;
  llm_cost_usd: number;
  error: string | null;
  trigger: string;
  competitor?: string;
  source_label?: string;
  source_url?: string;
  kind?: string;
  log?: { t: string; msg: string; [k: string]: unknown }[];
};

export type PromptVersion = {
  id: string;
  name: string;
  version: number;
  content: string;
  notes: string | null;
  active: boolean;
  created_at: string;
};

export type EvalDashboard = {
  live: {
    days: number;
    teams: Record<
      string,
      {
        name: string;
        feedback_count: number;
        surfaced_precision: number | null;
        missed_useful: number;
        recall_proxy: number | null;
        surfaced_total: number;
        assessed_total: number;
        surface_rate: number | null;
      }
    >;
  };
  history: {
    id: string;
    run_at: string;
    prompt_version: number | null;
    model: string | null;
    n_items: number;
    metrics: Record<string, { precision: number | null; recall: number | null; f1: number | null; tp: number; fp: number; fn: number; tn: number; n: number }>;
    cost_usd: number;
    trigger: string;
  }[];
  golden_count: number;
  golden_by_origin: Record<string, number>;
  disagreements: {
    feedback_id: string;
    item_id: string;
    team_key: string;
    team_name: string;
    headline: string;
    competitor: string;
    verdict: string;
    reason: string | null;
    relevance: number;
    route: string;
    kind: string;
    promoted: boolean;
    created_at: string;
  }[];
};
