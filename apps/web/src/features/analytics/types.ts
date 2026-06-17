export interface AnalyticsSummary {
  period_days: number;
  total_sent: number;
  total_delivered: number;
  total_replied: number;
  reply_rate: number;
  delivery_rate: number;
  total_spend_inr: number;
  meetings_scheduled: number;
  meetings_completed: number;
  leads_created: number;
  leads_booked: number;
  proposals_generated: number;
  proposals_approved: number;
  proposals_sent: number;
  proposal_approval_rate: number;
  booking_rate: number;
}

export interface DailyRollup {
  rollup_date: string;
  outreach_sent: number;
  outreach_replied: number;
  leads_created: number;
  leads_booked: number;
  proposals_sent: number;
  ai_spend_inr: number;
}

export interface AnalyticsFunnel {
  contacts: number;
  outreach_sent: number;
  replies: number;
  meetings: number;
  proposals: number;
  bookings: number;
}
