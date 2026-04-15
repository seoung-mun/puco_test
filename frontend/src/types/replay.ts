import type { GameState } from './gameState';

export interface ReplayPlayerInfo {
  display_name: string;
  is_bot: boolean;
}

export interface ReplayListItem {
  index: number;
  game_id: string;
  display_label: string;
  human_player_names: string[];
  played_date: string;
  created_at: string;
  num_players: number;
  winner: string | null;
  players: ReplayPlayerInfo[];
}

export interface ReplayListResponse {
  replays: ReplayListItem[];
  page: number;
  size: number;
  total_items: number;
  total_pages: number;
}

export interface ReplayFrame {
  frame_index: number;
  step: number | null;
  action: string | null;
  commentary: string | null;
  rich_state: GameState;
}

export interface ReplayDetailResponse {
  game_id: string;
  display_label: string;
  players: ReplayPlayerInfo[];
  replay_frames: ReplayFrame[];
  total_frames: number;
  final_scores: Array<Record<string, unknown>>;
}
