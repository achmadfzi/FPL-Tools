export type Confidence = "Tinggi" | "Sedang" | "Rendah";

export interface Player {
  id: number;
  name: string;
  team: string;
  team_name?: string;
  pos: string;
  price: number;
  proj: number | null;
  ep_next?: number | null;
  form?: number | null;
  ppg?: number | null;
  selected_by?: number | null;
  status?: string;
  news?: string;
  chance?: number | null;
  availability?: {
    label: string;
    pct: number;
    is_out: boolean;
    action: string;
  };
  fdr?: number | null;
  opponent?: string | null;
  is_home?: boolean | null;
  n_fixtures?: number;
  minutes?: number | null;
  starts?: number | null;
  exp_minutes?: number | null;
  xgi90?: number | null;
  dc_prob?: number | null;
  cs_prob?: number | null;
  last_points?: number | null;
  last_ppg?: number | null;
  last_value?: number | null;
  last_starts?: number | null;
  ml_proj?: number | null;
  xG90?: number | null;
  xA90?: number | null;
  bonus_pg?: number | null;
  creativity_pg?: number | null;
  ict_pg?: number | null;
  rec_form?: number | null;
  rec_xgi90?: number | null;
  rec_xg90?: number | null;
  rec_xa90?: number | null;
  rec_dc90?: number | null;
  saves_pg?: number | null;
  pen_order?: number | null;
  chance_this?: number | null;
  chance_next?: number | null;
}

export interface NextFixture {
  event: number;
  opponent: string;
  fdr: number | null;
  is_home: boolean;
  kickoff?: string | null;
}

export interface XiPlayer {
  id: number;
  name: string;
  team: string;
  pos: string;
  price: number;
  proj: number;
  ev: number;
  p_play: number;
  bench_slot?: number | string | null;
  status?: string;
  news?: string;
  opponent?: string | null;
  fdr?: number | null;
  is_home?: boolean | null;
  chance?: number | null;
  next_fixtures?: NextFixture[];
}

export interface Transfer {
  headline: string;
  first_gw: number | null;
  transfers: Array<{
    out_id?: number;
    out_name?: string;
    out_short?: string;
    out_price?: number;
    in_id?: number;
    in_name?: string;
    in_short?: string;
    in_price?: number;
    in_chance?: number;
    in_status?: string;
    gain_horizon?: number;
  }>;
  hits: number;
  gain: number | null;
  confidence: Confidence;
  meaning: string;
}

export interface Alert {
  id: number;
  name: string;
  team: string;
  status: string;
  label: string;
  pct: number;
  news: string;
  action: string;
  is_out: boolean;
}

export interface CaptainCandidate {
  id: number;
  web_name: string;
  team_short: string;
  proj: number;
  model_points?: number;
  selected_by: number;
  ev_captain: number;
  ev_no_vc: number;
  ev_se: number;
  p_plays: number;
  p_blank: number;
  p_haul: number;
  p10: number;
  p50: number;
  p90: number;
  best_vc_id: number | null;
  best_vc_name: string | null;
  ev_best_vc_effect: number;
  sim_minus_proj: number;
}

export interface ChipCalendarRow {
  gw: number;
  dgw: number[];
  bgw: number[];
  tc: number;
  bb: number;
  fh: number;
  wc: number;
  xi: number;
  total15: number;
}

export interface Dashboard {
  gw: { id: number; name: string; deadline: string; average_score?: number | null };
  updated_at: number;
  source: string;
  captain: {
    id: number | null;
    name: string;
    team: string;
    pos: string;
    price: number | null;
    proj: number | null;
    ev: number | null;
    sim_ev?: number | null;
    ev_no_vc?: number | null;
    p_play: number | null;
    p_blank: number | null;
    p_haul: number | null;
    p10: number | null;
    p50: number | null;
    p90: number | null;
    selected_by: number | null;
    confidence: Confidence;
    vice: string | null;
  };
  transfer: Transfer;
  chip: {
    headline: string;
    metric: string;
    meaning: string;
    confidence: Confidence;
    tone: "good" | "warn" | "bad";
    available: string[];
  };
  alerts: Alert[];
  xi: XiPlayer[];
  bench: XiPlayer[];
  line: { ev: number; ev_naive: number; formation: number[]; n: number };
  plan: {
    horizon: number;
    total_planned: number;
    hold_total: number;
    gain: number;
    final_bank: number;
    final_ft: number;
    plan: Array<{
      gw: number;
      hits: number;
      transfers: Array<{
        out_id: number;
        out_name: string;
        out_short: string;
        out_price: number;
        in_id: number;
        in_name: string;
        in_short: string;
        in_price: number;
        in_chance: number;
        in_status: string;
        gain_horizon?: number;
      }>;
    }>;
  };
  chips: Record<string, any>;
  chip_calendar: {
    calendar?: Array<{ chip: string; gw: number; score: number; dgw: number[]; bgw: number[] }>;
    best?: Record<string, { gw: number; score: number; dgw: number[]; bgw: number[] }>;
    by_gw?: ChipCalendarRow[];
    chips?: { available_now?: string[]; expires_gw?: number };
  };
  squad: {
    ids: number[];
    players: Player[];
    source: string;
    bank: number;
    team_value?: number;
    free_transfers: number;
    chips: string[];
  };
  top_players: Player[];
  easy_players: Player[];
  fdr_grid: Array<{
    team: string;
    team_name: string;
    opponent: string;
    fdr: number | null;
    is_home: boolean | null;
  }>;
  last_stars: Player[];
  last_value: Player[];
  rotation_risks: Array<{
    name: string;
    team: string;
    pos: string;
    reasons: string[];
    severity: string;
    proj: number | null;
  }>;
  market: {
    value_picks?: Array<Player & { value: number }>;
    differentials?: Array<Player & { diff_score: number }>;
    risk_players?: Player[];
    overpriced?: Player[];
    ticker?: any[];
    ticker_gw?: number;
  };
  injury_suggestions: Array<{
    action: string;
    player: Player;
    availability: any;
    replacement: Player | null;
    gain: number;
    player_total: number;
    replacement_total: number | null;
  }>;
  accuracy_summary: {
    gw: number;
    mae: number;
    rmse: number;
    bias?: number;
    n: number;
    n_gws: number;
    top10?: { n: number; mae: number; bias: number };
    captain?: any;
  } | null;
  data_health: {
    history_fresh: number;
    history_total: number;
    snapshot_available: boolean;
    snapshot_age_minutes?: number | null;
  };
}

export interface PerformanceHistory {
  gw: number;
  saved_at?: number;
  has_projections: boolean;
  has_actuals: boolean;
  metrics: {
    version?: number;
    n: number;
    mae: number;
    rmse: number;
    bias?: number;
    spearman?: number | null;
    top_k?: Record<string, { n: number; mae: number; bias: number; mean_proj: number; mean_actual: number }>;
    deciles?: Array<{ decile: number; n: number; proj: number; actual: number; bias: number }>;
    captain?: { name: string; proj: number; actual: number; oracle_name: string; oracle_actual: number; regret: number };
    by_pos?: Record<string, number>;
    by_fdr?: Record<string, number>;
    top_overestimate?: Array<{ name: string; pos: string; proj: number; actual: number; error: number }>;
    top_underestimate?: Array<{ name: string; pos: string; proj: number; actual: number; error: number }>;
  } | null;
  snapshot_count?: number;
}

export interface DecisionCaptainGw {
  gw: number;
  source: "proxy" | "rekomendasi";
  captain_id: number;
  captain: string;
  team: string;
  pos: string;
  proj: number;
  actual: number;
  result: "haul" | "return" | "blank";
  percentile: number;
  field_avg: number;
  regret: number;
  oracle: string;
  oracle_actual: number;
  top10_n: number;
  top10_returns: number;
  top10_hauls: number;
  top10_avg: number;
}

export interface DecisionTransferGw {
  gw: number;
  headline: string;
  hits: number;
  status: "pending" | "done";
  transfers: Array<{ out_id: number; out_name: string; in_id: number; in_name: string }>;
  out_points?: number;
  in_points?: number;
  hit_cost?: number;
  net?: number;
  result?: "win" | "loss" | "tie";
}

export interface DecisionAccuracy {
  captain: {
    n_gws: number;
    return_rate: number;
    haul_rate: number;
    blank_rate: number;
    avg_points: number;
    avg_field_points: number;
    lift: number | null;
    avg_regret: number;
    tracked_gws: number;
    top10: {
      n_players: number;
      return_rate: number;
      haul_rate: number;
      avg_points: number;
      lift: number | null;
    };
    by_gw: DecisionCaptainGw[];
  };
  transfer: {
    n: number;
    wins: number;
    losses: number;
    ties: number;
    win_rate: number;
    avg_net: number;
    pending: number;
    by_gw: DecisionTransferGw[];
  };
  notes: string[];
}

export interface PerformanceResponse {
  history: PerformanceHistory[];
  baselines: Array<{
    model: string;
    n: number;
    mae: number;
    rmse: number;
    bias: number;
    spearman: number | null;
    top10: { n: number; mae: number; bias: number } | null;
  }>;
  decisions: DecisionAccuracy;
}

export interface HistoryResponse {
  available: boolean;
  message?: string;
  team_id?: number;
  team_name?: string;
  manager_name?: string;
  overall_points?: number;
  overall_rank?: number;
  gw_results?: Array<{
    gw: number;
    points: number;
    total_points: number;
    overall_rank: number;
    rank: number;
    bank: number;
    team_value: number;
    transfers_made: number;
    transfers_cost: number;
    points_on_bench: number;
    average: number;
  }>;
  chips_played?: Array<{ name: string; event: number; time?: string }>;
  chip_impact?: Array<{ chip: string; gw: number; points: number; avg: number; gain: number; bench_pts?: number }>;
  best_gw?: { gw: number; points: number };
  worst_gw?: { gw: number; points: number };
  total_hits?: number;
  total_bench_pts?: number;
}

export interface SquadInsights {
  available: boolean;
  message?: string;
  source?: string;
  bank?: number;
  multi?: any[];
  single?: any[];
  plans?: any[];
  risky?: Array<{ player: Player; future: number }>;
}

export interface LabResponse {
  chip_calendar: Dashboard["chip_calendar"] | null;
  chips: Record<string, any> | null;
  calibration: {
    available: boolean;
    enabled: boolean;
    method?: string;
    n?: number;
    raw_mae_cv?: number | null;
    calibrated_mae_cv?: number | null;
    improvement_pct?: number | null;
  };
  ml: {
    available: boolean;
    enabled: boolean;
    n_samples?: number;
    n_gws?: number;
    gbr_mae?: number;
    formula_mae?: number;
    improvement_pct?: number;
  };
  adaptive: any;
  data_health: { history_fresh: number; history_total: number };
}
