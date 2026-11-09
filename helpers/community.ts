export type DailyFormat = "question" | "quote" | "trivia" | "recommendation" | "archive_spotlight" | "mystery";
export type CommunityActivity = "watch" | "read" | "play" | "discuss";

export interface DailySchedule {
  guild_id: string;
  channel_id: string;
  time_zone: string;
  local_time: string;
  format: DailyFormat;
  enabled: boolean;
  next_run_at: Date;
}

export interface CommunitySession {
  id: string;
  guild_id: string;
  channel_id: string;
  creator_id: string;
  host_id: string;
  title: string;
  description: string;
  activity_type: CommunityActivity;
  media_title: string | null;
  media_url: string | null;
  scheduled_at: Date;
  capacity: number | null;
  status: string;
  thread_id: string | null;
  scheduled_event_id: string | null;
}

export {
  nextLocalOccurrence,
  saveDailySchedule,
  disableDailySchedule,
  submitDailyItem,
  reviewDailyItem,
  dueDailySchedules,
  prepareDailyDelivery,
  dueDailyDeliveries,
  markDailyDelivery,
} from "./community-daily.js";
export {
  createRanking,
  addRankingCandidate,
  reviewRankingCandidate,
  voteForRanking,
  closeRanking,
  rankingResults,
  filterMediaNightCandidates,
  sampleMediaNightCandidates,
  createMediaNight,
  claimDueMediaNightResults,
  markMediaNightResultPublished,
} from "./community-rankings.js";
export {
  createCommunitySession,
  setSessionRsvp,
  getCommunitySession,
  createSpoilerDiscussion,
  closeDiscussion,
  listUpcomingSessions,
  getCommunityHistory,
  upcomingProviderReleases,
  formatActivity,
} from "./community-sessions.js";
