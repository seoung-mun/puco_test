export type GoodType = 'corn' | 'indigo' | 'sugar' | 'tobacco' | 'coffee';
export type RoleName = 'settler' | 'mayor' | 'builder' | 'craftsman' | 'trader' | 'captain' | 'prospector' | 'prospector_2';
export type PhaseType =
  | 'role_selection' | 'settler_action' | 'mayor_distribution' | 'mayor_action'
  | 'builder_action' | 'craftsman_action' | 'trader_action'
  | 'captain_action' | 'captain_discard' | 'end_of_round' | 'game_over';

export interface Meta {
  game_id?: string;
  round: number;
  num_players: number;
  player_order: string[];
  governor: string;
  phase: PhaseType;
  active_role: RoleName | null;
  active_player: string;
  players_acted_this_phase: string[];
  end_game_triggered: boolean;
  end_game_reason: string | null;
  vp_supply_remaining: number;
  captain_consecutive_passes: number;
  bot_thinking?: boolean;
  mayor_slot_idx?: number | null;
  mayor_can_skip?: boolean;
  // Channel API action indices
  pass_action_index?: number;
  hacienda_action_index?: number;
}

export interface Role {
  doubloons_on_role: number;
  taken_by: string | null;
  action_index?: number; // channel API: present when role is available (taken_by === null)
}

export interface Colonists {
  ship: number;
  supply: number;
}

export interface TradingHouse {
  goods: GoodType[];
  d_spaces_used: number;
  d_spaces_remaining: number;
  d_is_full: boolean;
}

export interface CargoShip {
  capacity: number;
  good: GoodType | null;
  d_filled: number;
  d_remaining_space: number;
  d_is_full: boolean;
  d_is_empty: boolean;
}

export interface PlantationDrawPile {
  corn: number;
  indigo: number;
  sugar: number;
  tobacco: number;
  coffee: number;
}

export interface FaceUpPlantation {
  type: string;
  action_index: number; // channel API: 8-13 for plantation slots, 14 for quarry
}

export interface AvailablePlantations {
  face_up: FaceUpPlantation[]; // channel API returns objects; legacy returned strings
  draw_pile: PlantationDrawPile;
}

export interface AvailableBuilding {
  cost: number;
  max_colonists: number;
  vp: number;
  copies_remaining: number;
  action_index?: number; // channel API: 16-38
}

export interface GoodsSupply {
  corn: number;
  indigo: number;
  sugar: number;
  tobacco: number;
  coffee: number;
}

export interface CommonBoard {
  roles: Record<RoleName, Role>;
  colonists: Colonists;
  trading_house: TradingHouse;
  cargo_ships: CargoShip[];
  available_plantations: AvailablePlantations;
  available_buildings: Record<string, AvailableBuilding>;
  quarry_supply_remaining: number;
  goods_supply: GoodsSupply;
}

export interface Plantation {
  type: string;
  colonized: boolean;
  slot_id?: string;
  capacity?: number;
}

export interface PlayerBuilding {
  name: string;
  max_colonists: number;
  current_colonists: number;
  empty_slots: number;
  is_active: boolean;
  vp: number;
  slot_id?: string;
  capacity?: number;
}

export interface GoodsStock {
  corn: number;
  indigo: number;
  sugar: number;
  tobacco: number;
  coffee: number;
  d_total: number;
}

export interface ProductionEntry {
  can_produce: boolean;
  amount: number;
}

export interface Production {
  corn: ProductionEntry;
  indigo: ProductionEntry;
  sugar: ProductionEntry;
  tobacco: ProductionEntry;
  coffee: ProductionEntry;
  d_total: number;
}

export interface Island {
  total_spaces: number;
  d_used_spaces: number;
  d_empty_spaces: number;
  d_active_quarries: number;
  plantations: Plantation[];
}

export interface City {
  total_spaces: number;
  d_used_spaces: number;
  d_empty_spaces: number;
  colonists_unplaced: number;
  d_quarry_discount: number;
  d_total_empty_colonist_slots: number;
  buildings: PlayerBuilding[];
}

export interface Warehouse {
  has_small_warehouse: boolean;
  has_large_warehouse: boolean;
  d_goods_storable: number;
  protected_goods: GoodType[];
}

export interface Player {
  display_name: string;
  is_governor: boolean;
  doubloons: number;
  vp_chips: number;
  goods: GoodsStock;
  island: Island;
  city: City;
  production: Production;
  warehouse: Warehouse;
  captain_first_load_done: boolean;
  wharf_used_this_phase: boolean;
  hacienda_used_this_phase: boolean;
}

export interface Decision {
  type: string;
  player: string;
  note: string;
}

export interface LobbyPlayer {
  name: string;
  player_id: string | null;
  is_host?: boolean;
  is_spectator?: boolean;
  is_bot?: boolean;
  connected?: boolean;
}

export interface ServerInfo {
  mode: 'idle' | 'single' | 'multiplayer';
  game_exists: boolean;
  lobby_status: 'waiting' | 'playing' | null;
  players: LobbyPlayer[] | null;
  host: string | null;
}

export interface HistoryEntry {
  ts: number;
  action: string;
  params: Record<string, string>;
}

export interface PlayerScore {
  vp_chips: number;
  building_vp: number;
  guild_hall_bonus: number;
  residence_bonus: number;
  fortress_bonus: number;
  customs_house_bonus: number;
  city_hall_bonus: number;
  total: number;
}

export interface FinalScoreSummary {
  scores: Record<string, PlayerScore>;
  winner: string;
  player_order: string[];
}

export interface GameState {
  meta: Meta;
  common_board: CommonBoard;
  players: Record<string, Player>;
  decision: Decision;
  history: HistoryEntry[];
  bot_players?: Record<string, string>;
  result_summary?: FinalScoreSummary | null;
}
