// Dashboard types — Sprint 28 Business Health Center
// Mirrors corpmind.modules.dashboard.schemas

export interface ComponentScore {
  name: string;
  score: number;   // 0–100
  weight: number;  // 0–1
}

export interface OperationalAlert {
  priority: "critical" | "warning" | "info";
  category: string;
  title: string;
  description: string;
  recommended_action: string;
  created_at: string;
}

export interface BusinessHealthOut {
  generated_at: string;
  overall_score: number;
  pipeline_score: number;
  revenue_score: number;
  campaign_score: number;
  recommendation_score: number;
  communication_score: number;
  components: ComponentScore[];
  top_alerts: OperationalAlert[];
  top_strengths: string[];
  areas_needing_attention: string[];
  health_trend: "improving" | "stable" | "declining";
}

export interface OperationalAlertsOut {
  alerts: OperationalAlert[];
  total: number;
}

export interface BusinessSummaryOut {
  generated_at: string;
  lines: string[];
  overall_assessment: "excellent" | "good" | "fair" | "poor";
}
